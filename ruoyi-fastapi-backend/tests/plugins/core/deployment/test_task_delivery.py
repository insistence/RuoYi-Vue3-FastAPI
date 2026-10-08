import sys
from pathlib import Path

import pytest
from sqlalchemy import Integer, MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.database import DataSourceRegistry
from config.env import DataBaseConfig
from module_admin.entity.do.menu_do import SysMenu
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.service import PluginDeploymentService
from plugins.core.lifecycle.migration import PluginMigrationRunner
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock
from scripts.plugin_task_integration import EXPECTED_MIGRATIONS, exercise_task_delivery

SOURCE = Path(__file__).resolve().parents[4] / 'plugins' / 'examples' / 'python' / 'task_demo'


@pytest.mark.asyncio
async def test_task_signed_delivery_preserves_data_and_exercises_crud(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    在 SQLite 中适配时间类型后执行 DDL，验证真实维护流程及交付包业务接口。

    :param deployment_sessions: 临时宿主表的数据库会话工厂
    :param deployment_config: 临时制品存储和信任配置
    :param tmp_path: 本次测试的独立目录
    :param monkeypatch: pytest 环境隔离工具
    :return: None
    """
    import shutil  # noqa: PLC0415

    # SQLite 只有 INTEGER PRIMARY KEY 才会生成自增值，宿主生产表使用 BIGINT。
    sqlite_menu = SysMenu.__table__.to_metadata(MetaData())
    sqlite_menu.c.menu_id.type = Integer()
    async with deployment_sessions.kw['bind'].begin() as connection:
        await connection.run_sync(SysMenu.__table__.drop)
        await connection.run_sync(sqlite_menu.create)
    # SQLite 不能同时持有生命周期 UoW 与迁移历史的两个写事务；只对宿主维护会话使用自动提交。
    # 业务 CRUD 保留下面传入的常规事务会话，真实数据库 CI 不使用此适配。
    host_sessions = async_sessionmaker(
        deployment_sessions.kw['bind'].execution_options(isolation_level='AUTOCOMMIT'), expire_on_commit=False
    )
    monkeypatch.setattr(DataSourceRegistry, 'session', host_sessions)
    monkeypatch.setattr(DataBaseConfig.default_source, 'db_type', 'postgresql')
    monkeypatch.setattr(sys, 'dont_write_bytecode', True)
    original_loader = PluginMigrationRunner._load_sql_statements

    def sqlite_statements(runner: PluginMigrationRunner, path: Path) -> list[str]:
        """
        仅替换 SQLite 不支持的 PostgreSQL 时间列语法，保留原文件与校验值。

        :param runner: 本次迁移运行器
        :param path: 原始迁移文件
        :return: 保持业务 DDL 不变的 SQLite 可执行语句
        """
        return [
            statement.replace('TIMESTAMP(3) WITH TIME ZONE', 'DATETIME') for statement in original_loader(runner, path)
        ]

    monkeypatch.setattr(PluginMigrationRunner, '_load_sql_statements', sqlite_statements)
    source = tmp_path / 'source'
    shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns('node_modules', 'dist', '__pycache__'))
    dist = source / 'web' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'index.html').write_text('<!doctype html><html><body>Task fixture</body></html>', encoding='utf-8')
    service = PluginDeploymentService(
        deployment_config, session_factory=host_sessions, lifecycle_lock=NoopPluginLifecycleLock()
    )
    try:
        result = await exercise_task_delivery(service, deployment_sessions, source, tmp_path / 'delivery')
        assert result['version'] == '1.1.0'
        assert result['migrations'] == EXPECTED_MIGRATIONS and result['retainedRows'] == 1
        assert result['crud'] and result['readOnlyDenied']
    finally:
        for name in list(sys.modules):
            if name == 'plugins.task_demo' or name.startswith('plugins.task_demo.'):
                monkeypatch.delitem(sys.modules, name)
