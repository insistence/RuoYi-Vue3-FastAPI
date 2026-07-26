import asyncio
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import false, true

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from exceptions.exception import ServiceException
from module_admin.dao.file_access_dao import FileAclDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.vo.file_vo import BatchSaveFileAclModel, SaveFileAclModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_access_service import FileAclService, FileAuditService

FILE_ID = '11111111-1111-4111-8111-111111111111'
FILE_ID_2 = '22222222-2222-4222-8222-222222222222'
PARENT_DEPT_ID = 100
CHILD_DEPT_ID = 110
BATCH_FILE_COUNT = 2


def make_query_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def make_current_user(
    user_id: int,
    role_ids: list[int] | None = None,
    dept_id: int | None = None,
    ancestors: str = '',
    admin: bool = False,
) -> SimpleNamespace:
    roles = [SimpleNamespace(role_id=role_id) for role_id in (role_ids or [])]
    dept = SimpleNamespace(dept_id=dept_id, ancestors=ancestors) if dept_id else None
    user = SimpleNamespace(
        user_id=user_id,
        user_name=f'user{user_id}',
        admin=admin,
        role=roles,
        role_ids=','.join(str(role_id) for role_id in role_ids or []),
        dept_id=dept_id,
        dept=dept,
    )
    return SimpleNamespace(user=user)


def make_file_info(
    owner_user_id: int = 10,
    upload_user_id: int = 11,
    uploader_access_enabled: str = '1',
) -> SimpleNamespace:
    return SimpleNamespace(
        owner_user_id=owner_user_id,
        upload_user_id=upload_user_id,
        uploader_access_enabled=uploader_access_enabled,
    )


def make_acl(
    subject_type: str,
    subject_id: int,
    effect: str = 'allow',
    include_children: str = '0',
) -> SimpleNamespace:
    return SimpleNamespace(
        subject_type=subject_type,
        subject_id=subject_id,
        effect=effect,
        include_children=include_children,
    )


@pytest.mark.parametrize(
    ('current_user', 'file_acl'),
    [
        (make_current_user(20), make_acl('user', 20)),
        (make_current_user(20, role_ids=[5]), make_acl('role', 5)),
        (make_current_user(20, dept_id=120), make_acl('dept', 120)),
        (make_current_user(20, dept_id=120, ancestors='0,100,110'), make_acl('dept', 100, include_children='1')),
    ],
)
def test_private_file_acl_allows_matching_user_role_or_department(
    current_user: SimpleNamespace,
    file_acl: SimpleNamespace,
) -> None:
    with patch.object(FileAclDao, 'get_effective_file_acl_list', new=AsyncMock(return_value=[file_acl])):
        result = asyncio.run(
            CommonService._has_private_file_download_permission(
                make_query_db(),
                current_user,
                make_file_info(),
                FILE_ID,
                datetime.now(),
            )
        )

    assert result is True


def test_private_file_acl_does_not_apply_parent_department_without_include_children() -> None:
    current_user = make_current_user(20, dept_id=120, ancestors='0,100,110')
    file_acl = make_acl('dept', 100, include_children='0')

    with patch.object(FileAclDao, 'get_effective_file_acl_list', new=AsyncMock(return_value=[file_acl])):
        result = asyncio.run(
            CommonService._has_private_file_download_permission(
                make_query_db(),
                current_user,
                make_file_info(),
                FILE_ID,
                datetime.now(),
            )
        )

    assert result is False


def test_file_acl_department_options_are_returned_as_tree() -> None:
    dept_list = [
        SimpleNamespace(dept_id=PARENT_DEPT_ID, dept_name='研发中心', parent_id=0),
        SimpleNamespace(dept_id=CHILD_DEPT_ID, dept_name='平台研发部', parent_id=PARENT_DEPT_ID),
    ]

    with patch.object(FileAclDao, 'get_acl_dept_list', new=AsyncMock(return_value=dept_list)):
        result = asyncio.run(FileAclService.get_file_acl_dept_tree_services(make_query_db(), true()))

    assert result[0].id == PARENT_DEPT_ID
    assert result[0].children[0].id == CHILD_DEPT_ID


