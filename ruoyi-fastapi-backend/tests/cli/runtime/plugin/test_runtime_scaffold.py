# ruff: noqa: F403, F405

import cli.runtime.plugin.scaffold.payload as scaffold_payload_module

from .conftest import *


class LazyPluginGateway:
    """
    测试用 CLI 插件网关，验证开发者能力可懒解析运行时依赖。
    """

    def __init__(self, backend_root: Path) -> None:
        """
        初始化测试用 CLI 插件网关。

        :param backend_root: 后端项目根目录
        :return: None
        """
        self.backend_root = backend_root
        self.runtime_environment_requested = False

    def get_core_runtime_environment(self) -> FakeRuntimeEnvironment:
        """
        获取测试运行时环境。

        :return: 测试运行时环境
        """
        self.runtime_environment_requested = True
        return FakeRuntimeEnvironment(self.backend_root)

    @staticmethod
    def build_exception_payload(message: str, exc: Exception) -> dict[str, object]:
        """
        构建测试异常负载。

        :param message: 异常消息
        :param exc: 异常对象
        :return: 异常负载
        """
        return {'ok': False, 'message': message, 'error': str(exc)}


def test_plugin_runtime_create_plugin_lazily_resolves_runtime_environment(tmp_path: Path) -> None:
    """
    校验插件模板创建会通过 CLI 网关懒解析运行时环境。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    backend_root = tmp_path / 'backend'
    backend_root.mkdir()
    plugin_gateway = LazyPluginGateway(backend_root)
    runtime = CliPluginRuntimeService(plugin_gateway=plugin_gateway)

    payload = runtime.create_plugin('demo', dry_run=True)

    assert payload['ok'] is True
    assert plugin_gateway.runtime_environment_requested is True


def test_plugin_runtime_create_plugin_dry_run_does_not_write_files(tmp_path: Path) -> None:
    """
    校验插件模板 dry-run 只返回写入计划，不写文件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('demo', dry_run=True)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['template'] == 'full-stack'
    assert payload['backend'] is True
    assert payload['frontend'] is True
    assert payload['test'] is True
    assert payload['backendTest'] is True
    assert payload['frontendTest'] is True
    assert str(backend_root / 'tests' / 'plugins' / 'demo') in payload['targetDirs']
    assert str(project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo') in payload['targetDirs']
    assert payload['files']
    assert not (backend_root / 'plugins' / 'demo' / 'plugin.yaml').exists()
    assert not (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').exists()
    assert not (project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js').exists()


def test_plugin_runtime_create_plugin_rejects_unsafe_plugin_id(tmp_path: Path) -> None:
    """
    校验插件模板创建会拒绝不安全的插件ID。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('../../evil', dry_run=True)

    assert payload['ok'] is False
    assert '插件ID必须' in str(payload['error'])
    assert not (project_root / 'evil').exists()


def test_plugin_runtime_create_plugin_uses_runtime_frontend_dir(tmp_path: Path) -> None:
    """
    校验插件模板创建使用运行时环境提供的前端目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'api-server'
    frontend_root = project_root / 'web-client'
    backend_root.mkdir(parents=True)

    payload = build_runtime(backend_root, frontend_root=frontend_root).create_plugin('demo')

    assert payload['ok'] is True
    assert (backend_root / 'plugins' / 'demo' / 'plugin.yaml').is_file()
    assert (frontend_root / 'plugins' / 'demo' / 'views' / 'index.vue').is_file()
    assert (frontend_root / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js').is_file()


def test_plugin_runtime_create_plugin_writes_backend_and_frontend_files(tmp_path: Path) -> None:
    """
    校验插件模板创建会写入后端和前端模板文件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('demo')

    assert payload['ok'] is True
    assert (backend_root / 'plugins' / 'demo' / 'plugin.yaml').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py').is_file()
    assert not (backend_root / 'plugins' / 'demo' / '__init__.py').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'controller' / '__init__.py').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'service' / '__init__.py').exists()
    assert (backend_root / 'plugins' / 'demo' / 'hooks.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'jobs.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'migrations' / '001_init.sql').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'seeds' / '001_seed.sql').is_file()
    assert (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').is_file()
    assert (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo' / 'views' / 'index.vue').is_file()
    assert (project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js').is_file()


def test_plugin_runtime_create_plugin_generates_checkable_template(tmp_path: Path) -> None:
    """
    校验插件模板创建后可立即通过插件结构检查。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)
    runtime = build_runtime(backend_root)

    create_payload = runtime.create_plugin('demo')
    check_payload = runtime.check_plugin('demo')

    assert create_payload['ok'] is True
    assert check_payload['ok'] is True
    assert check_payload['checks'][0]['structureErrors'] == []
    assert check_payload['checks'][0]['manifestWarnings'] == []
    assert (backend_root / 'plugins' / 'demo' / 'plugin.yaml').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'hooks.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'jobs.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'migrations' / '001_init.sql').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'seeds' / '001_seed.sql').is_file()
    assert (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').is_file()
    assert (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo' / 'views' / 'index.vue').is_file()
    assert (project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo' / 'pluginView.test.js').is_file()


def test_plugin_runtime_create_plugin_supports_optional_scaffold_parts(tmp_path: Path) -> None:
    """
    校验插件模板可以按参数跳过前端和可选后端示例。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)
    runtime = build_runtime(backend_root)

    create_payload = runtime.create_plugin(
        'demo',
        frontend=False,
        migration=False,
        seed=False,
        job=False,
        config=False,
        test=False,
    )
    check_payload = runtime.check_plugin('demo')

    assert create_payload['ok'] is True
    assert create_payload['frontend'] is False
    assert create_payload['migration'] is False
    assert create_payload['seed'] is False
    assert create_payload['job'] is False
    assert create_payload['config'] is False
    assert create_payload['test'] is False
    assert check_payload['ok'] is True
    assert check_payload['checks'][0]['structureErrors'] == []
    assert not (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'jobs.py').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'migrations' / '001_init.sql').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'seeds' / '001_seed.sql').exists()
    assert not (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').exists()
    assert not (project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo').exists()


def test_plugin_runtime_create_plugin_supports_minimal_template(tmp_path: Path) -> None:
    """
    校验 minimal 模板只生成后端最小插件和测试样例。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)
    runtime = build_runtime(backend_root)

    create_payload = runtime.create_plugin('demo', template='minimal')
    check_payload = runtime.check_plugin('demo')

    assert create_payload['ok'] is True
    assert create_payload['template'] == 'minimal'
    assert create_payload['backend'] is True
    assert create_payload['frontend'] is False
    assert create_payload['migration'] is False
    assert create_payload['seed'] is False
    assert create_payload['job'] is False
    assert create_payload['config'] is False
    assert create_payload['test'] is True
    assert check_payload['ok'] is True
    assert not (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo').exists()
    assert not (backend_root / 'plugins' / 'demo' / 'jobs.py').exists()
    assert (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').is_file()


def test_plugin_runtime_create_plugin_supports_scheduled_job_template(tmp_path: Path) -> None:
    """
    校验 scheduled-job 模板生成后端任务插件。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)
    runtime = build_runtime(backend_root)

    create_payload = runtime.create_plugin('demo', template='scheduled-job')
    check_payload = runtime.check_plugin('demo')

    assert create_payload['ok'] is True
    assert create_payload['template'] == 'scheduled-job'
    assert create_payload['backend'] is True
    assert create_payload['frontend'] is False
    assert create_payload['migration'] is False
    assert create_payload['seed'] is False
    assert create_payload['job'] is True
    assert create_payload['config'] is False
    assert check_payload['ok'] is True
    assert (backend_root / 'plugins' / 'demo' / 'jobs.py').is_file()
    assert not (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo').exists()


def test_plugin_runtime_create_plugin_supports_crud_page_template(tmp_path: Path) -> None:
    """
    校验 crud-page 模板生成后端接口、前端页面和测试样例。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    backend_root.mkdir(parents=True)
    runtime = build_runtime(backend_root)

    create_payload = runtime.create_plugin('demo', template='crud-page')
    check_payload = runtime.check_plugin('demo')

    assert create_payload['ok'] is True
    assert create_payload['template'] == 'crud-page'
    assert create_payload['backend'] is True
    assert create_payload['frontend'] is True
    assert create_payload['crud'] is True
    assert create_payload['job'] is False
    assert check_payload['ok'] is True
    assert check_payload['checks'][0]['manifestWarnings'] == []
    assert (backend_root / 'plugins' / 'demo' / 'controller' / 'demo_controller.py').is_file()
    assert (backend_root / 'plugins' / 'demo' / 'service' / 'demo_service.py').is_file()
    assert (backend_root / 'tests' / 'plugins' / 'demo' / 'test_ping.py').read_text(encoding='utf-8').find(
        'service_crud_flow'
    ) > -1
    assert (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo' / 'api' / 'demo.js').is_file()
    assert (project_root / 'ruoyi-fastapi-frontend' / 'plugins' / 'demo' / 'views' / 'index.vue').is_file()


def test_plugin_runtime_create_plugin_rejects_existing_target_dir(tmp_path: Path) -> None:
    """
    校验插件模板创建会拒绝覆盖已存在目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    (backend_root / 'plugins' / 'demo').mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('demo')

    assert payload['ok'] is False
    assert payload['conflicts'] == [str(backend_root / 'plugins' / 'demo')]


def test_plugin_runtime_create_plugin_rejects_existing_test_dir(tmp_path: Path) -> None:
    """
    校验插件模板创建会拒绝覆盖已存在后端测试目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    (backend_root / 'tests' / 'plugins' / 'demo').mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('demo')

    assert payload['ok'] is False
    assert payload['conflicts'] == [str(backend_root / 'tests' / 'plugins' / 'demo')]


def test_plugin_runtime_create_plugin_rejects_existing_frontend_test_dir(tmp_path: Path) -> None:
    """
    校验插件模板创建会拒绝覆盖已存在前端测试目录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    project_root = tmp_path / 'project'
    backend_root = project_root / 'ruoyi-fastapi-backend'
    frontend_test_root = project_root / 'ruoyi-fastapi-frontend' / 'tests' / 'plugins' / 'demo'
    backend_root.mkdir(parents=True)
    frontend_test_root.mkdir(parents=True)

    payload = build_runtime(backend_root).create_plugin('demo')

    assert payload['ok'] is False
    assert payload['conflicts'] == [str(frontend_test_root)]


def test_plugin_scaffold_builder_builds_payloads() -> None:
    """
    校验插件模板构建器生成响应负载。

    :return: None
    """
    scaffold_plan = {
        'template': 'minimal',
        'backend': True,
        'frontend': False,
        'files': [],
        'conflicts': [],
    }
    conflict_plan = {**scaffold_plan, 'conflicts': ['/tmp/demo']}

    success_payload = PluginScaffoldBuilder.build_success_payload('demo', scaffold_plan, dry_run=True)
    conflict_payload = PluginScaffoldBuilder.build_conflict_payload('demo', conflict_plan, dry_run=False)

    assert success_payload['ok'] is True
    assert success_payload['message'] == '插件模板预演完成'
    assert success_payload['template'] == 'minimal'
    assert conflict_payload['ok'] is False
    assert conflict_payload['conflicts'] == ['/tmp/demo']
    assert conflict_payload['exit_code'] == RUNTIME_ERROR


def test_plugin_scaffold_plan_payload_model_preserves_existing_contract(tmp_path: Path) -> None:
    """
    校验插件模板写入计划结构化负载保持既有 JSON 契约。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    file_path = tmp_path / 'plugins' / 'demo' / 'plugin.yaml'
    payload_model = getattr(scaffold_payload_module, 'PluginScaffoldPlanPayload', None)
    assert payload_model is not None

    payload = payload_model(
        template='minimal',
        backend=True,
        frontend=False,
        migration=False,
        seed=False,
        job=False,
        config=False,
        crud=False,
        test=True,
        backend_test=True,
        frontend_test=False,
        target_dirs=[str(tmp_path / 'plugins' / 'demo')],
        files=[(file_path, 'id: demo\n')],
        conflicts=[],
    ).to_payload()

    assert payload == {
        'backend': True,
        'frontend': False,
        'template': 'minimal',
        'migration': False,
        'seed': False,
        'job': False,
        'config': False,
        'crud': False,
        'test': True,
        'backendTest': True,
        'frontendTest': False,
        'targetDirs': [str(tmp_path / 'plugins' / 'demo')],
        'files': [{'path': str(file_path), 'content': 'id: demo\n'}],
        'conflicts': [],
    }


def test_plugin_scaffold_success_payload_model_preserves_existing_contract() -> None:
    """
    校验插件模板创建成功结构化负载保持既有 JSON 契约。

    :return: None
    """
    scaffold_plan = {
        'template': 'minimal',
        'backend': True,
        'frontend': False,
        'files': [],
        'conflicts': [],
    }

    payload_model = getattr(scaffold_payload_module, 'PluginScaffoldSuccessPayload', None)
    assert payload_model is not None

    payload = payload_model('demo', scaffold_plan, dry_run=True).to_payload()

    assert payload == {
        'ok': True,
        'message': '插件模板预演完成',
        'pluginId': 'demo',
        'dryRun': True,
        **scaffold_plan,
    }


def test_plugin_scaffold_conflict_payload_model_preserves_existing_contract() -> None:
    """
    校验插件模板目录冲突结构化负载保持既有 JSON 契约。

    :return: None
    """
    scaffold_plan = {
        'template': 'minimal',
        'backend': True,
        'frontend': False,
        'files': [],
        'conflicts': ['/tmp/demo'],
    }

    payload_model = getattr(scaffold_payload_module, 'PluginScaffoldConflictPayload', None)
    assert payload_model is not None

    payload = payload_model('demo', scaffold_plan, dry_run=False, failure_code=RUNTIME_ERROR).to_payload()

    assert payload == {
        'ok': False,
        'message': '插件目录已存在，拒绝覆盖',
        'pluginId': 'demo',
        'dryRun': False,
        **scaffold_plan,
        'exit_code': RUNTIME_ERROR,
    }
