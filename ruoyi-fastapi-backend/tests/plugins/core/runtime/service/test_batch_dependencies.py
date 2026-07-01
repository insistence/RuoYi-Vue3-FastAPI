# ruff: noqa: E402, F403, F405, I001

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(BACKEND_ROOT))

from tests.plugin_runtime_helpers import *
from plugins.core.runtime.service.audit import PluginAuditUseCase
import plugins.core.runtime.service.audit as audit_module
from plugins.core.runtime.service.dependencies import PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS


def test_plugin_runtime_check_deps_reports_dependency_items(tmp_path: Path) -> None:
    """
    校验插件依赖专项检查返回稳定负载。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
dependencies:
  python:
    - missing-python
  npm:
    - vue>=3.5.0
""",
    )

    payload = build_runtime(backend_root).check_plugin_dependencies('demo')

    assert payload['ok'] is False
    assert payload['pluginId'] == 'demo'
    assert payload['missingDependencies'] == ['missing-python']
    assert len(payload['dependencies']) == EXPECTED_DEPENDENCY_COUNT


def test_plugin_runtime_plan_plugins_returns_dependency_order(tmp_path: Path) -> None:
    """
    校验插件运行时可以生成批量操作拓扑计划。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - base
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'base',
        """
id: base
name: Base
version: 1.0.0
enabled: true
backend:
  module: plugins.base
""",
    )

    payload = build_runtime(backend_root).plan_plugins('install', ['app'])

    assert payload['ok'] is True
    assert payload['operation'] == 'install'
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['items'][0]['requested'] is False
    assert payload['plan']['items'][1]['requested'] is True


def test_plugin_runtime_plan_plugins_delegates_to_batch_use_case(tmp_path: Path) -> None:
    """
    校验插件批量计划入口委托给组合式批量 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeBatchUseCase:
        """
        测试用插件批量 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件批量 use case。
            """
            self.operation: str | None = None
            self.plugin_ids: list[str] | None = None

        def plan_plugins(self, operation: str, plugin_ids: list[str] | None = None) -> dict:
            """
            记录批量计划调用。

            :param operation: 批量操作类型
            :param plugin_ids: 插件ID列表
            :return: 测试负载
            """
            self.operation = operation
            self.plugin_ids = plugin_ids
            return {'ok': True, 'operation': operation, 'pluginIds': plugin_ids}

    batch = FakeBatchUseCase()
    runtime.batch = batch

    payload = runtime.plan_plugins('install', ['demo'])

    assert batch.operation == 'install'
    assert batch.plugin_ids == ['demo']
    assert payload == {'ok': True, 'operation': 'install', 'pluginIds': ['demo']}


def test_plugin_runtime_plan_plugins_reports_blockers(tmp_path: Path) -> None:
    """
    校验插件运行时计划会输出阻塞项。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - missing
""",
    )

    payload = build_runtime(backend_root).plan_plugins('install', ['app'])

    assert payload['ok'] is False
    assert payload['plan']['blockerCount'] == 1
    assert payload['plan']['blockers'][0]['status'] == 'missing'


def test_plugin_runtime_plan_plugins_reports_database_state_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    校验批量计划会显式输出数据库状态读取错误。

    :param tmp_path: pytest 临时目录
    :param monkeypatch: pytest monkeypatch fixture
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - base
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'base',
        """
id: base
name: Base
version: 1.0.0
backend:
  module: plugins.base
""",
    )
    runtime = build_runtime(backend_root)
    monkeypatch.setattr(
        runtime.context,
        'load_database_plugin_states_sync_with_error',
        lambda: ([], 'db unavailable'),
    )

    payload = runtime.plan_plugins('install', ['app'])

    assert payload['databaseAvailable'] is False
    assert payload['databaseError'] == 'db unavailable'