def test_file_acl_list_returns_current_version() -> None:
    acl_version = 7
    with (
        patch.object(
            FileInfoDao,
            'get_file_info_detail_by_id',
            new=AsyncMock(
                return_value=SimpleNamespace(
                    acl_version=acl_version,
                    access_type='private',
                    owner_user_id=10,
                    upload_user_id=11,
                    uploader_access_enabled='1',
                )
            ),
        ),
        patch.object(FileAclDao, 'get_file_acl_list', new=AsyncMock(return_value=[])),
        patch.object(
            FileAclDao,
            'get_acl_subject_name_map',
            new=AsyncMock(return_value={('user', 10): '文件所有者', ('user', 11): '文件上传人'}),
        ),
    ):
        result = asyncio.run(
            FileAclService.get_file_acl_list_services(
                make_query_db(),
                FILE_ID,
                true(),
                true(),
                true(),
            )
        )

    assert result.acl_version == acl_version
    assert result.entries == []
    assert [item.source for item in result.builtin_permissions] == ['admin', 'owner', 'uploader']
    assert result.builtin_permissions[1].subject_name == '文件所有者'
    assert result.builtin_permissions[1].deny_overridable is False
    assert result.builtin_permissions[2].subject_name == '文件上传人'
    assert result.builtin_permissions[2].enabled is True
    assert result.builtin_permissions[2].deny_overridable is True


def test_file_acl_list_marks_uploader_permission_non_overridable_when_uploader_is_owner() -> None:
    file_info = SimpleNamespace(
        acl_version=0,
        access_type='private',
        owner_user_id=10,
        upload_user_id=10,
        uploader_access_enabled='1',
    )
    with (
        patch.object(
            FileInfoDao,
            'get_file_info_detail_by_id',
            new=AsyncMock(return_value=file_info),
        ),
        patch.object(FileAclDao, 'get_file_acl_list', new=AsyncMock(return_value=[])),
        patch.object(
            FileAclDao,
            'get_acl_subject_name_map',
            new=AsyncMock(return_value={('user', 10): '上传人与所有者'}),
        ),
    ):
        result = asyncio.run(
            FileAclService.get_file_acl_list_services(
                make_query_db(),
                FILE_ID,
                true(),
                true(),
                true(),
            )
        )

    uploader_permission = result.builtin_permissions[2]
    assert uploader_permission.source == 'uploader'
    assert uploader_permission.enabled is True
    assert uploader_permission.deny_overridable is False


def test_file_acl_list_exposes_disabled_uploader_permission() -> None:
    file_info = SimpleNamespace(
        access_type='private',
        owner_user_id=10,
        upload_user_id=11,
        uploader_access_enabled='0',
    )

    builtin_permissions = FileAclService._build_builtin_permissions(
        file_info,
        {('user', 10): '文件所有者', ('user', 11): '文件上传人'},
    )

    uploader_permission = builtin_permissions[2]
    assert uploader_permission.source == 'uploader'
    assert uploader_permission.enabled is False
    assert uploader_permission.deny_overridable is False
    assert uploader_permission.description == '上传人访问权限已在文件转移时移除。'


def test_file_acl_role_options_exclude_roles_with_members_outside_user_data_scope() -> None:
    query_db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [(5, 20), (5, 30), (6, 20)]),
                SimpleNamespace(all=lambda: [(5, 20), (6, 20)]),
            ]
        )
    )

    result = asyncio.run(
        FileAclDao._filter_role_rows_by_data_scope(
            query_db,
            [(5, '跨部门角色'), (6, '本部门角色')],
            true(),
        )
    )

    assert result == [(6, '本部门角色')]


