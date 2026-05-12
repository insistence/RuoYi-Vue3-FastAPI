from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.exit_codes import DEPENDENCY_ERROR, SUCCESS
from cli.runtime.db import DATABASE_RUNTIME, DatabaseRuntimeService
from cli.runtime.ops import OPERATIONS_RUNTIME, OperationsRuntimeService

from .presenter import OpsCommandPresenter


class OpsCommandController:
    """
    运维命令控制器。

    该控制器负责组织 `ops` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 运维命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: OpsCommandPresenter | None = None,
        database_runtime: DatabaseRuntimeService | None = None,
        operations_runtime: OperationsRuntimeService | None = None,
    ) -> None:
        """
        初始化运维命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 运维命令文本渲染器
        :param database_runtime: 数据库运行时服务
        :param operations_runtime: 运维运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or OpsCommandPresenter()
        self.database_runtime = database_runtime or DATABASE_RUNTIME
        self.operations_runtime = operations_runtime or OPERATIONS_RUNTIME

    def ping_db(self, env: str, output: str) -> None:
        """
        检查数据库连接。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload(
            ctx, self.execution_service.run_async(self.database_runtime.ping_database())
        )

    def ping_redis(self, env: str, output: str) -> None:
        """
        检查 Redis 连接。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload(
            ctx,
            self.execution_service.run_async(self.operations_runtime.ping_redis()),
        )

    def health(self, env: str, output: str) -> None:
        """
        输出基础健康检查结果。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        db_status = self.execution_service.run_async(self.database_runtime.ping_database())
        redis_status = self.execution_service.run_async(self.operations_runtime.ping_redis())
        payload = {
            'env': ctx.env,
            'database': db_status,
            'redis': redis_status,
            'ok': db_status.get('ok', False) and redis_status.get('ok', False),
        }
        exit_code = SUCCESS if payload['ok'] else DEPENDENCY_ERROR
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_health_text,
            default_exit_code=exit_code,
        )

    def deps(self, env: str, output: str, *, include_dev: bool) -> None:
        """
        检查当前 CLI 和后端运行依赖版本。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param include_dev: 是否附带输出开发依赖
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.operations_runtime.get_dependency_versions(include_dev=include_dev)
        exit_code = SUCCESS if payload.get('ok', False) else DEPENDENCY_ERROR
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_dependencies_text,
            default_exit_code=exit_code,
        )

    def server_info(self, env: str, output: str) -> None:
        """
        输出服务器运行时信息。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.execution_service.run_async(self.operations_runtime.get_server_info())
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_server_info_text,
            default_exit_code=SUCCESS,
            text_condition=lambda data: data.get('ok', False),
        )
