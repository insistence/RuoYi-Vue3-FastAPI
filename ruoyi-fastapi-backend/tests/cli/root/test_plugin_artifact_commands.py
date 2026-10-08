import asyncio
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from cli.context import CliContext
from cli.core import CliContextFactory, CliExecutionService
from cli.exit_codes import ARGUMENT_ERROR, GUARD_REJECTED
from cli.groups.plugin.artifact_controller import PluginArtifactCommandController
from cli.groups.plugin.commands.artifact import register_artifact_commands

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DIGEST = 'a' * 64
GENERATION = 'b' * 32
EXPECTED_WORKERS = 3


@pytest.fixture(autouse=True)
def preserve_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    隔离测试对当前应用环境的修改。
    """
    monkeypatch.setenv('APP_ENV', os.environ.get('APP_ENV', 'dev'))


class CapturingController:
    """
    记录命令转发参数的控制器替身。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def capture(*args: Any, **kwargs: Any) -> None:
            self.calls.append((name, args, kwargs))

        return capture


def app_for(controller: Any) -> typer.Typer:
    """
    构建仅包含被测插件命令的 Typer 应用。
    """
    app = typer.Typer()
    register_artifact_commands(app, lambda: controller)
    return app


@pytest.mark.parametrize(
    ('arguments', 'method', 'options'),
    [
        (
            ['artifact', 'build', 'source', 'output.rpk', '--key-file', 'signing.pem', '--key-id', 'publisher'],
            'build_artifact',
            {'key_file': Path('signing.pem'), 'key_id': 'publisher', 'password_env': None},
        ),
        (['artifact', 'verify', 'output.rpk'], 'verify_artifact', {}),
        (
            ['artifact', 'import', 'output.rpk', '--dry-run'],
            'import_artifact',
            {'allow_prod': False, 'yes': False, 'dry_run': True},
        ),
        (['artifact', 'list', '--plugin-id', 'demo'], 'list_artifacts', {'plugin_id': 'demo'}),
        (['artifact', 'inspect'], 'maintain_artifacts', {'options': {'keep_last': 2, 'min_age_days': 7}}),
        (
            ['artifact', 'prune'],
            'maintain_artifacts',
            {
                'options': {'keep_last': 2, 'min_age_days': 7, 'expected_plan': None, 'maintenance': False},
                'allow_prod': False,
                'yes': False,
                'dry_run': True,
            },
        ),
        (
            ['artifact', 'prune', '--execute', '--expected-plan', DIGEST, '--maintenance'],
            'maintain_artifacts',
            {
                'options': {'keep_last': 2, 'min_age_days': 7, 'expected_plan': DIGEST, 'maintenance': True},
                'allow_prod': False,
                'yes': False,
                'dry_run': False,
            },
        ),
        (
            ['artifact', 'rotate-signature', 'next.rpk', '--expected-key-id', 'old'],
            'maintain_artifacts',
            {
                'options': {'archive': Path('next.rpk'), 'expected_key_id': 'old', 'maintenance': False},
                'allow_prod': False,
                'yes': False,
            },
        ),
        (
            ['artifact', 'reconcile'],
            'maintain_artifacts',
            {
                'options': {'maintenance': False},
                'allow_prod': False,
                'yes': False,
            },
        ),
        (['release', 'plan', 'demo', DIGEST], 'plan_release', {}),
        (
            ['release', 'prepare', 'demo', DIGEST, '--maintenance', '--yes'],
            'prepare_release',
            {'maintenance': True, 'allow_prod': False, 'yes': True, 'dry_run': False},
        ),
        (
            [
                'release',
                'select',
                'demo',
                DIGEST,
                '--expected-generation',
                GENERATION,
                '--expected-workers',
                '3',
                '--maintenance',
                '--yes',
                '--allow-prod',
            ],
            'select_release',
            {
                'expected_generation': GENERATION,
                'expected_workers': 3,
                'maintenance': True,
                'allow_prod': True,
                'yes': True,
            },
        ),
        (['release', 'status', '--plugin-id', 'demo'], 'release_status', {'plugin_id': 'demo'}),
        (
            ['release', 'wait', 'demo', DIGEST, '--generation', GENERATION, '--expected-workers', '3'],
            'wait_release',
            {
                'expected_generation': GENERATION,
                'expected_workers': 3,
                'timeout_seconds': 300,
                'poll_interval_seconds': 2,
            },
        ),
        (
            ['release', 'enable', 'demo', '--expected-generation', GENERATION, '--maintenance', '--yes'],
            'set_release_enabled',
            {'enabled': True, 'expected_generation': GENERATION, 'maintenance': True, 'allow_prod': False, 'yes': True},
        ),
        (
            ['release', 'disable', 'demo', '--expected-generation', GENERATION, '--maintenance', '--yes'],
            'set_release_enabled',
            {
                'enabled': False,
                'expected_generation': GENERATION,
                'maintenance': True,
                'allow_prod': False,
                'yes': True,
            },
        ),
        (
            [
                'release',
                'rollback',
                'demo',
                '--expected-generation',
                GENERATION,
                '--schema-compatible',
                '--maintenance',
            ],
            'rollback_release',
            {
                'expected_generation': GENERATION,
                'schema_compatible': True,
                'maintenance': True,
                'allow_prod': False,
                'yes': False,
            },
        ),
    ],
)
def test_cli_dispatches_artifact_and_release_parameters(
    arguments: list[str], method: str, options: dict[str, Any]
) -> None:
    """
    验证制品与发布命令将参数完整转交控制器。
    """
    controller = CapturingController()
    result = CliRunner().invoke(app_for(controller), [*arguments, '--env', 'test', '--output', 'json'])
    assert result.exit_code == 0, result.output
    name, args, kwargs = controller.calls[0]
    assert name == method
    assert args[-2:] == ('test', 'json')
    assert kwargs == options


