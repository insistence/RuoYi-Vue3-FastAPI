"""契约测试：实体 DO 的时间列必须使用 SQLAlchemy callable defaults。"""

import asyncio

import pytest
from sqlalchemy import DateTime, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.mixin import AuditTimeMixin, CreateTimeMixin
from config.database import Base
from module_admin.entity.do.config_do import SysConfig
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.dict_do import SysDictData, SysDictType
from module_admin.entity.do.file_do import (
    SysFileAccessLog,
    SysFileAcl,
    SysFileInfo,
    SysFileReconcileIssue,
    SysFileReconcileRun,
    SysFileReference,
    SysFileRetentionNotice,
    SysFileRetentionPolicy,
)
from module_admin.entity.do.job_do import SysJob, SysJobLog
from module_admin.entity.do.log_do import SysLogininfor, SysOperLog
from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.notice_do import SysNotice, SysNoticeRead
from module_admin.entity.do.post_do import SysPost
from module_admin.entity.do.role_do import SysRole, SysRoleDept, SysRoleMenu
from module_admin.entity.do.user_do import SysUser, SysUserPost, SysUserRole
from module_generator.entity.do.gen_do import GenTable, GenTableColumn
from plugins.ai.entity.do.ai_chat_do import AiChatConfig
from plugins.ai.entity.do.ai_model_do import AiModels
from plugins.core.management.entity.do.models import (
    SysPlugin,
    SysPluginConfig,
    SysPluginMenu,
    SysPluginMigration,
    SysPluginOperationLog,
)

EXPECTED_ENTITY_MODEL_COUNT = 35
EXPECTED_UPDATE_TIME_MODEL_COUNT = 19
EXPECTED_CREATE_TIME_ONLY_MODEL_COUNT = 6

# Keep both inventories explicit: there are 35 DO classes and 19 update_time
# columns. Adding/removing one should be an intentional model change.
ENTITY_MODELS = (
    SysConfig,
    SysDept,
    SysDictType,
    SysDictData,
    SysFileInfo,
    SysFileReference,
    SysFileRetentionPolicy,
    SysFileRetentionNotice,
    SysFileAcl,
    SysFileAccessLog,
    SysFileReconcileRun,
    SysFileReconcileIssue,
    SysJob,
    SysJobLog,
    SysLogininfor,
    SysOperLog,
    SysMenu,
    SysNotice,
    SysNoticeRead,
    SysPost,
    SysRole,
    SysRoleDept,
    SysRoleMenu,
    SysUser,
    SysUserRole,
    SysUserPost,
    GenTable,
    GenTableColumn,
    AiChatConfig,
    AiModels,
    SysPlugin,
    SysPluginMenu,
    SysPluginMigration,
    SysPluginConfig,
    SysPluginOperationLog,
)

UPDATE_TIME_MODELS = (
    SysConfig,
    SysDept,
    SysDictType,
    SysDictData,
    SysFileInfo,
    SysFileRetentionPolicy,
    SysJob,
    SysMenu,
    SysNotice,
    SysPost,
    SysRole,
    SysUser,
    GenTable,
    GenTableColumn,
    AiChatConfig,
    AiModels,
    SysPlugin,
    SysPluginMigration,
    SysPluginConfig,
)

CREATE_TIME_ONLY_MODELS = (
    SysFileReference,
    SysFileRetentionNotice,
    SysFileAcl,
    SysJobLog,
    SysPluginMenu,
    SysPluginOperationLog,
)

REQUIRED_CREATE_TIME_MODELS = {
    SysFileInfo,
    SysFileReference,
    SysFileRetentionPolicy,
    SysFileRetentionNotice,
    SysFileAcl,
}

REQUIRED_UPDATE_TIME_MODELS = {
    SysFileInfo,
    SysFileRetentionPolicy,
}


def _column_default(model: type, field_name: str, attribute: str) -> object | None:
    column = model.__table__.c[field_name]
    value = getattr(column, attribute)
    return None if value is None else value.arg


