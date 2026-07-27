import asyncio
import io
import re
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import false

from config.env import UploadConfig
from exceptions.exception import FileRangeNotSatisfiableException, ServiceException
from middlewares.cors_middleware import add_cors_middleware
from module_admin.dao.file_access_dao import FileAclDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.service.common_service import CommonService
from sub_applications.staticfiles import SecureStaticFiles
from utils.file_util import FileUtil
from utils.upload_util import FilePathUtil, UploadUtil

RANGE_TEST_FILE_SIZE = 10
RANGE_TEST_START = 3
RANGE_TEST_END = 6
RANGE_TEST_LENGTH = RANGE_TEST_END - RANGE_TEST_START + 1


async def collect_stream(stream: AsyncGenerator[bytes, None]) -> bytes:
    return b''.join([chunk async for chunk in stream])


async def collect_first_chunk_and_close(stream: AsyncGenerator[bytes, None]) -> bytes:
    chunk = await anext(stream)
    await stream.aclose()
    return chunk


def make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


def make_current_user(user_id: int = 10, admin: bool = False, dept_id: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        user=SimpleNamespace(user_id=user_id, user_name=f'user{user_id}', admin=admin, dept_id=dept_id)
    )


def make_query_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


@pytest.mark.parametrize(
    ('range_header', 'expected'),
    [
        (None, (0, 9, 10, False, 10)),
        ('bytes=2-5', (2, 5, 10, True, 4)),
        ('bytes=7-', (7, 9, 10, True, 3)),
        ('bytes=-3', (7, 9, 10, True, 3)),
        ('bytes=-99', (0, 9, 10, True, 10)),
        ('bytes=3-99', (3, 9, 10, True, 7)),
    ],
)
def test_parse_byte_range_supports_standard_single_ranges(
    range_header: str | None,
    expected: tuple[int, int, int, bool, int],
) -> None:
    byte_range = FileUtil.parse_byte_range(range_header, 10)

    assert (
        byte_range.start,
        byte_range.end,
        byte_range.file_size,
        byte_range.is_partial,
        byte_range.length,
    ) == expected


@pytest.mark.parametrize(
    'range_header',
    [
        'items=0-1',
        'bytes=',
        'bytes=-0',
        'bytes=10-',
        'bytes=8-7',
        'bytes=0-1,3-4',
    ],
)
def test_parse_byte_range_rejects_invalid_or_multiple_ranges(range_header: str) -> None:
    with pytest.raises(FileRangeNotSatisfiableException) as range_error:
        FileUtil.parse_byte_range(range_header, RANGE_TEST_FILE_SIZE)

    assert range_error.value.file_size == RANGE_TEST_FILE_SIZE


def test_parse_byte_range_allows_empty_full_download_but_rejects_empty_partial_download() -> None:
    byte_range = FileUtil.parse_byte_range(None, 0)

    assert byte_range.length == 0
    assert byte_range.is_partial is False
    with pytest.raises(FileRangeNotSatisfiableException):
        FileUtil.parse_byte_range('bytes=0-', 0)


def test_resolve_file_within_root_accepts_nested_relative_file(tmp_path: Path) -> None:
    root = tmp_path / 'download'
    target = root / 'nested' / 'report.txt'
    target.parent.mkdir(parents=True)
    target.write_text('safe', encoding='utf-8')

    resolved = FilePathUtil.resolve_file_within_root(root, 'nested/report.txt')

    assert resolved == target.resolve()


@pytest.mark.parametrize(
    'untrusted_path',
    [
        '/etc/passwd',
        'C:\\Windows\\win.ini',
        '\\\\server\\share\\secret.txt',
        '../secret.txt',
        '..\\secret.txt',
        'nested/../secret.txt',
        'nested\\..\\secret.txt',
    ],
)
def test_resolve_file_within_root_rejects_absolute_and_traversal_paths(tmp_path: Path, untrusted_path: str) -> None:
    root = tmp_path / 'download'
    root.mkdir()

    with pytest.raises(ValueError):
        FilePathUtil.resolve_file_within_root(root, untrusted_path)