def test_plugin_runtime_record_plugin_operation_log_delegates_to_audit_use_case(tmp_path: Path) -> None:
    """
    校验插件操作日志记录入口委托给组合式审计 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeAuditUseCase:
        """
        测试用插件审计 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件审计 use case。
            """
            self.payload: dict[str, object] | None = None
            self.dry_run: bool | None = None
            self.continue_on_error: bool | None = None

        async def record_plugin_operation_log(
            self,
            payload: dict[str, object],
            *,
            dry_run: bool,
            continue_on_error: bool,
        ) -> None:
            """
            记录插件操作日志调用。

            :param payload: 插件操作结果负载
            :param dry_run: 是否预演
            :param continue_on_error: 失败后是否继续
            :return: None
            """
            self.payload = payload
            self.dry_run = dry_run
            self.continue_on_error = continue_on_error

    audit = FakeAuditUseCase()
    runtime.audit = audit
    payload = {'ok': True, 'pluginId': 'demo'}

    asyncio.run(runtime.record_plugin_operation_log(payload, dry_run=False, continue_on_error=True))

    assert audit.payload is payload
    assert audit.dry_run is False
    assert audit.continue_on_error is True


def test_plugin_runtime_record_plugin_failure_state_delegates_to_audit_use_case(tmp_path: Path) -> None:
    """
    校验插件失败状态记录入口委托给组合式审计 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeAuditUseCase:
        """
        测试用插件审计 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件审计 use case。
            """
            self.payload: dict[str, object] | None = None
            self.default_message: str | None = None

        async def record_plugin_failure_state(
            self,
            payload: dict[str, object],
            default_message: str,
        ) -> None:
            """
            记录插件失败状态调用。

            :param payload: 插件操作返回负载
            :param default_message: 缺省失败信息
            :return: None
            """
            self.payload = payload
            self.default_message = default_message

    audit = FakeAuditUseCase()
    runtime.audit = audit
    payload = {'ok': False, 'pluginId': 'demo'}

    asyncio.run(runtime.record_plugin_failure_state(payload, '默认失败'))

    assert audit.payload is payload
    assert audit.default_message == '默认失败'


def test_record_plugin_failure_state_logs_and_swallows_persistence_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    校验失败状态辅助写入异常会记录日志且不影响主流程。

    :param monkeypatch: pytest monkeypatch对象
    :return: None
    """
    logged_messages = []

    class BrokenStateGateway:
        """
        测试用异常状态网关。
        """

        @staticmethod
        def get_async_session_local() -> None:
            """
            模拟获取数据库会话失败。

            :return: None
            """
            raise RuntimeError('db unavailable')

    def fake_exception(message: str, *args: object) -> None:
        logged_messages.append(message % args)

    monkeypatch.setattr(audit_module.logger, 'exception', fake_exception)
    use_case = PluginAuditUseCase(SimpleNamespace(state_gateway=BrokenStateGateway()))

    asyncio.run(use_case.record_plugin_failure_state({'ok': False, 'pluginId': 'demo'}, '失败'))

    assert logged_messages == ['记录插件失败状态失败：plugin_id=demo']


def test_plugin_runtime_batch_plugins_dry_run_returns_plan(tmp_path: Path) -> None:
    """
    校验插件批量执行 dry-run 只返回拓扑计划，执行汇总只统计显式选择插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - base
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'base',
        """
id: base
name: Base
version: 1.0.0
enabled: true
backend:
  module: plugins.base
""",
    )

    payload = asyncio.run(build_runtime(backend_root).batch_plugins('install', ['app'], dry_run=True))

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['continueOnError'] is False
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}


