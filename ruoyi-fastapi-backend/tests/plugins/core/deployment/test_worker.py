import asyncio
import base64
import json
import multiprocessing
import os
import shutil
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.database import Base
from plugins.core.artifacts import build_artifact
from plugins.core.deployment.catalog import PluginArtifactCatalog
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.service import PluginDeploymentService
from plugins.core.deployment.state import aggregate_release
from plugins.core.deployment.worker import PluginReleaseWorker
from plugins.core.discovery.registry import PluginRegistry
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.dao.release_dao import PluginReleaseDao
from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker
from plugins.core.runtime.application import PluginApplicationRuntime
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder
from plugins.core.runtime.explicit import ExplicitPluginRuntime
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from utils.time_util import TimezoneUtil


@pytest_asyncio.fixture
async def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    """构造真实签名目录与临时 SQLite 发布数据库。"""
    backend = tmp_path / 'backend'
    (backend / 'plugins').mkdir(parents=True)
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    trust = tmp_path / 'trusted.json'
    trust.write_text(
        json.dumps(
            {'schemaVersion': 1, 'keys': [{'keyId': 'test', 'publicKey': public, 'pluginIds': ['release_demo']}]}
        ),
        encoding='utf-8',
    )
    config = PluginDeploymentConfig(backend, tmp_path / 'store', trust, heartbeat_seconds=1, worker_ttl_seconds=6)
    database = tmp_path / 'workers.sqlite'
    engine = create_async_engine(f'sqlite+aiosqlite:///{database}')
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                SysPlugin.__table__,
                SysPluginArtifact.__table__,
                SysPluginRelease.__table__,
                SysPluginWorker.__table__,
            ],
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    try:
        yield SimpleNamespace(config=config, sessions=sessions, key=key, root=tmp_path, database=database)
    finally:
        for name in list(sys.modules):
            if name == 'plugins.release_demo' or name.startswith('plugins.release_demo.'):
                sys.modules.pop(name)
        await engine.dispose()


async def publish(deployment: SimpleNamespace, version: str = '1.0.0', *, fail: bool = False) -> str:
    """登记指定版本制品并建立测试需要的目标发布记录。"""
    source = deployment.root / f'source-{version}' / 'release_demo'
    source.mkdir(parents=True)
    (source / 'plugin.yaml').write_text(
        f'manifestVersion: 2\nid: release_demo\nname: Release test\nversion: {version}\n'
        'backend:\n  runtime: python\n  integration: asgi\n  module: plugins.release_demo\n'
        '  entrypoint: plugins.release_demo:create_plugin\n'
        'frontend:\n  delivery:\n    type: none\n',
        encoding='utf-8',
    )
    (source / '__init__.py').write_text(
        'from contextlib import asynccontextmanager\n'
        'from fastapi import FastAPI\n'
        'from plugins.core.sdk import PluginDefinition\n'
        f'LOADED_VERSION = {version!r}\n'
        'def create_plugin(host):\n'
        '    assert not host.startup_write_enabled\n'
        '    return PluginDefinition(app_factory=create_app)\n'
        'def create_app(host):\n'
        '    @asynccontextmanager\n'
        '    async def lifespan(app):\n'
        + ('        raise RuntimeError("broken lifespan")\n' if fail else '')
        + '        yield\n'
        '    return FastAPI(lifespan=lifespan)\n',
        encoding='utf-8',
    )
    package = deployment.root / f'v{version}.rpk'
    build_artifact(source, package, deployment.key, 'test')
    catalog = PluginArtifactCatalog(deployment.config, session_factory=deployment.sessions)
    result = await catalog.import_artifact(package)
    async with deployment.sessions() as db:
        plugin = await PluginDao.get_plugin_by_id(db, 'release_demo')
        if plugin is None:
            db.add(
                SysPlugin(
                    plugin_id='release_demo',
                    plugin_name='Release',
                    version=version,
                    installed_version=version,
                    source='artifact',
                    status='installed',
                    enabled='0',
                )
            )
        else:
            plugin.version = plugin.installed_version = version
        await db.flush()
        release = await PluginReleaseDao.set_preparation_status(
            db, 'release_demo', status='prepared', prepared_digest=result['digest'], prepared_version=version
        )
        await PluginReleaseDao.select_target(
            db,
            'release_demo',
            target_digest=result['digest'],
            expected_generation=release.generation,
            expected_workers=2,
        )
        await db.commit()
    return result['digest']


