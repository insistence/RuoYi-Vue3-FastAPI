import base64
import hashlib
from pathlib import Path

import yaml

from .conftest import build_runtime

EXPECTED_LOCK_ENTRY_COUNT = 2


def write_demo_dependency_manifest(backend_root: Path) -> None:
    """为 demo 插件补充外部依赖声明。"""
    manifest_path = backend_root / 'plugins' / 'demo' / 'plugin.yaml'
    manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    manifest['dependencies'] = {
        'python': ['openai>=2.0.0,<3.0.0'],
        'npm': ['dayjs>=1.11.0,<2.0.0'],
        'npmDev': [],
        'plugins': [],
    }
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding='utf-8')


def test_plugin_runtime_lock_dependencies_dry_run_returns_lockfile_template(tmp_path: Path) -> None:
    """校验插件依赖锁文件 dry-run 只返回锁文件模板，不写文件。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)

    payload = runtime.lock_plugin_dependencies('demo', dry_run=True)

    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['pluginId'] == 'demo'
    assert payload['outputFile'] == str(backend_root / 'plugins' / 'demo' / 'plugin.lock.yaml')
    assert payload['written'] is False
    assert payload['entryCount'] == EXPECTED_LOCK_ENTRY_COUNT
    assert 'resolvedVersion' in payload['warnings'][0]
    assert not (backend_root / 'plugins' / 'demo' / 'plugin.lock.yaml').exists()

    lockfile = yaml.safe_load(payload['lockfile'])
    assert lockfile['plugin'] == 'demo'
    assert lockfile['version'] == '0.1.0'
    assert lockfile['python'][0]['name'] == 'openai'
    assert lockfile['python'][0]['requirement'] == 'openai>=2.0.0,<3.0.0'
    assert lockfile['python'][0]['resolvedVersion'] == ''
    assert lockfile['python'][0]['hashes'] == []
    assert lockfile['npm'][0]['name'] == 'dayjs'
    assert lockfile['npm'][0]['integrity'] == ''


def test_plugin_runtime_lock_dependencies_writes_default_lockfile(tmp_path: Path) -> None:
    """校验插件依赖锁文件命令默认写入插件目录下的 plugin.lock.yaml。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)

    payload = runtime.lock_plugin_dependencies('demo')

    lockfile_path = backend_root / 'plugins' / 'demo' / 'plugin.lock.yaml'
    assert payload['ok'] is True
    assert payload['written'] is True
    assert payload['outputFile'] == str(lockfile_path)
    assert lockfile_path.is_file()
    assert yaml.safe_load(lockfile_path.read_text(encoding='utf-8'))['plugin'] == 'demo'


def test_plugin_runtime_lock_dependencies_rejects_existing_file_without_overwrite(tmp_path: Path) -> None:
    """校验已有锁文件时必须显式 overwrite。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)
    lockfile_path = backend_root / 'plugins' / 'demo' / 'plugin.lock.yaml'
    lockfile_path.write_text('plugin: existing\n', encoding='utf-8')

    payload = runtime.lock_plugin_dependencies('demo')

    assert payload['ok'] is False
    assert payload['written'] is False
    assert payload['outputFile'] == str(lockfile_path)
    assert '已存在' in payload['message']
    assert lockfile_path.read_text(encoding='utf-8') == 'plugin: existing\n'


def test_plugin_runtime_lock_dependencies_rejects_output_path_escape(tmp_path: Path) -> None:
    """校验插件依赖锁文件输出路径不能逃逸后端项目根目录。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)
    escaped_lockfile = tmp_path / 'escaped.lock.yaml'

    payload = runtime.lock_plugin_dependencies('demo', output_path='../escaped.lock.yaml')

    assert payload['ok'] is False
    assert '输出路径' in str(payload['error'])
    assert escaped_lockfile.exists() is False