def test_audit_time_columns_are_provided_by_mixins_without_changing_contracts() -> None:
    """审计字段统一由Mixin声明，并保留非空、注释及特殊默认值语义。"""
    assert len(UPDATE_TIME_MODELS) == EXPECTED_UPDATE_TIME_MODEL_COUNT
    assert len(CREATE_TIME_ONLY_MODELS) == EXPECTED_CREATE_TIME_ONLY_MODEL_COUNT

    for model in UPDATE_TIME_MODELS:
        assert issubclass(model, AuditTimeMixin)
        assert model.__table__.c.create_time.nullable is (model not in REQUIRED_CREATE_TIME_MODELS)
        assert model.__table__.c.update_time.nullable is (model not in REQUIRED_UPDATE_TIME_MODELS)
        assert model.__table__.c.create_time.server_default is None
        assert model.__table__.c.update_time.server_default is None

    for model in CREATE_TIME_ONLY_MODELS:
        assert issubclass(model, CreateTimeMixin)
        assert model.__table__.c.create_time.nullable is (model not in REQUIRED_CREATE_TIME_MODELS)
        assert model.__table__.c.create_time.server_default is None

    assert SysPluginMigration.__table__.c.create_time.comment == '执行时间'


def test_all_update_time_columns_use_callable_defaults_and_onupdate() -> None:
    """每个 update_time 都在每次插入/更新时求值，而非导入时冻结时间。"""
    assert len(UPDATE_TIME_MODELS) == EXPECTED_UPDATE_TIME_MODEL_COUNT

    for model in UPDATE_TIME_MODELS:
        onupdate = _column_default(model, 'update_time', 'onupdate')
        assert callable(onupdate)
        assert getattr(onupdate, '__name__', None) == 'now'

        if model is SysPluginMigration:
            # Migration history rows are created with an explicit timestamp;
            # preserve that special semantic while still tracking updates.
            assert _column_default(model, 'update_time', 'default') is None
        else:
            default = _column_default(model, 'update_time', 'default')
            assert callable(default)
            assert getattr(default, '__name__', None) == 'now'


def test_all_create_time_defaults_are_callable() -> None:
    """所有使用 datetime.now 默认值的 DateTime 列都必须传入 callable。"""
    assert len(ENTITY_MODELS) == EXPECTED_ENTITY_MODEL_COUNT

    for model in ENTITY_MODELS:
        for column in model.__table__.columns:
            if isinstance(column.type, DateTime) and column.default is not None:
                default = column.default.arg
                assert callable(default), f'{model.__name__}.{column.name}'
                assert getattr(default, '__name__', None) == 'now', f'{model.__name__}.{column.name}'


@pytest.mark.asyncio
async def test_core_model_time_defaults_are_evaluated_per_insert_and_core_update() -> None:
    """SQLite 行为契约：INSERT 默认值和 Core UPDATE onupdate 都重新求值。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__])

        async with session_maker() as session:
            first = SysPlugin(plugin_id='time-first', plugin_name='First', version='1.0.0')
            second = SysPlugin(plugin_id='time-second', plugin_name='Second', version='1.0.0')
            session.add(first)
            await session.flush()
            first_create_time = first.create_time
            first_update_time = first.update_time

            await asyncio.sleep(0.001)
            session.add(second)
            await session.flush()
            assert second.create_time != first_create_time
            assert second.update_time != first_update_time
            second_update_time = second.update_time

            await asyncio.sleep(0.001)
            await session.execute(
                update(SysPlugin).where(SysPlugin.plugin_id == first.plugin_id).values(version='1.1.0')
            )
            await session.refresh(first)
            assert first.update_time > first_update_time

            await asyncio.sleep(0.001)
            await session.execute(
                update(SysPlugin),
                [{'plugin_id': second.plugin_id, 'version': '1.1.0'}],
            )
            await session.refresh(second)
            assert second.update_time > second_update_time
    finally:
        await engine.dispose()
