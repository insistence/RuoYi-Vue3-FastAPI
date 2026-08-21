from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.database import Base
from module_admin.dao.job_dao import JobDao
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.role_do import SysRoleMenu
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.lifecycle.jobs import PluginJobInstaller, PluginJobModelBuilder, PluginJobRepository
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.entity.do.models import (
    SysPlugin,
    SysPluginConfig,
    SysPluginMenu,
    SysPluginMigration,
    SysPluginOperationLog,
)
from plugins.core.management.entity.vo.schemas import (
    PluginConfigUpdateModel,
    PluginMigrationModel,
    PluginOperationLogExportQueryModel,
    PluginOperationLogPageQueryModel,
    PluginOperationLogRetentionModel,
    PluginPageQueryModel,
)
from plugins.core.management.service.config import PluginConfigManager
from plugins.core.management.service.gateway import PluginManagementRuntimeGateway
from plugins.core.management.service.logs import PluginOperationLogBuilder
from plugins.core.management.service.service import PluginService
from plugins.core.manifest.schema import PluginManifest

INITIAL_MENU_ID = 100
UPDATED_MENU_ID = 101
EXPECTED_MIGRATION_STATEMENT_COUNT = 2
EXPECTED_PLUGIN_CONFIG_COUNT = 3
EXPECTED_PURGE_DESTRUCTIVE_COUNT = 5
EXPECTED_BATCH_SUCCEEDED_COUNT = 2
EXPECTED_PROVIDER_CONFIG_ORDER = 20
EXPECTED_PERMISSION_BUTTON_MENU_COUNT = 5


@pytest.mark.asyncio
async def test_plugin_table_rejects_invalid_state_domains() -> None:
    """校验数据库约束拒绝绕过服务层写入非法启停值和生命周期状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__])

    try:
        async with session_maker() as session:
            session.add(
                SysPlugin(
                    plugin_id='invalid-enabled',
                    plugin_name='Invalid Enabled',
                    version='1.0.0',
                    enabled='2',
                    status='discovered',
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

            session.add(
                SysPlugin(
                    plugin_id='invalid-status',
                    plugin_name='Invalid Status',
                    version='1.0.0',
                    enabled='1',
                    status='unknown',
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
    finally:
        await engine.dispose()


async def create_sqlite_sys_job_table(connection: object) -> None:
    """创建适配 SQLite 的测试用 sys_job 表。"""
    await connection.execute(
        text(
            """
            create table sys_job (
                job_id integer primary key autoincrement,
                job_name varchar(64) not null,
                job_group varchar(64) not null default 'default',
                job_executor varchar(64) default 'default',
                invoke_target varchar(500) not null,
                job_args varchar(255) default '',
                job_kwargs varchar(255) default '',
                cron_expression varchar(255) default '',
                misfire_policy varchar(20) default '3',
                concurrent char(1) default '1',
                status char(1) default '0',
                create_by varchar(64) default '',
                create_time datetime,
                update_by varchar(64) default '',
                update_time datetime,
                remark varchar(500) default ''
            )
            """
        )
    )


async def create_sqlite_sys_menu_table(connection: object) -> None:
    """创建适配 SQLite 的测试用 sys_menu 表。"""
    await connection.execute(
        text(
            """
            create table sys_menu (
                menu_id integer primary key autoincrement,
                menu_name varchar(50) not null,
                parent_id integer default 0,
                order_num integer default 0,
                path varchar(200) default '',
                component varchar(255),
                query varchar(255),
                route_name varchar(50) default '',
                is_frame integer default 1,
                is_cache integer default 0,
                menu_type char(1) default '',
                visible char(1) default '0',
                status char(1) default '0',
                perms varchar(100),
                icon varchar(100) default '#',
                create_by varchar(64) default '',
                create_time datetime,
                update_by varchar(64) default '',
                update_time datetime,
                remark varchar(500) default ''
            )
            """
        )
    )


def build_discovered_plugin(tmp_path: Path, enabled: bool = True, version: str = '1.0.0') -> DiscoveredPlugin:
    """构造测试用已发现插件对象。"""
    backend_path = tmp_path / 'plugins' / 'demo'
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True)
    manifest_path.write_text(
        f"""
id: demo
name: 演示插件
version: {version}
description: 用于测试
backend:
  module: plugins.demo