def test_private_file_acl_explicit_deny_overrides_uploader_and_allow_rule() -> None:
    current_user = make_current_user(20, role_ids=[5])
    file_acl_list = [make_acl('role', 5, effect='allow'), make_acl('user', 20, effect='deny')]

    with patch.object(FileAclDao, 'get_effective_file_acl_list', new=AsyncMock(return_value=file_acl_list)):
        result = asyncio.run(
            CommonService._has_private_file_download_permission(
                make_query_db(),
                current_user,
                make_file_info(upload_user_id=20),
                FILE_ID,
                datetime.now(),
            )
        )

    assert result is False


def test_private_file_acl_does_not_allow_uploader_when_compatibility_access_is_disabled() -> None:
    current_user = make_current_user(20)

    with patch.object(FileAclDao, 'get_effective_file_acl_list', new=AsyncMock(return_value=[])):
        result = asyncio.run(
            CommonService._has_private_file_download_permission(
                make_query_db(),
                current_user,
                make_file_info(upload_user_id=20, uploader_access_enabled='0'),
                FILE_ID,
                datetime.now(),
            )
        )

    assert result is False


@pytest.mark.parametrize('current_user', [make_current_user(20, admin=True), make_current_user(20)])
def test_private_file_acl_admin_or_owner_is_not_blocked_by_deny(current_user: SimpleNamespace) -> None:
    file_info = make_file_info(owner_user_id=20 if not current_user.user.admin else 10)
    get_acl_list = AsyncMock(return_value=[make_acl('user', 20, effect='deny')])

    with patch.object(FileAclDao, 'get_effective_file_acl_list', new=get_acl_list):
        result = asyncio.run(
            CommonService._has_private_file_download_permission(
                make_query_db(),
                current_user,
                file_info,
                FILE_ID,
                datetime.now(),
            )
        )

    assert result is True
    get_acl_list.assert_not_awaited()


def test_save_file_acl_normalizes_department_scope_and_commits() -> None:
    query_db = make_query_db()
    current_user = make_current_user(1, admin=True)
    acl_version = 3
    file_info = SimpleNamespace(access_type='private', acl_version=acl_version, update_by=None, update_time=None)
    save_model = SaveFileAclModel(
        aclVersion=acl_version,
        entries=[
            {
                'subjectType': 'dept',
                'subjectId': 100,
                'effect': 'allow',
                'includeChildren': True,
                'expireTime': datetime.now() + timedelta(days=1),
            },
            {
                'subjectType': 'user',
                'subjectId': 20,
                'effect': 'deny',
                'includeChildren': True,
            },
        ],
    )

    with (
        patch.object(FileInfoDao, 'get_file_info_by_id_for_update', new=AsyncMock(return_value=file_info)),
        patch.object(
            FileAclDao,
            'get_acl_subject_name_map',
            new=AsyncMock(return_value={('dept', 100): '研发部门', ('user', 20): '测试用户'}),
        ),
        patch.object(FileAclDao, 'replace_file_acl_list', new_callable=AsyncMock) as replace_file_acl_list,
        patch.object(FileAuditService, 'enqueue_file_audit', new_callable=AsyncMock) as enqueue_file_audit,
    ):
        result = asyncio.run(
            FileAclService.save_file_acl_services(
                query_db,
                current_user,
                FILE_ID,
                save_model,
                true(),
                true(),
                true(),
            )
        )

    saved_acl_list = replace_file_acl_list.await_args.args[2]
    assert result.is_success is True
    assert saved_acl_list[0].include_children == '1'
    assert saved_acl_list[1].include_children == '0'
    assert file_info.acl_version == acl_version + 1
    assert file_info.update_by == 'user1'
    query_db.commit.assert_awaited_once()
    enqueue_file_audit.assert_awaited_once()
    assert enqueue_file_audit.await_args.args[3:5] == ('acl_update', 'completed')
    audit_detail = enqueue_file_audit.await_args.kwargs['operation_detail']
    assert audit_detail['previousAclVersion'] == acl_version
    assert audit_detail['newAclVersion'] == acl_version + 1
    assert audit_detail['allowCount'] == 1
    assert audit_detail['denyCount'] == 1


