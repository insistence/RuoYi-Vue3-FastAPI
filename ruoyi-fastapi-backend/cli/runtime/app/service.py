from collections import defaultdict
from typing import Any

from fastapi.routing import APIRoute

from cli.runtime.base import RUNTIME_ENVIRONMENT, RuntimeEnvironmentService

from .gateway import AppInfrastructureGateway
from .support import AppSnapshotSupport


class AppRuntimeService:
    """
    应用运行时服务。

    该服务作为应用运行时 facade，对外统一暴露应用实例构建、
    应用配置快照与环境信息快照入口。

    :param runtime_environment: 运行时环境服务
    :param infrastructure_gateway: 应用基础设施网关
    :param snapshot_support: 应用快照支持对象
    """

    def __init__(
        self,
        *,
        runtime_environment: RuntimeEnvironmentService | None = None,
        infrastructure_gateway: AppInfrastructureGateway | None = None,
        snapshot_support: AppSnapshotSupport | None = None,
    ) -> None:
        """
        初始化应用运行时服务。

        :param runtime_environment: 运行时环境服务
        :param infrastructure_gateway: 应用基础设施网关
        :param snapshot_support: 应用快照支持对象
        :return: None
        """
        self.runtime_environment = runtime_environment or RUNTIME_ENVIRONMENT
        self.infrastructure_gateway = infrastructure_gateway or AppInfrastructureGateway()
        self.snapshot_support = snapshot_support or AppSnapshotSupport(
            self.infrastructure_gateway,
            self.runtime_environment,
        )

    def build_app_instance(self) -> Any:
        """
        构建当前环境下的 FastAPI 应用实例。

        :return: FastAPI 应用实例
        """
        server_module = self.infrastructure_gateway.get_server_module()
        return server_module.create_app()

    def get_app_config_snapshot(self) -> dict[str, Any]:
        """
        读取当前运行环境的应用配置快照。

        :return: 应用配置快照
        """
        return self.snapshot_support.build_app_config_snapshot()

    def get_app_env_snapshot(self) -> dict[str, Any]:
        """
        读取当前 CLI 进程的环境解析结果快照。

        :return: 环境解析结果快照
        """
        return self.snapshot_support.build_app_env_snapshot()

    def get_app_routes_snapshot(
        self,
        env: str,
        *,
        path_prefix: str = '',
        method: str = '',
        group_by: str = 'none',
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """
        读取当前应用的路由快照。

        :param env: 当前运行环境
        :param path_prefix: 路由路径前缀过滤条件
        :param method: HTTP 方法过滤条件
        :param group_by: 路由分组方式
        :param include_hidden: 是否包含未进入 OpenAPI 的路由
        :return: 标准路由快照
        """
        normalized_method = method.upper().strip()
        routes: list[dict[str, Any]] = []
        for route in self.build_app_instance().routes:
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
        routes.sort(key=lambda item: (item['path'], ','.join(item['methods'])))
        grouped_routes: dict[str, list[dict[str, Any]]] | None = None
        if group_by == 'tag':
            grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
            for route in routes:
                tags = route.get('tags') or ['未分组']
                for tag in tags:
                    grouped[str(tag)].append(route)
            grouped_routes = dict(sorted(grouped.items()))
        return {
            'ok': True,
            'env': env,
            'count': len(routes),
            'filters': {
                'pathPrefix': path_prefix,
                'method': normalized_method,
                'groupBy': group_by,
                'includeHidden': include_hidden,
            },
            'routes': routes,
            'groupedRoutes': grouped_routes,
        }


APP_RUNTIME = AppRuntimeService()
