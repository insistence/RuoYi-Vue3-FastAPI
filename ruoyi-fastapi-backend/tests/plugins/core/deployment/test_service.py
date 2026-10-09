import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.database import DataSourceRegistry
from plugins.core.artifacts import build_artifact
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.service import PluginDeploymentService
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.management.dao.release_dao import PluginReleaseConflictError, PluginReleaseDao
from plugins.core.management.entity.do.models import SysPlugin, SysPluginOperationLog
from plugins.core.management.entity.do.release_models import SysPluginRelease
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock, PluginLifecycleLockResult
from utils.time_util import TimezoneUtil

PLUGIN_ID = 'artifact_demo'


class MaintenanceRuntime:
    """模拟安装、升级及预检结果的维护运行时。"""

    def __init__(self, owner: 'MaintenanceFactory', plugins: list[DiscoveredPlugin]) -> None:
        """保存测试制品快照、数据库工厂及故障配置。"""
        self.owner = owner
        self.plugins = {plugin.manifest.id: plugin for plugin in plugins}

    async def install_plugin(self, plugin_id: str, **kwargs: Any) -> dict[str, Any]:
        """按测试配置模拟插件安装。"""
        return await self.execute('install', plugin_id, **kwargs)

    async def upgrade_plugin(self, plugin_id: str, **kwargs: Any) -> dict[str, Any]:
        """按测试配置模拟插件升级。"""
        return await self.execute('upgrade', plugin_id, **kwargs)

    async def check_plugin_async(self, plugin_id: str) -> dict[str, Any]:
        """返回当前测试指定的静态预检结果。"""
        self.owner.calls.append(('check', True, self.plugins[plugin_id].manifest.version))
        return {'ok': self.owner.failure != 'check', 'message': 'static dependency check'}

    async def execute(
        self, operation: str, plugin_id: str, *, dry_run: bool = False, operated_by: str | None = None
    ) -> dict[str, Any]:
        """模拟维护写入及失败场景，更新临时安装状态。"""
        plugin = self.plugins[plugin_id]
        self.owner.calls.append((operation, dry_run, plugin.manifest.version))
        if dry_run:
            return {'ok': True, 'message': 'static lifecycle plan'}
        if self.owner.failure == 'raise':
            raise RuntimeError('injected migration error')
        if self.owner.failure == 'result':
            return {'ok': False, 'message': 'lifecycle rejected candidate'}
        if self.owner.failure != 'no-version':
            async with self.owner.sessions() as db:
                row = await db.get(SysPlugin, plugin_id)
                if row is None:
                    row = SysPlugin(
                        plugin_id=plugin_id, plugin_name=plugin.manifest.name, version=plugin.manifest.version
                    )
                    db.add(row)
                row.version = row.installed_version = plugin.manifest.version
                row.status = 'installed'
                await db.commit()
        if self.owner.failure == 'tamper':
            (plugin.backend_path / '__init__.py').write_text('raise RuntimeError("modified by hook")\n')
        return {'ok': True, 'message': f'{operation} complete', 'operatedBy': operated_by}


