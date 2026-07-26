import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import true

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.env import UploadConfig
from exceptions.exception import ServiceException
from module_admin.dao.file_business_dao import FileReferenceDao, FileRetentionNoticeDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.vo.file_vo import (
    DisposeExpiredFileModel,
    ExtendFileRetentionModel,
    FileRetentionNoticePageQueryModel,
)
from module_admin.service.file_access_service import FileAuditService
from module_admin.service.file_business_service import (
    FileReferenceService,
    FileRetentionNoticeService,
    FileRetentionPolicyService,
)
from module_admin.service.file_service import FileLifecycleService, FileRetentionDispositionService
from utils.file_util import FileUtil

FILE_ID = '11111111-1111-4111-8111-111111111111'
PURGE_COMMIT_COUNT = 2


def make_query_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def make_current_user() -> SimpleNamespace:
    return SimpleNamespace(user=SimpleNamespace(user_id=1, user_name='admin', admin=True))


def make_file_info(
    access_type: str = 'private',
    expire_time: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        file_id=FILE_ID,
        original_name='private.txt',
        storage_type='local',
        access_type=access_type,
        storage_key='upload/private.txt',
        stored_name='private.txt',
        expire_time=expire_time,
        business_type=None,
        business_id=None,
        update_by='',
        update_time=None,
    )


def test_purge_file_removes_recycle_content_and_metadata(tmp_path: Path) -> None:
    public_root = tmp_path / 'public'
    trash_root = tmp_path / 'trash'
    trash_file = trash_root / FILE_ID / 'private.txt'
    trash_file.parent.mkdir(parents=True)
    trash_file.write_bytes(b'content')
    file_info = make_file_info(access_type='public')
    query_db = make_query_db()

    with (
        patch.object(UploadConfig, 'UPLOAD_PATH', str(public_root)),
        patch.object(UploadConfig, 'FILE_TRASH_PATH', str(trash_root)),
        patch.object(
            FileInfoDao,
            'get_purgeable_file_infos_by_ids_for_update',
            new=AsyncMock(return_value=[file_info]),
        ),
        patch.object(
            FileReferenceService,
            'get_file_reference_count_map_services',
            new=AsyncMock(return_value={}),
        ),
        patch.object(FileInfoDao, 'mark_file_infos_purging', new_callable=AsyncMock) as mark_purging,
        patch.object(FileInfoDao, 'purge_file_infos', new_callable=AsyncMock) as purge_file_infos,
        patch.object(FileAuditService, 'enqueue_file_audit', new_callable=AsyncMock) as enqueue_file_audit,
    ):
        result = asyncio.run(
            FileLifecycleService.purge_file_services(
                query_db,
                make_current_user(),
                FILE_ID,
                true(),
            )
        )

    assert result.is_success is True
    assert not trash_file.exists()
    mark_purging.assert_awaited_once()
    purge_file_infos.assert_awaited_once_with(query_db, [FILE_ID])
    assert query_db.commit.await_count == PURGE_COMMIT_COUNT
    assert enqueue_file_audit.await_args.args[2:5] == (FILE_ID, 'purge', 'completed')


def test_purge_file_rejects_business_reference(tmp_path: Path) -> None:
    file_info = make_file_info()
    query_db = make_query_db()

    with (
        patch.object(
            FileInfoDao,
            'get_purgeable_file_infos_by_ids_for_update',
            new=AsyncMock(return_value=[file_info]),
        ),
        patch.object(
            FileReferenceService,
            'get_file_reference_count_map_services',
            new=AsyncMock(return_value={FILE_ID: 1}),
        ),
        patch.object(FileInfoDao, 'mark_file_infos_purging', new_callable=AsyncMock) as mark_purging,
        pytest.raises(ServiceException) as reference_error,
    ):
        asyncio.run(
            FileLifecycleService.purge_file_services(
                query_db,
                make_current_user(),
                FILE_ID,
                true(),
            )
        )

    assert reference_error.value.message == '部分文件仍被业务引用，不能永久清理'
    mark_purging.assert_not_awaited()
    query_db.rollback.assert_awaited_once()