async def activate_worker(config: PluginDeploymentConfig, sessions: Any) -> tuple[Any, Any]:
    """创建进程发布快照并实际准备和激活插件入口。"""
    app = FastAPI()
    builder = PluginRuntimeBuilder(config.backend_root)
    app.state.plugin_runtime_builder = builder
    worker = PluginReleaseWorker(config, session_factory=sessions)
    await worker.start(app, builder, NoopPluginLifecycleLock())
    async with sessions() as db:
        registry = PluginRegistry.build(builder.discover_plugins(), await PluginDao.get_plugin_list(db))
    app.state.plugin_registry = registry
    runtime = ExplicitPluginRuntime(SimpleNamespace())
    app.state.plugin_explicit_runtime = runtime
    for plugin in registry.list_enabled_plugins():
        runtime.prepare(plugin, app, startup_write_enabled=True)
        try:
            await runtime.activate(plugin.plugin_id, app)
        except RuntimeError:
            pass
    await worker.ready()
    return worker, runtime


async def summary(deployment: SimpleNamespace, plugin_id: str = 'release_demo') -> dict[str, Any]:
    """读取发布记录和宿主报告并汇总当前集群状态。"""
    async with deployment.sessions() as db:
        release = await PluginReleaseDao.get_release(db, plugin_id)
        reports = await PluginReleaseDao.list_worker_reports(db)
        return aggregate_release(release, reports, now=TimezoneUtil.utc_now(), ttl_seconds=6).to_payload()


@pytest.mark.asyncio
async def test_real_entrypoint_ready_reports_and_shutdown(deployment: SimpleNamespace) -> None:
    """验证真实入口激活、就绪上报和关闭后的状态变化。"""
    digest = await publish(deployment)
    worker, runtime = await activate_worker(deployment.config, deployment.sessions)
    try:
        state = await summary(deployment)
        assert state['status'] == 'partial'
        assert state['healthyWorkers'] == 1
        assert sys.modules['plugins.release_demo'].LOADED_VERSION == '1.0.0'
        assert worker.targets[0].digest == digest
        await worker.catalog.get(digest)  # 导入入口和 lifespan 后不可变目录仍逐字节匹配。
        assert not list(deployment.config.store_root.rglob('__pycache__'))
    finally:
        await runtime.shutdown()
        await worker.stop()
    assert (await summary(deployment))['status'] == 'pending_restart'


@pytest.mark.asyncio
async def test_failed_lifespan_never_reports_ready(deployment: SimpleNamespace) -> None:
    """验证应用生命周期失败不会被上报为插件就绪。"""
    await publish(deployment, fail=True)
    worker, runtime = await activate_worker(deployment.config, deployment.sessions)
    try:
        state = await summary(deployment)
        assert state['status'] == 'failed'
        assert state['failedWorkers'] == 1
        assert state['healthyWorkers'] == 0
    finally:
        await runtime.shutdown()
        await worker.stop()


