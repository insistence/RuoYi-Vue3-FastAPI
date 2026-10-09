import asyncio
import json
import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import typer
from typer.testing import CliRunner

from cli.core import CliContextFactory, CliExecutionService
from cli.exit_codes import ARGUMENT_ERROR, RUNTIME_ERROR, SUCCESS
from cli.groups.plugin.artifact_controller import PluginArtifactCommandController
from cli.groups.plugin.commands.artifact import register_artifact_commands

DIGEST = 'a' * 64
GENERATION = 'b' * 32
TARGET = {'pluginId': 'demo', 'digest': DIGEST, 'generation': GENERATION, 'expectedWorkers': 3}


@pytest.fixture(autouse=True)
def preserve_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    恢复命令运行前的环境选择，避免影响其他 CLI 测试。

    :param monkeypatch: pytest 环境隔离工具
    :return: None
    """
    monkeypatch.setenv('APP_ENV', os.environ.get('APP_ENV', 'dev'))


def result_payload(reason: str = 'converged') -> dict[str, Any]:
    """
    构造服务已经完成的等待结果，验证 CLI 保留其字段和退出语义。

    :param reason: 等待服务返回的最终原因
    :return: 固定结构的等待结果
    """
    return {
        'ok': reason == 'converged',
        'operation': 'release_wait',
        'reason': reason,
        'message': '等待结果',
        'target': dict(TARGET),
        'lastObserved': {'pluginId': 'demo', 'targetDigest': DIGEST, 'generation': GENERATION},
        'attempts': 1,
        'elapsedSeconds': 0.125,
        'timeoutSeconds': 0,
        'intervalSeconds': 0.25,
    }


def controller_for(service: Any, *, config_factory: Any = object) -> PluginArtifactCommandController:
    """
    创建使用真实输出与异步执行器的控制器，隔离部署依赖及日志。

    :param service: 只读发布服务替身
    :param config_factory: 可记录或拒绝部署配置加载的工厂
    :return: 不连接外部服务的被测控制器
    """
    context = CliContextFactory(
        runtime_state=SimpleNamespace(suppress_logs=lambda: None, suppress_sqlalchemy_logs=lambda: None)
    )
    return PluginArtifactCommandController(
        context_factory=context,
        execution_service=CliExecutionService(),
        config_factory=config_factory,
        service_factory=lambda _: service,
    )


def app_for(controller: PluginArtifactCommandController) -> typer.Typer:
    """
    创建包含制品发布命令的隔离应用。

    :param controller: 被测制品命令控制器
    :return: Typer 测试应用
    """
    app = typer.Typer()
    register_artifact_commands(app, lambda: controller)
    return app


def wait_arguments(*overrides: str) -> list[str]:
    """
    提供无需维护确认的生产环境单次等待命令。

    :param overrides: 附加或覆盖的 CLI 选项
    :return: 命令行参数列表
    """
    return [
        'release',
        'wait',
        'demo',
        DIGEST,
        '--generation',
        GENERATION,
        '--expected-workers',
        '3',
        '--timeout',
        '0',
        '--interval',
        '0.25',
        '--env',
        'prod',
        '--output',
        'json',
        *overrides,
    ]


@pytest.mark.parametrize(
    'reason',
    [
        'converged',
        'not_converged',
        'timeout',
        'target_missing',
        'target_changed',
        'target_disabled',
        'worker_failed',
        'unavailable',
        'invalid_observation',
    ],
)
def test_wait_outputs_exactly_one_final_json_and_preserves_service_exit_semantics(reason: str) -> None:
    """
    成功、超时和各种失败都只输出一个最终对象，并使用统一退出码。

    :param reason: 服务的终止原因
    :return: None
    """
    payload = result_payload(reason)
    wait = AsyncMock(return_value=payload)
    result = CliRunner().invoke(app_for(controller_for(SimpleNamespace(wait=wait))), wait_arguments())

    assert result.exit_code == (SUCCESS if payload['ok'] else RUNTIME_ERROR), result.output
    assert json.loads(result.stdout) == payload
    assert result.stderr == ''
    wait.assert_awaited_once_with(
        'demo',
        DIGEST,
        expected_generation=GENERATION,
        expected_workers=3,
        timeout_seconds=0.0,
        poll_interval_seconds=0.25,
    )
    assert os.environ['APP_ENV'] == 'prod'


@pytest.mark.parametrize(
    'arguments',
    [
        ['release', 'wait'],
        ['release', 'wait', 'demo'],
        ['release', 'wait', 'demo', DIGEST, '--expected-workers', '3'],
        ['release', 'wait', 'demo', DIGEST, '--generation', GENERATION],
        wait_arguments('--expected-workers', '0'),
        wait_arguments('--expected-workers', '1.5'),
        wait_arguments('--expected-workers', 'true'),
        wait_arguments('--timeout', '-1'),
        wait_arguments('--maintenance'),
        wait_arguments('--allow-prod'),
        wait_arguments('--yes'),
        wait_arguments('--dry-run'),
    ],
)
def test_wait_requires_all_pins_and_rejects_write_options_before_loading_service(arguments: list[str]) -> None:
    """
    缺少固定目标、无效计数或写入选项均由参数层拒绝。

    :param arguments: 缺少必填项或包含不受支持选项的命令行
    :return: None
    """
    config = Mock(side_effect=AssertionError('参数错误时不能加载配置'))
    result = CliRunner().invoke(app_for(controller_for(SimpleNamespace(), config_factory=config)), arguments)
    assert result.exit_code == ARGUMENT_ERROR
    config.assert_not_called()


@pytest.mark.parametrize(
    'overrides',
    [
        {'plugin_id': '../demo'},
        {'plugin_id': 'd'},
        {'digest': 'a' * 63},
        {'digest': 'A' * 64},
        {'expected_generation': 'b' * 31},
        {'expected_generation': 'g' * 32},
        {'expected_workers': True},
        {'expected_workers': 1.5},
        {'expected_workers': 0},
        {'timeout_seconds': float('nan')},
        {'timeout_seconds': float('inf')},
        {'timeout_seconds': -1},
        {'timeout_seconds': True},
        {'poll_interval_seconds': float('nan')},
        {'poll_interval_seconds': float('inf')},
        {'poll_interval_seconds': float('-inf')},
        {'poll_interval_seconds': 0},
        {'poll_interval_seconds': -1},
        {'poll_interval_seconds': False},
    ],
)
def test_wait_controller_validates_before_context_and_service_creation(
    overrides: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """
    非法目标或非有限时间参数不能触发配置读取，也不会输出 NaN 或 Infinity。

    :param overrides: 替换正常调用的无效参数
    :param capsys: 标准输出捕获器
    :return: None
    """
    config = Mock(side_effect=AssertionError('不能读取配置'))
    controller = controller_for(SimpleNamespace(), config_factory=config)
    controller._context = Mock(side_effect=AssertionError('不能创建运行上下文'))
    arguments = {
        'plugin_id': 'demo',
        'digest': DIGEST,
        'env': 'prod',
        'output': 'json',
        'expected_generation': GENERATION,
        'expected_workers': 3,
        'timeout_seconds': 0,
        'poll_interval_seconds': 0.25,
        **overrides,
    }
    with pytest.raises(typer.Exit) as exited:
        controller.wait_release(**arguments)
    assert exited.value.exit_code == ARGUMENT_ERROR
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload['ok'] is False and payload['reason'] == 'invalid_arguments'
    assert payload['attempts'] == 0 and payload['lastObserved'] is None
    assert 'NaN' not in output.out and 'Infinity' not in output.out
    assert output.err == ''
    config.assert_not_called()
    controller._context.assert_not_called()


@pytest.mark.parametrize('option', ['--timeout', '--interval'])
@pytest.mark.parametrize('value', ['nan', 'inf', '-inf'])
def test_wait_cli_rejects_non_finite_durations(option: str, value: str) -> None:
    """
    命令行浮点解析不能让 NaN 或无穷大进入等待服务。

    :param option: 超时或查询间隔选项
    :param value: 非有限数值文本
    :return: None
    """
    config = Mock(side_effect=AssertionError('不能读取配置'))
    result = CliRunner().invoke(
        app_for(controller_for(SimpleNamespace(), config_factory=config)), wait_arguments(option, value)
    )
    assert result.exit_code == ARGUMENT_ERROR, result.output
    config.assert_not_called()


@pytest.mark.parametrize('exception', [asyncio.CancelledError, KeyboardInterrupt])
def test_wait_cli_cancellation_is_redacted_and_does_not_invent_progress(exception: type[BaseException]) -> None:
    """
    取消和用户中断都返回固定结果，不泄露异常文本或伪造已查询次数。

    :param exception: 异步取消或键盘中断异常类型
    :return: None
    """
    wait = AsyncMock(side_effect=exception('private-cancellation-detail'))
    result = CliRunner().invoke(app_for(controller_for(SimpleNamespace(wait=wait))), wait_arguments())
    assert result.exit_code == RUNTIME_ERROR, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == set(result_payload())
    assert payload['reason'] == 'cancelled' and payload['ok'] is False
    assert payload['target'] == TARGET
    assert payload['attempts'] is None and payload['lastObserved'] is None
    assert payload['elapsedSeconds'] >= 0
    assert 'private-cancellation-detail' not in result.output
    assert result.stderr == ''


def test_wait_initialization_failure_is_redacted_and_uses_final_result_schema() -> None:
    """
    部署配置初始化失败不能暴露连接凭据，仍返回同一最终结果结构。

    :return: None
    """
    config = Mock(side_effect=RuntimeError('private-database-password'))
    result = CliRunner().invoke(app_for(controller_for(SimpleNamespace(), config_factory=config)), wait_arguments())
    assert result.exit_code == RUNTIME_ERROR
    payload = json.loads(result.stdout)
    assert set(payload) == set(result_payload())
    assert payload['reason'] == 'unavailable'
    assert payload['attempts'] is None and payload['lastObserved'] is None
    assert 'private-database-password' not in result.output
    assert result.stderr == ''


def test_release_status_query_success_keeps_existing_ok_meaning() -> None:
    """
    查询未就绪发布仍表示查询成功，不改变已有 status 命令的退出契约。

    :return: None
    """
    payload = {'ok': True, 'releases': [{'pluginId': 'demo', 'status': 'pending_restart'}], 'workers': []}
    service = SimpleNamespace(status=AsyncMock(return_value=payload))
    result = CliRunner().invoke(
        app_for(controller_for(service)), ['release', 'status', '--plugin-id', 'demo', '--output', 'json']
    )
    assert result.exit_code == SUCCESS
    assert json.loads(result.stdout) == {**payload, 'env': 'dev'}