def test_resolve_file_within_root_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / 'download'
    root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('secret', encoding='utf-8')
    link = root / 'link.txt'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('当前环境不允许创建符号链接')

    with pytest.raises(ValueError):
        FilePathUtil.resolve_file_within_root(root, 'link.txt')


def test_download_rejects_absolute_path_without_scheduling_delete(tmp_path: Path) -> None:
    download_root = tmp_path / 'download'
    download_root.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('secret', encoding='utf-8')
    background_tasks = BackgroundTasks()

    with (
        patch.object(UploadConfig, 'DOWNLOAD_PATH', str(download_root)),
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.download_services(background_tasks, str(outside.resolve()), True))

    assert background_tasks.tasks == []
    assert outside.exists()


def test_download_keeps_delete_compatibility_inside_download_root(tmp_path: Path) -> None:
    download_root = tmp_path / 'download'
    download_root.mkdir()
    target = download_root / 'report.txt'
    target.write_bytes(b'report-content')
    background_tasks = BackgroundTasks()

    with patch.object(UploadConfig, 'DOWNLOAD_PATH', str(download_root)):
        result = asyncio.run(
            CommonService.download_services(
                background_tasks,
                'report.txt',
                True,
                range_header='bytes=0-5',
            )
        )
        assert asyncio.run(collect_stream(result.data)) == b'report-content'
        assert result.byte_range.is_partial is False
        assert result.accept_ranges is False
        assert target.exists()
        asyncio.run(background_tasks())

    assert not target.exists()


def test_resource_download_is_confined_to_upload_root(tmp_path: Path) -> None:
    upload_root = tmp_path / 'profile'
    target = upload_root / 'upload' / '2026' / '07' / 'report_20260719120000A001.txt'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'resource-content')

    with patch.object(UploadConfig, 'UPLOAD_PATH', str(upload_root)):
        result = asyncio.run(
            CommonService.download_resource_services('/profile/upload/2026/07/report_20260719120000A001.txt')
        )
        assert asyncio.run(collect_stream(result.data)) == b'resource-content'

        range_result = asyncio.run(
            CommonService.download_resource_services(
                '/profile/upload/2026/07/report_20260719120000A001.txt',
                range_header='bytes=3-10',
            )
        )
        assert asyncio.run(collect_stream(range_result.data)) == b'ource-co'
        assert range_result.byte_range.is_partial is True

        with pytest.raises(ServiceException):
            asyncio.run(CommonService.download_resource_services('/profile/../outside.txt'))


def test_resource_download_rejects_file_without_generated_filename(tmp_path: Path) -> None:
    upload_root = tmp_path / 'profile'
    target = upload_root / 'upload' / '2026' / '07' / 'report.txt'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'resource-content')

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(upload_root)),
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.download_resource_services('/profile/upload/2026/07/report.txt'))


def test_upload_uses_server_generated_filename_and_stays_in_upload_root(tmp_path: Path) -> None:
    upload_root = tmp_path / 'profile'
    upload = make_upload('../../attack:bad?.txt', b'safe-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(upload_root)),
        patch.object(UploadConfig, 'MAX_FILE_SIZE', 1024),
        patch.object(FileInfoDao, 'add_file_info_dao', new_callable=AsyncMock) as add_file_info,
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock),
    ):
        result = asyncio.run(CommonService.upload_service(request, query_db, current_user, upload))

    written_files = list(upload_root.rglob('*.*'))
    assert len(written_files) == 1
    assert written_files[0].resolve().is_relative_to(upload_root.resolve())
    assert written_files[0].read_bytes() == b'safe-content'
    assert result.result.original_filename == 'attack:bad?.txt'
    assert re.fullmatch(r'attack_bad_\d{14}A\d{3}\.txt', result.result.new_file_name)
    assert written_files[0].name == result.result.new_file_name
    assert result.result.access_type == 'public'
    assert result.result.file_id
    file_info = add_file_info.await_args.args[1]
    assert file_info.upload_user_id == current_user.user.user_id
    assert file_info.owner_user_id == current_user.user.user_id
    assert file_info.dept_id == current_user.user.dept_id
    assert file_info.file_size == len(b'safe-content')
    assert file_info.file_hash == '63a2f0f94f2efe262dee71613926b2bb5ceda47b0aa2950d9403dcfd5a089ec8'
    query_db.commit.assert_awaited_once()

    with patch.object(UploadConfig, 'UPLOAD_PATH', str(upload_root)):
        download_result = asyncio.run(CommonService.download_resource_services(result.result.file_name))
        assert asyncio.run(collect_stream(download_result.data)) == b'safe-content'