def test_plugin_runtime_batch_plugins_delegates_to_batch_use_case(tmp_path: Path) -> None:
    """
    校验插件批量执行入口委托给组合式批量 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeBatchUseCase:
        """
        测试用插件批量 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件批量 use case。
            """
            self.operation: str | None = None
            self.plugin_ids: list[str] | None = None
            self.dry_run: bool | None = None
            self.continue_on_error: bool | None = None

        async def batch_plugins(
            self,
            operation: str,
            plugin_ids: list[str] | None = None,
            *,
            dry_run: bool = False,
            continue_on_error: bool = False,
        ) -> dict:
            """
            记录批量执行调用。

            :param operation: 批量操作类型
            :param plugin_ids: 插件ID列表
            :param dry_run: 是否仅预演
            :param continue_on_error: 失败后是否继续
            :return: 测试负载
            """
            self.operation = operation
            self.plugin_ids = plugin_ids
            self.dry_run = dry_run
            self.continue_on_error = continue_on_error
            return {'ok': True, 'operation': operation, 'pluginIds': plugin_ids}

    batch = FakeBatchUseCase()
    runtime.batch = batch

    payload = asyncio.run(
        runtime.batch_plugins(
            'install',
            ['demo'],
            dry_run=True,
            continue_on_error=True,
        )
    )

    assert batch.operation == 'install'
    assert batch.plugin_ids == ['demo']
    assert batch.dry_run is True
    assert batch.continue_on_error is True
    assert payload == {'ok': True, 'operation': 'install', 'pluginIds': ['demo']}


def test_plugin_runtime_execute_batch_plugin_item_delegates_to_batch_use_case(tmp_path: Path) -> None:
    """
    校验批量单项执行入口委托给组合式批量 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeBatchUseCase:
        """
        测试用插件批量 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件批量 use case。
            """
            self.operation: str | None = None
            self.plugin_id: str | None = None

        async def execute_batch_plugin_item(self, operation: str, plugin_id: str) -> dict:
            """
            记录批量单项执行调用。

            :param operation: 批量操作类型
            :param plugin_id: 插件ID
            :return: 测试负载
            """
            self.operation = operation
            self.plugin_id = plugin_id
            return {'ok': True, 'operation': operation, 'pluginId': plugin_id}

    batch = FakeBatchUseCase()
    runtime.batch = batch

    payload = asyncio.run(runtime.execute_batch_plugin_item('install', 'demo'))

    assert batch.operation == 'install'
    assert batch.plugin_id == 'demo'
    assert payload == {'ok': True, 'operation': 'install', 'pluginId': 'demo'}


def test_plugin_runtime_batch_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验批量 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeBatchContextService:
        """
        测试用批量上下文服务。
        """

        @staticmethod
        def resolve_plugin_capability(discovered_plugin: object) -> object:
            """
            返回测试 capability。

            :param discovered_plugin: 已发现插件
            :return: 测试对象
            """
            return sentinel

    context = FakeBatchContextService()
    assert runtime.batch.context is runtime.context

    runtime.batch.context = context

    capability = runtime.batch._resolve_plugin_capability(object())

    assert capability is sentinel


def test_plugin_runtime_batch_plugins_stops_when_plan_has_blockers(tmp_path: Path) -> None:
    """
    校验插件批量执行遇到计划阻塞时不会执行写操作。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
dependencies:
  plugins:
    - missing
""",
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    payload = asyncio.run(build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['app']))

    assert payload['ok'] is False
    assert payload['continueOnError'] is False
    assert payload['plan']['blockerCount'] == 1
    assert payload['executed'] == []
    assert payload['failed'] is None
    assert payload['summary'] == {'total': 1, 'succeeded': 0, 'failed': 0, 'skipped': 1}
    assert FakePluginService.upsert_called is False
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['message'] == '插件批量操作计划存在阻塞项，未执行任何写操作'


def test_plugin_runtime_batch_plugins_executes_requested_plugins_only(tmp_path: Path) -> None:
    """
    校验插件批量执行只执行显式选择插件，依赖插件只参与计划校验和排序展示。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'app',
        """
id: app
name: App
version: 1.0.0
backend:
  module: plugins.app
frontend:
  menus: []
dependencies:
  plugins:
    - base
""",
    )
    write_manifest(
        backend_root / 'plugins' / 'base',
        """
id: base
name: Base
version: 1.0.0
enabled: true
backend:
  module: plugins.base
frontend:
  menus: []
