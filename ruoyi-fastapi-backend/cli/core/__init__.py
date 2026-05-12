from dataclasses import dataclass, field

from cli.core.app_builder import CliApplicationBuilder, ProjectRuntimeLocator
from cli.core.completion_dispatcher import CompletionDispatcher
from cli.core.context_factory import CliContextFactory, CliRuntimeState
from cli.core.execution import CliExecutionService
from cli.output import OutputRenderer


@dataclass
class CoreServiceContainer:
    """
    CLI 核心服务容器。

    该容器负责统一装配输出渲染器、运行期状态、上下文工厂与执行服务，
    作为控制器、向导和 TUI 等编排层的默认依赖入口。

    :param output_renderer: 输出渲染器
    :param runtime_state: CLI 运行期状态对象
    """

    output_renderer: OutputRenderer = field(default_factory=OutputRenderer)
    runtime_state: CliRuntimeState = field(default_factory=CliRuntimeState)
    context_factory: CliContextFactory = field(init=False)
    execution_service: CliExecutionService = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化核心服务依赖图。

        :return: None
        """
        self.context_factory = CliContextFactory(
            runtime_state=self.runtime_state,
            output_renderer=self.output_renderer,
        )
        self.execution_service = CliExecutionService(output_renderer=self.output_renderer)


DEFAULT_CORE_SERVICES = CoreServiceContainer()

__all__ = [
    'DEFAULT_CORE_SERVICES',
    'CliApplicationBuilder',
    'CliContextFactory',
    'CliExecutionService',
    'CliRuntimeState',
    'CompletionDispatcher',
    'CoreServiceContainer',
    'ProjectRuntimeLocator',
]