@pytest.mark.parametrize('extension', ['html', 'htm'])
def test_upload_accepts_html_as_download_only_file(tmp_path: Path, extension: str) -> None:
    file_content = b'<script>alert(1)</script>'
    upload = make_upload(f'attack.{extension}', file_content)
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(tmp_path)),
        patch.object(UploadConfig, 'MAX_FILE_SIZE', 1024),
        patch.object(FileInfoDao, 'add_file_info_dao', new_callable=AsyncMock),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock),
    ):
        result = asyncio.run(CommonService.upload_service(request, query_db, current_user, upload))
        download_result = asyncio.run(CommonService.download_resource_services(result.result.file_name))

    written_files = [path for path in tmp_path.rglob('*') if path.is_file()]
    assert len(written_files) == 1
    assert written_files[0].read_bytes() == file_content
    assert re.fullmatch(rf'attack_\d{{14}}A\d{{3}}\.{extension}', result.result.new_file_name)
    assert asyncio.run(collect_stream(download_result.data)) == file_content


def test_upload_enforces_total_size_and_removes_partial_file(tmp_path: Path) -> None:
    upload = make_upload('large.txt', b'12345')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(tmp_path)),
        patch.object(UploadConfig, 'MAX_FILE_SIZE', 4),
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.upload_service(request, query_db, current_user, upload))

    assert [path for path in tmp_path.rglob('*') if path.is_file()] == []


def test_upload_rejects_unknown_access_type_before_writing(tmp_path: Path) -> None:
    upload = make_upload('report.txt', b'report-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(tmp_path)),
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.upload_service(request, make_query_db(), make_current_user(), upload, 'shared'))

    assert list(tmp_path.rglob('*')) == []


def test_upload_removes_file_when_metadata_write_fails(tmp_path: Path) -> None:
    upload = make_upload('report.txt', b'report-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(tmp_path)),
        patch.object(FileInfoDao, 'add_file_info_dao', new=AsyncMock(side_effect=RuntimeError('db error'))),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock),
        pytest.raises(RuntimeError),
    ):
        asyncio.run(CommonService.upload_service(request, query_db, current_user, upload))

    assert [path for path in tmp_path.rglob('*') if path.is_file()] == []
    query_db.rollback.assert_awaited_once()


def test_upload_retries_name_collision_without_deleting_existing_file(tmp_path: Path) -> None:
    fixed_time = datetime(2026, 7, 19, 12, 0, 0)
    existing_file = tmp_path / 'upload' / '2026' / '07' / '19' / 'report_20260719120000A001.txt'
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(b'existing-content')
    upload = make_upload('report.txt', b'new-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(tmp_path)),
        patch('module_admin.service.common_service.datetime', new=SimpleNamespace(now=lambda: fixed_time)),
        patch.object(UploadUtil, 'generate_random_number', side_effect=['001', '002']),
        patch.object(FileInfoDao, 'add_file_info_dao', new_callable=AsyncMock),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock),
    ):
        result = asyncio.run(CommonService.upload_service(request, query_db, current_user, upload))

    assert existing_file.read_bytes() == b'existing-content'
    assert result.result.new_file_name == 'report_20260719120000A002.txt'
    assert (existing_file.parent / result.result.new_file_name).read_bytes() == b'new-content'


