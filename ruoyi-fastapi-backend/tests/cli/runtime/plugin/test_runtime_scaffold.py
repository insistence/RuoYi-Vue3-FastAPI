# ruff: noqa: F403, F405

from .conftest import *


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
