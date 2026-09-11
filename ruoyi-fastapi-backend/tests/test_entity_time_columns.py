import asyncio

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from common.types import DbUtcDateTime
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
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
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

# 显式维护 DO 类及 update_time 列清单，新增或移除时需同步核对模型。
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
    SysJobSync,
    SysJobExecution,
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
    SysJobSync,
    SysJobExecution,
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


def test_audit_time_columns_preserve_nullability_and_migration_semantics() -> None:
    """审计字段保留非空约束、迁移时间注释和应用侧默认值。"""
    for model in UPDATE_TIME_MODELS:
        assert model.__table__.c.create_time.nullable is (model not in REQUIRED_CREATE_TIME_MODELS)
        assert model.__table__.c.update_time.nullable is (model not in REQUIRED_UPDATE_TIME_MODELS)
        assert model.__table__.c.create_time.server_default is None
        assert model.__table__.c.update_time.server_default is None

    for model in CREATE_TIME_ONLY_MODELS:
        assert model.__table__.c.create_time.nullable is (model not in REQUIRED_CREATE_TIME_MODELS)
        assert model.__table__.c.create_time.server_default is None

    assert SysPluginMigration.__table__.c.create_time.comment == '执行时间'


def test_all_update_time_columns_use_callable_defaults_and_onupdate() -> None:
    """每个 update_time 都在每次插入/更新时求值，而非导入时冻结时间。"""
    for model in UPDATE_TIME_MODELS:
        onupdate = _column_default(model, 'update_time', 'onupdate')
        assert callable(onupdate)

        if model is SysPluginMigration:
            # 迁移历史在创建时显式传入时间，同时保留后续更新的审计行为。
            assert _column_default(model, 'update_time', 'default') is None
        else:
            default = _column_default(model, 'update_time', 'default')
            assert callable(default)


def test_all_time_columns_use_utc_type_and_callable_defaults() -> None:
    """时刻列使用DbUtcDateTime，并在写入时计算默认值。"""
    for model in ENTITY_MODELS:
        for column in model.__table__.columns:
            # 耗时和延迟宽限以数值存储，不属于UTC时刻。
            if column.name.endswith(('_time', '_date')) and column.name not in {'cost_time', 'misfire_grace_time'}:
                assert isinstance(column.type, DbUtcDateTime), f'{model.__name__}.{column.name}'
            if isinstance(column.type, DbUtcDateTime) and column.default is not None:
                default = column.default.arg
                assert callable(default), f'{model.__name__}.{column.name}'


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