def test_private_upload_is_physically_isolated_and_owner_can_download(tmp_path: Path) -> None:
    public_root = tmp_path / 'public'
    private_root = tmp_path / 'private'
    upload = make_upload('contract.pdf', b'private-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(public_root)),
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(private_root)),
        patch.object(FileInfoDao, 'add_file_info_dao', new_callable=AsyncMock) as add_file_info,
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
    ):
        result = asyncio.run(
            CommonService.upload_service(request, query_db, current_user, upload, access_type='private')
        )
        file_info = add_file_info.await_args.args[1]
        with patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)):
            download_result = asyncio.run(
                CommonService.download_managed_file_services(request, query_db, current_user, result.result.file_id)
            )
            assert asyncio.run(collect_stream(download_result.data)) == b'private-content'

    assert list(public_root.rglob('*')) == []
    assert len([path for path in private_root.rglob('*') if path.is_file()]) == 1
    assert result.result.file_name.startswith('/common/files/')
    assert not result.result.file_name.startswith(UploadConfig.UPLOAD_PREFIX)
    assert result.result.access_type == 'private'
    assert download_result.filename == 'contract.pdf'
    audit_results = [call.kwargs['result'] for call in enqueue_audit.await_args_list]
    assert audit_results == ['completed', 'allowed', 'completed']


def test_private_download_rejects_other_user(tmp_path: Path) -> None:
    private_root = tmp_path / 'private'
    target = private_root / 'upload' / '2026' / '07' / 'contract_20260719120000A001.pdf'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'private-content')
    file_info = SimpleNamespace(
        storage_type='local',
        access_type='private',
        upload_user_id=10,
        owner_user_id=10,
        expire_time=None,
        storage_key='upload/2026/07/contract_20260719120000A001.pdf',
        original_name='contract.pdf',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    other_user = make_current_user(user_id=20)

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(private_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(FileAclDao, 'get_effective_file_acl_list', new=AsyncMock(return_value=[])),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.download_managed_file_services(request, query_db, other_user, 'file-id'))

    enqueue_audit.assert_awaited_once()
    assert enqueue_audit.await_args.kwargs['result'] == 'denied'


def test_file_manager_can_download_private_file_without_owner_match(tmp_path: Path) -> None:
    private_root = tmp_path / 'private'
    target = private_root / 'upload' / '2026' / '07' / 'contract_20260719120000A001.pdf'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'private-content')
    file_info = SimpleNamespace(
        storage_type='local',
        access_type='private',
        upload_user_id=10,
        owner_user_id=10,
        expire_time=None,
        storage_key='upload/2026/07/contract_20260719120000A001.pdf',
        original_name='contract.pdf',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    file_manager = make_current_user(user_id=20)

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(private_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock),
    ):
        download_result = asyncio.run(
            CommonService.download_managed_file_services(
                request,
                query_db,
                file_manager,
                'file-id',
                enforce_owner_permission=False,
            )
        )
        assert asyncio.run(collect_stream(download_result.data)) == b'private-content'

    assert download_result.filename == 'contract.pdf'


def test_file_manager_download_rejects_file_outside_data_scope() -> None:
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    file_manager = make_current_user(user_id=20)
    file_data_scope_sql = false()

    with (
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=None)) as get_file_info,
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
        pytest.raises(ServiceException),
    ):
        asyncio.run(
            CommonService.download_managed_file_services(
                request,
                query_db,
                file_manager,
                'file-id',
                enforce_owner_permission=False,
                file_data_scope_sql=file_data_scope_sql,
            )
        )

    assert get_file_info.await_args.args[2] is file_data_scope_sql
    assert enqueue_audit.await_args.kwargs['result'] == 'denied'


