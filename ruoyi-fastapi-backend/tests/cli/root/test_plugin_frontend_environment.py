import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from cli.exit_codes import SUCCESS

pytestmark = pytest.mark.contract
SDK_FILES = ('pluginBridge.js', 'pluginBridge.d.ts', 'pluginBridge.sdk.json')


@pytest.mark.parametrize('framework', ['vue2', 'vue3'])
def test_cold_cli_preserves_frontend_framework_across_scaffold_sdk_and_dependency_lock(
    tmp_path: Path,
    backend_dir: Path,
    untracked_bundle_project: Path,
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
    framework: str,
) -> None:
    """
    校验独立进程从框架环境变量启动后，模板、SDK 与依赖锁选择相同工程。

    所有宿主文件位于临时目录；创建和锁定只预演，SDK 更新仅修改测试副本。
    """
    backend = tmp_path / 'backend'
    frontend_container = tmp_path / 'ruoyi-fastapi-frontend'
    for host_framework in ('vue2', 'vue3'):
        frontend = frontend_container / host_framework / 'web'
        source = frontend / 'src' / 'utils'
        source.mkdir(parents=True)
        (frontend / 'package.json').write_text(
            json.dumps({'dependencies': {'vue': f'^{host_framework[-1]}.0.0'}}), encoding='utf-8'
        )
        original_source = backend_dir.parent / 'ruoyi-fastapi-frontend' / host_framework / 'web' / 'src' / 'utils'
        for name in SDK_FILES:
            (source / name).write_bytes((original_source / name).read_bytes())
    plugin = backend / 'plugins' / 'environment_demo'
    plugin.mkdir(parents=True)
    (plugin / 'plugin.yaml').write_text(
        yaml.safe_dump(
            {
                'id': 'environment_demo',
                'name': 'Environment Demo',
                'version': '1.0.0',
                'backend': {'module': 'plugins.environment_demo'},
                'dependencies': {
                    'frontend': {
                        'vue2': {'npm': ['vue2-renderer==2.0.0']},
                        'vue3': {'npm': ['vue3-renderer==3.0.0']},
                    }
                },
            }
        ),
        encoding='utf-8',
    )
    (plugin / '__init__.py').write_text('raise RuntimeError("must never import this plugin")\n', encoding='utf-8')
    environment = {
        key: value for key, value in os.environ.items() if key != 'APP_ENV' and not key.startswith(('RUOYI_', 'OIDC_'))
    }
    environment.update(
        RUOYI_PLUGIN_BACKEND_ROOT=str(backend),
        RUOYI_PLUGIN_FRONTEND_ROOT=str(frontend_container),
        RUOYI_PLUGIN_FRONTEND_FRAMEWORK=framework,
        RUOYI_FRONTEND_FRAMEWORK='vue3' if framework == 'vue2' else 'vue2',
        LOG_FILE_ENABLED='false',
    )
    original_files = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}

    created = run_cli_command(
        'plugin',
        'create',
        'environment_scaffold',
        '--frontend-framework',
        'auto',
        '--dry-run',
        '--output',
        'json',
        env=environment,
    )
    assert created.returncode == SUCCESS, created.stdout + created.stderr
    scaffold = json.loads(created.stdout)
    selected_frontend = frontend_container / framework / 'web'
    assert scaffold['frontendFramework'] == framework
    assert str(backend / 'plugins' / 'environment_scaffold') in scaffold['targetDirs']
    assert str(selected_frontend / 'plugins' / 'environment_scaffold') in scaffold['targetDirs']
    assert all(Path(item['path']).is_relative_to(tmp_path) for item in scaffold['files'])

    locked = run_cli_command(
        'plugin', 'lock-deps', 'environment_demo', '--dry-run', '--output', 'json', env=environment
    )
    assert locked.returncode == SUCCESS, locked.stdout + locked.stderr
    lock_payload = json.loads(locked.stdout)
    lockfile = yaml.safe_load(lock_payload['lockfile'])
    assert Path(lock_payload['outputFile']) == plugin / 'plugin.lock.yaml'
    assert lockfile['frontendFramework'] == framework
    assert [item['requirement'] for item in lockfile['npm']] == [f'{framework}-renderer=={framework[-1]}.0.0']
    assert lock_payload['written'] is False
    assert original_files == {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}

    updated = run_cli_command(
        'plugin',
        'sdk',
        'update',
        str(untracked_bundle_project),
        '--frontend-framework',
        'auto',
        '--force',
        '--output',
        'json',
        env=environment,
    )
    assert updated.returncode == SUCCESS, updated.stdout + updated.stderr
    assert json.loads(updated.stdout)['updated'] is True
    metadata = json.loads((untracked_bundle_project / 'web/vendor/pluginBridge.sdk.json').read_text(encoding='utf-8'))
    assert metadata['source'] == {
        'project': 'RuoYi-FastAPI',
        'directory': f'ruoyi-fastapi-frontend/{framework}/web/src/utils',
    }
    host_files = {
        path: content for path, content in original_files.items() if not path.is_relative_to(untracked_bundle_project)
    }
    assert host_files == {
        path: path.read_bytes()
        for path in tmp_path.rglob('*')
        if path.is_file() and not path.is_relative_to(untracked_bundle_project)
    }