def test_retention_scan_creates_expiring_and_expired_notices() -> None:
    current_time = datetime.now()
    expired_file = make_file_info(expire_time=current_time - timedelta(days=1))
    expiring_file = SimpleNamespace(
        **{
            **expired_file.__dict__,
            'file_id': '22222222-2222-4222-8222-222222222222',
            'expire_time': current_time + timedelta(days=1),
        }
    )
    query_db = make_query_db()

    with (
        patch.object(
            FileRetentionNoticeDao,
            'get_missing_notice_candidates',
            new=AsyncMock(side_effect=[[expired_file], [expiring_file]]),
        ),
        patch.object(
            FileRetentionNoticeDao,
            'invalidate_expiring_notices',
            new_callable=AsyncMock,
        ) as invalidate_notices,
        patch.object(
            FileRetentionNoticeDao,
            'add_file_retention_notices',
            new_callable=AsyncMock,
        ) as add_notices,
    ):
        result = asyncio.run(
            FileRetentionNoticeService.scan_file_retention_notices_services(
                query_db,
                remind_days=7,
                batch_size=100,
                file_data_scope_sql=true(),
            )
        )

    assert result.expiring_count == 1
    assert result.expired_count == 1
    invalidate_notices.assert_awaited_once_with(query_db, [FILE_ID])
    notice_list = add_notices.await_args.args[1]
    assert [(notice.file_id, notice.notice_type) for notice in notice_list] == [
        (FILE_ID, 'expired'),
        (expiring_file.file_id, 'expiring'),
    ]
    query_db.commit.assert_awaited_once()


def test_mark_retention_notice_read_checks_data_scope() -> None:
    query_db = make_query_db()
    query_object = FileRetentionNoticePageQueryModel()

    with (
        patch.object(
            FileRetentionNoticeDao,
            'get_file_retention_notice_list',
            new=AsyncMock(return_value=[]),
        ) as get_notice_list,
        patch.object(
            FileRetentionNoticeDao,
            'get_notice_ids_in_data_scope_for_update',
            new=AsyncMock(return_value=[1, 2]),
        ),
        patch.object(
            FileRetentionNoticeDao,
            'mark_file_retention_notices_read',
            new_callable=AsyncMock,
        ) as mark_notices_read,
    ):
        result = asyncio.run(
            FileRetentionNoticeService.get_file_retention_notice_list_services(
                query_db,
                query_object,
                true(),
                is_page=True,
            )
        )
        read_result = asyncio.run(
            FileRetentionNoticeService.mark_file_retention_notices_read_services(
                query_db,
                '1,2',
                'admin',
                true(),
            )
        )

    assert result == []
    assert get_notice_list.await_args.args[3] is True
    assert read_result.is_success is True
    assert mark_notices_read.await_args.args[1] == [1, 2]
    query_db.commit.assert_awaited_once()


def test_retention_policy_rejects_public_business_file() -> None:
    query_db = make_query_db()
    public_file = make_file_info(access_type='public')

    with (
        patch.object(
            FileInfoDao,
            'get_file_infos_by_ids_for_update',
            new=AsyncMock(return_value=[public_file]),
        ),
        patch.object(
            FileRetentionPolicyService,
            'get_enabled_file_retention_policy_services',
            new=AsyncMock(return_value=SimpleNamespace(retention_days=30)),
        ),
        patch.object(
            FileReferenceDao,
            'replace_business_file_references',
            new_callable=AsyncMock,
        ) as replace_references,
        pytest.raises(ServiceException) as access_type_error,
    ):
        asyncio.run(
            FileReferenceService.replace_business_file_references_services(
                query_db,
                'notice',
                '1',
                [FILE_ID],
                'admin',
                true(),
            )
        )

    assert access_type_error.value.message == '配置保留策略的业务只能引用受保护文件'
    replace_references.assert_not_awaited()


