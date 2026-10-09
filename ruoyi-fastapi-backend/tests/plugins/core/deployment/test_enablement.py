import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.menu_do import SysMenu
from plugins.core.artifacts import build_artifact
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.enablement import PluginArtifactEnablementService
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.management.dao.release_dao import PluginReleaseConflictError, PluginReleaseDao
from plugins.core.management.entity.do.models import SysPlugin, SysPluginMenu, SysPluginOperationLog
from plugins.core.management.entity.do.release_models import SysPluginRelease
from plugins.core.runtime.job_dispatcher import DISPATCH_TARGET
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock
from tests.plugins.core.deployment.test_service import (
    PLUGIN_ID,
    MaintenanceFactory,
    MaintenanceRuntime,
    import_prepare_select,
    new_archive,
)
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

PLUGIN_MENU_ID = 101
OTHER_MENU_ID = 102
FIRST_JOB_ID = 201


class EnablementRuntime(MaintenanceRuntime):
    """模拟启停预检结果及并发状态变化的维护运行时。"""

    async def set_plugin_enabled(self, plugin_id: str, *, enabled: bool, dry_run: bool) -> dict[str, Any]:
        """返回测试指定的启停预检结果。"""
        owner: EnablementFactory = self.owner
        owner.checks.append((plugin_id, enabled, dry_run))
        if owner.before_check is not None:
            await owner.before_check()
        return {'ok': not owner.reject, 'message': 'injected dependency rejection'}


class EnablementFactory(MaintenanceFactory):
    """记录启停运行时创建信息的测试工厂。"""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        """初始化预检结果与回调记录。"""
        super().__init__(sessions)
        self.checks: list[tuple[str, bool, bool]] = []
        self.before_check: Callable[[], Awaitable[None]] | None = None
        self.reject = False

    def __call__(self, config: PluginDeploymentConfig, plugins: list[DiscoveredPlugin]) -> EnablementRuntime:
        """根据测试配置创建启停维护运行时。"""
        return EnablementRuntime(self, plugins)


@pytest.fixture
def enablement_factory(deployment_sessions: async_sessionmaker[AsyncSession]) -> EnablementFactory:
    """提供可注入预检行为的维护运行时工厂。"""
    return EnablementFactory(deployment_sessions)