class MaintenanceFactory:
    """记录维护运行时创建情况并提供可控故障的测试工厂。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """初始化测试数据库和维护故障配置。"""
        self.sessions = sessions
        self.calls: list[tuple[str, bool, str]] = []
        self.failure: str | None = None

    def __call__(self, config: PluginDeploymentConfig, plugins: list[DiscoveredPlugin]) -> MaintenanceRuntime:
        """为当前候选制品创建测试维护运行时。"""
        return MaintenanceRuntime(self, plugins)


@pytest.fixture
def maintenance_factory(deployment_sessions: async_sessionmaker[AsyncSession]) -> MaintenanceFactory:
    """提供可记录维护操作的运行时工厂。"""
    return MaintenanceFactory(deployment_sessions)


@pytest.fixture
def service(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    maintenance_factory: MaintenanceFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> PluginDeploymentService:
    """创建使用临时数据库与测试生命周期锁的发布服务。"""
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    return PluginDeploymentService(
        deployment_config,
        session_factory=deployment_sessions,
        lifecycle_lock=NoopPluginLifecycleLock(),
        runtime_factory=maintenance_factory,
    )


async def import_prepare_select(service: PluginDeploymentService, archive: Path) -> dict[str, Any]:
    """依次导入、维护准备并选择测试制品。"""
    imported = await service.catalog.import_artifact(archive)
    prepared = await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True, actor='operator')
    return await service.select(
        PLUGIN_ID,
        imported['digest'],
        maintenance=True,
        expected_generation=prepared['generation'],
        actor='operator',
    )


def new_archive(source: Path, destination: Path, key: Ed25519PrivateKey, version: str) -> Path:
    """为指定版本创建新的签名测试制品。"""
    manifest = yaml.safe_load((source / 'plugin.yaml').read_text())
    manifest['version'] = version
    (source / 'plugin.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    build_artifact(source, destination, key, 'publisher')
    return destination


@pytest.mark.asyncio
async def test_install_plan_prepare_select_and_pending_restart_are_distinct(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
    maintenance_factory: MaintenanceFactory,
) -> None:
    """验证安装计划、维护准备、目标选择和等待重启状态相互独立。"""
    imported = await service.catalog.import_artifact(deployment_archive)
    digest = imported['digest']
    planned = await service.plan(PLUGIN_ID, digest)
    assert planned['ok'] and planned['operation'] == 'install'
    assert planned['generation'] is None
    assert maintenance_factory.calls == [('install', True, '1.0.0')]
    async with deployment_sessions() as db:
        assert await db.get(SysPlugin, PLUGIN_ID) is None
        assert await db.get(SysPluginRelease, PLUGIN_ID) is None
    with pytest.raises(ValueError, match='maintenance'):
        await service.prepare(PLUGIN_ID, digest)
    prepared = await service.prepare(PLUGIN_ID, digest, maintenance=True, actor='operator')
    async with deployment_sessions() as db:
        row = await db.get(SysPluginRelease, PLUGIN_ID)
        assert row.target_digest is None
        assert row.prepared_digest == digest
        assert row.prepared_version == '1.0.0'
        assert (await db.get(SysPlugin, PLUGIN_ID)).installed_version == '1.0.0'
    again = await service.prepare(PLUGIN_ID, digest, maintenance=True)
    assert again['ok']
    assert maintenance_factory.calls.count(('install', False, '1.0.0')) == 1
    reuse = await service.plan(PLUGIN_ID, digest)
    assert reuse['ok'] and reuse['preparationMatches'] and reuse['operation'] == 'reuse_prepared'
    selected = await service.select(PLUGIN_ID, digest, expected_generation=prepared['generation'], maintenance=True)
    assert selected['generation'] != prepared['generation']
    assert selected['restartRequired']
    status = await service.status(PLUGIN_ID)
    assert status['releases'][0]['status'] == 'pending_restart'
    assert status['releases'][0]['targetDigest'] == digest
    assert status['releases'][0]['installedVersion'] == '1.0.0'
    assert status['workers'] == []
    assert 'plugins.artifact_demo' not in sys.modules
    async with deployment_sessions() as db:
        logs = (await db.scalars(select(SysPluginOperationLog))).all()
        assert len(logs) == 1 and logs[0].operation == 'release_select'


@pytest.mark.asyncio
async def test_same_version_digest_is_not_guessed_from_installed_version(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_source: Path,
    deployment_key: Ed25519PrivateKey,
    deployment_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """验证同版本制品必须具有匹配摘要的准备证据。"""
    selected = await import_prepare_select(service, deployment_archive)
    (deployment_source / 'new-file.txt').write_text('Different build with the same version')
    changed = new_archive(deployment_source, tmp_path / 'different.rpk', deployment_key, '1.0.0')
    imported = await service.catalog.import_artifact(changed)
    assert imported['digest'] != selected['digest']
    plan = await service.plan(PLUGIN_ID, imported['digest'])
    assert not plan['ok'] and not plan['preparationMatches']
    assert '不能猜测' in plan['message']
    with pytest.raises(ValueError, match='同版本'):
        await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)
    with pytest.raises(ValueError, match='尚未完成维护准备'):
        await service.select(
            PLUGIN_ID, imported['digest'], maintenance=True, expected_generation=selected['generation']
        )
    async with deployment_sessions() as db:
        assert (await db.get(SysPluginRelease, PLUGIN_ID)).target_digest == selected['digest']


@pytest.mark.asyncio
async def test_plan_same_version_without_any_preparation_proof_is_not_ready(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证同版本缺少准备证据时预检不能判定可直接发布。"""
    imported = await service.catalog.import_artifact(deployment_archive)
    async with deployment_sessions() as db:
        db.add(SysPlugin(plugin_id=PLUGIN_ID, plugin_name='existing', version='1.0.0', installed_version='1.0.0'))
        await db.commit()
    result = await service.plan(PLUGIN_ID, imported['digest'])
    assert not result['ok'] and not result['preparationMatches']
    with pytest.raises(ValueError, match='同版本'):
        await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['raise', 'result', 'no-version', 'tamper'])
