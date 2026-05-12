import inspect
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, Generic, TypeVar

import typer

from cli.context import CliContext, OutputOption
from cli.core import DEFAULT_CORE_SERVICES, CliContextFactory, CliExecutionService
from cli.output import CommandResult
from cli.utils import NESTED_CLI_SUPPORT
from cli.wizard.preview import WIZARD_PREVIEW_RENDERER, WizardPreviewRenderer
from cli.wizard.prompts import WIZARD_PROMPT_SERVICE, WizardPromptService

SelectionT = TypeVar('SelectionT')


class WizardInteractionSupport:
    """
    向导交互与上下文构建支持对象。

    :param context_factory: CLI 上下文工厂
    :param prompt_service: 向导提示服务
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory,
        prompt_service: WizardPromptService,
    ) -> None:
        """
        初始化交互支持对象。

        :param context_factory: CLI 上下文工厂
        :param prompt_service: 向导提示服务
        :return: None
        """
        self.context_factory = context_factory
        self.prompt_service = prompt_service

    def build_regular_context(
        self,
        env: str,
        output: OutputOption,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> CliContext:
        """
        构建普通可写命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境执行
        :param yes: 是否跳过确认
        :param dry_run: 是否执行预演
        :return: CLI 上下文
        """
        return self.context_factory.build_regular(env, output, allow_prod, yes, dry_run)

    def build_readonly_context(self, env: str, output: OutputOption) -> CliContext:
        """
        构建只读命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :return: CLI 上下文
        """
        return self.context_factory.build_readonly(env, output)

    def prompt_confirm(self, prompt_text: str, *, default_value: bool) -> bool:
        """
        执行标准确认交互。

        :param prompt_text: 提示文本
        :param default_value: 默认值
        :return: 是否确认
        """
        return self.prompt_service.prompt_confirm(prompt_text, default_value=default_value)


class WizardResultSupport:
    """
    向导结果收口支持对象。

    :param execution_service: CLI 执行服务
    :param preview_renderer: 向导预览渲染器
    """

    def __init__(
        self,
        *,
        execution_service: CliExecutionService,
        preview_renderer: WizardPreviewRenderer,
    ) -> None:
        """
        初始化结果收口支持对象。

        :param execution_service: CLI 执行服务
        :param preview_renderer: 向导预览渲染器
        :return: None
        """
        self.execution_service = execution_service
        self.preview_renderer = preview_renderer

    def complete_result(self, ctx: CliContext, result: CommandResult) -> None:
        """
        输出命令结果对象。

        :param ctx: CLI 上下文
        :param result: 命令结果对象
        :return: None
        """
        self.execution_service.complete_result(ctx, result)

    def complete_payload(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        default_exit_code: int = 0,
    ) -> None:
        """
        输出标准结果负载。

        :param ctx: CLI 上下文
        :param payload: 标准结果负载
        :param default_exit_code: 默认退出码
        :return: None
        """
        self.execution_service.complete_payload(ctx, payload, default_exit_code=default_exit_code)

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
        统一按输出格式收口标准结果负载。

        :param ctx: CLI 上下文
        :param payload: 标准结果负载
        :param text_builder: 文本结果构建函数
        :param default_exit_code: 默认退出码
        :param text_condition: 文本模式结果构建判定函数
        :return: None
        """
        self.execution_service.complete_payload_result(
            ctx,
            payload,
            text_builder=text_builder,
            default_exit_code=default_exit_code,
            text_condition=text_condition,
        )

    def build_cancel_result(self, wizard_name: str) -> CommandResult:
        """
        构建统一的向导取消结果。

        :param wizard_name: 向导名称
        :return: 命令结果对象
        """
        return self.preview_renderer.build_cancel_result(wizard_name)

    def get_preview_renderer(self) -> WizardPreviewRenderer:
        """
        返回当前项目默认的向导预览渲染器。

        :return: 预览渲染器
        """
        return self.preview_renderer


