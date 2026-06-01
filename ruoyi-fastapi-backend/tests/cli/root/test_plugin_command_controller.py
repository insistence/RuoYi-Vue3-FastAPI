import asyncio
import inspect
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from cli.exit_codes import DEPENDENCY_ERROR  # noqa: E402
from cli.groups.plugin.controller import PluginCommandController  # noqa: E402


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
        """
        构造危险命令上下文。

        :return: CLI上下文
        """
        return type('FakeContext', (), {'env': env, 'output': output})()


class FakeExecutionService:
    """
    测试用 CLI 执行服务。
    """

    def __init__(self) -> None:
        """
        初始化测试执行服务。

        :return: None
        """
        self.completed_payload: dict[str, Any] | None = None
        self.default_exit_code: int | None = None

    def run_async(self, value: Any) -> Any:
        """
        直接返回测试中的 awaitable 结果。

        :param value: 执行结果
        :return: 执行结果
        """
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
        """
        记录完成参数。

        :param ctx: CLI上下文
        :param payload: payload
        :param text_builder: 文本构造器
        :param default_exit_code: 默认退出码
        :return: None
        """
        self.completed_payload = payload
        self.default_exit_code = default_exit_code


class FakePresenter:
    """
    测试用 presenter。
    """

    @staticmethod
    def build_install_text(payload: dict[str, Any]) -> str:
        """
        构造安装文本。

        :param payload: payload
        :return: 文本
        """
        return str(payload)


class FakePluginRuntime:
    """
    测试用插件运行时。
    """

    async def install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        返回失败安装结果。

        :param plugin_id: 插件ID
        :param dry_run: 是否仅预演
        :return: 安装结果
        """
        return {'ok': False, 'message': '插件安装失败', 'pluginId': plugin_id}


def test_install_plugin_uses_failure_exit_code_when_payload_is_not_ok() -> None:
    """
    校验插件安装失败时 CLI 使用失败退出码。

    :return: None
    """
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
