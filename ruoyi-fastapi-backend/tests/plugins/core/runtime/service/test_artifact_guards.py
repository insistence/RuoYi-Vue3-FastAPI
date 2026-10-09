import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.core.validation.dependency_policy import DependencyInstallPolicyConfig
from tests.plugins.core.runtime.fakes import (
    FakePluginRuntimeGateway,
    FakePluginService,
    build_runtime_with_gateway,
    write_manifest,
)

EXPECTED_DATABASE_OPERATIONS = 2


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['install', 'upgrade', 'enable', 'disable', 'uninstall', 'purge'])
@pytest.mark.parametrize('dry_run', [False, True])
async def test_database_artifact_source_blocks_legacy_lifecycle_without_source_directory(
    tmp_path: Path, operation: str, dry_run: bool
) -> None:
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(plugin_id='demo', source='artifact')
    runtime = build_runtime_with_gateway(tmp_path / 'backend', gateway)
    if operation in {'enable', 'disable'}:
        payload = await runtime.set_plugin_enabled('demo', enabled=operation == 'enable', dry_run=dry_run)
    else:
        payload = await getattr(runtime, f'{operation}_plugin')('demo', dry_run=dry_run)
    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['operation'] == operation
    assert payload['capability']['runtimeManageable'] is False
    assert gateway.lifecycle_uows == []
    assert gateway.session_local.sessions == []
    assert FakePluginService.marked_errors == []
    assert FakePluginService.operation_logs == []
    assert FakePluginService.purge_by_id_called_with is None


@pytest.mark.asyncio
async def test_state_query_failure_cannot_authorize_orphan_purge(tmp_path: Path) -> None:
    class FailingGateway(FakePluginRuntimeGateway):
        async def get_plugin_state(self, plugin_id: str) -> None:
            raise RuntimeError('state database unavailable')

    gateway = FailingGateway()
    payload = await build_runtime_with_gateway(tmp_path / 'backend', gateway).purge_plugin('demo')
    assert payload['status'] == 'blocked'
    assert '无法确认插件来源' in payload['message']
    assert gateway.session_local.sessions == []


@pytest.mark.asyncio
async def test_config_read_resolves_selected_artifact_without_source_directory(tmp_path: Path) -> None:
    selected = object()

    class ArtifactGateway(FakePluginRuntimeGateway):
        async def get_selected_artifact_plugin(self, plugin_id: str, backend_root: Path) -> object:
            assert plugin_id == 'demo'
            assert backend_root == tmp_path / 'backend'
            return selected

        async def get_plugin_config(self, discovered_plugin: object, *, reveal_secret: bool = False) -> list:
            assert discovered_plugin is selected
            assert reveal_secret is False
            return []

        async def set_plugin_config(self, discovered_plugin: object, values: dict, **kwargs: object) -> list:
            assert discovered_plugin is selected
            assert values == {'provider': 'local'}
            return []

    FakePluginService.detail_plugin = SimpleNamespace(plugin_id='demo', source='artifact')
    runtime = build_runtime_with_gateway(tmp_path / 'backend', ArtifactGateway())
    result = await runtime.get_plugin_config('demo')
    assert result['ok'] is True
    assert result['configs'] == []
    result = await runtime.set_plugin_config('demo', {'provider': 'local'})
    assert result['ok'] is True