class WizardNestedCommandSupport:
    """
    向导内部 CLI 调用支持对象。

    :param command_runner: 内部 CLI 子进程调用函数
    :param live_command_runner: 内部 CLI 实时执行函数
    """

    def __init__(
        self,
        *,
        command_runner: Callable[..., Any],
        live_command_runner: Callable[..., Any],
    ) -> None:
        """
        初始化内部 CLI 调用支持对象。

        :param command_runner: 内部 CLI 子进程调用函数
        :param live_command_runner: 内部 CLI 实时执行函数
        :return: None
        """
        self.command_runner = command_runner
        self.live_command_runner = live_command_runner

    @staticmethod
    def resolve_callable_override(owner: type['BaseCliWizardFlow[Any]'], attribute_name: str) -> Callable[..., Any]:
        """
        解析类级可调用注入点，避免普通函数在实例访问时被绑定为方法。

        :param owner: 向导类
        :param attribute_name: 类属性名称
        :return: 可直接调用的函数对象
        """
        attribute = inspect.getattr_static(owner, attribute_name)
        if isinstance(attribute, staticmethod):
            return attribute.__func__
        return attribute

    def run_nested_command(self, *arguments: str, parse_json: bool = False) -> Any:
        """
        调用内部 CLI 并按需解析 JSON。

        :param arguments: CLI 参数列表
        :param parse_json: 是否解析 JSON
        :return: 内部 CLI 调用结果
        """
        return self.command_runner(*arguments, parse_json=parse_json)

    def exec_nested_command(self, *arguments: str) -> Any:
        """
        直接切换到内部 CLI 的实时执行路径。

        :param arguments: CLI 参数列表
        :return: 内部 CLI 调用结果
        """
        return self.live_command_runner(*arguments)


class WizardExecutionResultSupport:
    """
    向导执行结果翻译支持对象。

    该对象负责提取内部 CLI 结果的 payload、退出码与错误文本，并构建
    默认失败负载，让模板基类不再直接持有结果翻译细节。

    :param failure_message: 默认失败提示
    """

    def __init__(self, *, failure_message: str) -> None:
        """
        初始化执行结果翻译支持对象。

        :param failure_message: 默认失败提示
        :return: None
        """
        self.failure_message = failure_message

    @staticmethod
    def extract_payload(nested_result: Any) -> dict[str, Any] | None:
        """
        提取内部 CLI JSON 负载。

        :param nested_result: 内部 CLI 调用结果
        :return: JSON 负载
        """
        payload = getattr(nested_result, 'payload', None)
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def extract_returncode(nested_result: Any) -> int:
        """
        提取内部 CLI 退出码。

        :param nested_result: 内部 CLI 调用结果
        :return: 退出码
        """
        return int(getattr(nested_result, 'returncode', 0) or 0)

    @staticmethod
    def extract_stdout(nested_result: Any) -> str:
        """
        提取内部 CLI 标准输出。

        :param nested_result: 内部 CLI 调用结果
        :return: 标准输出文本
        """
        return str(getattr(nested_result, 'stdout', '') or '').strip()

    @staticmethod
    def extract_stderr(nested_result: Any) -> str:
        """
        提取内部 CLI 标准错误。

        :param nested_result: 内部 CLI 调用结果
        :return: 标准错误文本
        """
        return str(getattr(nested_result, 'stderr', '') or '').strip()

    def build_failure_payload(self, nested_result: Any) -> dict[str, Any]:
        """
        为内部 CLI 非 JSON 结果构建失败负载。

        :param nested_result: 内部 CLI 调用结果
        :return: 失败负载
        """
        error_text = self.extract_stderr(nested_result) or self.extract_stdout(nested_result)
        return {
            'ok': False,
            'message': self.failure_message,
            'error': error_text,
            'exit_code': self.extract_returncode(nested_result),
        }