@pytest.mark.asyncio
async def test_missing_preparation_and_source_conflict_never_fall_back(deployment: SimpleNamespace) -> None:
    """验证准备证据缺失或源码冲突时不会回退加载源码插件。"""
    await publish(deployment)
    async with deployment.sessions() as db:
        await PluginReleaseDao.set_preparation_status(db, 'release_demo', status='failed', last_error='failed prepare')
        await db.commit()
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    builder = PluginRuntimeBuilder(deployment.config.backend_root)
    app = FastAPI()
    try:
        await worker.start(app, builder, NoopPluginLifecycleLock())
        assert builder.discover_plugins() == []
        assert '维护准备' in worker.errors['release_demo']
        assert 'plugins.release_demo' not in sys.modules
        await worker.ready()
        assert (await summary(deployment))['status'] == 'failed'
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_tampered_selected_artifact_is_isolated(deployment: SimpleNamespace) -> None:
    """验证已选择制品被篡改后会被隔离而不导入。"""
    digest = await publish(deployment)
    catalog = PluginArtifactCatalog(deployment.config, session_factory=deployment.sessions)
    artifact = await catalog.get(digest)
    (artifact.plugin_path / '__init__.py').write_text('raise RuntimeError("must not execute")', encoding='utf-8')
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    builder = PluginRuntimeBuilder(deployment.config.backend_root)
    try:
        await worker.start(FastAPI(), builder, NoopPluginLifecycleLock())
        assert builder.discover_plugins() == []
        assert worker.errors['release_demo']
        assert 'plugins.release_demo' not in sys.modules
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_imported_unselected_id_cannot_fall_back_to_a_source_directory(deployment: SimpleNamespace) -> None:
    """验证已导入但未选目标的插件ID不能回退到同名源码目录。"""
    await publish(deployment)
    async with deployment.sessions() as db:
        release = await PluginReleaseDao.get_release(db, 'release_demo')
        release.target_digest = None
        await db.commit()
    shutil.copytree(
        deployment.root / 'source-1.0.0' / 'release_demo', deployment.config.backend_root / 'plugins' / 'release_demo'
    )
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    builder = PluginRuntimeBuilder(deployment.config.backend_root)
    try:
        await worker.start(FastAPI(), builder, NoopPluginLifecycleLock())
        assert not worker.targets
        assert builder.discover_plugins() == []
        assert any('同时存在' in item.error_message for item in builder.discovery_errors)
        assert 'plugins.release_demo' not in sys.modules
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_disabled_snapshot_reports_stopped_without_executing_entrypoint(deployment: SimpleNamespace) -> None:
    """验证停用快照只报告停止状态且不执行入口。"""
    await publish(deployment)
    async with deployment.sessions() as db:
        plugin = await PluginDao.get_plugin_by_id(db, 'release_demo')
        plugin.enabled = '1'
        release = await PluginReleaseDao.get_release(db, 'release_demo')
        release.expected_workers = 1
        await db.commit()
    worker, runtime = await activate_worker(deployment.config, deployment.sessions)
    try:
        assert 'plugins.release_demo' not in sys.modules
        status = await PluginDeploymentService(deployment.config, session_factory=deployment.sessions).status(
            'release_demo'
        )
        assert status['releases'][0]['status'] == 'disabled'
        assert status['releases'][0]['disabledWorkers'] == 1
        assert not status['releases'][0]['restartRequired']
    finally:
        await runtime.shutdown()
        await worker.stop()


@pytest.mark.asyncio
async def test_snapshot_change_rejected_and_barrier_generation_changes(deployment: SimpleNamespace) -> None:
    """验证发布快照变化被拒绝且启动屏障代际随目标变化。"""
    await publish(deployment)
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    try:
        await worker.start(FastAPI(), PluginRuntimeBuilder(deployment.config.backend_root), NoopPluginLifecycleLock())
        before = worker.generation('fixed-app-release')
        await publish(deployment, '2.0.0')
        with pytest.raises(RuntimeError, match='变化'):
            await worker.assert_snapshot_current()
        second = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
        try:
            await second.start(
                FastAPI(), PluginRuntimeBuilder(deployment.config.backend_root), NoopPluginLifecycleLock()
            )
            assert second.generation('fixed-app-release') != before
        finally:
            await second.stop()
    finally:
        await worker.stop()


@pytest.mark.asyncio
async def test_starting_host_blocks_maintenance_even_without_targets(deployment: SimpleNamespace) -> None:
    """验证没有插件目标的启动中宿主仍会阻止维护。"""
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    service = PluginDeploymentService(deployment.config, session_factory=deployment.sessions)
    try:
        await worker.start(FastAPI(), PluginRuntimeBuilder(deployment.config.backend_root), NoopPluginLifecycleLock())
        with pytest.raises(ValueError, match='存活'):
            await service._require_quiescent()
    finally:
        await worker.stop()
    await service._require_quiescent()