""".strip(),
        encoding='utf-8',
    )
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': version,
            'description': '用于测试',
            'backend': {'module': 'plugins.demo'},
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_discovered_plugin_with_menu(tmp_path: Path, perms: str) -> DiscoveredPlugin:
    """构造带菜单权限声明的测试插件。"""
    backend_path = tmp_path / 'plugins' / 'demo'
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '演示页面',
                        'path': 'demo',
                        'component': 'plugin/demo/index',
                        'perms': perms,
                    }
                ]
            },
            'permissions': [perms] if perms else [],
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_discovered_plugin_with_permission_buttons(tmp_path: Path) -> DiscoveredPlugin:
    """构造带页面菜单和顶层按钮权限声明的测试插件。"""
    backend_path = tmp_path / 'plugins' / 'demo'
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'frontend': {
                'menus': [
                    {
                        'name': '演示管理',
                        'path': 'demo',
                        'component': 'Layout',
                        'type': 'M',
                        'children': [
                            {
                                'name': '用户管理',
                                'path': 'user',
                                'component': 'plugin/demo/user/index',
                                'perms': 'demo:user:list',
                            }
                        ],
                    }
                ]
            },
            'permissions': ['demo:user:list', 'demo:user:add', 'demo:user:edit', 'demo:user:remove'],
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_discovered_plugin_with_config(tmp_path: Path) -> DiscoveredPlugin:
    """构造带配置声明的测试插件。"""
    backend_path = tmp_path / 'plugins' / 'demo'
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo'},
            'config': {
                'items': [
                    {
                        'key': 'provider',
                        'label': '模型供应商',
                        'type': 'select',
                        'default': 'openai',
                        'required': True,
                        'group': 'model',
                        'order': 20,
                        'placeholder': '请选择模型供应商',
                        'options': [
                            {'label': 'OpenAI', 'value': 'openai'},
                            {'label': 'Mistral', 'value': 'mistral'},
                        ],
                    },
                    {
                        'key': 'api_key',
                        'label': 'API Key',
                        'type': 'password',
                        'default': 'secret-value',
                        'secret': True,
                        'pattern': r'^secret-.+',
                    },
                    {
                        'key': 'temperature',
                        'label': '温度',
                        'type': 'number',
                        'default': 0.5,
                        'min': 0,
                        'max': 1,
                    },
                ]
            },
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def build_discovered_plugin_with_job(tmp_path: Path) -> DiscoveredPlugin:
    """构造带定时任务声明的测试插件。"""
    backend_path = tmp_path / 'plugins' / 'demo'
    manifest_path = backend_path / 'plugin.yaml'
    backend_path.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('', encoding='utf-8')
    manifest = PluginManifest.model_validate(
        {
            'id': 'demo',
            'name': '演示插件',
            'version': '1.0.0',
            'backend': {
                'module': 'plugins.demo',
                'jobs': [
                    {
                        'id': 'cleanup',
                        'name': '清理任务',
                        'callable': 'plugins.demo.jobs.cleanup',
                        'cronExpression': '0 0/5 * * * ?',
                        'args': ['tenant,a', 'dry-run'],
                        'kwargs': {'days': 7},
                    }
                ],
            },
        }
    )

    return DiscoveredPlugin(manifest=manifest, backend_path=backend_path, manifest_path=manifest_path)


def test_plugin_tables_are_registered_with_expected_names() -> None:
    """校验插件管理表使用预期表名注册。"""
    assert SysPlugin.__tablename__ == 'sys_plugin'
    assert SysPluginMenu.__tablename__ == 'sys_plugin_menu'
    assert SysPluginMigration.__tablename__ == 'sys_plugin_migration'
    assert SysPluginConfig.__tablename__ == 'sys_plugin_config'
    assert SysPluginOperationLog.__tablename__ == 'sys_plugin_operation_log'
    assert 'plugin_id' in SysPlugin.__table__.columns
    assert 'last_error' in SysPlugin.__table__.columns
    assert 'continue_on_error' in SysPluginOperationLog.__table__.columns
    assert set(SysPluginMenu.__table__.primary_key.columns.keys()) == {'plugin_id', 'menu_id'}
    unique_constraints = {constraint.name: constraint for constraint in SysPluginMenu.__table__.constraints}
    assert set(unique_constraints['uk_sys_plugin_menu_key'].columns.keys()) == {'plugin_id', 'menu_key'}
    assert set(SysPluginMigration.__table__.primary_key.columns.keys()) == {'plugin_id', 'migration_path'}
    assert 'attempt_count' in SysPluginMigration.__table__.columns
    assert 'started_time' in SysPluginMigration.__table__.columns
    assert 'finished_time' in SysPluginMigration.__table__.columns
    assert 'update_time' in SysPluginMigration.__table__.columns
    assert set(SysPluginConfig.__table__.primary_key.columns.keys()) == {'plugin_id', 'config_key'}


def test_plugin_job_model_builder_maps_manifest_to_job_model(tmp_path: Path) -> None:
    """校验插件任务模型构建器能映射 manifest 任务声明。"""
    discovered_plugin = build_discovered_plugin_with_job(tmp_path)
    job_model = PluginJobModelBuilder.build('demo', discovered_plugin.manifest.backend.jobs[0])

    assert job_model.job_name == 'demo:cleanup'
    assert job_model.job_group == 'default'
    assert job_model.invoke_target == 'plugins.demo.jobs.cleanup'
    assert job_model.job_args == '["tenant,a", "dry-run"]'
    assert job_model.job_kwargs == '{"days": 7}'
    assert job_model.cron_expression == '0 0/5 * * * ?'
    assert job_model.status == '0'


def test_build_plugin_model_uses_discovered_state_for_new_plugin(tmp_path: Path) -> None:
    """校验新插件模型采用发现阶段状态。"""
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
    backend_root = tmp_path / 'plugins'
    frontend_root = tmp_path / 'frontend_plugins'

    plugin = PluginService._build_plugin_model(discovered_plugin, backend_root, frontend_root, None)

    assert plugin.plugin_id == 'demo'
    assert plugin.plugin_name == '演示插件'
    assert plugin.enabled == '0'
    assert plugin.status == 'discovered'
    assert plugin.backend_path == 'demo'
    assert plugin.frontend_path == 'demo'
    assert plugin.description == '用于测试'


def test_plugin_runtime_environment_uses_explicit_backend_root(tmp_path: Path) -> None:
    """校验插件运行环境服务使用明确后端目录。"""
    environment = PluginRuntimeEnvironmentService(tmp_path)

    assert environment.get_backend_dir() == str(tmp_path)


def test_build_plugin_model_keeps_database_enabled_value(tmp_path: Path) -> None:
    """校验插件模型保留数据库中的启用值。"""
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
    existing_plugin = SimpleNamespace(enabled='1', installed_version='1.0.0')

    plugin = PluginService._build_plugin_model(discovered_plugin, tmp_path / 'plugins', None, existing_plugin)

    assert plugin.enabled == '1'
    assert plugin.status == 'installed'


def test_build_plugin_model_marks_pending_upgrade(tmp_path: Path) -> None:
    """校验插件模型在版本变化时标记待升级。"""
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
    existing_plugin = SimpleNamespace(enabled='0', installed_version='0.9.0')

    plugin = PluginService._build_plugin_model(discovered_plugin, tmp_path / 'plugins', None, existing_plugin)

    assert plugin.status == 'pending_upgrade'


def test_build_plugin_model_keeps_installed_when_source_version_is_older(tmp_path: Path) -> None:
    """校验源码版本低于已安装版本时插件管理状态不会误标记待升级。"""
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True, version='1.2.0')
    existing_plugin = SimpleNamespace(enabled='0', installed_version='1.10.0')

    plugin = PluginService._build_plugin_model(discovered_plugin, tmp_path / 'plugins', None, existing_plugin)

    assert plugin.status == 'installed'


def test_build_plugin_model_keeps_error_status_and_last_error(tmp_path: Path) -> None:
    """校验插件扫描合并时会保留数据库中的异常状态和最近错误。"""
    discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
    existing_plugin = SimpleNamespace(
        enabled='0',
        installed_version='1.0.0',
        status='error',
        last_error='broken startup',
    )

    plugin = PluginService._build_plugin_model(discovered_plugin, tmp_path / 'plugins', None, existing_plugin)

    assert plugin.status == 'error'
    assert plugin.last_error == 'broken startup'


@pytest.mark.asyncio
async def test_upsert_discovered_plugin_persists_plugin(tmp_path: Path) -> None:
    """校验发现插件的写入流程可以持久化插件状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            plugin = await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await session.commit()

            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert plugin.plugin_id == 'demo'
        assert db_plugin is not None
        assert db_plugin.plugin_name == '演示插件'
        assert db_plugin.enabled == '0'
        assert db_plugin.status == 'discovered'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mark_plugin_installed_updates_installed_version(tmp_path: Path) -> None:
    """校验插件安装完成后会写入 installed_version 和最终状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            plugin = await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await session.commit()

            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert plugin.installed_version == '1.0.0'
        assert plugin.status == 'installed'
        assert plugin.update_time is not None
        assert db_plugin is not None
        assert db_plugin.installed_version == '1.0.0'
        assert db_plugin.status == 'installed'
        assert plugin.update_time == db_plugin.update_time
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_install_plugin_with_disabled_menus_can_be_enabled_later(tmp_path: Path) -> None:
    """校验默认停用插件安装时会写入停用菜单，后续启用插件可恢复菜单状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])
        await create_sqlite_sys_menu_table(connection)
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_menu(tmp_path, 'demo:list')
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.update_plugin_enabled_services(session, 'demo', enabled=False)
            await PluginService.install_plugin_menu_services(session, discovered_plugin, enabled=False)
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await session.commit()

            plugin_menu = await PluginDao.get_plugin_menu_by_key(session, 'demo', 'perm:demo:list')
            assert plugin_menu is not None
            db_menu = await PluginDao.get_sys_menu_by_id(session, plugin_menu.menu_id)
            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

            assert db_menu is not None
            assert db_menu.status == '1'
            assert db_plugin is not None
            assert db_plugin.status == 'installed'

            result = await PluginService.update_plugin_enabled_services(session, 'demo', enabled=True)
            await session.commit()

            enabled_menu = await PluginDao.get_sys_menu_by_id(session, plugin_menu.menu_id)
            enabled_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert result.is_success is True
        assert enabled_menu is not None
        assert enabled_menu.status == '0'
        assert enabled_plugin is not None
        assert enabled_plugin.enabled == '0'
        assert enabled_plugin.status == 'installed'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_install_plugin_menu_services_generates_permission_buttons(tmp_path: Path) -> None:
    """校验插件安装菜单时会为顶层权限声明生成按钮菜单。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMenu.__table__])
        await create_sqlite_sys_menu_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_permission_buttons(tmp_path)

            await PluginService.install_plugin_menu_services(session, discovered_plugin, enabled=True)
            await session.commit()

            plugin_menus = await PluginDao.get_plugin_menu_list(session, 'demo')
            user_page_link = await PluginDao.get_plugin_menu_by_key(session, 'demo', 'perm:demo:user:list')
            add_button_link = await PluginDao.get_plugin_menu_by_key(
                session,
                'demo',
                'button:perm:demo:user:list/新增#demo:user:add',
            )
            edit_button_link = await PluginDao.get_plugin_menu_by_key(
                session,
                'demo',
                'button:perm:demo:user:list/修改#demo:user:edit',
            )
            remove_button_link = await PluginDao.get_plugin_menu_by_key(
                session,
                'demo',
                'button:perm:demo:user:list/删除#demo:user:remove',
            )
            add_button = await PluginDao.get_sys_menu_by_id(session, add_button_link.menu_id)
            edit_button = await PluginDao.get_sys_menu_by_id(session, edit_button_link.menu_id)
            remove_button = await PluginDao.get_sys_menu_by_id(session, remove_button_link.menu_id)

        assert len(plugin_menus) == EXPECTED_PERMISSION_BUTTON_MENU_COUNT
        assert user_page_link is not None
        assert add_button is not None
        assert add_button.menu_type == 'F'
        assert add_button.parent_id == user_page_link.menu_id
        assert add_button.perms == 'demo:user:add'
        assert edit_button is not None
        assert edit_button.parent_id == user_page_link.menu_id
        assert edit_button.perms == 'demo:user:edit'
        assert remove_button is not None
        assert remove_button.parent_id == user_page_link.menu_id
        assert remove_button.perms == 'demo:user:remove'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mark_plugin_uninstalled_clears_installed_version(tmp_path: Path) -> None:
    """校验插件卸载会清空 installed_version 并回到可安装状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysRoleMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_job(tmp_path)
            discovered_plugin.manifest_path.write_text(
                """
id: demo
name: 演示插件
version: 1.0.0
backend:
  module: plugins.demo
  jobs:
    - id: cleanup
      name: 清理任务
      callable: plugins.demo.jobs.cleanup
      cronExpression: '0 0/5 * * * ?'
      kwargs:
        days: 7
""".strip(),
                encoding='utf-8',
            )
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin)
            session.add(
                SysMenu(
                    menu_id=INITIAL_MENU_ID,
                    menu_name='演示菜单',
                    parent_id=0,
                    path='demo',
                    component='plugin/demo/index',
                    status='0',
                )
            )
            session.add(
                SysPluginMenu(plugin_id='demo', menu_id=INITIAL_MENU_ID, menu_key='route:demo/demo#plugin/demo/index')
            )
            session.add(SysRoleMenu(role_id=2, menu_id=INITIAL_MENU_ID))
            await session.flush()

            result = await PluginService.mark_plugin_uninstalled_services(session, 'demo')
            await session.commit()

            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')
            db_menu = await PluginDao.get_sys_menu_by_id(session, INITIAL_MENU_ID)
            db_plugin_menu = await PluginDao.get_plugin_menu_by_key(
                session,
                'demo',
                'route:demo/demo#plugin/demo/index',
            )
            role_menu_count = (
                await session.execute(
                    text('select count(*) from sys_role_menu where menu_id = :menu_id'),
                    {'menu_id': INITIAL_MENU_ID},
                )
            ).scalar_one()
            job_list = await JobDao.get_all_job_list_for_scheduler(session)
            plugin_detail = await PluginService.plugin_detail_services(
                session,
                'demo',
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )

        assert result.is_success is True
        assert db_plugin is not None
        assert db_plugin.installed_version is None
        assert db_plugin.enabled == '1'
        assert db_plugin.status == 'discovered'
        assert db_menu is None
        assert db_plugin_menu is None
        assert role_menu_count == 0
        assert job_list[0].status == '1'
        assert plugin_detail is not None
        assert plugin_detail.installed_version is None
        assert plugin_detail.status == 'discovered'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mark_plugin_error_preserves_desired_state_and_isolates_resources(tmp_path: Path) -> None:
    """校验标记异常会保留启用意图，同时依靠 error 状态隔离菜单和运行时。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            discovered_plugin.manifest_path.write_text(
                """