class WizardSupportCache:
    """
    向导协作者缓存。

    该对象负责延迟构建并复用当前 flow 需要的 interaction/result/nested
    support collaborator，让 `BaseCliWizardFlow` 回到模板骨架与桥接层角色。

    :param owner: 当前向导 flow
    """

    def __init__(self, owner: 'BaseCliWizardFlow[Any]') -> None:
        """
        初始化向导协作者缓存。

        :param owner: 当前向导 flow
        :return: None
        """
        self.owner = owner
        self._interaction_support: WizardInteractionSupport | None = None
        self._result_support: WizardResultSupport | None = None
        self._nested_command_support: WizardNestedCommandSupport | None = None
        self._execution_result_support: WizardExecutionResultSupport | None = None

    def get_interaction_support(self) -> WizardInteractionSupport:
        """
        返回当前向导使用的交互支持对象。

        :return: 交互支持对象
        """
        if self._interaction_support is None:
            self._interaction_support = WizardInteractionSupport(
                context_factory=self.owner.context_factory,
                prompt_service=self.owner.prompt_service,
            )
        return self._interaction_support

    def get_result_support(self) -> WizardResultSupport:
        """
        返回当前向导使用的结果收口支持对象。

        :return: 结果收口支持对象
        """
        if self._result_support is None:
            self._result_support = WizardResultSupport(
                execution_service=self.owner.execution_service,
                preview_renderer=self.owner.preview_renderer,
            )
        return self._result_support

    def get_nested_command_support(self) -> WizardNestedCommandSupport:
        """
        返回当前向导使用的内部 CLI 调用支持对象。

        :return: 内部 CLI 调用支持对象
        """
        if self._nested_command_support is None:
            self._nested_command_support = WizardNestedCommandSupport(
                command_runner=WizardNestedCommandSupport.resolve_callable_override(
                    type(self.owner), 'nested_command_runner'
                ),
                live_command_runner=WizardNestedCommandSupport.resolve_callable_override(
                    type(self.owner),
                    'nested_live_command_runner',
                ),
            )
        return self._nested_command_support

    def get_execution_result_support(self) -> WizardExecutionResultSupport:
        """
        返回当前向导使用的执行结果翻译支持对象。

        :return: 执行结果翻译支持对象
        """
        if self._execution_result_support is None:
            self._execution_result_support = WizardExecutionResultSupport(
                failure_message=self.owner.failure_message,
            )
        return self._execution_result_support


