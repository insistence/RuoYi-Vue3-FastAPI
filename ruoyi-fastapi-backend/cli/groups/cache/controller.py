from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.cache import CACHE_RUNTIME, CacheRuntimeService

from .presenter import CacheCommandPresenter


class CacheCommandController:
    """
    缓存命令控制器。

    该控制器负责组织 `cache` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 缓存命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: CacheCommandPresenter | None = None,
        runtime_service: CacheRuntimeService | None = None,
    ) -> None:
        """
        初始化缓存命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 缓存命令文本渲染器
        :param runtime_service: 缓存运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or CacheCommandPresenter()
        self.runtime_service = runtime_service or CACHE_RUNTIME

    def stats(self, env: str, output: str) -> None:
        """
        查看缓存统计信息。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.get_cache_stats())
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_cache_stats_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def keys(self, cache_name: str, env: str, output: str) -> None:
        """
        查看指定缓存名称下的键名列表。

        :param cache_name: 缓存名称
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.list_cache_keys(cache_name))
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_cache_keys_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def get(self, cache_name: str, cache_key: str, env: str, output: str) -> None:
        """
        查看指定缓存内容。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.get_cache_value(cache_name, cache_key))
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_cache_value_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def clear(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        cache_name: str,
        cache_key: str,
        clear_all: bool,
    ) -> None:
        """
        清理缓存。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param cache_name: 缓存名称前缀
        :param cache_key: 缓存键名
        :param clear_all: 是否清理全部缓存
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='cache clear',
        )
        self.execution_service.complete_payload(
            ctx,
            self.execution_service.run_async(
                self.runtime_service.clear_cache(
                    cache_name=cache_name,
                    cache_key=cache_key,
                    clear_all=clear_all,
                    dry_run=dry_run,
                )
            ),
        )

    def ttl(self, cache_name: str, cache_key: str, env: str, output: str) -> None:
        """
        查看指定缓存键的剩余过期时间。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.get_cache_ttl(cache_name, cache_key))
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_cache_ttl_text,
            text_condition=lambda result_data: 'error' not in result_data,
        )

    def warmup(self, env: str, output: str, allow_prod: bool, yes: bool) -> None:
        """
        执行系统缓存预热。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            False,
            command_name='cache warmup',
        )
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.runtime_service.warmup_cache())
        )