id: demo
name: 演示插件
version: 1.0.0
description: 用于测试
backend:
  module: plugins.demo
""".strip(),
                encoding='utf-8',
            )
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            session.add(
                SysMenu(
                    menu_id=INITIAL_MENU_ID,
                    menu_name='演示菜单',
                    parent_id=0,
                    path='demo',
                    component='plugin/demo/index',
                    status='0',
                )
            )
            session.add(
                SysPluginMenu(plugin_id='demo', menu_id=INITIAL_MENU_ID, menu_key='route:demo/demo#plugin/demo/index')
            )
            await session.flush()

            result = await PluginService.mark_plugin_error_services(session, 'demo', 'broken startup')
            await session.commit()

            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')
            db_menu = await PluginDao.get_sys_menu_by_id(session, INITIAL_MENU_ID)

        assert result.is_success is True
        assert db_plugin is not None
        assert db_plugin.enabled == '0'
        assert db_plugin.status == 'error'
        assert db_plugin.last_error == 'broken startup'
        assert db_menu is not None
        assert db_menu.status == '1'
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ('installed', 'expected_status'),
    [
        (False, 'discovered'),
        (True, 'installed'),
    ],
)
@pytest.mark.asyncio
async def test_recover_plugin_dependency_error_restores_lifecycle_state(
    tmp_path: Path,
    installed: bool,
    expected_status: str,
) -> None:
    """校验依赖恢复仅清除启动依赖错误，并按安装版本恢复插件状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            if installed:
                await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await PluginService.mark_plugin_error_services(
                session,
                'demo',
                '插件启动依赖检查失败：Python 依赖未安装：agno',
            )

            result = await PluginService.recover_plugin_dependency_error_services(
                session,
                discovered_plugin,
            )
            await session.commit()
            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert result.is_success is True
        assert db_plugin is not None
        assert db_plugin.enabled == '0'
        assert db_plugin.status == expected_status
        assert db_plugin.installed_version == ('1.0.0' if installed else None)
        assert db_plugin.last_error is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_recover_plugin_dependency_error_preserves_explicit_disable_intent(tmp_path: Path) -> None:
    """校验用户在依赖异常后显式停用插件时，恢复不会擅自重新启用。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await PluginService.mark_plugin_error_services(
                session,
                'demo',
                '插件启动依赖检查失败：Python 依赖未安装：agno',
            )
            await PluginService.update_plugin_enabled_services(session, 'demo', enabled=False)

            result = await PluginService.recover_plugin_dependency_error_services(
                session,
                discovered_plugin,
            )
            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert result.is_success is True
        assert db_plugin is not None
        assert db_plugin.enabled == '1'
        assert db_plugin.status == 'installed'
        assert db_plugin.last_error is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_recover_plugin_dependency_error_preserves_unrelated_error(tmp_path: Path) -> None:
    """校验启动恢复不会误清除 hook、migration 等其他插件错误。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_error_services(session, 'demo', '插件启动钩子执行失败：broken')

            result = await PluginService.recover_plugin_dependency_error_services(
                session,
                discovered_plugin,
            )
            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert result.is_success is False
        assert db_plugin is not None
        assert db_plugin.enabled == '0'
        assert db_plugin.status == 'error'
        assert db_plugin.last_error == '插件启动钩子执行失败：broken'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enable_plugin_rejects_uninstalled_error_state(tmp_path: Path) -> None:
    """校验安装失败插件不能通过启用操作伪装为已安装。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_error_services(session, 'demo', 'broken install')

            result = await PluginService.update_plugin_enabled_services(session, 'demo', enabled=True)
            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')

        assert result.is_success is False
        assert result.message == '插件尚未安装，不能启用'
        assert db_plugin is not None
        assert db_plugin.installed_version is None
        assert db_plugin.enabled == '0'
        assert db_plugin.status == 'error'
        assert db_plugin.last_error == 'broken install'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enable_plugin_rejects_error_state_without_repair_lifecycle(tmp_path: Path) -> None:
    """校验异常插件不能靠启用开关伪装修复，必须重新安装或升级。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            session.add(
                SysMenu(
                    menu_id=INITIAL_MENU_ID,
                    menu_name='演示菜单',
                    parent_id=0,
                    path='demo',
                    component='plugin/demo/index',
                    status='1',
                )
            )
            session.add(
                SysPluginMenu(plugin_id='demo', menu_id=INITIAL_MENU_ID, menu_key='route:demo/demo#plugin/demo/index')
            )
            await PluginService.mark_plugin_error_services(session, 'demo', 'broken startup')

            result = await PluginService.update_plugin_enabled_services(session, 'demo', enabled=True)
            await session.commit()

            db_plugin = await PluginDao.get_plugin_by_id(session, 'demo')
            db_menu = await PluginDao.get_sys_menu_by_id(session, INITIAL_MENU_ID)

        assert result.is_success is False
        assert result.message == '插件状态不允许执行当前启停操作'
        assert db_plugin is not None
        assert db_plugin.enabled == '0'
        assert db_plugin.status == 'error'
        assert db_plugin.last_error == 'broken startup'
        assert db_menu is not None
        assert db_menu.status == '1'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_install_plugin_jobs_upserts_sys_job_idempotently(tmp_path: Path) -> None:
    """校验单插件任务同步会幂等写入系统任务表。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_job(tmp_path)
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin, enabled=True)
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin, enabled=True)
            await session.commit()

            job_list = await JobDao.get_job_list_for_scheduler(session)

        assert len(job_list) == 1
        assert job_list[0].job_name == 'demo:cleanup'
        assert job_list[0].status == '0'
        assert job_list[0].invoke_target == 'plugins.demo.jobs.cleanup'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_job_sync_deletes_stale_owned_jobs_but_keeps_manual_jobs(tmp_path: Path) -> None:
    """校验任务同步删除旧插件任务且不误删用户同名前缀任务。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_job(tmp_path)
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin)
            session.add(
                SysJob(
                    job_name='demo:manual',
                    job_group='default',
                    invoke_target='module_task.scheduler_test.job',
                    status='0',
                    remark='用户手工任务',
                )
            )
            await session.flush()
            discovered_plugin.manifest.backend.jobs = []

            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin)
            await session.commit()
            job_list = await JobDao.get_all_job_list_for_scheduler(session)

        assert [(job.job_name, job.remark) for job in job_list] == [('demo:manual', '用户手工任务')]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_job_sync_rejects_exact_name_collision_with_manual_job(tmp_path: Path) -> None:
    """校验插件任务不会接管同名的用户手工任务。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            session.add(
                SysJob(
                    job_name='demo:cleanup',
                    job_group='default',
                    invoke_target='module_task.scheduler_test.job',
                    status='0',
                    remark='用户手工任务',
                )
            )
            await session.flush()

            with pytest.raises(ValueError, match='拒绝覆盖'):
                await PluginJobInstaller(session).install_plugin_jobs(build_discovered_plugin_with_job(tmp_path))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_disable_plugin_pauses_plugin_jobs(tmp_path: Path) -> None:
    """校验停用插件时会暂停对应插件任务。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_job(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin)

            result = await PluginService.update_plugin_enabled_services(session, 'demo', enabled=False)
            await session.commit()

            job_list = await JobDao.get_all_job_list_for_scheduler(session)

        assert result.is_success is True
        assert len(job_list) == 1
        assert job_list[0].status == '1'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_enable_plugin_restores_plugin_jobs(tmp_path: Path) -> None:
    """校验启用插件时会恢复声明的插件任务。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_job(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            await PluginJobInstaller(session).install_plugin_jobs(discovered_plugin)
            await PluginService.update_plugin_enabled_services(session, 'demo', enabled=False)

            result = await PluginService.update_plugin_enabled_services(
                session,
                'demo',
                enabled=True,
                discovered_plugin=discovered_plugin,
            )
            await session.commit()

            job_list = await JobDao.get_all_job_list_for_scheduler(session)

        assert result.is_success is True
        assert len(job_list) == 1
        assert job_list[0].status == '0'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_plugin_page_list_filters_by_status(tmp_path: Path) -> None:
    """校验插件分页列表支持按状态筛选。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            await PluginService.mark_plugin_installed_services(session, discovered_plugin)
            plugin_page_result = await PluginService.get_plugin_page_list_services(
                session,
                PluginPageQueryModel(status='installed'),
                is_page=True,
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )

        assert plugin_page_result.total == 1
        assert plugin_page_result.rows[0]['pluginId'] == 'demo'
        assert plugin_page_result.rows[0]['status'] == 'installed'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_plugin_page_list_includes_discovered_plugins_without_database_state(tmp_path: Path) -> None:
    """校验插件分页列表会返回本地已发现但尚未写入数据库的插件。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=True)
            discovered_plugin.manifest_path.write_text(
                """