def test_extend_file_retention_updates_terminal_references() -> None:
    current_time = datetime.now()
    previous_expire_time = current_time + timedelta(days=1)
    new_expire_time = current_time + timedelta(days=31)
    file_info = make_file_info(expire_time=previous_expire_time)
    reference = SimpleNamespace(
        reference_id=1,
        retention_expire_time=previous_expire_time,
    )
    query_db = make_query_db()

    with (
        patch.object(
            FileRetentionNoticeDao,
            'get_file_retention_notice_context_for_update',
            new=AsyncMock(return_value=(SimpleNamespace(notice_id=1), file_info)),
        ),
        patch.object(
            FileReferenceDao,
            'get_file_reference_list_for_update',
            new=AsyncMock(return_value=[reference]),
        ),
        patch.object(
            FileRetentionNoticeDao,
            'invalidate_file_retention_notices',
            new_callable=AsyncMock,
        ) as invalidate_notices,
        patch.object(FileAuditService, 'enqueue_file_audit', new_callable=AsyncMock) as enqueue_file_audit,
    ):
        result = asyncio.run(
            FileRetentionDispositionService.extend_file_retention_services(
                query_db,
                make_current_user(),
                1,
                ExtendFileRetentionModel(expireTime=new_expire_time, reason='业务继续留存'),
                true(),
                request=SimpleNamespace(),
            )
        )

    assert result.is_success is True
    assert file_info.expire_time == new_expire_time
    assert reference.retention_expire_time == new_expire_time
    invalidate_notices.assert_awaited_once_with(query_db, FILE_ID)
    query_db.commit.assert_awaited_once()
    assert enqueue_file_audit.await_args.args[3:5] == ('retention_extend', 'completed')


def test_dispose_expired_file_releases_expired_references() -> None:
    current_time = datetime.now()
    expire_time = current_time - timedelta(days=1)
    file_info = make_file_info(expire_time=expire_time)
    reference = SimpleNamespace(
        reference_id=1,
        business_type='notice',
        business_id='1',
        business_name='测试公告',
        retention_expire_time=expire_time,
    )
    query_db = make_query_db()

    with (
        patch.object(
            FileRetentionNoticeDao,
            'get_file_retention_notice_context_for_update',
            new=AsyncMock(return_value=(SimpleNamespace(notice_id=1), file_info)),
        ),
        patch.object(
            FileReferenceDao,
            'get_file_reference_list_for_update',
            new=AsyncMock(return_value=[reference]),
        ),
        patch.object(FileUtil, 'stage_file_deletions', return_value=[]),
        patch.object(FileReferenceDao, 'delete_file_references', new_callable=AsyncMock) as delete_references,
        patch.object(FileInfoDao, 'soft_delete_file_infos', new_callable=AsyncMock) as soft_delete_file_infos,
        patch.object(FileAuditService, 'enqueue_file_audit', new_callable=AsyncMock) as enqueue_file_audit,
    ):
        result = asyncio.run(
            FileRetentionDispositionService.dispose_expired_file_services(
                query_db,
                make_current_user(),
                1,
                DisposeExpiredFileModel(reason='保留期已结束'),
                true(),
                request=SimpleNamespace(),
            )
        )

    assert result.is_success is True
    delete_references.assert_awaited_once_with(query_db, FILE_ID)
    soft_delete_file_infos.assert_awaited_once()
    query_db.commit.assert_awaited_once()
    assert enqueue_file_audit.await_args.args[3:5] == ('retention_dispose', 'completed')
    assert enqueue_file_audit.await_args.kwargs['operation_detail']['releasedReferenceCount'] == 1


def test_dispose_expired_file_rejects_active_reference() -> None:
    expire_time = datetime.now() - timedelta(days=1)
    file_info = make_file_info(expire_time=expire_time)
    reference = SimpleNamespace(
        reference_id=1,
        retention_expire_time=None,
    )
    query_db = make_query_db()

    with (
        patch.object(
            FileRetentionNoticeDao,
            'get_file_retention_notice_context_for_update',
            new=AsyncMock(return_value=(SimpleNamespace(notice_id=1), file_info)),
        ),
        patch.object(
            FileReferenceDao,
            'get_file_reference_list_for_update',
            new=AsyncMock(return_value=[reference]),
        ),
        patch.object(FileUtil, 'stage_file_deletions') as stage_file_deletions,
        patch.object(FileReferenceDao, 'delete_file_references', new_callable=AsyncMock) as delete_references,
        pytest.raises(ServiceException) as active_reference_error,
    ):
        asyncio.run(
            FileRetentionDispositionService.dispose_expired_file_services(
                query_db,
                make_current_user(),
                1,
                DisposeExpiredFileModel(reason='保留期已结束'),
                true(),
            )
        )

    assert active_reference_error.value.message == '文件存在永久或尚未到期的业务引用，不能执行到期处置'
    stage_file_deletions.assert_not_called()
    delete_references.assert_not_awaited()
    query_db.rollback.assert_awaited_once()
