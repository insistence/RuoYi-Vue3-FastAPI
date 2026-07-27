from pathlib import Path

import yaml

from .conftest import build_runtime


def test_plugin_runtime_allowlist_example_dry_run_returns_yaml_without_writing(tmp_path: Path) -> None:
    """校验允许列表示例 dry-run 只返回 YAML，不写入默认文件。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)

    payload = runtime.generate_plugin_dependency_allowlist_example(dry_run=True)

    output_path = backend_root / 'config' / 'plugin_dependency_allowlist.yaml'
    assert payload['ok'] is True
    assert payload['dryRun'] is True
    assert payload['written'] is False
    assert payload['outputFile'] == str(output_path)
    assert not output_path.exists()
    allowlist = yaml.safe_load(payload['allowlist'])
    assert allowlist['python']['openai']['versions'] == ['>=2.0.0,<3.0.0']
    assert allowlist['npm']['dayjs']['source'] == 'internal-npm'
    assert allowlist['npmDev']['vitest']['versions'] == ['>=3.0.0,<4.0.0']


def test_plugin_runtime_allowlist_example_writes_relative_output_path(tmp_path: Path) -> None:
    """校验允许列表示例命令可以写入后端根目录相对路径。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)

    payload = runtime.generate_plugin_dependency_allowlist_example(
        output_path='config/team_allowlist.yaml',
    )

    output_path = backend_root / 'config' / 'team_allowlist.yaml'
    assert payload['ok'] is True
    assert payload['dryRun'] is False
    assert payload['written'] is True
    assert payload['outputFile'] == str(output_path)
    assert output_path.read_text(encoding='utf-8') == payload['allowlist']


def test_plugin_runtime_allowlist_example_rejects_output_path_escape(tmp_path: Path) -> None:
    """校验允许列表示例输出路径不能逃逸后端项目根目录。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    escaped_allowlist = tmp_path / 'escaped_allowlist.yaml'

    payload = runtime.generate_plugin_dependency_allowlist_example(output_path='../escaped_allowlist.yaml')

    assert payload['ok'] is False
    assert '输出路径' in str(payload['error'])
    assert escaped_allowlist.exists() is False


def test_plugin_runtime_allowlist_example_rejects_existing_file_without_overwrite(tmp_path: Path) -> None:
    """校验允许列表示例文件已存在时必须显式 overwrite。"""
    backend_root = tmp_path / 'backend'
    runtime = build_runtime(backend_root)
    output_path = backend_root / 'config' / 'team_allowlist.yaml'
    output_path.parent.mkdir(parents=True)
    output_path.write_text('python: {}\n', encoding='utf-8')

    payload = runtime.generate_plugin_dependency_allowlist_example(
        output_path='config/team_allowlist.yaml',
    )

    assert payload['ok'] is False
    assert payload['written'] is False
    assert payload['outputFile'] == str(output_path)
    assert '已存在' in payload['message']
    assert output_path.read_text(encoding='utf-8') == 'python: {}\n'
