import asyncio
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import true

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from exceptions.exception import ServiceException
from module_admin.dao.file_business_dao import FileReferenceDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileReference
from module_admin.entity.vo.file_vo import FileRetentionPolicyModel
from module_admin.service.file_business_service import FileReferenceService, FileRetentionPolicyService

FILE_ID = '11111111-1111-4111-8111-111111111111'


def make_query_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def test_get_file_reference_list_includes_legacy_reference() -> None:
    file_info = {
        'file_id': FILE_ID,
        'business_type': 'notice',
        'business_id': '10',
    }
    with (
        patch.object(
            FileInfoDao,
            'get_file_management_detail_by_id',
            new=AsyncMock(return_value=file_info),
        ),
        patch.object(FileReferenceDao, 'get_file_reference_list', new=AsyncMock(return_value=[])),
    ):
        result = asyncio.run(
            FileReferenceService.get_file_reference_list_services(
                make_query_db(),
                FILE_ID,
                true(),
            )
        )

    assert len(result) == 1
    assert result[0].business_type == 'notice'
    assert result[0].business_id == '10'
    assert result[0].legacy is True


def test_replace_business_file_references_locks_files_without_committing() -> None:
    query_db = make_query_db()
    file_infos = [SimpleNamespace(file_id=FILE_ID)]
    with (
        patch.object(
            FileInfoDao,
            'get_file_infos_by_ids_for_update',
            new=AsyncMock(return_value=file_infos),
        ) as get_file_infos,
        patch.object(
            FileReferenceDao,
            'replace_business_file_references',
            new_callable=AsyncMock,
        ) as replace_references,
        patch.object(
            FileRetentionPolicyService,
            'get_enabled_file_retention_policy_services',
            new=AsyncMock(return_value=None),
        ),
    ):
        asyncio.run(
            FileReferenceService.replace_business_file_references_services(
                query_db,
                'notice',
                '10',
                [FILE_ID, FILE_ID],
                create_by='admin',
                file_data_scope_sql=true(),
                business_name='系统公告',
            )
        )

    assert get_file_infos.await_args.args[1] == [FILE_ID]
    reference_list = replace_references.await_args.args[3]
    assert len(reference_list) == 1
    assert isinstance(reference_list[0], SysFileReference)
    assert reference_list[0].file_id == FILE_ID
    assert reference_list[0].business_type == 'notice'
    assert reference_list[0].business_id == '10'
    assert reference_list[0].business_name == '系统公告'
    query_db.commit.assert_not_awaited()


def test_replace_business_file_references_rejects_invalid_file() -> None:
    query_db = make_query_db()
    with (
        patch.object(FileInfoDao, 'get_file_infos_by_ids_for_update', new=AsyncMock(return_value=[])),
        patch.object(
            FileReferenceDao,
            'replace_business_file_references',
            new_callable=AsyncMock,
        ) as replace_references,
        pytest.raises(ServiceException) as file_error,
    ):
        asyncio.run(
            FileReferenceService.replace_business_file_references_services(
                query_db,
                'notice',
                '10',
                [FILE_ID],
                create_by='admin',
                file_data_scope_sql=true(),
            )
        )

    assert file_error.value.message == '部分引用文件不存在或已失效'
    replace_references.assert_not_awaited()


def test_remove_business_file_references_does_not_lock_files() -> None:
    query_db = make_query_db()
    with (
        patch.object(
            FileReferenceDao,
            'replace_business_file_references',
            new_callable=AsyncMock,
        ) as replace_references,
        patch.object(
            FileRetentionPolicyService,
            'get_enabled_file_retention_policy_services',
            new=AsyncMock(return_value=None),
        ),
    ):
        asyncio.run(
            FileReferenceService.remove_business_file_references_services(
                query_db,
                'notice',
                '10',
            )
        )

    assert replace_references.await_args.args[3] == []
    query_db.commit.assert_not_awaited()


def test_replace_business_file_references_applies_retention_policy() -> None:
    query_db = make_query_db()
    create_time = datetime(2026, 7, 23, 10, 0, 0)
    policy = FileRetentionPolicyModel(businessType='notice', retentionDays=30)
    with (
        patch.object(
            FileInfoDao,
            'get_file_infos_by_ids_for_update',
            new=AsyncMock(return_value=[SimpleNamespace(file_id=FILE_ID)]),
        ),
        patch.object(
            FileRetentionPolicyService,
            'get_enabled_file_retention_policy_services',
            new=AsyncMock(return_value=policy),
        ),
        patch.object(
            FileReferenceDao,
            'replace_business_file_references',
            new_callable=AsyncMock,
        ) as replace_references,
        patch(
            'module_admin.service.file_business_service.datetime',
            new=SimpleNamespace(now=lambda: create_time),
        ),
    ):
        asyncio.run(
            FileReferenceService.replace_business_file_references_services(
                query_db,
                'notice',
                '10',
                [FILE_ID],
                create_by='admin',
                file_data_scope_sql=true(),
            )
        )

    reference = replace_references.await_args.args[3][0]
    assert reference.retention_expire_time == create_time + timedelta(days=30)


def test_refresh_file_expire_times_uses_latest_reference_expiration() -> None:
    first_expire_time = datetime(2026, 8, 1)
    last_expire_time = datetime(2026, 9, 1)
    file_info = SimpleNamespace(
        file_id=FILE_ID,
        business_type=None,
        business_id=None,
        expire_time=None,
    )
    query_db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    (FILE_ID, first_expire_time),
                    (FILE_ID, last_expire_time),
                ]
            )
        )
    )

    asyncio.run(
        FileReferenceDao._refresh_file_expire_times(
            query_db,
            [FILE_ID],
            {FILE_ID: file_info},
        )
    )

    assert file_info.expire_time == last_expire_time
