import asyncio
import inspect
import sys
from typing import Any

from cli.exit_codes import ARGUMENT_ERROR, DEPENDENCY_ERROR, RUNTIME_ERROR
from cli.groups.plugin.controller import PluginCommandController
from cli.groups.plugin.options import (
    PluginDependencyAllowlistExampleCommandOptions,
    PluginDependencyInstallCommandOptions,
    PluginDependencyLockCommandOptions,
)


class FakeContextFactory:
    """
    测试用 CLI 上下文工厂。
    """

    def build_dangerous(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        command_name: str,
    ) -> Any:
        """构造危险命令上下文。"""
        return type('FakeContext', (), {'env': env, 'output': output})()

    def build_regular(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> Any:
        """构造普通命令上下文。"""
        return type(
            'FakeContext',
            (),
            {'env': env, 'output': output, 'allow_prod': allow_prod, 'yes': yes, 'dry_run': dry_run},
        )()

    def build_readonly(self, env: str, output: str) -> Any:
        """构造只读命令上下文。"""
        return type('FakeContext', (), {'env': env, 'output': output})()


class FakeExecutionService:
    """
    测试用 CLI 执行服务。
    """

    def __init__(self) -> None:
        """初始化测试执行服务。"""
        self.completed_payload: dict[str, Any] | None = None
        self.default_exit_code: int | None = None

    def run_async(self, value: Any) -> Any:
        """直接返回测试中的 awaitable 结果。"""
        if inspect.isawaitable(value):
            return asyncio.run(value)
        return value

    def complete_payload_with_text(
        self,
        ctx: Any,
        payload: dict[str, Any],
        *,
        text_builder: Any,
        default_exit_code: int,
    ) -> None:
        """记录完成参数。"""
        self.completed_payload = payload
        self.default_exit_code = default_exit_code


class FakePresenter:
    """
    测试用 presenter。
    """

    @staticmethod
    def build_list_text(payload: dict[str, Any]) -> str:
        """构造列表文本。"""
        return str(payload)

    @staticmethod
    def build_info_text(payload: dict[str, Any]) -> str:
        """构造详情文本。"""
        return str(payload)

    @staticmethod
    def build_enabled_text(payload: dict[str, Any]) -> str:
        """构造启停文本。"""
        return str(payload)

    @staticmethod
    def build_install_text(payload: dict[str, Any]) -> str:
        """构造安装文本。"""
        return str(payload)

    @staticmethod
    def build_check_text(payload: dict[str, Any]) -> str:
        """构造检查文本。"""
        return str(payload)

    @staticmethod
    def build_config_text(payload: dict[str, Any]) -> str:
        """构造配置文本。"""
        return str(payload)

    @staticmethod
    def build_dependency_install_text(payload: dict[str, Any]) -> str:
        """构造依赖安装文本。"""
        return str(payload)

    @staticmethod
    def build_dependency_lock_text(payload: dict[str, Any]) -> str:
        """构造依赖锁文件文本。"""
        return str(payload)

    @staticmethod
    def build_dependency_allowlist_example_text(payload: dict[str, Any]) -> str:
        """构造允许列表示例文本。"""
        return str(payload)


class FakeCoreRuntime:
    """
    测试用核心插件运行时。
    """

    def __init__(self) -> None:
        """初始化测试用核心插件运行时。"""
        self.dependency_install_calls: list[dict[str, Any]] = []
        self.config_set_calls: list[dict[str, Any]] = []
        self.list_with_state_called = False

    async def list_plugins_with_state(self) -> dict[str, Any]:
        """返回合并状态后的插件列表。"""
        self.list_with_state_called = True
        return {
            'ok': True,
            'count': 1,
            'databaseAvailable': True,
            'databaseError': None,
            'plugins': [
                {
                    'pluginId': 'demo',
                    'enabled': True,
                    'status': 'installed',
                }
            ],
        }

    async def install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """返回失败安装结果。"""
        return {'ok': False, 'message': '插件安装失败', 'pluginId': plugin_id}

    @staticmethod
    def check_plugin(plugin_id: str | None = None) -> dict[str, Any]:
        """返回缺失 ok 字段的检查结果。"""
        return {'message': '插件检查结果缺失 ok', 'pluginId': plugin_id}

    async def set_plugin_config(self, plugin_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """返回失败配置更新结果。"""
        self.config_set_calls.append({'plugin_id': plugin_id, 'values': values})
        return {'ok': False, 'message': '插件配置更新失败', 'pluginId': plugin_id, 'values': values}

    def install_plugin_dependencies_from_cli(
        self,
        plugin_id: str,
        *,
        dry_run: bool = False,
        policy_config: object | None = None,
        confirmed: bool = False,
        output_callback: object | None = None,
    ) -> dict[str, Any]:
        """返回 CLI 依赖安装测试结果。"""
        self.dependency_install_calls.append(
            {
                'plugin_id': plugin_id,
                'dry_run': dry_run,
                'policy_config': policy_config,
                'confirmed': confirmed,
                'output_callback': output_callback,
            }
        )
        return {
            'ok': True,
            'message': '插件依赖安装演练完成',
            'pluginId': plugin_id,
            'dryRun': dry_run,
            'policyConfig': policy_config,
            'confirmed': confirmed,
        }


class FakePluginRuntime:
    """
    测试用插件 CLI 运行时。
    """

    def __init__(self) -> None:
        """初始化测试用插件 CLI 运行时。"""
        self.core_runtime = FakeCoreRuntime()
        self.dependency_lock_calls: list[dict[str, Any]] = []
        self.dependency_allowlist_example_calls: list[dict[str, Any]] = []

    def lock_plugin_dependencies(
        self,
        plugin_id: str,
        *,
        output_path: str = '',
        offline_dir: str = '',
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """返回依赖锁文件测试结果。"""
        self.dependency_lock_calls.append(
            {
                'plugin_id': plugin_id,
                'output_path': output_path,
                'offline_dir': offline_dir,
                'dry_run': dry_run,
                'overwrite': overwrite,
            }
        )
        return {
            'ok': True,
            'message': '插件依赖锁文件模板生成完成',
            'pluginId': plugin_id,
            'outputFile': output_path,
            'offlineDir': offline_dir,
            'dryRun': dry_run,
            'overwrite': overwrite,
        }

    def generate_plugin_dependency_allowlist_example(
        self,
        *,
        output_path: str = '',
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """返回允许列表示例测试结果。"""
        self.dependency_allowlist_example_calls.append(
            {
                'output_path': output_path,
                'dry_run': dry_run,
                'overwrite': overwrite,
            }
        )
        return {
            'ok': True,
            'message': '插件依赖允许列表示例生成完成',
            'outputFile': output_path,
            'dryRun': dry_run,
            'overwrite': overwrite,
        }


def test_list_plugins_uses_database_state_aware_query() -> None:
    """校验插件列表 CLI 使用合并数据库状态的查询入口。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.list_plugins('dev', 'json')

    assert plugin_runtime.core_runtime.list_with_state_called is True
    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['plugins'][0]['runtimeEnabled'] is True
    assert 'enabled' not in execution_service.completed_payload['plugins'][0]
    assert execution_service.completed_payload['plugins'][0]['status'] == 'installed'


def test_install_plugin_uses_failure_exit_code_when_payload_is_not_ok() -> None:
    """校验插件安装失败时 CLI 使用失败退出码。"""
    execution_service = FakeExecutionService()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=FakePluginRuntime(),
    )

    controller.install_plugin('demo', 'dev', 'text', allow_prod=False, yes=True, dry_run=False)

    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['ok'] is False
    assert execution_service.default_exit_code == DEPENDENCY_ERROR


def test_check_plugin_uses_failure_exit_code_when_payload_has_no_ok() -> None:
    """校验插件检查结果缺失 ok 时 CLI 使用失败退出码。"""
    execution_service = FakeExecutionService()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=FakePluginRuntime(),
    )

    controller.check_plugin('demo', 'dev', 'text')

    assert execution_service.completed_payload is not None
    assert 'ok' not in execution_service.completed_payload
    assert execution_service.default_exit_code == DEPENDENCY_ERROR


def test_plugin_config_set_uses_failure_exit_code_when_payload_is_not_ok() -> None:
    """校验插件配置更新失败时 CLI 使用失败退出码。"""
    execution_service = FakeExecutionService()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=FakePluginRuntime(),
    )

    controller.plugin_config(
        'demo',
        'set',
        ['provider="openai"'],
        'dev',
        'text',
        allow_prod=False,
        yes=True,
    )

    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['ok'] is False
    assert execution_service.completed_payload['values'] == {'provider': 'openai'}
    assert execution_service.default_exit_code == DEPENDENCY_ERROR


def test_plugin_config_set_argument_error_uses_structured_payload() -> None:
    """校验插件配置参数格式错误时 CLI 走统一 payload 输出。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.plugin_config(
        'demo',
        'set',
        ['badpair'],
        'dev',
        'text',
        allow_prod=False,
        yes=True,
    )

    assert plugin_runtime.core_runtime.config_set_calls == []
    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['ok'] is False
    assert execution_service.completed_payload['message'] == '配置参数必须使用 key=value 格式：badpair'
    assert execution_service.default_exit_code == ARGUMENT_ERROR


def test_plugin_payload_with_error_uses_runtime_error_exit_code() -> None:
    """校验带 error 的插件运行时异常负载由 CLI 映射为运行时错误退出码。"""
    payload = {'ok': False, 'message': '插件配置导入失败', 'error': 'database unavailable'}

    exit_code = PluginCommandController._resolve_plugin_exit_code(
        payload,
        success_exit_code=0,
        failure_exit_code=DEPENDENCY_ERROR,
    )

    assert exit_code == RUNTIME_ERROR


def test_install_plugin_dependencies_passes_policy_config_to_runtime() -> None:
    """校验 CLI install-deps 将策略参数收口后传给运行时。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.install_plugin_dependencies(
        'demo',
        'stage',
        'text',
        options=PluginDependencyInstallCommandOptions(
            allow_prod=True,
            yes=True,
            dry_run=False,
            policy_mode='locked',
            allow_unlisted=True,
            lockfile='plugins/demo/plugin.lock.yaml',
            allowlist='config/plugin_dependency_allowlist.yaml',
            offline_dir='artifacts/plugin-dependencies',
            require_lockfile=True,
        ),
    )

    assert execution_service.completed_payload is not None
    policy_config = execution_service.completed_payload['policyConfig']
    assert execution_service.completed_payload['confirmed'] is True
    assert policy_config.mode == 'locked'
    assert policy_config.env == 'stage'
    assert policy_config.allow_prod is True
    assert policy_config.allow_prod_install is True
    assert policy_config.require_yes is True
    assert policy_config.allow_unlisted is True
    assert policy_config.require_allowlist is False
    assert str(policy_config.lockfile_path) == 'plugins/demo/plugin.lock.yaml'
    assert str(policy_config.allowlist_path) == 'config/plugin_dependency_allowlist.yaml'
    assert str(policy_config.offline_dir) == 'artifacts/plugin-dependencies'
    assert policy_config.require_lockfile is True
    assert len(plugin_runtime.core_runtime.dependency_install_calls) == 1
    assert callable(plugin_runtime.core_runtime.dependency_install_calls[0]['output_callback'])


def test_install_plugin_dependencies_json_output_disables_live_progress() -> None:
    """校验 JSON 输出不会注入依赖安装进度文本。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.install_plugin_dependencies(
        'demo',
        'dev',
        'json',
        options=PluginDependencyInstallCommandOptions(yes=True),
    )

    assert plugin_runtime.core_runtime.dependency_install_calls[0]['output_callback'] is None


def test_dependency_install_output_callback_routes_stderr_separately(monkeypatch: Any) -> None:
    """校验依赖安装实时输出保留 stdout 和 stderr 通道。"""
    emitted: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        'typer.echo',
        lambda text, *, nl, err: emitted.append((text, err)),
    )
    ctx = type('FakeContext', (), {'output': 'text'})()

    output_callback = PluginCommandController._build_dependency_install_output_callback(ctx)

    assert output_callback is not None
    output_callback('status', '[1/1] 开始安装\n')
    output_callback('stdout', 'downloading\n')
    output_callback('stderr', 'warning\n')
    assert emitted == [
        ('[1/1] 开始安装\n', False),
        ('downloading\n', False),
        ('warning\n', True),
    ]


def test_install_plugin_dependencies_tty_confirm_previews_then_executes(
    monkeypatch: Any,
) -> None:
    """校验 TTY 交互安装会先生成预览，确认后再执行真实安装。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: True)
    emitted_lines: list[str] = []
    monkeypatch.setattr('typer.echo', emitted_lines.append)

    controller.install_plugin_dependencies(
        'demo',
        'dev',
        'text',
        options=PluginDependencyInstallCommandOptions(dry_run=False, yes=False),
    )

    assert [call['dry_run'] for call in plugin_runtime.core_runtime.dependency_install_calls] == [True, False]
    assert [call['confirmed'] for call in plugin_runtime.core_runtime.dependency_install_calls] == [True, True]
    assert emitted_lines
    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['dryRun'] is False
    assert execution_service.completed_payload['confirmed'] is True


def test_install_plugin_dependencies_tty_decline_does_not_execute_real_install(
    monkeypatch: Any,
) -> None:
    """校验 TTY 交互拒绝后不会执行真实依赖安装。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr('typer.confirm', lambda *args, **kwargs: False)
    monkeypatch.setattr('typer.echo', lambda _: None)

    controller.install_plugin_dependencies(
        'demo',
        'dev',
        'text',
        options=PluginDependencyInstallCommandOptions(dry_run=False, yes=False),
    )

    assert [call['dry_run'] for call in plugin_runtime.core_runtime.dependency_install_calls] == [True]
    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['ok'] is False
    assert execution_service.completed_payload['message'] == '已取消插件依赖安装'


def test_install_plugin_dependencies_non_tty_without_yes_does_not_preview(
    monkeypatch: Any,
) -> None:
    """校验非 TTY 未传 --yes 时不进入交互预览，交给策略返回确认阻断。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)

    controller.install_plugin_dependencies(
        'demo',
        'dev',
        'text',
        options=PluginDependencyInstallCommandOptions(dry_run=False, yes=False),
    )

    assert [call['dry_run'] for call in plugin_runtime.core_runtime.dependency_install_calls] == [False]
    assert plugin_runtime.core_runtime.dependency_install_calls[0]['confirmed'] is False


def test_lock_plugin_dependencies_passes_options_to_runtime() -> None:
    """校验 CLI lock-deps 将锁文件参数收口后传给运行时。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.lock_plugin_dependencies(
        'demo',
        'dev',
        'text',
        options=PluginDependencyLockCommandOptions(
            output_path='plugins/demo/plugin.lock.yaml',
            offline_dir='artifacts/plugin-dependencies',
            dry_run=True,
            overwrite=True,
        ),
    )

    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['dryRun'] is True
    assert execution_service.completed_payload['overwrite'] is True
    assert plugin_runtime.dependency_lock_calls == [
        {
            'plugin_id': 'demo',
            'output_path': 'plugins/demo/plugin.lock.yaml',
            'offline_dir': 'artifacts/plugin-dependencies',
            'dry_run': True,
            'overwrite': True,
        }
    ]


def test_generate_plugin_dependency_allowlist_example_passes_options_to_runtime() -> None:
    """校验 CLI allowlist-example 将参数收口后传给运行时。"""
    execution_service = FakeExecutionService()
    plugin_runtime = FakePluginRuntime()
    controller = PluginCommandController(
        context_factory=FakeContextFactory(),
        execution_service=execution_service,
        presenter=FakePresenter(),
        plugin_runtime=plugin_runtime,
    )

    controller.generate_plugin_dependency_allowlist_example(
        'dev',
        'text',
        options=PluginDependencyAllowlistExampleCommandOptions(
            output_path='config/plugin_dependency_allowlist.yaml',
            dry_run=True,
            overwrite=True,
        ),
    )

    assert execution_service.completed_payload is not None
    assert execution_service.completed_payload['dryRun'] is True
    assert execution_service.completed_payload['overwrite'] is True
    assert plugin_runtime.dependency_allowlist_example_calls == [
        {
            'output_path': 'config/plugin_dependency_allowlist.yaml',
            'dry_run': True,
            'overwrite': True,
        }
    ]
