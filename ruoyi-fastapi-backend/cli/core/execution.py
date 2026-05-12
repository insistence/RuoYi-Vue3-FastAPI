import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cli.context import CliContext
from cli.exit_codes import RUNTIME_ERROR
from cli.output import CommandResult, OutputRenderer


@dataclass
class CliExecutionService:
    """
    CLI 执行与结果收口服务。

    :param output_renderer: 输出渲染器
    """

    output_renderer: OutputRenderer = field(default_factory=OutputRenderer)

    def run_async(self, coroutine: Any) -> Any:
        """
        执行异步协程并返回结果。

        :param coroutine: 待执行协程
        :return: 协程执行结果
        """
        return asyncio.run(coroutine)

    def complete_payload(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        default_exit_code: int = 0,
    ) -> None:
        """
        输出标准字典负载并结束命令。

        :param ctx: CLI 上下文
        :param payload: 标准结果字典
        :param default_exit_code: 默认退出码
        :return: None
        """
        self.output_renderer.complete_command(self.build_result(payload, default_exit_code=default_exit_code), ctx)

    def complete_result(
        self,
        ctx: CliContext,
        result: CommandResult,
    ) -> None:
        """
        输出命令结果对象并结束命令。

        :param ctx: CLI 上下文
        :param result: 命令执行结果对象
        :return: None
        """
        self.output_renderer.complete_command(result, ctx)

    def complete_payload_with_text(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        text_builder: Callable[[dict[str, Any]], Any],
        default_exit_code: int = 0,
        text_condition: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """
        按输出格式收口标准负载，必要时先转换为文本结果。

        :param ctx: CLI 上下文
        :param payload: 标准结果字典
        :param text_builder: 文本结果构建函数
        :param default_exit_code: 默认退出码
        :param text_condition: 文本模式下是否应用构建函数的判定函数
        :return: None
        """
        if ctx.output != 'text':
            self.complete_payload(ctx, payload, default_exit_code=default_exit_code)
            return

        result = self.build_result(payload, default_exit_code=default_exit_code)
        should_build_text = True
        if callable(text_condition) and isinstance(result.data, dict):
            should_build_text = bool(text_condition(result.data))
        if should_build_text and isinstance(result.data, dict):
            result.data = text_builder(result.data)
        self.complete_result(ctx, result)

    def complete_payload_result(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        text_builder: Callable[[dict[str, Any]], Any] | None = None,
        default_exit_code: int = 0,
        text_condition: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """
        统一收口标准负载，按输出格式决定是否渲染为文本结果。

        :param ctx: CLI 上下文
        :param payload: 标准结果字典
        :param text_builder: 文本结果构建函数
        :param default_exit_code: 默认退出码
        :param text_condition: 文本模式下是否应用构建函数的判定函数
        :return: None
        """
        if text_builder is None:
            self.complete_payload(ctx, payload, default_exit_code=default_exit_code)
            return
        self.complete_payload_with_text(
            ctx,
            payload,
            text_builder=text_builder,
            default_exit_code=default_exit_code,
            text_condition=text_condition,
        )

    @staticmethod
    def build_result(payload: dict[str, Any], *, default_exit_code: int = 0) -> CommandResult:
        """
        将标准字典负载转换为命令结果对象。

        :param payload: 标准结果字典
        :param default_exit_code: 默认退出码；当 payload 未显式提供 exit_code 且
            该值仍为 0 时，失败结果会统一回退到 `RUNTIME_ERROR`
        :return: 命令结果对象
        """
        result_payload = dict(payload)
        exit_code = result_payload.pop('exit_code', None)
        if exit_code is None:
            is_ok = bool(result_payload.get('ok', True))
            exit_code = default_exit_code if is_ok or default_exit_code != 0 else RUNTIME_ERROR
        return CommandResult(data=result_payload, exit_code=exit_code)