@pytest.mark.parametrize(
    'arguments',
    [
        ['release', 'select', 'demo', DIGEST],
        ['release', 'select', 'demo', DIGEST, '--expected-generation', GENERATION, '--expected-workers', '0'],
        ['release', 'select', 'demo', DIGEST, '--expected-generation', GENERATION, '--dry-run'],
        ['release', 'rollback', 'demo', '--expected-generation', GENERATION, '--dry-run'],
        ['release', 'enable', 'demo'],
        ['release', 'disable', 'demo', '--expected-generation', GENERATION, '--dry-run'],
        ['artifact', 'build', 'source', 'target.rpk', '--key-file', 'signing.pem'],
    ],
)
def test_cli_rejects_missing_concurrency_token_and_unsupported_flags(arguments: list[str]) -> None:
    """
    验证缺失发布代际和不支持的选项会被拒绝。
    """
    controller = CapturingController()
    result = CliRunner().invoke(app_for(controller), arguments)
    assert result.exit_code == ARGUMENT_ERROR
    assert not controller.calls


@pytest.mark.parametrize(
    'help_arguments',
    [
        ['artifact', '--help'],
        ['release', '--help'],
        ['release', 'select', '--help'],
        ['release', 'wait', '--help'],
        ['artifact', 'prune', '--help'],
    ],
)
def test_help_keeps_config_crypto_database_and_plugin_code_unloaded(help_arguments: list[str]) -> None:
    """
    验证帮助查询不加载配置、加密、数据库或插件代码。
    """
    observed = (
        'config.env',
        'config.database',
        'cryptography',
        'plugins.core.artifacts',
        'plugins.core.deployment.config',
        'plugins.core.deployment.service',
        'plugins.core.runtime.service',
        'cli.groups.plugin.artifact_controller',
    )
    script = (
        'import importlib,json,sys; from typer.testing import CliRunner; '
        "m=importlib.import_module('cli.groups.plugin.command'); "
        f'r=CliRunner().invoke(m.app,{help_arguments!r}); '
        f'print(json.dumps({{"exit":r.exit_code,"loaded":{{name:name in sys.modules for name in {observed!r}}}}}))'
    )
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=BACKEND_ROOT, capture_output=True, text=True, check=True
    )
    payload = json.loads(result.stdout)
    assert payload['exit'] == 0
    assert not any(payload['loaded'].values())


class RecordingContextFactory:
    """
    记录上下文创建顺序的工厂替身。
    """

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def build_regular(self, env: str, output: str, allow_prod: bool, yes: bool, dry_run: bool) -> CliContext:
        assert os.environ['APP_ENV'] == env
        self.events.append('context')
        return CliContext(env=env, output=output, allow_prod=allow_prod, yes=yes, dry_run=dry_run)

    def build_dangerous(
        self, env: str, output: str, allow_prod: bool, yes: bool, dry_run: bool, *, command_name: str
    ) -> CliContext:
        self.events.append(command_name)
        return self.build_regular(env, output, allow_prod, yes, dry_run)