@pytest.mark.parametrize(
    ('access_type', 'current_user'),
    [
        ('private', make_current_user(user_id=1, admin=True)),
        ('public', make_current_user(user_id=20)),
    ],
)
def test_managed_download_allows_administrator_or_public_file(
    tmp_path: Path,
    access_type: str,
    current_user: SimpleNamespace,
) -> None:
    storage_root = tmp_path / access_type
    target = storage_root / 'upload' / '2026' / '07' / 'report_20260719120000A001.txt'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'file-content')
    file_info = SimpleNamespace(
        storage_type='local',
        access_type=access_type,
        upload_user_id=10,
        owner_user_id=10,
        expire_time=None,
        storage_key='upload/2026/07/report_20260719120000A001.txt',
        original_name='report.txt',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(storage_root)),
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(storage_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
    ):
        download_result = asyncio.run(
            CommonService.download_managed_file_services(request, query_db, current_user, 'file-id')
        )
        assert asyncio.run(collect_stream(download_result.data)) == b'file-content'

    assert download_result.filename == 'report.txt'
    assert [call.kwargs['result'] for call in enqueue_audit.await_args_list] == ['allowed', 'completed']


@pytest.mark.parametrize('admin', [False, True])
def test_private_download_rejects_expired_file(tmp_path: Path, admin: bool) -> None:
    private_root = tmp_path / 'private'
    file_info = SimpleNamespace(
        storage_type='local',
        access_type='private',
        upload_user_id=10,
        owner_user_id=10,
        expire_time=datetime.now() - timedelta(seconds=1),
        storage_key='upload/2026/07/report_20260719120000A001.txt',
        original_name='report.txt',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user(user_id=10, admin=admin)

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(private_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
        pytest.raises(ServiceException),
    ):
        asyncio.run(CommonService.download_managed_file_services(request, query_db, current_user, 'file-id'))

    enqueue_audit.assert_awaited_once()
    assert enqueue_audit.await_args.kwargs['result'] == 'denied'


def test_managed_download_records_interrupted_stream(tmp_path: Path) -> None:
    target = tmp_path / 'report.txt'
    target.write_bytes(b'partial-content')
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    current_user = make_current_user()

    with patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit:
        byte_range = FileUtil.parse_byte_range(None, target.stat().st_size)
        stream = CommonService._generate_audited_file(request, current_user, 'file-id', target, byte_range)
        assert asyncio.run(collect_first_chunk_and_close(stream)) == b'partial-content'

    enqueue_audit.assert_awaited_once()
    assert enqueue_audit.await_args.kwargs['result'] == 'failed'
    assert enqueue_audit.await_args.kwargs['error_message'] == 'StreamClosed'


def test_managed_download_supports_range_and_records_partial_bytes(tmp_path: Path) -> None:
    storage_root = tmp_path / 'private'
    target = storage_root / 'upload' / '2026' / '07' / 'report_20260719120000A001.txt'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'0123456789')
    file_info = SimpleNamespace(
        storage_type='local',
        access_type='private',
        upload_user_id=10,
        owner_user_id=10,
        expire_time=None,
        storage_key='upload/2026/07/report_20260719120000A001.txt',
        original_name='report.txt',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)
    query_db = make_query_db()
    current_user = make_current_user()

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(storage_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
    ):
        download_result = asyncio.run(
            CommonService.download_managed_file_services(
                request,
                query_db,
                current_user,
                'file-id',
                range_header='bytes=3-6',
            )
        )
        assert asyncio.run(collect_stream(download_result.data)) == b'3456'

    assert download_result.byte_range.start == RANGE_TEST_START
    assert download_result.byte_range.end == RANGE_TEST_END
    assert download_result.byte_range.length == RANGE_TEST_LENGTH
    assert [call.kwargs['result'] for call in enqueue_audit.await_args_list] == ['allowed', 'completed']
    assert enqueue_audit.await_args_list[0].kwargs['operation_detail'] == {
        'rangeStart': RANGE_TEST_START,
        'rangeEnd': RANGE_TEST_END,
        'fileSize': RANGE_TEST_FILE_SIZE,
    }
    assert enqueue_audit.await_args_list[1].kwargs['bytes_sent'] == RANGE_TEST_LENGTH