id: demo
name: 演示插件
version: 1.0.0
description: 用于测试
backend:
  module: plugins.demo
""".strip(),
                encoding='utf-8',
            )
            plugin_page_result = await PluginService.get_plugin_page_list_services(
                session,
                PluginPageQueryModel(),
                is_page=True,
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )

        assert plugin_page_result.total == 1
        assert plugin_page_result.rows[0]['pluginId'] == 'demo'
        assert plugin_page_result.rows[0]['pluginName'] == '演示插件'
        assert plugin_page_result.rows[0]['enabled'] == '0'
        assert plugin_page_result.rows[0]['status'] == 'discovered'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_plugin_page_list_includes_database_orphan_for_metadata_purge(tmp_path: Path) -> None:
    """校验源码缺失的数据库孤儿记录仍可在管理列表中被发现和清理。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__])

    try:
        async with session_maker() as session:
            session.add(
                SysPlugin(
                    plugin_id='orphan',
                    plugin_name='孤儿插件',
                    version='1.0.0',
                    installed_version='1.0.0',
                    enabled='1',
                    status='installed',
                    source='local',
                )
            )
            await session.commit()

            plugin_page_result = await PluginService.get_plugin_page_list_services(
                session,
                PluginPageQueryModel(source='orphan'),
                is_page=True,
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )
            plugin_detail = await PluginService.plugin_detail_services(
                session,
                'orphan',
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )

        assert plugin_page_result.total == 1
        orphan_row = plugin_page_result.rows[0]
        assert orphan_row['pluginId'] == 'orphan'
        assert orphan_row['source'] == 'orphan'
        assert 'install' in orphan_row['capability']['blockedOperations']
        assert 'purge' not in orphan_row['capability']['blockedOperations']
        assert plugin_detail is not None
        assert plugin_detail.source == 'orphan'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_detail_returns_discovered_plugin_without_database_state(tmp_path: Path) -> None:
    """校验插件详情会返回本地已发现但尚未写入数据库的插件。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin(tmp_path, enabled=False)
            discovered_plugin.manifest_path.write_text(
                """