def test_batch_save_file_acl_replaces_all_selected_private_files() -> None:
    query_db = make_query_db()
    current_user = make_current_user(1, admin=True)
    file_infos = [
        SimpleNamespace(file_id=FILE_ID, access_type='private', acl_version=2, update_by=None, update_time=None),
        SimpleNamespace(file_id=FILE_ID_2, access_type='private', acl_version=4, update_by=None, update_time=None),
    ]
    save_model = BatchSaveFileAclModel(
        fileIds=f'{FILE_ID},{FILE_ID_2}',
        entries=[{'subjectType': 'user', 'subjectId': 20, 'effect': 'allow'}],
    )

    with (
        patch.object(FileInfoDao, 'get_file_infos_by_ids_for_update', new=AsyncMock(return_value=file_infos)),
        patch.object(
            FileAclDao,
            'get_acl_subject_name_map',
            new=AsyncMock(return_value={('user', 20): '测试用户'}),
        ),
        patch.object(FileAclDao, 'replace_file_acl_lists', new_callable=AsyncMock) as replace_file_acl_lists,
        patch.object(FileAuditService, 'enqueue_file_audit', new_callable=AsyncMock) as enqueue_file_audit,
    ):
        result = asyncio.run(
            FileAclService.batch_save_file_acl_services(
                query_db,
                current_user,
                save_model,
                true(),
                true(),
                true(),
            )
        )

    saved_acl_list = replace_file_acl_lists.await_args.args[2]
    assert result.is_success is True
    assert {item.file_id for item in saved_acl_list} == {FILE_ID, FILE_ID_2}
    assert [file_info.acl_version for file_info in file_infos] == [3, 5]
    assert enqueue_file_audit.await_count == BATCH_FILE_COUNT
    assert all(item.kwargs['operation_detail']['batch'] is True for item in enqueue_file_audit.await_args_list)
    query_db.commit.assert_awaited_once()


def test_batch_save_file_acl_rejects_public_files() -> None:
    query_db = make_query_db()
    save_model = BatchSaveFileAclModel(fileIds=FILE_ID, entries=[])
    file_infos = [SimpleNamespace(file_id=FILE_ID, access_type='public', acl_version=0)]

    with (
        patch.object(FileInfoDao, 'get_file_infos_by_ids_for_update', new=AsyncMock(return_value=file_infos)),
        patch.object(FileAclDao, 'replace_file_acl_lists', new_callable=AsyncMock) as replace_file_acl_lists,
        pytest.raises(ServiceException) as public_error,
    ):
        asyncio.run(
            FileAclService.batch_save_file_acl_services(
                query_db,
                make_current_user(1, admin=True),
                save_model,
                true(),
                true(),
                true(),
            )
        )

    assert public_error.value.message == '批量授权仅支持受保护文件'
    replace_file_acl_lists.assert_not_awaited()
    query_db.rollback.assert_awaited_once()


