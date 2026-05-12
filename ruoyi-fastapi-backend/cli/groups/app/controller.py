from collections import defaultdict
from typing import Any

from fastapi.routing import APIRoute

from cli.bootstrap import APP_BOOTSTRAP, AppBootstrapService
from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.exit_codes import DEPENDENCY_ERROR, SUCCESS
from cli.runtime.app import APP_RUNTIME, AppRuntimeService
from cli.runtime.crypto import CRYPTO_RUNTIME, CryptoRuntimeService
from cli.runtime.db import DATABASE_RUNTIME, DatabaseRuntimeService
from cli.runtime.ops import OPERATIONS_RUNTIME, OperationsRuntimeService

from .presenter import AppCommandPresenter


class AppCommandController:
    """
    应用命令控制器。

    该控制器负责组织 `app` 命令组的上下文准备、runtime 调用、
    payload 构建，以及基于输出格式选择 presenter 或直接返回 JSON。
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: AppCommandPresenter | None = None,
        runtime_service: AppRuntimeService | None = None,
        database_runtime: DatabaseRuntimeService | None = None,
        operations_runtime: OperationsRuntimeService | None = None,
        crypto_runtime: CryptoRuntimeService | None = None,
        bootstrap_service: AppBootstrapService | None = None,
    ) -> None:
        """
        初始化应用命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 应用命令文本渲染器
        :param runtime_service: 应用运行时服务
        :param database_runtime: 数据库运行时服务
        :param operations_runtime: 运维运行时服务
        :param crypto_runtime: 传输加密运行时服务
        :param bootstrap_service: 应用引导服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or AppCommandPresenter()
        self.runtime_service = runtime_service or APP_RUNTIME
        self.database_runtime = database_runtime or DATABASE_RUNTIME
        self.operations_runtime = operations_runtime or OPERATIONS_RUNTIME
        self.crypto_runtime = crypto_runtime or CRYPTO_RUNTIME
        self.bootstrap_service = bootstrap_service or APP_BOOTSTRAP

    def run_app(self, env: str) -> None:
        """
        启动当前 FastAPI 应用。

        :param env: 当前命令运行环境
        :return: None
        """
        self.bootstrap_service.exec_app_run_command(env)

    def doctor(self, env: str, output: str) -> None:
        """
        执行应用启动前检查。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        db_status = self.execution_service.run_async(self.database_runtime.ping_database())
        redis_status = self.execution_service.run_async(self.operations_runtime.ping_redis())
        crypto_status = self.crypto_runtime.validate_crypto_config()
        payload = {
            'env': ctx.env,
            'database': db_status,
            'redis': redis_status,
            'crypto': crypto_status,
        }
        payload['ok'] = all(item.get('ok', False) for item in (db_status, redis_status, crypto_status))
        exit_code = SUCCESS if payload['ok'] else DEPENDENCY_ERROR
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_doctor_text,
            default_exit_code=exit_code,
        )

    def show_config(self, env: str, output: str) -> None:
        """
        输出当前应用配置快照。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload_result(
            ctx,
            {'ok': True, 'env': ctx.env, 'config': self.runtime_service.get_app_config_snapshot()},
            text_builder=self.presenter.build_app_config_text,
            default_exit_code=SUCCESS,
        )

    def show_env(self, env: str, output: str) -> None:
        """
        输出当前 CLI 解析到的应用环境信息。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload_result(
            ctx,
            {'ok': True, 'env': ctx.env, 'runtime': self.runtime_service.get_app_env_snapshot()},
            text_builder=self.presenter.build_app_env_text,
            default_exit_code=SUCCESS,
        )

    def show_routes(
        self,
        env: str,
        output: str,
        *,
        path_prefix: str,
        method: str,
        group_by: str,
        include_hidden: bool,
    ) -> None:
        """
        输出当前应用注册路由清单。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param path_prefix: 路由前缀过滤条件
        :param method: 请求方法过滤条件
        :param group_by: 路由分组方式
        :param include_hidden: 是否包含隐藏路由
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        routes_payload = self._serialize_routes(
            self.runtime_service.build_app_instance(),
            path_prefix=path_prefix,
            method=method,
            include_hidden=include_hidden,
        )
        grouped_routes = self._group_routes_by_tag(routes_payload) if group_by == 'tag' else None
        payload = {
            'ok': True,
            'env': ctx.env,
            'count': len(routes_payload),
            'filters': {
                'pathPrefix': path_prefix,
                'method': method.upper().strip(),
                'groupBy': group_by,
                'includeHidden': include_hidden,
            },
            'routes': routes_payload,
            'groupedRoutes': grouped_routes,
        }
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_routes_text,
            default_exit_code=SUCCESS,
            text_condition=lambda data: data.get('ok', False),
        )

    @staticmethod
    def _serialize_routes(
        app_instance: Any,
        *,
        path_prefix: str = '',
        method: str = '',
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        """
        序列化 FastAPI 路由信息。

        :param app_instance: FastAPI 应用实例
        :param path_prefix: 路径前缀过滤条件
        :param method: 请求方法过滤条件
        :param include_hidden: 是否包含未出现在 OpenAPI 中的路由
        :return: 序列化后的路由列表
        """
        normalized_method = method.upper().strip()
        routes = []
        for route in app_instance.routes:
            if not isinstance(route, APIRoute):
                continue
            if not include_hidden and not route.include_in_schema:
                continue
            if path_prefix and not route.path.startswith(path_prefix):
                continue
            route_methods = sorted(item for item in route.methods if item not in {'HEAD', 'OPTIONS'})
            if normalized_method and normalized_method not in route_methods:
                continue
            routes.append(
                {
                    'path': route.path,
                    'methods': route_methods,
                    'name': route.name,
                    'summary': route.summary or '',
                    'operationId': route.operation_id or '',
                    'tags': route.tags or [],
                    'includeInSchema': route.include_in_schema,
                }
            )
        return sorted(routes, key=lambda item: (item['path'], ','.join(item['methods'])))

    @staticmethod
    def _group_routes_by_tag(routes_payload: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """
        按标签对路由信息分组。

        :param routes_payload: 原始路由列表
        :return: 按标签分组后的路由映射
        """
        grouped_routes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for route in routes_payload:
            tags = route.get('tags') or ['__untagged__']
            for tag in tags:
                grouped_routes[tag].append(route)
        return dict(sorted(grouped_routes.items(), key=lambda item: item[0]))