@pytest.fixture
def enablement_service(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    enablement_factory: EnablementFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> PluginArtifactEnablementService:
    """创建使用临时数据库和测试维护运行时的启停服务。"""
    monkeypatch.setattr(sys, 'dont_write_bytecode', sys.dont_write_bytecode)
    return PluginArtifactEnablementService(
        deployment_config,
        session_factory=deployment_sessions,
        lifecycle_lock=NoopPluginLifecycleLock(),
        runtime_factory=enablement_factory,
    )


@pytest.fixture
def resource_archive(deployment_source: Path, deployment_key: Ed25519PrivateKey, tmp_path: Path) -> Path:
    """构建带菜单与任务声明的签名测试制品。"""
    manifest = yaml.safe_load((deployment_source / 'plugin.yaml').read_text(encoding='utf-8'))
    manifest['backend']['jobs'] = [
        {
            'id': job_id,
            'name': job_id,
            'callable': f'plugins.{PLUGIN_ID}.{job_id}',
            'cronExpression': '0 */5 * * * ?',
            'enabled': enabled,
        }
        for job_id, enabled in [('heartbeat', True), ('dormant', False)]
    ]
    (deployment_source / 'plugin.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    archive = tmp_path / 'resources.rpk'
    build_artifact(deployment_source, archive, deployment_key, 'publisher')
    return archive


async def _seed_resources(sessions: async_sessionmaker[AsyncSession], *, disabled: bool = False) -> None:
    """在临时数据库中写入启停测试需要的声明资源。"""
    status = '1' if disabled else '0'
    async with sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        plugin.enabled = status
        db.add(SysMenu(menu_id=PLUGIN_MENU_ID, menu_name='Owned menu', status=status))
        db.add(SysMenu(menu_id=OTHER_MENU_ID, menu_name='Unrelated menu', status='0'))
        db.add(SysPluginMenu(plugin_id=PLUGIN_ID, menu_id=PLUGIN_MENU_ID, menu_key='owned-menu'))
        for index, (job_id, job_status, remark) in enumerate(
            [
                ('heartbeat', status, f'[plugin-job] {PLUGIN_ID}:heartbeat Declared task'),
                ('dormant', '1', f'[plugin-job] {PLUGIN_ID}:dormant Disabled declaration'),
                ('manual', '0', 'A user task sharing the prefix'),
            ],
            start=FIRST_JOB_ID,
        ):
            db.add(
                SysJob(
                    job_id=index,
                    job_name=f'{PLUGIN_ID}:{job_id}',
                    job_group='default',
                    invoke_target=DISPATCH_TARGET,
                    job_args=[PLUGIN_ID, job_id, plugin.installed_version],
                    job_kwargs={},
                    cron_expression='0 */5 * * * ?',
                    time_zone='Asia/Shanghai',
                    status=job_status,
                    remark=remark,
                )
            )
        await db.commit()


@pytest_asyncio.fixture
async def selected_release(
    enablement_service: PluginArtifactEnablementService,
    resource_archive: Path,
    deployment_sessions: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    """准备已完成维护且已选择目标的发布记录。"""
    selected = await import_prepare_select(enablement_service, resource_archive)
    await _seed_resources(deployment_sessions)
    return selected


async def _snapshot(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """读取发布状态、插件状态及声明资源的完整比较快照。"""
    async with sessions() as db:
        plugin = await db.get(SysPlugin, PLUGIN_ID)
        release = await db.get(SysPluginRelease, PLUGIN_ID)
        return {
            'plugin': (plugin.enabled, plugin.status, plugin.version, plugin.installed_version),
            'release': (
                release.generation,
                release.target_digest,
                release.previous_digest,
                release.prepared_digest,
                release.prepared_version,
                release.prepare_status,
            ),
            'menus': dict((await db.execute(select(SysMenu.menu_id, SysMenu.status))).all()),
            'jobs': dict((await db.execute(select(SysJob.job_name, SysJob.status))).all()),
            'audit': (
                await db.execute(select(SysPluginOperationLog.operation_id, SysPluginOperationLog.operation))
            ).all(),
        }


@pytest.mark.asyncio
async def test_disable_and_enable_commit_resources_generation_and_preserve_previous_digest(
    enablement_service: PluginArtifactEnablementService,
    enablement_factory: EnablementFactory,
    resource_archive: Path,
    deployment_source: Path,
    deployment_key: Ed25519PrivateKey,
    deployment_sessions: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    """验证启停原子更新资源及代际，同时保留上一制品摘要。"""
    first = await import_prepare_select(enablement_service, resource_archive)
    upgraded = new_archive(deployment_source, tmp_path / 'upgrade.rpk', deployment_key, '2.0.0')
    second = await import_prepare_select(enablement_service, upgraded)
    await _seed_resources(deployment_sessions)

    disabled = await enablement_service.set_enabled(
        PLUGIN_ID, enabled=False, expected_generation=second['generation'], maintenance=True, actor='operator'
    )
    snapshot = await _snapshot(deployment_sessions)
    assert disabled['restartRequired'] and disabled['operation'] == 'release_disable'
    assert disabled['generation'] != second['generation']
    assert snapshot['plugin'] == ('1', 'installed', '2.0.0', '2.0.0')
    assert snapshot['menus'] == {PLUGIN_MENU_ID: '1', OTHER_MENU_ID: '0'}
    assert snapshot['jobs'] == {f'{PLUGIN_ID}:heartbeat': '1', f'{PLUGIN_ID}:dormant': '1', f'{PLUGIN_ID}:manual': '0'}

    enabled = await enablement_service.set_enabled(
        PLUGIN_ID, enabled=True, expected_generation=disabled['generation'], maintenance=True, actor='operator'
    )
    snapshot = await _snapshot(deployment_sessions)
    assert enabled['generation'] != disabled['generation']
    assert snapshot['plugin'] == ('0', 'installed', '2.0.0', '2.0.0')
    assert snapshot['release'] == (
        enabled['generation'],
        second['digest'],
        first['digest'],
        second['digest'],
        '2.0.0',
        'prepared',
    )
    assert snapshot['menus'] == {PLUGIN_MENU_ID: '0', OTHER_MENU_ID: '0'}
    assert snapshot['jobs'] == {f'{PLUGIN_ID}:heartbeat': '0', f'{PLUGIN_ID}:dormant': '1', f'{PLUGIN_ID}:manual': '0'}
    assert [operation for _, operation in snapshot['audit']][-2:] == ['release_disable', 'release_enable']
    assert enablement_factory.checks == [(PLUGIN_ID, False, True), (PLUGIN_ID, True, True)]
    assert f'plugins.{PLUGIN_ID}' not in sys.modules


@pytest.mark.asyncio
@pytest.mark.parametrize('gate', ['maintenance', 'live_worker', 'stale_generation', 'precheck'])
async def test_enablement_gates_preserve_all_resources_and_release_state(
    enablement_service: PluginArtifactEnablementService,
    enablement_factory: EnablementFactory,
    selected_release: dict[str, Any],
    deployment_sessions: async_sessionmaker[AsyncSession],
    gate: str,
) -> None:
    """验证维护门禁失败时资源和发布状态均保持原值。"""
    if gate == 'live_worker':
        async with deployment_sessions() as db:
            await PluginReleaseDao.upsert_worker_report(
                db,
                worker_id='a' * 32,
                plugin_id='__runtime__',
                state='ready',
                heartbeat_time=TimezoneUtil.utc_now(),
            )
            await db.commit()
    if gate == 'precheck':
        enablement_factory.reject = True
    before = await _snapshot(deployment_sessions)
    messages = {
        'maintenance': 'maintenance',
        'live_worker': '存活的宿主 worker',
        'stale_generation': '发布代际',
        'precheck': 'injected dependency rejection',
    }
    with pytest.raises(ValueError, match=messages[gate]):
        await enablement_service.set_enabled(
            PLUGIN_ID,
            enabled=False,
            expected_generation='f' * 32 if gate == 'stale_generation' else selected_release['generation'],
            maintenance=gate != 'maintenance',
        )
    assert await _snapshot(deployment_sessions) == before
    assert enablement_factory.checks == ([(PLUGIN_ID, False, True)] if gate == 'precheck' else [])


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_generation_plugin_menu_and_job_updates(
    enablement_service: PluginArtifactEnablementService,
    selected_release: dict[str, Any],
    deployment_sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证审计失败会回滚代际、插件、菜单及任务更新。"""
    before = await _snapshot(deployment_sessions)

    async def failed_audit(db: AsyncSession, payload: dict[str, Any], actor: str | None) -> None:
        assert (await db.get(SysPlugin, PLUGIN_ID)).enabled == '1'
        assert (await db.get(SysMenu, PLUGIN_MENU_ID)).status == '1'
        assert (await db.get(SysJob, FIRST_JOB_ID)).status == '1'
        assert (await db.get(SysPluginRelease, PLUGIN_ID)).generation == payload['generation']
        raise RuntimeError('audit unavailable')

    monkeypatch.setattr(enablement_service, '_audit', failed_audit)
    with pytest.raises(RuntimeError, match='audit unavailable'):
        await enablement_service.set_enabled(
            PLUGIN_ID, enabled=False, expected_generation=selected_release['generation'], maintenance=True
        )
    assert await _snapshot(deployment_sessions) == before


@pytest.mark.asyncio
async def test_job_ownership_failure_rolls_back_prior_menu_and_plugin_writes(
    enablement_service: PluginArtifactEnablementService,
    selected_release: dict[str, Any],
    deployment_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证任务归属冲突会回滚先前的菜单和插件写入。"""
    disabled = await enablement_service.set_enabled(
        PLUGIN_ID, enabled=False, expected_generation=selected_release['generation'], maintenance=True
    )
    async with deployment_sessions() as db:
        job = await db.get(SysJob, FIRST_JOB_ID)
        job.remark = 'Existing user-owned task must not be overwritten'
        await db.commit()
    before = await _snapshot(deployment_sessions)

    with pytest.raises(ValueError, match='非插件任务重名'):
        await enablement_service.set_enabled(
            PLUGIN_ID, enabled=True, expected_generation=disabled['generation'], maintenance=True
        )
    assert await _snapshot(deployment_sessions) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('changed_field', ['generation', 'target_digest', 'installed_version'])
async def test_precheck_race_cannot_apply_enablement_against_changed_preparation(
    enablement_service: PluginArtifactEnablementService,
    enablement_factory: EnablementFactory,
    selected_release: dict[str, Any],
    deployment_sessions: async_sessionmaker[AsyncSession],
    changed_field: str,
) -> None:
    """验证预检后的准备证据变化会阻止启停提交。"""
    after_concurrent_change: dict[str, Any] = {}

    async def concurrent_change() -> None:
        async with deployment_sessions() as db:
            if changed_field == 'installed_version':
                await db.execute(
                    update(SysPlugin).where(SysPlugin.plugin_id == PLUGIN_ID).values(installed_version='2.0.0')
                )
            else:
                value = 'f' * 32 if changed_field == 'generation' else None
                await db.execute(
                    update(SysPluginRelease)
                    .where(SysPluginRelease.plugin_id == PLUGIN_ID)
                    .values(**{changed_field: value})
                )
            await db.commit()
        after_concurrent_change.update(await _snapshot(deployment_sessions))

    enablement_factory.before_check = concurrent_change
    with pytest.raises(PluginReleaseConflictError):
        await enablement_service.set_enabled(
            PLUGIN_ID, enabled=False, expected_generation=selected_release['generation'], maintenance=True
        )
    assert await _snapshot(deployment_sessions) == after_concurrent_change