@pytest.mark.parametrize('method', ['install_plugin_dependencies', 'install_plugin_dependencies_from_cli'])
def test_artifact_source_blocks_dependency_install_even_when_same_id_source_exists(tmp_path: Path, method: str) -> None:
    backend = tmp_path / 'backend'
    write_manifest(
        backend / 'plugins' / 'demo',
        'id: demo\nname: Demo\nversion: 1.0.0\nbackend:\n  module: plugins.demo\n',
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.detail_plugin = SimpleNamespace(plugin_id='demo', source='artifact')
    payload = getattr(build_runtime_with_gateway(backend, gateway), method)('demo', confirmed=True)
    assert payload['status'] == 'blocked'
    assert '签名制品' in payload['message']
    assert gateway.commands == []
    assert gateway.session_local.sessions == []


def test_dependency_install_fails_closed_when_source_query_fails(tmp_path: Path) -> None:
    class FailingGateway(FakePluginRuntimeGateway):
        async def get_plugin_state(self, plugin_id: str) -> None:
            raise RuntimeError('database unavailable')

    gateway = FailingGateway()
    payload = build_runtime_with_gateway(tmp_path, gateway).install_plugin_dependencies_from_cli('demo', confirmed=True)
    assert payload['status'] == 'blocked'
    assert gateway.commands == []


@pytest.mark.asyncio
async def test_sync_dependency_install_never_runs_nested_event_loop(tmp_path: Path) -> None:
    class UnexpectedQueryGateway(FakePluginRuntimeGateway):
        async def get_plugin_state(self, plugin_id: str) -> None:
            pytest.fail('synchronous wrapper must not query within the running loop')

    gateway = UnexpectedQueryGateway()
    payload = build_runtime_with_gateway(tmp_path, gateway).install_plugin_dependencies_from_cli('demo', confirmed=True)
    assert payload['status'] == 'blocked'
    assert '事件循环' in payload['message']
    assert gateway.commands == []


@pytest.mark.asyncio
async def test_configuration_never_falls_back_to_conflicting_source(tmp_path: Path) -> None:
    backend = tmp_path / 'backend'
    write_manifest(
        backend / 'plugins' / 'demo',
        'id: demo\nname: Demo\nversion: 1.0.0\nbackend:\n  module: plugins.demo\n',
    )

    class ConflictingGateway(FakePluginRuntimeGateway):
        async def get_selected_artifact_plugin(self, plugin_id: str, backend_root: Path) -> None:
            raise ValueError('制品与源码目录冲突')

    FakePluginService.detail_plugin = SimpleNamespace(plugin_id='demo', source='artifact')
    gateway = ConflictingGateway()
    runtime = build_runtime_with_gateway(backend, gateway)
    for payload in (await runtime.get_plugin_config('demo'), await runtime.set_plugin_config('demo', {'key': 'value'})):
        assert payload['ok'] is False
        assert '冲突' in str(payload)
    assert gateway.session_local.sessions == []


@pytest.mark.parametrize('method', ['install_plugin_dependencies', 'install_plugin_dependencies_from_cli'])
def test_dependency_source_check_and_audit_share_one_event_loop(tmp_path: Path, method: str) -> None:
    backend = tmp_path / 'backend'
    write_manifest(
        backend / 'plugins' / 'demo',
        'id: demo\nname: Demo\nversion: 1.0.0\nbackend:\n  module: plugins.demo\n'
        'dependencies:\n  python:\n    - missing-python\n',
    )
    loops: list[asyncio.AbstractEventLoop] = []

    class LoopAffineGateway(FakePluginRuntimeGateway):
        async def get_plugin_state(self, plugin_id: str) -> None:
            loops.append(asyncio.get_running_loop())

        async def add_plugin_operation_log(self, payload: dict, *, dry_run: bool, continue_on_error: bool) -> None:
            current_loop = asyncio.get_running_loop()
            if loops[0] is not current_loop:
                raise RuntimeError('shared async database pool was reused from a different event loop')
            loops.append(current_loop)
            await super().add_plugin_operation_log(payload, dry_run=dry_run, continue_on_error=continue_on_error)

    gateway = LoopAffineGateway()
    payload = getattr(build_runtime_with_gateway(backend, gateway), method)(
        'demo', policy_config=DependencyInstallPolicyConfig(mode='explicit', env='dev'), confirmed=True
    )
    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert len(loops) == EXPECTED_DATABASE_OPERATIONS
    assert loops[0] is loops[1]
    assert loops[0].is_closed()
    assert len(FakePluginService.operation_logs) == 1