""",
    )
    create_controller_dir(backend_root / 'plugins' / 'app')
    create_controller_dir(backend_root / 'plugins' / 'base')
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
    FakePluginService.plugin_list = [
        SimpleNamespace(plugin_id='base', installed_version='1.0.0', enabled='0', status='installed')
    ]

    payload = asyncio.run(build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['app']))

    assert payload['ok'] is True
    assert payload['plan']['orderedPluginIds'] == ['base', 'app']
    assert payload['plan']['requestedPluginIds'] == ['app']
    assert [item['pluginId'] for item in payload['executed']] == ['app']
    assert all(item['status'] == 'success' for item in payload['executed'])
    assert all(isinstance(item['durationMs'], int) for item in payload['executed'])
    assert payload['summary'] == {'total': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0}
    assert payload['failed'] is None
    assert len(FakePluginService.operation_logs) == 1
    assert FakePluginService.operation_logs[0].payload['summary']['succeeded'] == 1


def test_plugin_runtime_batch_plugins_continue_on_error_runs_remaining_items(tmp_path: Path) -> None:
    """
    校验插件批量执行开启 continue-on-error 后会继续执行后续插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    for plugin_id in ['alpha', 'beta', 'gamma']:
        write_manifest(
            backend_root / 'plugins' / plugin_id,
            f"""
id: {plugin_id}
name: {plugin_id.title()}
version: 1.0.0
enabled: true
backend:
  module: plugins.{plugin_id}
frontend:
  menus: []
""",
        )

    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()
    FakePluginService.operation_logs = [
        SimpleNamespace(
            payload={'ok': True, 'operation': 'install', 'pluginId': 'demo', 'message': 'installed'},
            dry_run=False,
            continue_on_error=False,
        ),
        SimpleNamespace(
            payload={'ok': True, 'operation': 'install', 'pluginId': 'other', 'message': 'other installed'},
            dry_run=False,
            continue_on_error=False,
        ),
    ]
    runtime = build_runtime_with_gateway(backend_root, gateway)
    executed_plugin_ids = []

    async def fake_execute(operation: str, plugin_id: str) -> dict[str, object]:
        """
        测试用单插件执行函数。

        :param operation: 批量操作类型
        :param plugin_id: 插件ID
        :return: 单插件执行负载
        """
        executed_plugin_ids.append(plugin_id)
        return {
            'ok': plugin_id != 'beta',
            'message': '失败' if plugin_id == 'beta' else '成功',
            'pluginId': plugin_id,
        }

    runtime.execute_batch_plugin_item = fake_execute

    payload = asyncio.run(runtime.batch_plugins('install', ['alpha', 'beta', 'gamma'], continue_on_error=True))

    assert payload['ok'] is False
    assert payload['continueOnError'] is True
    assert executed_plugin_ids == ['alpha', 'beta', 'gamma']
    assert [item['pluginId'] for item in payload['executed']] == ['alpha', 'beta', 'gamma']
    assert payload['failed']['pluginId'] == 'beta'
    assert payload['summary'] == {'total': 3, 'succeeded': 2, 'failed': 1, 'skipped': 0}


def test_plugin_runtime_batch_plugins_dry_run_does_not_record_operation_log(tmp_path: Path) -> None:
    """
    校验插件批量执行 dry-run 不写入审计日志。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus: []
""",
    )
    gateway = FakePluginRuntimeGateway()
    FakePluginService.reset()

    payload = asyncio.run(
        build_runtime_with_gateway(backend_root, gateway).batch_plugins('install', ['demo'], dry_run=True)
    )

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert FakePluginService.operation_logs == []


def test_plugin_runtime_install_deps_dry_run_returns_plan(tmp_path: Path) -> None:
    """
    校验插件依赖安装 dry-run 返回安装计划且不执行安装。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    expected_plan_count = 3
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: 演示插件
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
dependencies:
  python:
    - missing-python
  npm:
    - missing-npm
  npmDev:
    - missing-dev-npm
""",
    )

    payload = build_runtime(backend_root).install_plugin_dependencies('demo', dry_run=True)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['planCount'] == expected_plan_count
    assert payload['plan'][0]['kind'] == 'python'
    assert payload['plan'][0]['command'][1:4] == ['-m', 'pip', 'install']
    assert payload['plan'][1]['kind'] == 'npm'
    assert payload['plan'][1]['command'] == ['npm', 'install', 'missing-npm']
    assert payload['plan'][2]['kind'] == 'npmDev'
    assert payload['plan'][2]['command'] == ['npm', 'install', '--save-dev', 'missing-dev-npm']


