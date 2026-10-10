import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

CLI_PROCESS_TIMEOUT_SECONDS = 60


@pytest.fixture
def backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def run_cli_command(backend_dir: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    def _run_cli_command(*args: str, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, '-X', 'utf8', '-m', 'cli.main', *args],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
            timeout=CLI_PROCESS_TIMEOUT_SECONDS,
        )

    return _run_cli_command


@pytest.fixture
def run_text_cli_command(
    run_cli_command: Callable[..., subprocess.CompletedProcess[str]],
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def _run_text_cli_command(*args: str) -> subprocess.CompletedProcess[str]:
        return run_cli_command('--color=never', '--icon=none', *args)

    return _run_text_cli_command


@pytest.fixture
def run_cli_completion_command(
    backend_dir: Path,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def _run_cli_completion_command(
        *,
        comp_words: str,
        comp_cword: int | str,
        instruction: str = 'bash_complete',
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, '-X', 'utf8', '-m', 'cli.main'],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
            timeout=CLI_PROCESS_TIMEOUT_SECONDS,
            env={
                **os.environ,
                'COMP_WORDS': comp_words,
                'COMP_CWORD': str(comp_cword),
                '_RUOYI_COMPLETE': instruction,
            },
        )

    return _run_cli_completion_command


@pytest.fixture
def untracked_bundle_project(tmp_path: Path) -> Path:
    """
    创建带未跟踪 SDK 的隔离 bundle 工程，供 CLI 检查与更新测试复用。

    :param tmp_path: pytest 临时目录
    :return: 不包含可执行业务插件的测试工程目录
    """
    root = tmp_path / 'example'
    vendor = root / 'web' / 'vendor'
    vendor.mkdir(parents=True)
    (root / 'plugin.yaml').write_text(
        'manifestVersion: 2\nid: example\nname: Example\nversion: 1.0.0\n'
        'backend:\n  module: plugins.example\n  entrypoint: plugins.example:create_plugin\n  integration: asgi\n'
        'frontend:\n  delivery:\n    type: bundle\n',
        encoding='utf-8',
    )
    (root / '__init__.py').write_text('raise RuntimeError("must never import this project")\n', encoding='utf-8')
    for name in ('pluginBridge.js', 'pluginBridge.d.ts'):
        (vendor / name).write_text('old untracked SDK\n', encoding='utf-8')
    return root


@pytest.fixture
def parse_json_stdout() -> Callable[[subprocess.CompletedProcess[str]], dict[str, Any]]:
    def _parse_json_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        return json.loads(completed.stdout)

    return _parse_json_stdout


@pytest.fixture
def assert_check_payload_contract() -> Callable[[dict[str, Any], bool], None]:
    def _assert_check_payload_contract(payload: dict[str, Any], allow_exit_code: bool) -> None:
        assert isinstance(payload, dict)
        assert isinstance(payload.get('ok'), bool)
        assert isinstance(payload.get('message'), str)

        if payload['ok']:
            if 'error' in payload:
                assert isinstance(payload['error'], str)
            if 'exit_code' in payload:
                assert isinstance(payload['exit_code'], int)
        else:
            assert isinstance(payload.get('error'), str)
            if allow_exit_code:
                assert isinstance(payload.get('exit_code'), int)

    return _assert_check_payload_contract
