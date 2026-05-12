from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.dev import DEVELOPMENT_RUNTIME, DevelopmentRuntimeService

from .presenter import DevCommandPresenter


class DevCommandController:
    """
    开发命令控制器。

    该控制器负责组织 `dev` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 开发命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: DevCommandPresenter | None = None,
        runtime_service: DevelopmentRuntimeService | None = None,
    ) -> None:
        """
        初始化开发命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 开发命令文本渲染器
        :param runtime_service: 开发运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or DevCommandPresenter()
        self.runtime_service = runtime_service or DEVELOPMENT_RUNTIME

    def lint(
        self,
        targets: list[str] | None,
        env: str,
        output: str,
        *,
        check_only: bool,
        fix: bool,
        unsafe_fixes: bool,
    ) -> None:
        """
        执行 Ruff 格式化与静态检查。

        :param targets: 待检查路径列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param check_only: 是否仅检查不写回
        :param fix: 是否自动修复可修复问题
        :param unsafe_fixes: 是否允许不安全修复
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.run_lint(targets, check_only=check_only, fix=fix, unsafe_fixes=unsafe_fixes)
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_dev_lint_text,
        )

    def test(
        self,
        targets: list[str] | None,
        env: str,
        output: str,
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
    ) -> None:
        """
        执行项目测试。

        :param targets: 测试目标路径列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param keyword: pytest 关键字过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.run_tests(targets, keyword=keyword, maxfail=maxfail, quiet=quiet)
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_dev_test_text,
        )
