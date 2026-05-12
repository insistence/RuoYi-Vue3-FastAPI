from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.db import DATABASE_RUNTIME, DatabaseRuntimeService

from .presenter import DbCommandPresenter


class DbCommandController:
    """
    数据库命令控制器。

    该控制器负责组织 `db` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 数据库命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: DbCommandPresenter | None = None,
        runtime_service: DatabaseRuntimeService | None = None,
    ) -> None:
        """
        初始化数据库命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 数据库命令文本渲染器
        :param runtime_service: 数据库运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or DbCommandPresenter()
        self.runtime_service = runtime_service or DATABASE_RUNTIME

    def check(self, env: str, output: str) -> None:
        """
        检查数据库连接状态。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.runtime_service.ping_database())
        )

    def current(self, env: str, output: str) -> None:
        """
        查看数据库当前迁移版本。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.get_current_revision()
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_current_revision_text,
            text_condition=lambda result_data: bool(result_data.get('ok', False)),
        )

    def upgrade(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        revision: str,
    ) -> None:
        """
        执行数据库升级。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param revision: 目标迁移版本
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='db upgrade',
        )
        self.execution_service.complete_payload(ctx, self.runtime_service.upgrade_database(revision, dry_run=dry_run))

    def init(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        初始化数据库到最新迁移版本。

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
            command_name='db init',
        )
        self.execution_service.complete_payload(ctx, self.runtime_service.init_database(dry_run=dry_run))

    def downgrade(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        revision: str,
    ) -> None:
        """
        执行数据库回退。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param revision: 目标回退版本
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='db downgrade',
        )
        self.execution_service.complete_payload(ctx, self.runtime_service.downgrade_database(revision, dry_run=dry_run))

    def revision(
        self,
        message: str,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        autogenerate: bool,
    ) -> None:
        """
        创建新的数据库迁移版本文件。

        :param message: 迁移说明
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param autogenerate: 是否自动生成迁移内容
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='db revision',
        )
        self.execution_service.complete_payload(
            ctx,
            self.runtime_service.create_revision(message, autogenerate=autogenerate, dry_run=dry_run),
        )

    def heads(self, env: str, output: str) -> None:
        """
        查看当前代码仓库中的 Alembic heads。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.get_alembic_heads()
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_alembic_revisions_text,
            text_condition=lambda result_data: 'error' not in result_data,
        )

    def history(self, env: str, output: str, *, limit: int) -> None:
        """
        查看当前代码仓库中的 Alembic 历史版本。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param limit: 输出的最大历史记录数量
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.get_alembic_history(limit=limit)
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_alembic_revisions_text,
            text_condition=lambda result_data: 'error' not in result_data,
        )