@pytest.mark.asyncio
async def test_heartbeat_refreshes_actual_snapshot_and_failed_host_is_not_active(deployment: SimpleNamespace) -> None:
    """验证心跳刷新实际快照且失败宿主不能形成 active 状态。"""
    await publish(deployment)
    worker, runtime = await activate_worker(deployment.config, deployment.sessions)
    try:
        await asyncio.sleep(1.1)
        assert worker.task is not None and not worker.task.done()
        await worker.stop(failed=True)
        assert (await summary(deployment))['status'] == 'failed'
    finally:
        await runtime.shutdown()
        await worker.stop()


@pytest.mark.asyncio
async def test_real_application_startup_does_not_run_artifact_install_or_resource_writes(
    deployment: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证真实应用启动不会再次执行制品安装或全局资源写入。"""
    await publish(deployment)
    monkeypatch.setattr('config.database.DataSourceRegistry.session', deployment.sessions)

    class ReadOnlyGateway:
        list_plugins = staticmethod(PluginDao.get_plugin_list)
        install_plugin_resources = AsyncMock(
            side_effect=AssertionError('startup must not reinstall artifact resources')
        )
        upsert_discovered_plugin = AsyncMock(side_effect=AssertionError('startup must not install artifacts'))

    gateway = ReadOnlyGateway()
    builder = PluginRuntimeBuilder(deployment.config.backend_root)
    manager = PluginRuntimeStartupManager(
        builder,
        management_gateway=gateway,
        route_state_gateway=SimpleNamespace(),
        default_enabled_builtin_plugin_ids={'release_demo'},
    )
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    runtime = PluginApplicationRuntime(manager, release_worker=worker, startup_generation='app-release')
    app = FastAPI()
    app.state.redis = SimpleNamespace(get=AsyncMock(return_value=None), set=AsyncMock(), delete=AsyncMock())
    create_tables = AsyncMock()
    try:
        await runtime.startup(app, create_tables=create_tables)
        assert app.state.plugin_startup_generation != 'app-release'
        assert app.state.plugin_release_worker is worker
        assert app.state.plugin_explicit_runtime.loaded['release_demo'].active
        gateway.upsert_discovered_plugin.assert_not_awaited()
        gateway.install_plugin_resources.assert_not_awaited()
        assert (await summary(deployment))['healthyWorkers'] == 1
        assert not await manager.requires_startup_write()
    finally:
        await runtime.shutdown(app)


@pytest.mark.asyncio
async def test_worker_failure_does_not_mark_global_plugin_error(deployment: SimpleNamespace) -> None:
    """验证单个进程失败不会覆盖插件的全局安装状态。"""
    await publish(deployment)
    worker, runtime = await activate_worker(deployment.config, deployment.sessions)
    app = worker.app
    app.state.plugin_release_worker = worker
    gateway = SimpleNamespace(mark_plugin_error=AsyncMock(side_effect=AssertionError('must remain per-worker')))
    manager = PluginRuntimeStartupManager(management_gateway=gateway)
    try:
        await manager.mark_plugin_runtime_error(app, 'release_demo', 'one worker failed')
        await worker.report()
        assert (await summary(deployment))['status'] == 'failed'
        async with deployment.sessions() as db:
            plugin = await PluginDao.get_plugin_by_id(db, 'release_demo')
            assert plugin.status == 'installed'
            assert plugin.enabled == '0'
    finally:
        await runtime.shutdown()
        await worker.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_mode', ['writer', 'reader'])
async def test_failed_artifact_stays_disabled_after_source_failure_reloads_registry(
    deployment: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, failure_mode: str
) -> None:
    """验证源码失败触发注册表重载后，失败制品仍保持禁用。"""
    await publish(deployment)
    monkeypatch.setattr('config.database.DataSourceRegistry.session', deployment.sessions)
    builder = PluginRuntimeBuilder(deployment.config.backend_root)
    gateway = SimpleNamespace(
        list_plugins=PluginDao.get_plugin_list,
        mark_plugin_error=AsyncMock(return_value=SimpleNamespace(is_success=True)),
    )
    manager = PluginRuntimeStartupManager(builder, management_gateway=gateway)
    app = FastAPI()
    worker = PluginReleaseWorker(deployment.config, session_factory=deployment.sessions)
    if failure_mode == 'writer':
        app.state.plugin_release_worker = worker
    run_hook = AsyncMock()
    monkeypatch.setattr(manager, 'run_single_plugin_hook', run_hook)
    try:
        await worker.start(app, builder, NoopPluginLifecycleLock())
        await manager.load_registry_from_database(app)
        assert app.state.plugin_registry.get_plugin('release_demo').enabled

        if failure_mode == 'writer':
            await manager.mark_plugin_runtime_error(app, 'release_demo', 'entrypoint preparation failed')
            assert worker.errors['release_demo'] == 'entrypoint preparation failed'
        else:
            manager.disable_runtime_plugins(app, {'release_demo'})
            assert not hasattr(app.state, 'plugin_release_worker')
        assert not app.state.plugin_registry.get_plugin('release_demo').enabled
        failed_registry = app.state.plugin_registry

        await manager.mark_plugin_runtime_error(app, 'source_demo', 'source entity import failed')
        assert app.state.plugin_registry is not failed_registry
        assert not app.state.plugin_registry.get_plugin('release_demo').enabled
        gateway.mark_plugin_error.assert_awaited_once()
        assert gateway.mark_plugin_error.await_args.args[1] == 'source_demo'

        await manager.run_enabled_plugin_hooks(app, 'on_startup')
        run_hook.assert_not_awaited()
    finally:
        await worker.stop()


def _run_process(config: PluginDeploymentConfig, database: str, ready: Any, stop: Any) -> None:
    """在独立进程中实际激活制品并报告加载路径和版本。"""

    async def run() -> None:
        engine = create_async_engine(f'sqlite+aiosqlite:///{database}')
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        worker = runtime = None
        try:
            worker, runtime = await activate_worker(config, sessions)
            target = worker.targets[0]
            loaded = runtime.loaded[target.plugin_id]
            module_name = loaded.plugin.discovered_plugin.manifest.backend.entrypoint.split(':')[0]
            module = sys.modules[module_name]
            ready.put(
                {
                    'workerId': worker.worker_id,
                    'version': getattr(module, 'LOADED_VERSION', worker.versions[target.plugin_id]),
                    'modulePath': module.__file__,
                    'active': loaded.active,
                }
            )
            await asyncio.to_thread(stop.wait, 45)
        except BaseException as exc:
            ready.put({'error': repr(exc)})
            raise
        finally:
            if runtime:
                await runtime.shutdown()
            if worker:
                await worker.stop()
            await engine.dispose()

    asyncio.run(run())


@asynccontextmanager
async def running_processes(deployment: SimpleNamespace, count: int = 1) -> AsyncGenerator[list[dict[str, Any]], None]:
    """启动指定数量的独立测试进程并在退出时完整回收。"""
    context = multiprocessing.get_context('spawn')
    ready = context.Queue()
    stop = context.Event()
    processes = [
        context.Process(target=_run_process, args=(deployment.config, str(deployment.database), ready, stop))
        for _ in range(count)
    ]
    try:
        for process in processes:
            process.start()
        reports = [await asyncio.to_thread(ready.get, True, 30) for _ in processes]
        yield reports
    finally:
        stop.set()
        for process in processes:
            await asyncio.to_thread(process.join, 15)
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 5)
        ready.close()
        ready.join_thread()
    assert all(process.exitcode == 0 for process in processes)


@pytest.mark.asyncio
async def test_two_spawned_processes_load_only_target_and_converge(deployment: SimpleNamespace) -> None:
    """验证两个独立进程只加载目标制品并汇总为就绪。"""
    await publish(deployment)
    expected_worker_count = 2
    async with running_processes(deployment, expected_worker_count) as reports:
        assert all(item.get('version') == '1.0.0' for item in reports), reports
        assert reports[0]['workerId'] != reports[1]['workerId']
        state = await summary(deployment)
        assert state['status'] == 'active'
        assert state['healthyWorkers'] == state['liveWorkers'] == expected_worker_count
    assert (await summary(deployment))['status'] == 'pending_restart'


@pytest.mark.asyncio
async def test_restarted_process_loads_upgrade_then_rollback_without_downgrading_schema(
    deployment: SimpleNamespace,
) -> None:
    """验证新进程加载升级及回滚代码时不倒退数据结构安装版本。"""
    first = await publish(deployment)
    async with running_processes(deployment) as reports:
        assert reports[0]['version'] == '1.0.0'
        await publish(deployment, '2.0.0')  # 模拟绕过维护守卫的外部目标变化，旧进程不能冒充新版本。
        state = await summary(deployment)
        assert state['mismatchWorkers'] == 1
        assert state['healthyWorkers'] == 0
    async with running_processes(deployment) as reports:
        assert reports[0]['version'] == '2.0.0'
    async with deployment.sessions() as db:
        release = await PluginReleaseDao.get_release(db, 'release_demo')
        generation = release.generation
        await PluginReleaseDao.set_preparation_status(
            db,
            'release_demo',
            status='prepared',
            prepared_digest=first,
            prepared_version='2.0.0',
            expected_generation=generation,
        )
        await PluginReleaseDao.select_target(
            db,
            'release_demo',
            target_digest=first,
            expected_generation=generation,
            expected_workers=1,
        )
        await db.commit()
    async with running_processes(deployment) as reports:
        assert reports[0]['version'] == '1.0.0'
        assert (await summary(deployment))['status'] == 'active'
    async with deployment.sessions() as db:
        assert (await PluginDao.get_plugin_by_id(db, 'release_demo')).installed_version == '2.0.0'


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get('RUOYI_NATIVE_PLUGIN_DIR'), reason='需要预先构建的真实 Rust 制品')
async def test_signed_native_artifact_loads_from_store_in_clean_process(deployment: SimpleNamespace) -> None:
    """验证干净进程从不可变存储实际加载签名原生制品。"""
    trust = json.loads(deployment.config.trust_file.read_text(encoding='utf-8'))
    trust['keys'][0]['pluginIds'] = ['rust_demo']
    deployment.config.trust_file.write_text(json.dumps(trust), encoding='utf-8')
    package = deployment.root / 'rust.rpk'
    build_artifact(Path(os.environ['RUOYI_NATIVE_PLUGIN_DIR']), package, deployment.key, 'test')
    catalog = PluginArtifactCatalog(deployment.config, session_factory=deployment.sessions)
    result = await catalog.import_artifact(package)
    async with deployment.sessions() as db:
        db.add(
            SysPlugin(
                plugin_id='rust_demo',
                plugin_name='Rust',
                version=result['version'],
                installed_version=result['version'],
                status='installed',
                source='artifact',
                enabled='0',
            )
        )
        await db.flush()
        release = await PluginReleaseDao.set_preparation_status(
            db,
            'rust_demo',
            status='prepared',
            prepared_digest=result['digest'],
            prepared_version=result['version'],
        )
        await PluginReleaseDao.select_target(
            db,
            'rust_demo',
            target_digest=result['digest'],
            expected_generation=release.generation,
        )
        await db.commit()
    async with running_processes(deployment) as reports:
        assert reports[0].get('active'), reports
        native_path = Path(reports[0]['modulePath'])
        assert native_path.is_relative_to(deployment.config.store_root)
        assert native_path.suffix in {'.pyd', '.so'}
        assert (await summary(deployment, 'rust_demo'))['status'] == 'active'
    await catalog.get(result['digest'])
