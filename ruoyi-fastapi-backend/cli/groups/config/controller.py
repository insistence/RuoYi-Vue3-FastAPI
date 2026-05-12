from typing import Literal

from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.config import CONFIG_RUNTIME, ConfigRuntimeService

from .presenter import ConfigCommandPresenter


class ConfigCommandController:
    """
    参数配置命令控制器。

    该控制器负责组织 `config` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 参数配置命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: ConfigCommandPresenter | None = None,
        runtime_service: ConfigRuntimeService | None = None,
    ) -> None:
        """
        初始化参数配置命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 参数配置命令文本渲染器
        :param runtime_service: 参数配置运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or ConfigCommandPresenter()
        self.runtime_service = runtime_service or CONFIG_RUNTIME

    def list_configs(
        self,
        env: str,
        output: str,
        *,
        config_name: str,
        config_key: str,
        config_type: Literal['Y', 'N'] | None,
        begin_date: str,
        end_date: str,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> None:
        """
        查看参数配置列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param config_name: 参数名称过滤条件
        :param config_key: 参数键名过滤条件
        :param config_type: 参数类型过滤条件
        :param begin_date: 查询开始日期
        :param end_date: 查询结束日期
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(
            self.runtime_service.list_configs(
                config_name=config_name,
                config_key=config_key,
                config_type=config_type,
                begin_date=begin_date,
                end_date=end_date,
                paged=paged,
                page_num=page_num,
                page_size=page_size,
            )
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_config_list_text,
            text_condition=lambda data: data.get('ok', False),
        )

    def get_config(
        self,
        config_key: str,
        env: str,
        output: str,
        *,
        source: Literal['db', 'cache', 'both'],
    ) -> None:
        """
        查看单个参数配置详情。

        :param config_key: 需要查询的参数键名
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param source: 配置读取来源
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.get_config(config_key, source=source))
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_config_get_text,
            text_condition=lambda data: data.get('ok', False),
        )

    def set_config(
        self,
        config_key: str,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        value: str,
        name: str | None,
        config_type: Literal['Y', 'N'] | None,
        remark: str | None,
    ) -> None:
        """
        新增或更新单个参数配置。

        :param config_key: 需要写入的参数键名
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param value: 参数键值
        :param name: 参数名称
        :param config_type: 参数类型
        :param remark: 参数备注
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='config set',
        )
        payload = self.execution_service.run_async(
            self.runtime_service.set_config(
                config_key,
                value,
                config_name=name,
                config_type=config_type,
                remark=remark,
                dry_run=dry_run,
            )
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)

    def sync_cache(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        刷新参数配置缓存。

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
            command_name='config sync-cache',
        )
        payload = self.execution_service.run_async(self.runtime_service.sync_config_cache())
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)

    def doctor(
        self,
        env: str,
        output: str,
        *,
        sample_limit: int,
    ) -> None:
        """
        诊断参数配置数据库与缓存是否一致。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param sample_limit: 问题示例键名输出上限
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.diagnose_config(sample_limit=sample_limit))
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_config_doctor_text,
            text_condition=lambda data: 'error' not in data,
        )