id: demo
name: 演示插件
version: 1.0.0
description: 用于测试
backend:
  module: plugins.demo
""".strip(),
                encoding='utf-8',
            )
            plugin_detail = await PluginService.plugin_detail_services(
                session,
                'demo',
                backend_root=tmp_path / 'plugins',
                frontend_root=tmp_path / 'frontend_plugins',
            )

        assert plugin_detail is not None
        assert plugin_detail.plugin_id == 'demo'
        assert plugin_detail.plugin_name == '演示插件'
        assert plugin_detail.enabled == '0'
        assert plugin_detail.status == 'discovered'
        assert plugin_detail.installed_version is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_plugin_menu_updates_existing_menu_key(tmp_path: Path) -> None:
    """校验写入插件菜单时更新已有菜单自然键。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPlugin.__table__, SysPluginMenu.__table__])

    try:
        async with session_maker() as session:
            await PluginService.upsert_plugin_menu_services(session, 'demo', INITIAL_MENU_ID, 'perm:demo:list')
            await PluginService.upsert_plugin_menu_services(session, 'demo', UPDATED_MENU_ID, 'perm:demo:list')
            await session.commit()

            plugin_menu_list = await PluginDao.get_plugin_menu_list(session, 'demo')

        assert len(plugin_menu_list) == 1
        assert plugin_menu_list[0].menu_id == UPDATED_MENU_ID
        assert plugin_menu_list[0].menu_key == 'perm:demo:list'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_migration_history_can_be_persisted_and_read(tmp_path: Path) -> None:
    """校验插件 migration 执行历史可以写入和读取。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMigration.__table__])

    try:
        async with session_maker() as session:
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum',
                    version='1.0.0',
                    statementCount=EXPECTED_MIGRATION_STATEMENT_COUNT,
                ),
            )
            await session.commit()

            plugin_migration = await PluginService.get_plugin_migration_services(
                session,
                'demo',
                'migrations/001_demo.sql',
            )

        assert plugin_migration is not None
        assert plugin_migration.plugin_id == 'demo'
        assert plugin_migration.migration_path == 'migrations/001_demo.sql'
        assert plugin_migration.migration_checksum == 'checksum'
        assert plugin_migration.statement_count == EXPECTED_MIGRATION_STATEMENT_COUNT
        assert plugin_migration.attempt_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_migration_history_upserts_failed_record_to_success() -> None:
    """校验失败 migration 历史可被后续成功执行覆盖。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    failed_statement_count = 1
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMigration.__table__])

    try:
        async with session_maker() as session:
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum',
                    version='1.0.0',
                    statementCount=failed_statement_count,
                    status='failed',
                    errorMessage='boom',
                ),
            )
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum',
                    version='1.0.0',
                    statementCount=EXPECTED_MIGRATION_STATEMENT_COUNT,
                    status='success',
                ),
            )
            await session.commit()

            plugin_migration = await PluginService.get_plugin_migration_services(
                session,
                'demo',
                'migrations/001_demo.sql',
            )

        assert plugin_migration is not None
        assert plugin_migration.status == 'success'
        assert plugin_migration.error_message is None
        assert plugin_migration.statement_count == EXPECTED_MIGRATION_STATEMENT_COUNT
        assert plugin_migration.finished_time is not None
        assert plugin_migration.update_time is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_migration_history_can_be_listed_and_marked() -> None:
    """校验插件 migration 历史可以列表查询并人工标记状态。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMigration.__table__])

    try:
        async with session_maker() as session:
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum-1',
                    version='1.0.0',
                    statementCount=1,
                    status='success',
                ),
            )
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/002_demo.sql',
                    migrationChecksum='checksum-2',
                    version='1.0.0',
                    statementCount=1,
                    status='running',
                ),
            )
            await session.commit()

            running_migrations = await PluginService.get_plugin_migration_list_services(session, 'demo', 'running')
            marked_migration = await PluginService.mark_plugin_migration_status_services(
                session,
                'demo',
                'migrations/002_demo.sql',
                'failed',
                '人工确认未完成',
            )
            await session.commit()

        assert [migration.migration_path for migration in running_migrations] == ['migrations/002_demo.sql']
        assert running_migrations[0].attempt_count == 1
        assert running_migrations[0].started_time is not None
        assert marked_migration is not None
        assert marked_migration.status == 'failed'
        assert marked_migration.error_message == '人工确认未完成'
        assert marked_migration.finished_time is not None
        assert marked_migration.update_time is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_check_installed_menu_conflict_reports_core_permission(tmp_path: Path) -> None:
    """校验插件权限与核心菜单权限重复时会报告冲突。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysMenu.__table__, SysPlugin.__table__, SysPluginMenu.__table__],
        )

    try:
        async with session_maker() as session:
            session.add(
                SysMenu(
                    menu_id=900,
                    menu_name='核心菜单',
                    parent_id=0,
                    path='core',
                    component='core/index',
                    perms='demo:list',
                )
            )
            await session.flush()

            conflicts = await PluginService.check_installed_menu_conflict_services(
                session,
                build_discovered_plugin_with_menu(tmp_path, 'demo:list'),
            )

        assert len(conflicts) == 1
        assert conflicts[0].kind == 'installed_permission'
        assert conflicts[0].conflict_plugin_id is None
        assert conflicts[0].value == 'demo:list'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_default_config_can_be_installed_and_masked(tmp_path: Path) -> None:
    """校验插件默认配置可以落库并对敏感值脱敏。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            installed_configs = await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            configs = await PluginService.get_plugin_config_services(session, discovered_plugin)

        config_map = {config.key: config for config in configs}
        assert len(installed_configs) == EXPECTED_PLUGIN_CONFIG_COUNT
        assert set(config_map) == {'provider', 'api_key', 'temperature'}
        assert config_map['provider'].value == 'openai'
        assert config_map['provider'].group == 'model'
        assert config_map['provider'].order == EXPECTED_PROVIDER_CONFIG_ORDER
        assert config_map['provider'].placeholder == '请选择模型供应商'
        assert config_map['api_key'].value == '******'
        assert config_map['api_key'].pattern == r'^secret-.+'
        assert config_map['temperature'].min == 0
        assert config_map['temperature'].max == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_secret_plugin_config_is_encrypted_at_rest(tmp_path: Path) -> None:
    """校验敏感插件配置加密落库且读取时可按需解密或脱敏。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            await PluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                PluginConfigUpdateModel(values={'api_key': 'secret-updated'}),
            )
            db_config = await PluginDao.get_plugin_config_by_key(session, 'demo', 'api_key')
            masked_configs = await PluginService.get_plugin_config_services(session, discovered_plugin)
            revealed_configs = await PluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=True,
            )

        masked_api_key = next(config for config in masked_configs if config.key == 'api_key')
        revealed_api_key = next(config for config in revealed_configs if config.key == 'api_key')
        assert db_config is not None
        assert db_config.config_value.startswith(PluginConfigManager.ENCRYPTED_PREFIX)
        assert 'secret-updated' not in db_config.config_value
        assert masked_api_key.value == PluginConfigManager.MASK_VALUE
        assert masked_api_key.default == PluginConfigManager.MASK_VALUE
        assert revealed_api_key.value == 'secret-updated'
        assert revealed_api_key.default == 'secret-value'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_config_sync_removes_items_deleted_from_manifest(tmp_path: Path) -> None:
    """校验配置同步会删除 manifest 已移除的旧配置。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            discovered_plugin.manifest.config.items = [
                item for item in discovered_plugin.manifest.config.items if item.key == 'provider'
            ]

            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            configs = await PluginDao.get_plugin_config_list(session, 'demo')

        assert [config.config_key for config in configs] == ['provider']
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_config_sync_reencrypts_value_when_secret_policy_changes(tmp_path: Path) -> None:
    """校验配置项升级为敏感配置时会迁移已有明文值。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            await PluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                PluginConfigUpdateModel(values={'provider': 'mistral'}),
            )
            provider_item = next(item for item in discovered_plugin.manifest.config.items if item.key == 'provider')
            provider_item.secret = True

            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            db_config = await PluginDao.get_plugin_config_by_key(session, 'demo', 'provider')
            configs = await PluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=True,
            )

        provider_config = next(config for config in configs if config.key == 'provider')
        assert db_config is not None
        assert db_config.secret == '0'
        assert db_config.config_value.startswith(PluginConfigManager.ENCRYPTED_PREFIX)
        assert provider_config.value == 'mistral'
    finally:
        await engine.dispose()