async def test_failed_preparation_clears_proof_and_preserves_previous_target(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_source: Path,
    deployment_key: Ed25519PrivateKey,
    deployment_sessions: async_sessionmaker[AsyncSession],
    maintenance_factory: MaintenanceFactory,
    tmp_path: Path,
    failure: str,
) -> None:
    """验证维护准备失败清除证据但保留原发布目标。"""
    selected = await import_prepare_select(service, deployment_archive)
    upgrade = new_archive(deployment_source, tmp_path / 'upgrade.rpk', deployment_key, '2.0.0')
    imported = await service.catalog.import_artifact(upgrade)
    maintenance_factory.failure = failure
    with pytest.raises((ValueError, RuntimeError)):
        await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)
    async with deployment_sessions() as db:
        row = await db.get(SysPluginRelease, PLUGIN_ID)
        assert row.target_digest == selected['digest']
        assert row.generation == selected['generation']
        assert row.prepare_status == 'failed'
        assert row.prepared_digest is None and row.prepared_version is None
        assert row.last_error


@pytest.mark.asyncio
async def test_upgrade_and_explicit_code_rollback_preserve_newer_installed_schema(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_source: Path,
    deployment_key: Ed25519PrivateKey,
    deployment_sessions: async_sessionmaker[AsyncSession],
    maintenance_factory: MaintenanceFactory,
    tmp_path: Path,
) -> None:
    """验证代码回滚保留升级后的数据结构安装版本。"""
    first = await import_prepare_select(service, deployment_archive)
    upgrade = new_archive(deployment_source, tmp_path / 'upgrade.rpk', deployment_key, '2.0.0')
    second = await import_prepare_select(service, upgrade)
    assert (await service.plan(PLUGIN_ID, first['digest']))['operation'] == 'rollback_required'
    assert not (await service.plan(PLUGIN_ID, first['digest']))['ok']
    with pytest.raises(ValueError, match='撤销数据库迁移'):
        await service.rollback(PLUGIN_ID, expected_generation=second['generation'], maintenance=True)
    before = list(maintenance_factory.calls)
    rolled = await service.rollback(
        PLUGIN_ID,
        expected_generation=second['generation'],
        maintenance=True,
        schema_compatible=True,
    )
    assert rolled['digest'] == first['digest']
    assert rolled['version'] == '1.0.0'
    assert rolled['installedVersion'] == '2.0.0'
    assert rolled['generation'] != second['generation']
    assert maintenance_factory.calls == [*before, ('check', True, '1.0.0')]
    async with deployment_sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        release = await db.get(SysPluginRelease, PLUGIN_ID)
        assert plugin.installed_version == '2.0.0'
        assert plugin.version == '1.0.0'
        assert release.target_digest == first['digest']
        assert release.previous_digest == second['digest']
        assert release.prepared_version == '2.0.0'
        assert release.prepared_digest == first['digest']


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['prepare', 'select', 'rollback'])
async def test_live_host_worker_blocks_all_maintenance_mutations(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
    operation: str,
) -> None:
    """验证存活宿主进程阻止维护发布写操作。"""
    selected = await import_prepare_select(service, deployment_archive)
    async with deployment_sessions() as db:
        await PluginReleaseDao.upsert_worker_report(
            db,
            worker_id='1' * 32,
            plugin_id='__runtime__',
            state='ready',
            heartbeat_time=TimezoneUtil.utc_now(),
        )
        await db.commit()
    with pytest.raises(ValueError, match='存活的宿主 worker'):
        if operation == 'prepare':
            await service.prepare(PLUGIN_ID, selected['digest'], maintenance=True)
        elif operation == 'select':
            await service.select(
                PLUGIN_ID, selected['digest'], maintenance=True, expected_generation=selected['generation']
            )
        else:
            await service.rollback(
                PLUGIN_ID, maintenance=True, schema_compatible=True, expected_generation=selected['generation']
            )
    status = await service.status(PLUGIN_ID)
    assert status['workers'][0]['heartbeatTime']
    assert status['releases'][0]['targetDigest'] == selected['digest']


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['stopped', 'expired'])
async def test_stopped_or_expired_host_reports_do_not_block_maintenance(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
    state: str,
) -> None:
    """验证已停止或过期宿主报告不阻止维护操作。"""
    now = TimezoneUtil.utc_now()
    async with deployment_sessions() as db:
        await PluginReleaseDao.upsert_worker_report(
            db,
            worker_id='2' * 32,
            plugin_id='__runtime__',
            state='stopped' if state == 'stopped' else 'ready',
            heartbeat_time=now
            if state == 'stopped'
            else now - timedelta(seconds=service.config.worker_ttl_seconds + 1),
        )
        await db.commit()
    result = await import_prepare_select(service, deployment_archive)
    assert result['ok']


