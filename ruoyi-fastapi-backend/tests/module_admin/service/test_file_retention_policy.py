import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from exceptions.exception import ServiceException
from module_admin.dao.file_business_dao import FileRetentionPolicyDao
from module_admin.entity.do.file_do import SysFileRetentionPolicy
from module_admin.entity.vo.file_vo import FileRetentionPolicyModel
from module_admin.service.file_business_service import FileRetentionPolicyService

RETENTION_DAYS = 365


def make_query_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def test_get_file_retention_policy_list_maps_orm_field_names() -> None:
    query_db = make_query_db()
    db_policy = SysFileRetentionPolicy(
        business_type='notice',
        retention_days=RETENTION_DAYS,
        status='0',
        remark='公告附件',
    )
    with patch.object(
        FileRetentionPolicyDao,
        'get_file_retention_policy_list',
        new=AsyncMock(return_value=[db_policy]),
    ):
        result = asyncio.run(FileRetentionPolicyService.get_file_retention_policy_list_services(query_db))

    assert len(result) == 1
    assert result[0].business_type == 'notice'
    assert result[0].retention_days == RETENTION_DAYS


def test_get_enabled_file_retention_policy_maps_orm_field_names() -> None:
    query_db = make_query_db()
    db_policy = SysFileRetentionPolicy(
        business_type='notice',
        retention_days=RETENTION_DAYS,
        status='0',
    )
    with patch.object(
        FileRetentionPolicyDao,
        'get_file_retention_policy_by_business_type',
        new=AsyncMock(return_value=db_policy),
    ) as get_policy:
        result = asyncio.run(
            FileRetentionPolicyService.get_enabled_file_retention_policy_services(
                query_db,
                'notice',
            )
        )

    assert result is not None
    assert result.business_type == 'notice'
    assert result.retention_days == RETENTION_DAYS
    get_policy.assert_awaited_once_with(query_db, 'notice', enabled_only=True)


def test_add_file_retention_policy_commits_new_policy() -> None:
    query_db = make_query_db()
    policy = FileRetentionPolicyModel(
        businessType='notice',
        retentionDays=RETENTION_DAYS,
        status='0',
        remark='公告附件',
    )
    with (
        patch.object(
            FileRetentionPolicyDao,
            'get_file_retention_policy_by_business_type',
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            FileRetentionPolicyDao,
            'add_file_retention_policy',
            new_callable=AsyncMock,
        ) as add_policy,
    ):
        result = asyncio.run(
            FileRetentionPolicyService.add_file_retention_policy_services(
                query_db,
                policy,
                'admin',
            )
        )

    assert result.is_success is True
    assert add_policy.await_args.args[1].business_type == 'notice'
    assert add_policy.await_args.args[1].retention_days == RETENTION_DAYS
    assert add_policy.await_args.args[1].create_by == 'admin'
    query_db.commit.assert_awaited_once()


def test_add_file_retention_policy_rejects_duplicate_business_type() -> None:
    query_db = make_query_db()
    policy = FileRetentionPolicyModel(businessType='notice', retentionDays=30)
    with (
        patch.object(
            FileRetentionPolicyDao,
            'get_file_retention_policy_by_business_type',
            new=AsyncMock(return_value=SimpleNamespace(business_type='notice')),
        ),
        patch.object(
            FileRetentionPolicyDao,
            'add_file_retention_policy',
            new_callable=AsyncMock,
        ) as add_policy,
        pytest.raises(ServiceException) as policy_error,
    ):
        asyncio.run(
            FileRetentionPolicyService.add_file_retention_policy_services(
                query_db,
                policy,
                'admin',
            )
        )

    assert policy_error.value.message == '业务类型notice的保留策略已存在'
    add_policy.assert_not_awaited()
    query_db.commit.assert_not_awaited()