def test_secret_plugin_config_rejects_plaintext_storage() -> None:
    """校验敏感插件配置读取时拒绝未加密存储值。"""
    config = SimpleNamespace(
        config_key='api_key',
        config_label='API Key',
        config_type='string',
        config_value='plain-secret',
        default_value=None,
        required='0',
        secret='0',
    )

    with pytest.raises(ValueError, match='敏感插件配置不是加密存储格式'):
        PluginConfigManager.build_config_value(config, reveal_secret=True)


def test_secret_plugin_config_encrypts_user_value_with_encrypted_prefix() -> None:
    """校验用户输入类似密文前缀的敏感值也会重新加密存储。"""
    user_value = f'{PluginConfigManager.ENCRYPTED_PREFIX}not-a-token'

    stored_value = PluginConfigManager.serialize_config_value(user_value, secret=True)
    revealed_value = PluginConfigManager.deserialize_config_value(stored_value, secret=True)

    assert stored_value is not None
    assert stored_value.startswith(PluginConfigManager.ENCRYPTED_PREFIX)
    assert stored_value != user_value
    assert revealed_value == user_value


def test_plugin_config_options_exposes_parse_error() -> None:
    """校验插件配置选项 JSON 损坏时返回可见解析错误。"""
    options = PluginConfigManager.deserialize_options('{broken')

    assert options == [{'parseError': '配置选项 JSON 解析失败'}]


