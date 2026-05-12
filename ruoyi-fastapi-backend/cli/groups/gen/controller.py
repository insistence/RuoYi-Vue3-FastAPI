from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.gen import GEN_RUNTIME, GenRuntimeService

from .presenter import GenCommandPresenter


class GenCommandController:
    """
    代码生成命令控制器。

    该控制器负责组织 `gen` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 代码生成命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: GenCommandPresenter | None = None,
        runtime_service: GenRuntimeService | None = None,
    ) -> None:
        """
        初始化代码生成命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 代码生成命令文本渲染器
        :param runtime_service: 代码生成运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or GenCommandPresenter()
        self.runtime_service = runtime_service or GEN_RUNTIME

    def import_table(
        self,
        table_names: list[str],
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        导入数据库表到代码生成业务表。

        :param table_names: 待导入表名列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='gen import-table',
        )
        payload = self.execution_service.run_async(self.runtime_service.import_tables(table_names, dry_run=dry_run))
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)

    def list_tables(
        self,
        env: str,
        output: str,
        *,
        table_name: str,
        table_comment: str,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> None:
        """
        查看代码生成业务表列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param table_name: 表名称过滤条件
        :param table_comment: 表描述过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(
            self.runtime_service.list_gen_tables(
                table_name=table_name,
                table_comment=table_comment,
                paged=paged,
                page_num=page_num,
                page_size=page_size,
            )
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=lambda data: self.presenter.build_gen_table_list_text(data, db_mode=False),
            text_condition=lambda data: data.get('ok', False),
        )

    def list_db_tables(
        self,
        env: str,
        output: str,
        *,
        table_name: str,
        table_comment: str,
        paged: bool,
        page_num: int,
        page_size: int,
    ) -> None:
        """
        查看数据库中可导入的物理表列表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param table_name: 表名称过滤条件
        :param table_comment: 表描述过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(
            self.runtime_service.list_gen_db_tables(
                table_name=table_name,
                table_comment=table_comment,
                paged=paged,
                page_num=page_num,
                page_size=page_size,
            )
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=lambda data: self.presenter.build_gen_table_list_text(data, db_mode=True),
            text_condition=lambda data: data.get('ok', False),
        )

    def show_detail(self, table_id: int, env: str, output: str) -> None:
        """
        查看单个代码生成业务表详情。

        :param table_id: 业务表 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.get_gen_table_detail(table_id))
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_gen_detail_text,
            text_condition=lambda data: 'error' not in data,
        )

    def create_table(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        sql: str,
        sql_file: str,
    ) -> None:
        """
        根据建表 SQL 创建表结构并导入代码生成业务表。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param sql: 直接传入的 SQL 文本
        :param sql_file: SQL 文件路径
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='gen create-table',
        )
        payload = self.execution_service.run_async(self.runtime_service.create_tables(sql, sql_file, dry_run=dry_run))
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)

    def preview(self, table_id: int, env: str, output: str) -> None:
        """
        预览指定业务表的代码生成结果。

        :param table_id: 业务表 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.runtime_service.preview_code(table_id))
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_gen_preview_text,
            text_condition=lambda data: data.get('ok', False),
        )

    def export(
        self,
        table_names: list[str],
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        mode: str,
        output_file: str,
    ) -> None:
        """
        导出代码生成结果。

        :param table_names: 业务表名称列表
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param mode: 导出模式
        :param output_file: zip 导出目标文件路径
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='gen export',
        )
        payload = self.execution_service.run_async(
            self.runtime_service.export_code(table_names, mode=mode, output_file=output_file, dry_run=dry_run)
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_gen_export_text,
            text_condition=lambda data: data.get('ok', False),
        )

    def sync_db(
        self,
        table_name: str,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        同步指定业务表的数据库表结构。

        :param table_name: 业务表名称
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
            command_name='gen sync-db',
        )
        payload = self.execution_service.run_async(self.runtime_service.sync_gen_table_from_db(table_name))
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)