class RecordingExecution:
    """
    记录命令结果的执行服务替身。
    """

    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}

    @staticmethod
    def run_async(coroutine: Any) -> Any:
        return asyncio.run(coroutine)

    def complete_payload(self, ctx: CliContext, payload: dict[str, Any]) -> None:
        self.payload = payload


def quiet_context_factory() -> CliContextFactory:
    """
    创建不初始化日志输出的测试上下文工厂。
    """
    return CliContextFactory(
        runtime_state=SimpleNamespace(suppress_logs=lambda: None, suppress_sqlalchemy_logs=lambda: None)
    )


def test_production_mutations_are_guarded_before_loading_runtime() -> None:
    """
    验证生产写入保护先于运行时加载执行。
    """

    def forbidden_config() -> None:
        pytest.fail('rejected CLI must not construct runtime')

    controller = PluginArtifactCommandController(
        context_factory=quiet_context_factory(),
        execution_service=CliExecutionService(),
        config_factory=forbidden_config,
    )
    app = app_for(controller)
    for arguments in (
        ['artifact', 'import', 'target.rpk'],
        ['artifact', 'prune', '--execute', '--maintenance'],
        ['artifact', 'rotate-signature', 'next.rpk', '--expected-key-id', 'old', '--maintenance'],
        ['artifact', 'reconcile', '--maintenance'],
        ['release', 'prepare', 'demo', DIGEST, '--maintenance'],
        ['release', 'select', 'demo', DIGEST, '--expected-generation', GENERATION, '--maintenance'],
        ['release', 'rollback', 'demo', '--expected-generation', GENERATION, '--maintenance', '--schema-compatible'],
        ['release', 'enable', 'demo', '--expected-generation', GENERATION, '--maintenance'],
        ['release', 'disable', 'demo', '--expected-generation', GENERATION, '--maintenance'],
    ):
        result = CliRunner().invoke(app, [*arguments, '--env', 'prod', '--yes', '--output', 'json'])
        assert result.exit_code == GUARD_REJECTED
        assert json.loads(result.stdout)['ok'] is False


def test_dry_run_is_readonly_and_environment_precedes_runtime() -> None:
    """
    验证预演保持只读，且先设置环境再创建运行时。
    """
    events: list[str] = []
    execution = RecordingExecution()

    def config() -> object:
        assert events == ['context']
        assert os.environ['APP_ENV'] == 'prod'
        events.append('config')
        return object()

    class Catalog:
        async def import_artifact(self, path: Path, *, actor: str, dry_run: bool) -> dict[str, Any]:
            assert actor
            assert dry_run
            return {'ok': True, 'dryRun': dry_run}

    controller = PluginArtifactCommandController(
        context_factory=RecordingContextFactory(events),
        execution_service=execution,
        config_factory=config,
        catalog_factory=lambda _: Catalog(),
    )
    controller.import_artifact(Path('artifact.rpk'), 'prod', 'json', allow_prod=False, yes=False, dry_run=True)
    assert execution.payload == {'ok': True, 'dryRun': True, 'env': 'prod'}
    assert events == ['context', 'config']


def test_controller_forwards_maintenance_cas_and_schema_compatibility() -> None:
    """
    验证维护、并发校验与数据兼容选项完整传递。
    """
    events: list[str] = []
    execution = RecordingExecution()
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    class Service:
        def __getattr__(self, name: str) -> Any:
            async def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
                calls.append((name, args, kwargs))
                return {'ok': True}

            return call

    controller = PluginArtifactCommandController(
        context_factory=RecordingContextFactory(events),
        execution_service=execution,
        config_factory=object,
        service_factory=lambda _: Service(),
    )
    controller.select_release(
        'demo',
        DIGEST,
        'dev',
        'json',
        expected_generation=GENERATION,
        expected_workers=EXPECTED_WORKERS,
        maintenance=True,
        allow_prod=False,
        yes=True,
    )
    assert calls[-1][0:2] == ('select', ('demo', DIGEST))
    assert calls[-1][2]['expected_generation'] == GENERATION
    assert calls[-1][2]['expected_workers'] == EXPECTED_WORKERS
    assert calls[-1][2]['maintenance'] is True
    controller.rollback_release(
        'demo',
        'dev',
        'json',
        expected_generation=GENERATION,
        schema_compatible=True,
        maintenance=True,
        allow_prod=False,
        yes=True,
    )
    assert calls[-1][0:2] == ('rollback', ('demo',))
    assert calls[-1][2]['schema_compatible'] is True
    assert calls[-1][2]['expected_generation'] == GENERATION
    assert events[0] == 'plugin release select'
    assert events[-2] == 'plugin release rollback'


