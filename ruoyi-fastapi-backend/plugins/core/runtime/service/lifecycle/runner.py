from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from ..responses import PluginLifecycleResponse

TContext = TypeVar('TContext')
TStepResult = PluginLifecycleResponse | None


class PluginLifecycleStepFailed(Exception):
    """
    插件生命周期步骤执行失败。
    """

    def __init__(self, step_name: str, original_error: Exception) -> None:
        """
        初始化生命周期步骤失败异常。

        :param step_name: 失败步骤名称
        :param original_error: 原始异常
        """
        super().__init__(str(original_error))
        self.step_name = step_name
        self.original_error = original_error


@dataclass(slots=True)
class PluginLifecycleStepStop:
    """
    插件生命周期步骤中止结果。
    """

    step_name: str
    payload: PluginLifecycleResponse


@dataclass(slots=True)
class PluginLifecycleStep(Generic[TContext]):
    """
    插件生命周期声明式步骤。
    """

    name: str
    handler: Callable[[TContext], Awaitable[TStepResult]]


@dataclass(slots=True)
class PluginLifecycleStepRunResult(Generic[TContext]):
    """
    插件生命周期步骤运行结果。
    """

    context: TContext
    stop: PluginLifecycleStepStop | None = None


class PluginLifecycleStepRunner(Generic[TContext]):
    """
    插件生命周期声明式步骤运行器。
    """

    def __init__(self, steps: list[PluginLifecycleStep[TContext]]) -> None:
        """
        初始化生命周期步骤运行器。

        :param steps: 生命周期步骤列表
        """
        self.steps = steps

    async def run(self, context: TContext) -> PluginLifecycleStepRunResult[TContext]:
        """
        按顺序执行生命周期步骤。

        :param context: 生命周期上下文
        :return: 生命周期运行结果
        """
        for step in self.steps:
            try:
                payload = await step.handler(context)
            except Exception as exc:
                raise PluginLifecycleStepFailed(step.name, exc) from exc
            if payload is not None:
                return PluginLifecycleStepRunResult(context=context, stop=PluginLifecycleStepStop(step.name, payload))

        return PluginLifecycleStepRunResult(context=context)