def test_plugin_runtime_install_plugin_dependencies_delegates_to_dependency_use_case(tmp_path: Path) -> None:
    """
    校验插件依赖安装入口委托给组合式依赖 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')

    class FakeDependencyUseCase:
        """
        测试用插件依赖 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件依赖 use case。
            """
            self.plugin_id: str | None = None
            self.dry_run: bool | None = None

        def install_plugin_dependencies(self, plugin_id: str, *, dry_run: bool = False) -> dict:
            """
            记录插件依赖安装调用。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dry_run = dry_run
            return {'ok': True, 'pluginId': plugin_id, 'dryRun': dry_run}

    dependency = FakeDependencyUseCase()
    runtime.dependency = dependency

    payload = runtime.install_plugin_dependencies('demo', dry_run=True)

    assert dependency.plugin_id == 'demo'
    assert dependency.dry_run is True
    assert payload == {'ok': True, 'pluginId': 'demo', 'dryRun': True}


def test_plugin_runtime_install_plugin_dependencies_from_result_delegates_to_dependency_use_case(
    tmp_path: Path,
) -> None:
    """
    校验插件依赖安装内部入口委托给组合式依赖 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    dependency_result = DependencyCheckResult(plugin_id='demo', items=[])

    class FakeDependencyUseCase:
        """
        测试用插件依赖 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件依赖 use case。
            """
            self.plugin_id: str | None = None
            self.dependency_result: DependencyCheckResult | None = None
            self.dry_run: bool | None = None
            self.discovered_plugin: object | None = None

        def install_plugin_dependencies_from_result(
            self,
            plugin_id: str,
            dependency_result: DependencyCheckResult,
            *,
            dry_run: bool = False,
            discovered_plugin: object | None = None,
        ) -> dict:
            """
            记录插件依赖安装内部调用。

            :param plugin_id: 插件ID
            :param dependency_result: 依赖检查结果
            :param dry_run: 是否仅预演
            :param discovered_plugin: 已发现插件
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dependency_result = dependency_result
            self.dry_run = dry_run
            self.discovered_plugin = discovered_plugin
            return {'ok': True, 'pluginId': plugin_id, 'fromResult': True}

    dependency = FakeDependencyUseCase()
    runtime.dependency = dependency

    payload = runtime.install_plugin_dependencies_from_result('demo', dependency_result, dry_run=True)

    assert dependency.plugin_id == 'demo'
    assert dependency.dependency_result is dependency_result
    assert dependency.dry_run is True
    assert dependency.discovered_plugin is None
    assert payload == {'ok': True, 'pluginId': 'demo', 'fromResult': True}


def test_plugin_runtime_dependency_install_uses_default_command_timeout(tmp_path: Path) -> None:
    """
    校验插件依赖安装命令使用默认超时时间。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
dependencies:
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)

    payload = runtime.install_plugin_dependencies('demo')

    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert gateway.commands[0][2] == PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS


def test_plugin_runtime_install_plugin_dependencies_from_result_async_delegates_to_dependency_use_case(
    tmp_path: Path,
) -> None:
    """
    校验插件依赖安装异步入口委托给组合式依赖 use case。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    dependency_result = DependencyCheckResult(plugin_id='demo', items=[])

    class FakeDependencyUseCase:
        """
        测试用插件依赖 use case。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件依赖 use case。
            """
            self.plugin_id: str | None = None
            self.dependency_result: DependencyCheckResult | None = None
            self.dry_run: bool | None = None
            self.discovered_plugin: object | None = None

        async def install_plugin_dependencies_from_result_async(
            self,
            plugin_id: str,
            dependency_result: DependencyCheckResult,
            *,
            dry_run: bool = False,
            discovered_plugin: object | None = None,
        ) -> dict:
            """
            记录插件依赖安装异步调用。

            :param plugin_id: 插件ID
            :param dependency_result: 依赖检查结果
            :param dry_run: 是否仅预演
            :param discovered_plugin: 已发现插件
            :return: 测试负载
            """
            self.plugin_id = plugin_id
            self.dependency_result = dependency_result
            self.dry_run = dry_run
            self.discovered_plugin = discovered_plugin
            return {'ok': True, 'pluginId': plugin_id, 'fromResultAsync': True}

    dependency = FakeDependencyUseCase()
    runtime.dependency = dependency

    payload = asyncio.run(
        runtime.install_plugin_dependencies_from_result_async('demo', dependency_result, dry_run=True)
    )

    assert dependency.plugin_id == 'demo'
    assert dependency.dependency_result is dependency_result
    assert dependency.dry_run is True
    assert dependency.discovered_plugin is None
    assert payload == {'ok': True, 'pluginId': 'demo', 'fromResultAsync': True}