class BaseNestedCommandWizardFlow(ABC, Generic[SelectionT]):
    """
    统一封装通过内部 CLI 执行的向导流程。

    子类需要提供参数采集、上下文构建、预览摘要、执行参数和
    结果收口策略，从而复用向导的通用交互主链路。
    """

    wizard_name: str
    preview_title: str
    failure_message: str

    def run(self, output: OutputOption = 'text') -> None:
        """
        执行向导主流程。

        :param output: 输出格式
        :return: None
        """
        selection = self.collect_selection()
        self.prepare_execution_state(selection, output)
        ctx = self.prepare_context(selection, output)
        typer.echo(self.render_preview(selection))
        if not self.prompt_confirm(self.confirm_prompt(selection), default_value=self.confirm_default_value(selection)):
            self.complete_result(ctx, self.build_cancel_result())
            return

        nested_result = self.execute(selection, output)
        if self.handle_execution_result(ctx, nested_result, output):
            return
        payload = self.extract_payload(nested_result)
        if payload is not None:
            self.complete_payload(ctx, payload, default_exit_code=self.extract_returncode(nested_result))
            return
        self.complete_payload(ctx, self.build_failure_payload(nested_result))

    def render_preview(self, selection: SelectionT) -> str:
        """
        生成向导预览文本。

        :param selection: 向导采集结果
        :return: 预览文本
        """
        return self.get_preview_renderer().render_preview(
            self.preview_title,
            summary=self.build_preview_summary(selection),
            command=self.build_preview_command(selection),
            notes=self.build_preview_notes(selection),
        )

    def confirm_default_value(self, selection: SelectionT) -> bool:
        """
        返回最终确认默认值。

        :param selection: 向导采集结果
        :return: 默认确认值
        """
        del selection
        return False

    def build_preview_notes(self, selection: SelectionT) -> list[str] | None:
        """
        构建预览附加说明。

        :param selection: 向导采集结果
        :return: 预览附加说明
        """
        del selection
        return None

    def prepare_execution_state(self, selection: SelectionT, output: OutputOption) -> None:
        """
        在渲染预览前准备 flow 级执行状态。

        该钩子用于少量需要在预览、确认默认值或执行前共享状态的 flow，
        例如预先探测只读诊断结果，但不允许子类因此重写整个模板主链路。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: None
        """
        del selection, output

    def handle_execution_result(self, ctx: CliContext, nested_result: Any, output: OutputOption) -> bool:
        """
        允许子类在默认 payload 收口前接管执行结果。

        该钩子适用于需要切换到 live exec、实时终端占用或其他非标准 payload
        收口路径的少数 flow。返回 `True` 表示结果已处理完成。

        :param ctx: CLI 上下文
        :param nested_result: 执行结果
        :param output: 输出格式
        :return: 是否已完成结果处理
        """
        del ctx, nested_result, output
        return False

    def build_failure_payload(self, nested_result: Any) -> dict[str, Any]:
        """
        为内部 CLI 非 JSON 结果构建失败负载。

        :param nested_result: 内部 CLI 调用结果
        :return: 失败负载
        """
        return self.get_execution_result_support().build_failure_payload(nested_result)

    @staticmethod
    def extract_payload(nested_result: Any) -> dict[str, Any] | None:
        """
        提取内部 CLI JSON 负载。

        :param nested_result: 内部 CLI 调用结果
        :return: JSON 负载
        """
        return WizardExecutionResultSupport.extract_payload(nested_result)

    @staticmethod
    def extract_returncode(nested_result: Any) -> int:
        """
        提取内部 CLI 退出码。

        :param nested_result: 内部 CLI 调用结果
        :return: 退出码
        """
        return WizardExecutionResultSupport.extract_returncode(nested_result)

    @staticmethod
    def extract_stdout(nested_result: Any) -> str:
        """
        提取内部 CLI 标准输出。

        :param nested_result: 内部 CLI 调用结果
        :return: 标准输出文本
        """
        return WizardExecutionResultSupport.extract_stdout(nested_result)

    @staticmethod
    def extract_stderr(nested_result: Any) -> str:
        """
        提取内部 CLI 标准错误。

        :param nested_result: 内部 CLI 调用结果
        :return: 标准错误文本
        """
        return WizardExecutionResultSupport.extract_stderr(nested_result)

    @abstractmethod
    def collect_selection(self) -> SelectionT:
        """
        采集向导参数。

        :return: 向导采集结果
        """

    @abstractmethod
    def prepare_context(self, selection: SelectionT, output: OutputOption) -> CliContext:
        """
        构建命令上下文。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: CLI 上下文
        """

    @abstractmethod
    def build_preview_summary(self, selection: SelectionT) -> dict[str, Any]:
        """
        构建预览摘要。

        :param selection: 向导采集结果
        :return: 预览摘要
        """

    @abstractmethod
    def build_preview_command(self, selection: SelectionT) -> list[str]:
        """
        构建用户视角命令。

        :param selection: 向导采集结果
        :return: 用户视角命令参数
        """

    @abstractmethod
    def confirm_prompt(self, selection: SelectionT) -> str:
        """
        返回最终确认提示文本。

        :param selection: 向导采集结果
        :return: 确认提示
        """

    @abstractmethod
    def build_execute_arguments(self, selection: SelectionT, output: OutputOption) -> list[str]:
        """
        构建内部 CLI 执行参数。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 参数
        """

    @abstractmethod
    def prompt_confirm(self, prompt_text: str, *, default_value: bool) -> bool:
        """
        执行确认交互。

        :param prompt_text: 提示文本
        :param default_value: 默认值
        :return: 是否确认
        """

    @abstractmethod
    def complete_result(self, ctx: CliContext, result: CommandResult) -> None:
        """
        输出命令结果对象。

        :param ctx: CLI 上下文
        :param result: 命令结果
        :return: None
        """

    @abstractmethod
    def build_cancel_result(self) -> CommandResult:
        """
        构建向导取消结果。

        :return: 命令结果对象
        """

    @abstractmethod
    def get_preview_renderer(self) -> WizardPreviewRenderer:
        """
        获取当前向导使用的预览渲染器。

        :return: 预览渲染器
        """

    @abstractmethod
    def complete_payload(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        default_exit_code: int = 0,
    ) -> None:
        """
        输出标准负载。

        :param ctx: CLI 上下文
        :param payload: 结果负载
        :param default_exit_code: 默认退出码
        :return: None
        """

    def execute(self, selection: SelectionT, output: OutputOption) -> Any:
        """
        执行内部 CLI 命令。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: 内部 CLI 调用结果
        """
        return self.run_nested_command(*self.build_execute_arguments(selection, output), parse_json=True)

    @abstractmethod
    def run_nested_command(self, *arguments: str, parse_json: bool = False) -> Any:
        """
        调用内部 CLI。

        :param arguments: 参数列表
        :param parse_json: 是否解析 JSON
        :return: 内部 CLI 调用结果
        """