def test_managed_download_audits_unsatisfied_range_without_disclosing_before_permission(tmp_path: Path) -> None:
    storage_root = tmp_path / 'private'
    target = storage_root / 'upload' / '2026' / '07' / 'report_20260719120000A001.txt'
    target.parent.mkdir(parents=True)
    target.write_bytes(b'0123456789')
    file_info = SimpleNamespace(
        storage_type='local',
        access_type='private',
        upload_user_id=10,
        owner_user_id=10,
        expire_time=None,
        storage_key='upload/2026/07/report_20260719120000A001.txt',
        original_name='report.txt',
    )
    request = SimpleNamespace(base_url='https://example.test/prod-api/', headers={}, client=None)

    with (
        patch.object(UploadConfig, 'PRIVATE_UPLOAD_PATH', str(storage_root)),
        patch.object(FileInfoDao, 'get_file_info_by_id', new=AsyncMock(return_value=file_info)),
        patch.object(CommonService, '_enqueue_file_access_log', new_callable=AsyncMock) as enqueue_audit,
        pytest.raises(FileRangeNotSatisfiableException),
    ):
        asyncio.run(
            CommonService.download_managed_file_services(
                request,
                make_query_db(),
                make_current_user(),
                'file-id',
                range_header='bytes=20-',
            )
        )

    enqueue_audit.assert_awaited_once()
    assert enqueue_audit.await_args.kwargs['result'] == 'failed'
    assert enqueue_audit.await_args.kwargs['error_message'] == 'RangeNotSatisfiable'


def test_download_headers_force_attachment_and_disable_sniffing() -> None:
    byte_range = FileUtil.parse_byte_range('bytes=2-5', 10)
    headers = UploadUtil.build_download_headers('../../report.html', byte_range)

    assert headers['Content-Disposition'].startswith('attachment;')
    assert headers['download-filename'] == 'report.html'
    assert headers['Accept-Ranges'] == 'bytes'
    assert headers['Content-Length'] == '4'
    assert headers['Content-Range'] == 'bytes 2-5/10'
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Content-Security-Policy'].startswith('sandbox;')
    assert headers['X-Frame-Options'] == 'DENY'


def test_static_files_force_only_html_to_download(tmp_path: Path) -> None:
    html_file = tmp_path / 'legacy.html'
    html_file.write_text('<script>alert(1)</script>', encoding='utf-8')
    image_file = tmp_path / 'safe.png'
    image_file.write_bytes(b'not-a-real-image')
    pdf_file = tmp_path / 'report.pdf'
    pdf_file.write_bytes(b'%PDF-1.4')
    static_files = SecureStaticFiles(directory=tmp_path)
    scope = {'type': 'http', 'method': 'GET', 'path': '/profile/legacy.html', 'headers': []}

    html_response = asyncio.run(static_files.get_response('legacy.html', scope))
    image_response = asyncio.run(static_files.get_response('safe.png', scope))
    pdf_response = asyncio.run(static_files.get_response('report.pdf', scope))

    assert html_response.headers['Content-Type'] == 'application/octet-stream'
    assert html_response.headers['Content-Disposition'].startswith('attachment;')
    assert html_response.headers['Content-Security-Policy'] == (
        "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    assert html_response.headers['X-Content-Type-Options'] == 'nosniff'
    assert html_response.headers['X-Frame-Options'] == 'DENY'
    assert 'Content-Disposition' not in image_response.headers
    assert image_response.headers['X-Content-Type-Options'] == 'nosniff'
    assert pdf_response.headers['Content-Type'] == 'application/pdf'
    assert 'Content-Disposition' not in pdf_response.headers
    assert pdf_response.headers['X-Content-Type-Options'] == 'nosniff'


def test_cors_exposes_download_headers() -> None:
    app = FastAPI()
    add_cors_middleware(app)

    cors_middleware = next(item for item in app.user_middleware if item.cls is CORSMiddleware)
    expose_headers = {header.lower() for header in cors_middleware.kwargs['expose_headers']}

    assert 'download-filename' in expose_headers
    assert 'content-disposition' in expose_headers
    assert 'accept-ranges' in expose_headers
    assert 'content-range' in expose_headers
    assert 'content-length' in expose_headers