@pytest.mark.asyncio
async def test_generation_conflict_and_audit_failure_cannot_commit_target_change(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证代际冲突和审计失败均不能提交目标变更。"""
    imported = await service.catalog.import_artifact(deployment_archive)
    prepared = await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)
    with pytest.raises(PluginReleaseConflictError):
        await service.select(PLUGIN_ID, imported['digest'], maintenance=True, expected_generation='f' * 32)

    async def failed_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError('audit transaction failed')

    monkeypatch.setattr(service, '_audit', failed_audit)
    with pytest.raises(RuntimeError, match='audit transaction failed'):
        await service.select(
            PLUGIN_ID, imported['digest'], maintenance=True, expected_generation=prepared['generation']
        )
    async with deployment_sessions() as db:
        row = await db.get(SysPluginRelease, PLUGIN_ID)
        assert row.target_digest is None and row.generation == prepared['generation']
        assert row.prepared_digest == imported['digest']


@pytest.mark.asyncio
async def test_rollback_resource_and_target_changes_share_a_transaction(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_source: Path,
    deployment_key: Ed25519PrivateKey,
    deployment_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证回滚时声明资源与代码目标在同一事务中更新。"""
    first = await import_prepare_select(service, deployment_archive)
    upgrade = new_archive(deployment_source, tmp_path / 'upgrade.rpk', deployment_key, '2.0.0')
    second = await import_prepare_select(service, upgrade)

    async def failed_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError('rollback audit failed')

    monkeypatch.setattr(service, '_audit', failed_audit)
    with pytest.raises(RuntimeError, match='rollback audit failed'):
        await service.rollback(
            PLUGIN_ID, expected_generation=second['generation'], maintenance=True, schema_compatible=True
        )
    async with deployment_sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        row = await db.get(SysPluginRelease, PLUGIN_ID)
        assert plugin.version == plugin.installed_version == '2.0.0'
        assert row.generation == second['generation']
        assert row.target_digest == second['digest'] and row.previous_digest == first['digest']
        assert row.prepared_digest == second['digest']


@pytest.mark.asyncio
async def test_already_loaded_namespace_cannot_prepare_another_artifact(
    service: PluginDeploymentService,
    deployment_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证已加载插件命名空间的进程不能准备其他制品。"""
    imported = await service.catalog.import_artifact(deployment_archive)
    monkeypatch.setitem(sys.modules, 'plugins.artifact_demo.old_module', object())
    with pytest.raises(ValueError, match='已加载插件模块'):
        await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)


@pytest.mark.asyncio
async def test_lifecycle_lock_denial_is_not_bypassed(
    service: PluginDeploymentService, deployment_archive: Path
) -> None:
    """验证无法取得生命周期锁时不执行维护操作。"""

    class DeniedLock:
        @asynccontextmanager
        async def lock(self, plugin_id: str, operation: str) -> AsyncGenerator[PluginLifecycleLockResult, None]:
            yield PluginLifecycleLockResult(False, 'maintenance already running')

    imported = await service.catalog.import_artifact(deployment_archive)
    service.lifecycle_lock = DeniedLock()
    with pytest.raises(ValueError, match='maintenance already running'):
        await service.prepare(PLUGIN_ID, imported['digest'], maintenance=True)


@pytest.mark.asyncio
async def test_real_maintenance_runtime_prepares_minimal_signed_artifact_in_sqlite(
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证真实维护网关完成资源同步、安装状态和审计写入且不导入插件模块。"""
    monkeypatch.setattr(DataSourceRegistry, 'session', staticmethod(deployment_sessions))
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    actual = PluginDeploymentService(
        deployment_config,
        session_factory=deployment_sessions,
        lifecycle_lock=NoopPluginLifecycleLock(),
    )
    imported = await actual.catalog.import_artifact(deployment_archive)
    planned = await actual.plan(PLUGIN_ID, imported['digest'])
    assert planned['ok'], planned
    async with deployment_sessions() as db:
        assert await db.get(SysPlugin, PLUGIN_ID) is None
        assert await db.get(SysPluginRelease, PLUGIN_ID) is None
    prepared = await actual.prepare(PLUGIN_ID, imported['digest'], maintenance=True, actor='smoke-test')
    assert prepared['ok']
    async with deployment_sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        release = await db.get(SysPluginRelease, PLUGIN_ID)
        assert plugin.installed_version == '1.0.0'
        assert plugin.source == 'artifact'
        assert plugin.backend_path == f'artifact:{imported["digest"]}'
        assert release.prepare_status == 'prepared'
        assert release.prepared_digest == imported['digest']
        assert release.target_digest is None
        logs = (await db.scalars(select(SysPluginOperationLog))).all()
        assert len(logs) == 1 and logs[0].operation == 'install'
    assert 'plugins.artifact_demo' not in sys.modules
    assert not list(deployment_config.store_root.rglob('*.pyc'))
    assert (await actual.catalog.get(imported['digest'])).digest == imported['digest']


@pytest.mark.asyncio
async def test_status_reports_disabled_only_after_worker_confirms_current_generation(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证进程确认当前代际停止后才显示已停用状态。"""
    selected = await import_prepare_select(service, deployment_archive)
    async with deployment_sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        plugin.enabled = '1'
        await PluginReleaseDao.upsert_worker_report(
            db,
            worker_id='d' * 32,
            plugin_id='__runtime__',
            state='ready',
            heartbeat_time=TimezoneUtil.utc_now(),
        )
        await db.commit()
    pending = (await service.status(PLUGIN_ID))['releases'][0]
    assert not pending['enabled']
    assert pending['status'] == 'pending_restart' and pending['restartRequired']
    async with deployment_sessions() as db:
        await PluginReleaseDao.upsert_worker_report(
            db,
            worker_id='d' * 32,
            plugin_id=PLUGIN_ID,
            state='stopped',
            heartbeat_time=TimezoneUtil.utc_now(),
            artifact_digest=selected['digest'],
            version=selected['version'],
            generation=selected['generation'],
        )
        await db.commit()
    confirmed = (await service.status(PLUGIN_ID))['releases'][0]
    assert confirmed['status'] == 'disabled'
    assert confirmed['disabledWorkers'] == 1
    assert not confirmed['restartRequired']


@pytest.mark.asyncio
async def test_wait_assertion_uses_existing_release_reports_without_database_writes(
    service: PluginDeploymentService,
    deployment_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """完整服务通过真实查询验收固定代际，期间不写发布、worker 或审计记录。"""
    selected = await import_prepare_select(service, deployment_archive)
    async with deployment_sessions() as db:
        for plugin_id in ('__runtime__', PLUGIN_ID):
            await PluginReleaseDao.upsert_worker_report(
                db,
                worker_id='d' * 32,
                plugin_id=plugin_id,
                state='ready',
                heartbeat_time=TimezoneUtil.utc_now(),
                artifact_digest=selected['digest'] if plugin_id == PLUGIN_ID else None,
                generation=selected['generation'] if plugin_id == PLUGIN_ID else None,
                version=selected['version'] if plugin_id == PLUGIN_ID else None,
            )
        await db.commit()
    statements = []
    engine = deployment_sessions.kw['bind'].sync_engine

    def record_statement(
        connection: object, cursor: object, statement: str, parameters: object, context: object, executemany: bool
    ) -> None:
        """记录验收阶段 SQL，不修改当前数据库连接。"""
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', record_statement)
    try:
        result = await service.wait(
            PLUGIN_ID,
            selected['digest'],
            expected_generation=selected['generation'],
            expected_workers=1,
            timeout_seconds=0,
        )
    finally:
        event.remove(engine, 'before_cursor_execute', record_statement)
    assert result['reason'] == 'converged' and result['ok'] is True
    assert statements and all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