@pytest.mark.asyncio
async def test_get_plugin_config_services_reuses_bulk_config_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """校验读取插件配置时不会逐项查询默认配置。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    async def fail_get_config_by_key(*_args: object, **_kwargs: object) -> None:
        """模拟读取插件配置失败。"""
        raise AssertionError('get_plugin_config_by_key should not be used for default config diff')

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            monkeypatch.setattr(PluginDao, 'get_plugin_config_by_key', fail_get_config_by_key)

            configs = await PluginService.get_plugin_config_services(session, discovered_plugin)
            persisted_count = (await session.execute(text('select count(*) from sys_plugin_config'))).scalar_one()

        assert {config.key for config in configs} == {'provider', 'api_key', 'temperature'}
        assert persisted_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_config_gateway_rejects_uninstalled_plugin_updates(tmp_path: Path) -> None:
    """校验配置写入口不会为尚未安装的插件隐式创建持久化配置。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SysPlugin.__table__, SysPluginConfig.__table__],
        )

    class TestPluginManagementRuntimeGateway(PluginManagementRuntimeGateway):
        """注入测试数据库会话工厂。"""

        @staticmethod
        def get_async_session_local() -> object:
            """获取测试数据库会话工厂。"""
            return session_maker

    try:
        async with session_maker() as session:
            session.add(
                SysPlugin(
                    plugin_id='demo',
                    plugin_name='Demo',
                    version='1.0.0',
                    installed_version=None,
                    enabled='1',
                    status='discovered',
                )
            )
            await session.commit()

        discovered_plugin = build_discovered_plugin_with_config(tmp_path)
        gateway = TestPluginManagementRuntimeGateway()
        with pytest.raises(ValueError, match='插件尚未安装，不能修改配置：demo'):
            await gateway.update_plugin_config(discovered_plugin, {'provider': 'mistral'})
        with pytest.raises(ValueError, match='插件尚未安装，不能修改配置：demo'):
            await gateway.set_plugin_config(
                discovered_plugin,
                {'provider': 'mistral'},
                audit_operation='config_update',
                success_message='配置更新成功',
            )

        async with session_maker() as session:
            persisted_count = (await session.execute(text('select count(*) from sys_plugin_config'))).scalar_one()
        assert persisted_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_config_can_be_updated(tmp_path: Path) -> None:
    """校验插件配置可以更新。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            configs = await PluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                PluginConfigUpdateModel(values={'provider': 'mistral'}),
            )

        provider_config = next(config for config in configs if config.key == 'provider')
        assert provider_config.value == 'mistral'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_config_update_validates_enhanced_constraints(tmp_path: Path) -> None:
    """校验插件配置更新会应用范围和正则约束。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginConfig.__table__])

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            with pytest.raises(ValueError, match='不能大于'):
                await PluginService.update_plugin_config_services(
                    session,
                    discovered_plugin,
                    PluginConfigUpdateModel(values={'temperature': 2}),
                )
            with pytest.raises(ValueError, match='不匹配正则约束'):
                await PluginService.update_plugin_config_services(
                    session,
                    discovered_plugin,
                    PluginConfigUpdateModel(values={'api_key': 'bad'}),
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_build_plugin_purge_plan_counts_platform_metadata(tmp_path: Path) -> None:
    """校验插件物理清理计划会统计平台拥有的插件元数据。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                SysMenu.__table__,
                SysRoleMenu.__table__,
                SysPlugin.__table__,
                SysPluginMenu.__table__,
                SysPluginConfig.__table__,
            ],
        )
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMigration.__table__])
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            session.add(
                SysMenu(
                    menu_id=INITIAL_MENU_ID,
                    menu_name='演示菜单',
                    parent_id=0,
                    path='demo',
                    component='plugin/demo/index',
                    status='0',
                )
            )
            session.add(
                SysPluginMenu(plugin_id='demo', menu_id=INITIAL_MENU_ID, menu_key='route:demo/demo#plugin/demo/index')
            )
            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum',
                    version='1.0.0',
                    statementCount=1,
                ),
            )
            await PluginJobInstaller(session).install_plugin_jobs(build_discovered_plugin_with_job(tmp_path))
            await session.flush()

            plan = await PluginService.build_plugin_purge_plan_services(session, discovered_plugin)

        item_map = {item.name: item for item in plan.items}
        assert item_map['delete_plugin_menus'].count == 1
        assert item_map['delete_plugin_configs'].count == EXPECTED_PLUGIN_CONFIG_COUNT
        assert item_map['delete_plugin_migrations'].count == 1
        assert item_map['delete_plugin_jobs'].count == 1
        assert item_map['remove_source'].enabled is False
        assert plan.removes_source is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_purge_plugin_metadata_by_id_deletes_orphan_platform_metadata(tmp_path: Path) -> None:
    """校验源码缺失时可按插件 ID 删除平台拥有的孤儿元数据。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                SysMenu.__table__,
                SysRoleMenu.__table__,
                SysPlugin.__table__,
                SysPluginMenu.__table__,
                SysPluginConfig.__table__,
            ],
        )
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginMigration.__table__])
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            discovered_plugin = build_discovered_plugin_with_config(tmp_path)
            await PluginService.upsert_discovered_plugin_services(
                session,
                discovered_plugin,
                tmp_path / 'plugins',
                tmp_path / 'frontend_plugins',
            )
            session.add(
                SysMenu(
                    menu_id=INITIAL_MENU_ID,
                    menu_name='演示菜单',
                    parent_id=0,
                    path='demo',
                    component='plugin/demo/index',
                    status='0',
                )
            )
            session.add(
                SysPluginMenu(plugin_id='demo', menu_id=INITIAL_MENU_ID, menu_key='route:demo/demo#plugin/demo/index')
            )
            await PluginService.install_plugin_default_config_services(session, discovered_plugin)
            await PluginService.add_plugin_migration_services(
                session,
                PluginMigrationModel(
                    pluginId='demo',
                    migrationPath='migrations/001_demo.sql',
                    migrationChecksum='checksum',
                    version='1.0.0',
                    statementCount=1,
                ),
            )
            await PluginJobInstaller(session).install_plugin_jobs(build_discovered_plugin_with_job(tmp_path))

            plan = await PluginService.purge_plugin_metadata_by_id_services(session, 'demo')
            await session.commit()

            plugin = await PluginDao.get_plugin_by_id(session, 'demo')
            plugin_menus = await PluginDao.get_plugin_menu_list(session, 'demo')
            menu = await PluginDao.get_sys_menu_by_id(session, INITIAL_MENU_ID)
            config_count = await PluginDao.count_plugin_configs(session, 'demo')
            migration_count = await PluginDao.count_plugin_migrations(session, 'demo')
            job_count = await PluginJobRepository(session).count_jobs_by_name_prefix('demo:')

        assert plan.destructive_count == EXPECTED_PURGE_DESTRUCTIVE_COUNT
        assert plugin is None
        assert plugin_menus == []
        assert menu is None
        assert config_count == 0
        assert migration_count == 0
        assert job_count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_job_prefix_queries_treat_like_wildcards_as_literals() -> None:
    """校验插件任务前缀查询会把插件 ID 中的 LIKE 通配符当作普通字符。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await create_sqlite_sys_job_table(connection)

    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysJob(
                        job_name='foo_bar:cleanup',
                        job_group='default',
                        invoke_target='plugins.foo_bar.jobs.cleanup',
                        status='0',
                        remark=f'{PluginJobModelBuilder.REMARK_PREFIX} foo_bar:cleanup',
                    ),
                    SysJob(
                        job_name='fooXbar:cleanup',
                        job_group='default',
                        invoke_target='plugins.fooXbar.jobs.cleanup',
                        status='0',
                        remark=f'{PluginJobModelBuilder.REMARK_PREFIX} fooXbar:cleanup',
                    ),
                ]
            )
            await session.commit()

            repository = PluginJobRepository(session)
            before_count = await repository.count_jobs_by_name_prefix('foo_bar:')
            await repository.pause_jobs_by_name_prefix('foo_bar:')
            await session.commit()

            rows = (await session.execute(text('select job_name, status from sys_job order by job_name'))).all()
            await repository.delete_jobs_by_name_prefix('foo_bar:')
            await session.commit()
            remaining_rows = (await session.execute(text('select job_name from sys_job order by job_name'))).all()

        assert before_count == 1
        assert rows == [('fooXbar:cleanup', '0'), ('foo_bar:cleanup', '1')]
        assert remaining_rows == [('fooXbar:cleanup',)]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_add_plugin_operation_log_services_persists_batch_report() -> None:
    """校验插件批量操作审计日志可以落库。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            payload = {
                'ok': False,
                'operation': 'install',
                'dryRun': False,
                'continueOnError': True,
                'message': '插件批量操作完成，存在失败项',
                'plan': {'orderedPluginIds': ['base', 'app'], 'blockerCount': 0},
                'summary': {'total': 2, 'succeeded': 1, 'failed': 1, 'skipped': 0},
            }
            operation_log = await PluginService.add_plugin_operation_log_services(
                session,
                payload,
                dry_run=False,
                continue_on_error=True,
            )
            await session.commit()

            db_operation_log = await session.get(SysPluginOperationLog, operation_log.operation_id)

        assert operation_log.operation == 'install'
        assert operation_log.status == 'failed'
        assert operation_log.dry_run == '1'
        assert operation_log.continue_on_error == '0'
        assert db_operation_log is not None
        assert db_operation_log.plugin_ids == '["base", "app"]'
        assert '"failed": 1' in db_operation_log.summary
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_operation_log_services_returns_page_and_detail() -> None:
    """校验插件批量操作审计日志分页和详情会解析 JSON 字段。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            payload = {
                'ok': True,
                'operation': 'enable',
                'dryRun': False,
                'continueOnError': False,
                'message': '插件批量操作完成',
                'plan': {'orderedPluginIds': ['base', 'app'], 'blockerCount': 0},
                'summary': {'total': 2, 'succeeded': 2, 'failed': 0, 'skipped': 0},
                'executed': [{'pluginId': 'base'}, {'pluginId': 'app'}],
            }
            operation_log = await PluginService.add_plugin_operation_log_services(
                session,
                payload,
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()

            page_result = await PluginService.get_plugin_operation_log_page_list_services(
                session,
                PluginOperationLogPageQueryModel(pageNum=1, pageSize=10, operation='enable', pluginId='app'),
                is_page=True,
            )
            detail_result = await PluginService.plugin_operation_log_detail_services(
                session,
                operation_log.operation_id,
            )

        assert page_result.total == 1
        assert page_result.rows[0].plugin_ids == ['base', 'app']
        assert page_result.rows[0].summary['succeeded'] == EXPECTED_BATCH_SUCCEEDED_COUNT
        assert detail_result is not None
        assert detail_result.result['executed'][1]['pluginId'] == 'app'
        assert detail_result.continue_on_error is False
    finally:
        await engine.dispose()


def test_build_plugin_operation_log_model_supports_single_plugin_payload() -> None:
    """校验插件操作审计日志构建器支持单插件操作负载。"""
    operation_log = PluginOperationLogBuilder.build_model(
        {
            'ok': True,
            'operation': 'purge',
            'pluginId': 'demo',
            'dryRun': False,
            'message': '插件物理清理完成',
        },
        dry_run=False,
        continue_on_error=False,
    )

    assert operation_log.operation == 'purge'
    assert operation_log.plugin_ids == '["demo"]'
    assert operation_log.status == 'success'


def test_plugin_operation_log_detail_exposes_invalid_json_parse_error() -> None:
    """校验插件操作日志详情 JSON 损坏时返回可见解析错误。"""
    detail = PluginOperationLogBuilder.build_detail(
        {
            'operationId': 1,
            'operation': 'install',
            'pluginIds': '["demo"]',
            'dryRun': '1',
            'continueOnError': '1',
            'status': 'failed',
            'summary': '{broken',
            'result': '[]',
        }
    )

    assert detail.summary == {'parseError': 'JSON 解析失败'}
    assert detail.result == {'parseError': 'JSON 内容不是对象'}


@pytest.mark.asyncio
async def test_plugin_operation_log_plugin_id_filter_matches_json_array_element() -> None:
    """校验操作日志按插件 ID 查询时不会命中 JSON 数组里的相似插件 ID。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["foo"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                    ),
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["foobar"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                    ),
                ]
            )
            await session.commit()

            page_result = await PluginService.get_plugin_operation_log_page_list_services(
                session,
                PluginOperationLogPageQueryModel(pageNum=1, pageSize=10, pluginId='foo'),
                is_page=True,
            )

        assert page_result.total == 1
        assert page_result.rows[0].plugin_ids == ['foo']
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_operation_log_plugin_id_filter_treats_like_wildcards_as_literals() -> None:
    """校验操作日志插件 ID 过滤不会把 _ 和 % 当成 SQL LIKE 通配符。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["foo_bar"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                    ),
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["prefix", "fooXbar", "suffix"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                    ),
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["prefix", "foo%bar", "suffix"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                    ),
                ]
            )
            await session.commit()

            page_result = await PluginService.get_plugin_operation_log_page_list_services(
                session,
                PluginOperationLogPageQueryModel(pageNum=1, pageSize=10, pluginId='foo_bar'),
                is_page=True,
            )

        assert page_result.total == 1
        assert page_result.rows[0].plugin_ids == ['foo_bar']
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_plugin_operation_log_export_services_returns_filtered_rows() -> None:
    """校验插件操作审计日志导出服务会按查询条件返回可导出数据。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            await PluginService.add_plugin_operation_log_services(
                session,
                {
                    'ok': True,
                    'operation': 'install',
                    'pluginId': 'demo',
                    'summary': {'total': 1, 'succeeded': 1, 'failed': 0},
                },
                dry_run=False,
                continue_on_error=False,
            )
            await PluginService.add_plugin_operation_log_services(
                session,
                {
                    'ok': False,
                    'operation': 'upgrade',
                    'pluginId': 'demo',
                    'summary': {'total': 1, 'succeeded': 0, 'failed': 1},
                },
                dry_run=False,
                continue_on_error=False,
            )
            await PluginService.add_plugin_operation_log_services(
                session,
                {
                    'ok': False,
                    'operation': 'upgrade',
                    'pluginId': 'other',
                    'summary': {'total': 1, 'succeeded': 0, 'failed': 1},
                },
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()

            today = datetime.now().strftime('%Y-%m-%d')
            export_list = await PluginService.get_plugin_operation_log_export_list_services(
                session,
                PluginOperationLogExportQueryModel(
                    operation='upgrade',
                    status='failed',
                    pluginId='demo',
                    beginTime=today,
                    endTime=today,
                    exportLimit=10,
                ),
            )
            export_binary = PluginService.export_plugin_operation_log_list_services(
                export_list,
                {'upgrade': '升级'},
            )

        assert len(export_list) == 1
        assert export_list[0].operation == 'upgrade'
        assert export_list[0].status == 'failed'
        assert export_binary.startswith(b'PK')
        workbook = load_workbook(BytesIO(export_binary))
        sheet = workbook.active
        assert sheet['B2'].value == '升级'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retain_plugin_operation_log_services_supports_dry_run_and_delete() -> None:
    """校验插件操作审计日志保留策略支持预览和删除。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            session.add_all(
                [
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["old"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                        create_time=datetime.now() - timedelta(days=30),
                    ),
                    SysPluginOperationLog(
                        operation='install',
                        plugin_ids='["new"]',
                        dry_run='1',
                        continue_on_error='1',
                        status='success',
                        create_time=datetime.now(),
                    ),
                ]
            )
            await session.commit()

            dry_run_result = await PluginService.retain_plugin_operation_log_services(
                session,
                PluginOperationLogRetentionModel(retentionDays=7, dryRun=True),
            )
            delete_result = await PluginService.retain_plugin_operation_log_services(
                session,
                PluginOperationLogRetentionModel(retentionDays=7, dryRun=False),
            )
            await session.commit()
            remaining_count = await PluginDao.count_plugin_operation_logs_before(
                session,
                datetime.now() + timedelta(days=1),
            )

        assert dry_run_result.matched_count == 1
        assert dry_run_result.deleted_count == 0
        assert delete_result.matched_count == 1
        assert delete_result.deleted_count == 1
        assert remaining_count == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_retain_plugin_operation_log_services_accepts_zero_days() -> None:
    """校验插件操作审计日志保留策略支持 0 天，便于清理当前时间之前的全部日志。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            session.add(
                SysPluginOperationLog(
                    operation='install',
                    plugin_ids='["demo"]',
                    dry_run='1',
                    continue_on_error='1',
                    status='success',
                    create_time=datetime.now() - timedelta(minutes=1),
                )
            )
            await session.commit()

            delete_result = await PluginService.retain_plugin_operation_log_services(
                session,
                PluginOperationLogRetentionModel(retentionDays=0, dryRun=False),
            )
            await session.commit()
            remaining_count = await PluginDao.count_plugin_operation_logs_before(
                session,
                datetime.now() + timedelta(days=1),
            )

        assert delete_result.retention_days == 0
        assert delete_result.matched_count == 1
        assert delete_result.deleted_count == 1
        assert remaining_count == 0
    finally:
        await engine.dispose()