def test_offline_build_encrypted_key_never_imports_plugin_or_requires_feature_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    验证离线构建使用加密私钥且不导入插件或部署配置。
    """
    source = tmp_path / 'artifact_demo'
    source.mkdir()
    (source / 'plugin.yaml').write_text(
        'manifestVersion: 2\nid: artifact_demo\nname: Demo\nversion: 1.0.0\n'
        'backend:\n  module: plugins.artifact_demo\n  entrypoint: plugins.artifact_demo:create_plugin\n',
        encoding='utf-8',
    )
    (source / '__init__.py').write_text('raise RuntimeError("must not import")\n', encoding='utf-8')
    secret = 'test-only-signing-key-password'
    monkeypatch.setenv('TEST_ARTIFACT_KEY_PASSWORD', secret)
    signing_key = Ed25519PrivateKey.generate()
    key_data = signing_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(secret.encode()),
    )
    key_file = tmp_path / 'publisher.pem'
    key_file.write_bytes(key_data)
    execution = RecordingExecution()

    def forbidden_config() -> None:
        pytest.fail('offline build must not require feature config')

    controller = PluginArtifactCommandController(
        context_factory=RecordingContextFactory([]), execution_service=execution, config_factory=forbidden_config
    )
    output = tmp_path / 'demo.rpk'
    controller.build_artifact(
        source, output, 'dev', 'json', key_file=key_file, key_id='publisher', password_env='TEST_ARTIFACT_KEY_PASSWORD'
    )
    assert execution.payload['ok'], execution.payload
    verified = importlib.import_module('plugins.core.artifacts').verify_artifact(
        output, {'publisher': signing_key.public_key()}
    )
    assert verified.plugin_id == 'artifact_demo'
    assert 'plugins.artifact_demo' not in sys.modules
    assert secret not in json.dumps(execution.payload)
    assert key_data not in output.read_bytes()
    original = output.read_bytes()
    controller.build_artifact(
        source, output, 'dev', 'json', key_file=key_file, key_id='publisher', password_env='TEST_ARTIFACT_KEY_PASSWORD'
    )
    assert execution.payload['ok'] is False
    assert output.read_bytes() == original
    inside_key = source / 'publisher.pem'
    inside_key.write_bytes(key_data)
    controller.build_artifact(source, tmp_path / 'unsafe.rpk', 'dev', 'json', key_file=inside_key, key_id='publisher')
    assert execution.payload['ok'] is False
    assert '之外' in execution.payload['message']
    assert not (tmp_path / 'unsafe.rpk').exists()


@pytest.mark.parametrize('enabled', [True, False])
def test_controller_enablement_forwards_maintenance_and_cas(enabled: bool) -> None:
    """
    验证制品启停传递维护确认与发布代际。
    """
    recorded: dict[str, Any] = {}

    class Enablement:
        @staticmethod
        async def set_enabled(plugin_id: str, **kwargs: Any) -> dict[str, Any]:
            recorded.update(pluginId=plugin_id, **kwargs)
            return {'ok': True, 'restartRequired': True}

    execution = RecordingExecution()
    controller = PluginArtifactCommandController(
        context_factory=RecordingContextFactory([]),
        execution_service=execution,
        config_factory=object,
        enablement_factory=lambda _: Enablement(),
    )
    controller.set_release_enabled(
        'demo',
        'dev',
        'json',
        enabled=enabled,
        expected_generation=GENERATION,
        maintenance=True,
        allow_prod=False,
        yes=True,
    )
    assert recorded['pluginId'] == 'demo'
    assert recorded['enabled'] is enabled
    assert recorded['expected_generation'] == GENERATION
    assert recorded['maintenance'] is True
    assert execution.payload['restartRequired'] is True