class BaseCliWizardFlow(BaseNestedCommandWizardFlow[SelectionT], ABC):
    """
    当前项目使用的 CLI 向导基类。

    该基类在通用向导主链路之上继续下沉当前项目稳定复用的桥接逻辑，
    包括确认交互、上下文构建、命令结果收口与内部 CLI 调用封装。
    """

    context_factory: ClassVar[CliContextFactory] = DEFAULT_CORE_SERVICES.context_factory
    execution_service: ClassVar[CliExecutionService] = DEFAULT_CORE_SERVICES.execution_service
    prompt_service: ClassVar[WizardPromptService] = WIZARD_PROMPT_SERVICE
    preview_renderer: ClassVar[WizardPreviewRenderer] = WIZARD_PREVIEW_RENDERER
    nested_command_runner: ClassVar[Callable[..., Any]] = staticmethod(NESTED_CLI_SUPPORT.run)
    nested_live_command_runner: ClassVar[Callable[..., Any]] = staticmethod(NESTED_CLI_SUPPORT.exec)

    def __init__(self) -> None:
        """
        初始化当前项目向导基类。

        该基类通过协作者缓存稳定持有交互、结果收口和内部 CLI 调用 support，
        避免模板方法执行过程中重复构建同类对象。

        :return: None
        """
        self._support_cache: WizardSupportCache | None = None

    def get_support_cache(self) -> WizardSupportCache:
        """
        返回当前向导使用的协作者缓存。

        保持惰性创建，以兼容未显式调用基类 `__init__` 的现有 flow。

        :return: 协作者缓存
        """
        support_cache = getattr(self, '_support_cache', None)
        if support_cache is None:
            self._support_cache = WizardSupportCache(self)
        return self._support_cache

    def get_interaction_support(self) -> WizardInteractionSupport:
        """
        返回当前向导使用的交互支持对象。

        :return: 交互支持对象
        """
        return self.get_support_cache().get_interaction_support()

    def get_result_support(self) -> WizardResultSupport:
        """
        返回当前向导使用的结果收口支持对象。

        :return: 结果收口支持对象
        """
        return self.get_support_cache().get_result_support()

    def get_nested_command_support(self) -> WizardNestedCommandSupport:
        """
        返回当前向导使用的内部 CLI 调用支持对象。

        :return: 内部 CLI 调用支持对象
        """
        return self.get_support_cache().get_nested_command_support()

    def get_execution_result_support(self) -> WizardExecutionResultSupport:
        """
        返回当前向导使用的执行结果翻译支持对象。

        :return: 执行结果翻译支持对象
        """
        return self.get_support_cache().get_execution_result_support()

    def build_regular_context(
        self,
        env: str,
        output: OutputOption,
        *,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> CliContext:
        """
        构建普通可写命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境执行
        :param yes: 是否跳过确认
        :param dry_run: 是否执行预演
        :return: CLI 上下文
        """
        return self.get_interaction_support().build_regular_context(
            env,
            output,
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
        )

    def build_readonly_context(self, env: str, output: OutputOption) -> CliContext:
        """
        构建只读命令上下文。

        :param env: 运行环境
        :param output: 输出格式
        :return: CLI 上下文
        """
        return self.get_interaction_support().build_readonly_context(env, output)

    def prompt_confirm(self, prompt_text: str, *, default_value: bool) -> bool:
        """
        执行标准确认交互。

        :param prompt_text: 提示文本
        :param default_value: 默认值
        :return: 是否确认
        """
        return self.get_interaction_support().prompt_confirm(prompt_text, default_value=default_value)

    def complete_result(self, ctx: CliContext, result: CommandResult) -> None:
        """
        输出命令结果对象。

        :param ctx: CLI 上下文
        :param result: 命令结果对象
        :return: None
        """
        self.get_result_support().complete_result(ctx, result)

    def complete_payload(
        self,
        ctx: CliContext,
        payload: dict[str, Any],
        *,
        default_exit_code: int = 0,
    ) -> None:
        """
        输出标准结果负载。

        :param ctx: CLI 上下文
        :param payload: 标准结果负载
        :param default_exit_code: 默认退出码
        :return: None
        """
        self.get_result_support().complete_payload(ctx, payload, default_exit_code=default_exit_code)

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
        统一按输出格式收口标准结果负载。

        :param ctx: CLI 上下文
        :param payload: 标准结果负载
        :param text_builder: 文本结果构建函数
        :param default_exit_code: 默认退出码
        :param text_condition: 文本模式结果构建判定函数
        :return: None
        """
        self.get_result_support().complete_payload_result(
            ctx,
            payload,
            text_builder=text_builder,
            default_exit_code=default_exit_code,
            text_condition=text_condition,
        )

    def build_cancel_result(self) -> CommandResult:
        """
        构建统一的向导取消结果。

        :return: 命令结果对象
        """
        return self.get_result_support().build_cancel_result(self.wizard_name)

    def get_preview_renderer(self) -> WizardPreviewRenderer:
        """
        返回当前项目默认的向导预览渲染器。

        :return: 预览渲染器
        """
        return self.get_result_support().get_preview_renderer()

    def run_nested_command(self, *arguments: str, parse_json: bool = False) -> Any:
        """
        调用内部 CLI 并按需解析 JSON。

        :param arguments: CLI 参数列表
        :param parse_json: 是否解析 JSON
        :return: 内部 CLI 调用结果
        """
        return self.get_nested_command_support().run_nested_command(*arguments, parse_json=parse_json)

    def exec_nested_command(self, *arguments: str) -> Any:
        """
        直接切换到内部 CLI 的实时执行路径。

        :param arguments: CLI 参数列表
        :return: 内部 CLI 调用结果
        """
        return self.get_nested_command_support().exec_nested_command(*arguments)


class BaseLiveExecCliWizardFlow(BaseCliWizardFlow[SelectionT], ABC):
    """
    统一封装“确认后切换到实时终端执行路径”的 CLI 向导基类。

    该特化基类用于少量不走 JSON payload 收口，而是在确认后直接
    切换到现有命令实时执行链路的向导场景，例如 `wizard app-run`。
    它在保留预览与确认模板骨架的前提下，显式表达“执行阶段即完成收口”，
    避免子类再通过覆写 `complete_payload()` 或 `handle_execution_result()`
    实现规避式短路。
    """

    def execute(self, selection: SelectionT, output: OutputOption) -> None:
        """
        切换到内部 CLI 的实时执行路径。

        :param selection: 向导采集结果
        :param output: 输出格式
        :return: None
        """
        self.exec_nested_command(*self.build_execute_arguments(selection, output))

    def handle_execution_result(self, ctx: CliContext, nested_result: Any, output: OutputOption) -> bool:
        """
        标记实时执行路径已完成结果收口。

        :param ctx: CLI 上下文
        :param nested_result: 执行结果
        :param output: 输出格式
        :return: 是否已完成结果处理
        """
        del ctx, nested_result, output
        return True