def test_plugin_runtime_dependency_install_async_uses_default_command_timeout(tmp_path: Path) -> None:
    """
    校验插件依赖异步安装命令使用默认超时时间。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
backend:
  module: plugins.demo
dependencies:
  python:
    - missing-python
""",
    )
    gateway = FakePluginRuntimeGateway()
    runtime = build_runtime_with_gateway(backend_root, gateway)
    discovered_plugin = runtime.context.get_discovered_plugin('demo')
    assert discovered_plugin is not None
    dependency_result = runtime.dependencies.dependency_checker.check_manifest(discovered_plugin.manifest)

    payload = asyncio.run(
        runtime.install_plugin_dependencies_from_result_async(
            'demo',
            dependency_result,
            discovered_plugin=discovered_plugin,
        )
    )

    assert payload['ok'] is True
    assert len(gateway.commands) == 1
    assert gateway.commands[0][2] == PLUGIN_DEPENDENCY_INSTALL_TIMEOUT_SECONDS


def test_plugin_runtime_dependency_use_case_uses_injected_context_service(tmp_path: Path) -> None:
    """
    校验依赖 use case 通过显式注入的 context service 使用上下文能力。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    runtime = build_runtime(tmp_path / 'backend')
    sentinel = object()

    class FakeDependencyContextService:
        """
        测试用依赖上下文服务。
        """

        @staticmethod
        def with_plugin_capability(payload: dict, discovered_plugin: object | None) -> dict:
            """
            记录 capability 附加调用。

            :param payload: 响应负载
            :param discovered_plugin: 已发现插件
            :return: 附加后的响应负载
            """
            payload['contextPlugin'] = discovered_plugin
            return payload

    context = FakeDependencyContextService()
    assert runtime.dependency.context is runtime.context

    runtime.dependency.context = context

    payload = runtime.dependency._with_plugin_capability({'ok': True}, sentinel)

    assert payload == {'ok': True, 'contextPlugin': sentinel}


def test_plugin_runtime_blocks_state_changes_in_service_mode(tmp_path: Path) -> None:
    """
    校验服务运行模式下阻断插件状态变更。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
""",
    )
    runtime = build_runtime(backend_root)
    runtime.dependencies.runtime_environment.backend_runtime_mode = 'service'

    payload = asyncio.run(runtime.install_plugin('demo', dry_run=True))

    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['capability']['backendRuntimeManageable'] is False
    assert 'install' in payload['capability']['blockedOperations']


def test_plugin_runtime_blocks_frontend_plugin_dependency_install_in_built_mode(tmp_path: Path) -> None:
    """
    校验已构建前端模式下阻断前端源码插件依赖安装。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    write_manifest(
        backend_root / 'plugins' / 'demo',
        """
id: demo
name: Demo
version: 1.0.0
enabled: true
backend:
  module: plugins.demo
frontend:
  menus:
    - name: Demo
      path: demo
      component: plugin/demo/index
      perms: demo:list
permissions:
  - demo:list
dependencies:
  npm:
    - missing-npm
""",
    )
    create_frontend_view(backend_root, 'demo')
    runtime = build_runtime(backend_root)
    runtime.dependencies.runtime_environment.frontend_mode = 'built'

    payload = runtime.install_plugin_dependencies('demo', dry_run=True)

    assert payload['ok'] is False
    assert payload['status'] == 'blocked'
    assert payload['capability']['frontendRuntimeManageable'] is False
    assert 'dependency_install' in payload['capability']['blockedOperations']