def test_save_file_acl_rejects_duplicate_or_expired_entries() -> None:
    query_db = make_query_db()
    current_user = make_current_user(1, admin=True)
    file_info = SimpleNamespace(access_type='private', acl_version=0)
    duplicate_model = SaveFileAclModel(
        aclVersion=0,
        entries=[
            {'subjectType': 'user', 'subjectId': 20, 'effect': 'allow'},
            {'subjectType': 'user', 'subjectId': 20, 'effect': 'deny'},
        ],
    )
    expired_model = SaveFileAclModel(
        aclVersion=0,
        entries=[
            {
                'subjectType': 'user',
                'subjectId': 20,
                'effect': 'allow',
                'expireTime': datetime.now() - timedelta(seconds=1),
            }
        ],
    )

    with patch.object(FileInfoDao, 'get_file_info_by_id_for_update', new=AsyncMock(return_value=file_info)):
        with pytest.raises(ServiceException) as duplicate_error:
            asyncio.run(
                FileAclService.save_file_acl_services(
                    query_db,
                    current_user,
                    FILE_ID,
                    duplicate_model,
                    true(),
                    true(),
                    true(),
                )
            )
        with pytest.raises(ServiceException) as expired_error:
            asyncio.run(
                FileAclService.save_file_acl_services(
                    query_db,
                    current_user,
                    FILE_ID,
                    expired_model,
                    true(),
                    true(),
                    true(),
                )
            )

    assert duplicate_error.value.message == '同一授权主体不能重复配置'
    assert expired_error.value.message == '授权过期时间必须晚于当前时间'


def test_save_file_acl_rejects_subject_outside_data_scope() -> None:
    query_db = make_query_db()
    current_user = make_current_user(1, admin=True)
    file_info = SimpleNamespace(access_type='private', acl_version=0)
    save_model = SaveFileAclModel(
        aclVersion=0,
        entries=[{'subjectType': 'user', 'subjectId': 20, 'effect': 'allow'}],
    )

    with (
        patch.object(FileInfoDao, 'get_file_info_by_id_for_update', new=AsyncMock(return_value=file_info)),
        patch.object(FileAclDao, 'get_acl_subject_name_map', new=AsyncMock(return_value={})),
        pytest.raises(ServiceException) as scope_error,
    ):
        asyncio.run(
            FileAclService.save_file_acl_services(
                query_db,
                current_user,
                FILE_ID,
                save_model,
                true(),
                true(),
                true(),
            )
        )

    assert scope_error.value.message == '部分授权主体不存在、已停用或超出数据权限'


def test_save_file_acl_rejects_file_outside_data_scope() -> None:
    query_db = make_query_db()
    current_user = make_current_user(20)
    save_model = SaveFileAclModel(aclVersion=0, entries=[])
    file_data_scope_sql = false()

    with (
        patch.object(
            FileInfoDao,
            'get_file_info_by_id_for_update',
            new=AsyncMock(return_value=None),
        ) as get_file_info,
        patch.object(FileAclDao, 'replace_file_acl_list', new_callable=AsyncMock) as replace_file_acl_list,
        pytest.raises(ServiceException) as scope_error,
    ):
        asyncio.run(
            FileAclService.save_file_acl_services(
                query_db,
                current_user,
                FILE_ID,
                save_model,
                file_data_scope_sql,
                true(),
                true(),
            )
        )

    assert get_file_info.await_args.args[2] is file_data_scope_sql
    assert scope_error.value.message == '文件信息不存在、已删除或超出数据权限'
    replace_file_acl_list.assert_not_awaited()


def test_save_file_acl_rejects_stale_acl_version() -> None:
    query_db = make_query_db()
    file_info = SimpleNamespace(access_type='private', acl_version=2)
    save_model = SaveFileAclModel(aclVersion=1, entries=[])

    with (
        patch.object(FileInfoDao, 'get_file_info_by_id_for_update', new=AsyncMock(return_value=file_info)),
        patch.object(FileAclDao, 'replace_file_acl_list', new_callable=AsyncMock) as replace_file_acl_list,
        pytest.raises(ServiceException) as version_error,
    ):
        asyncio.run(
            FileAclService.save_file_acl_services(
                query_db,
                make_current_user(1, admin=True),
                FILE_ID,
                save_model,
                true(),
                true(),
                true(),
            )
        )

    assert version_error.value.message == '文件权限已被其他用户修改，请刷新后重试'
    replace_file_acl_list.assert_not_awaited()
    query_db.rollback.assert_awaited_once()