def test_plugin_runtime_lock_dependencies_fills_lockfile_from_offline_artifacts(tmp_path: Path) -> None:
    """校验锁文件模板可以从本地离线制品反填版本和完整性校验值。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)
    offline_dir = tmp_path / 'artifacts'
    python_artifact = offline_dir / 'python' / 'openai-2.17.0-py3-none-any.whl'
    npm_artifact = offline_dir / 'npm' / 'dayjs-1.11.19.tgz'
    python_artifact.parent.mkdir(parents=True)
    npm_artifact.parent.mkdir(parents=True)
    python_artifact.write_bytes(b'wheel')
    npm_artifact.write_bytes(b'tgz')

    payload = runtime.lock_plugin_dependencies('demo', dry_run=True, offline_dir=str(offline_dir))

    assert payload['ok'] is True
    assert payload['artifactCount'] == EXPECTED_LOCK_ENTRY_COUNT
    assert payload['warnings'] == []
    lockfile = yaml.safe_load(payload['lockfile'])
    assert lockfile['python'][0]['resolvedVersion'] == '2.17.0'
    assert lockfile['python'][0]['hashes'] == [f'sha256:{hashlib.sha256(b"wheel").hexdigest()}']
    assert lockfile['npm'][0]['resolvedVersion'] == '1.11.19'
    expected_integrity = base64.b64encode(hashlib.sha512(b'tgz').digest()).decode('ascii')
    assert lockfile['npm'][0]['integrity'] == f'sha512-{expected_integrity}'


def test_plugin_runtime_lock_dependencies_filters_offline_artifacts_by_requirement(tmp_path: Path) -> None:
    """校验多个离线制品中只有一个满足版本声明时可以自动匹配。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)
    offline_dir = tmp_path / 'artifacts'
    old_python_artifact = offline_dir / 'python' / 'openai-1.9.0-py3-none-any.whl'
    valid_python_artifact = offline_dir / 'python' / 'openai-2.17.0-py3-none-any.whl'
    old_npm_artifact = offline_dir / 'npm' / 'dayjs-0.9.0.tgz'
    valid_npm_artifact = offline_dir / 'npm' / 'dayjs-1.11.19.tgz'
    valid_python_artifact.parent.mkdir(parents=True)
    valid_npm_artifact.parent.mkdir(parents=True)
    old_python_artifact.write_bytes(b'old-wheel')
    valid_python_artifact.write_bytes(b'wheel')
    old_npm_artifact.write_bytes(b'old-tgz')
    valid_npm_artifact.write_bytes(b'tgz')

    payload = runtime.lock_plugin_dependencies('demo', dry_run=True, offline_dir=str(offline_dir))

    assert payload['ok'] is True
    assert payload['warnings'] == []
    lockfile = yaml.safe_load(payload['lockfile'])
    assert lockfile['python'][0]['resolvedVersion'] == '2.17.0'
    assert lockfile['npm'][0]['resolvedVersion'] == '1.11.19'


def test_plugin_runtime_lock_dependencies_warns_when_offline_artifact_missing(tmp_path: Path) -> None:
    """校验本地离线制品缺失时保留锁文件占位并返回 warning。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    runtime.create_plugin('demo', frontend=True, dry_run=False)
    write_demo_dependency_manifest(backend_root)
    offline_dir = tmp_path / 'artifacts'

    payload = runtime.lock_plugin_dependencies('demo', dry_run=True, offline_dir=str(offline_dir))

    assert payload['ok'] is True
    assert payload['artifactCount'] == 0
    assert any('未找到离线制品：python openai' in warning for warning in payload['warnings'])
    assert any('未找到离线制品：npm dayjs' in warning for warning in payload['warnings'])
    lockfile = yaml.safe_load(payload['lockfile'])
    assert lockfile['python'][0]['resolvedVersion'] == ''
    assert lockfile['python'][0]['hashes'] == []
    assert lockfile['npm'][0]['resolvedVersion'] == ''
    assert lockfile['npm'][0]['integrity'] == ''
