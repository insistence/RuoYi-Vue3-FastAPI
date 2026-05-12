import socket
from typing import Any

from cli.exit_codes import REDIS_ERROR, RUNTIME_ERROR, SCHEDULER_ERROR

from .gateway import OperationsInfrastructureGateway
from .support import (
    OperationsDependencyInspector,
    OperationsServerInfoSupport,
)


class OperationsRuntimeService:
    """
    运维运行时服务。

    该服务作为运维运行时 facade，对外统一暴露依赖版本检查、Redis 探活、
    调度同步以及服务器运行时信息采集入口。

    :param infrastructure_gateway: 运维基础设施网关
    :param dependency_inspector: 运维依赖检查器
    :param server_info_support: 服务器信息支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: OperationsInfrastructureGateway | None = None,
        dependency_inspector: OperationsDependencyInspector | None = None,
        server_info_support: OperationsServerInfoSupport | None = None,
    ) -> None:
        """
        初始化运维运行时服务。

        :param infrastructure_gateway: 运维基础设施网关
        :param dependency_inspector: 运维依赖检查器
        :param server_info_support: 服务器信息支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or OperationsInfrastructureGateway()
        self.dependency_inspector = dependency_inspector or OperationsDependencyInspector()
        self.server_info_support = server_info_support or OperationsServerInfoSupport(self.infrastructure_gateway)

    def get_dependency_versions(self, *, include_dev: bool = False) -> dict[str, Any]:
        """
        读取 CLI 和后端运行所依赖的核心 Python 包版本。

        :param include_dev: 是否附带开发阶段依赖
        :return: 依赖检查结果
        """
        return self.dependency_inspector.inspect(include_dev=include_dev)

    async def ping_redis(self) -> dict[str, Any]:
        """
        检查 Redis 连通性。

        :return: Redis 检查结果
        """
        redis_util = self.infrastructure_gateway.get_redis_util()
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        redis = await redis_util.create_redis_pool(log_enabled=False)
        try:
            await redis.ping()
            return {'ok': True, 'message': 'Redis连接成功'}
        except redis_error as exc:
            return {'ok': False, 'message': 'Redis连接失败', 'error': str(exc), 'exit_code': REDIS_ERROR}
        finally:
            await redis.close()

    async def sync_jobs(self) -> dict[str, Any]:
        """
        同步调度任务配置。

        :return: 任务同步执行结果
        """
        redis = None
        scheduler_util = None
        try:
            redis_util = self.infrastructure_gateway.get_redis_util()
            scheduler_util = self.infrastructure_gateway.get_scheduler_util()
            redis = await redis_util.create_redis_pool(log_enabled=False)
            await scheduler_util.init_system_scheduler(redis)
            await scheduler_util.request_scheduler_sync()
            return {
                'ok': True,
                'operation': 'sync',
                'operationLabel': '同步调度配置',
                'schedulerSyncRequested': True,
                'message': '调度配置同步请求已发送',
                'isLeader': scheduler_util._is_leader,
            }
        except Exception as exc:
            return {
                'ok': False,
                'operation': 'sync',
                'operationLabel': '同步调度配置',
                'schedulerSyncRequested': False,
                'message': '调度配置同步失败',
                'error': str(exc),
                'exit_code': SCHEDULER_ERROR,
            }
        finally:
            if scheduler_util is not None:
                try:
                    await scheduler_util.close_system_scheduler()
                except Exception:
                    pass
            if redis is not None:
                try:
                    await redis.close()
                except Exception:
                    pass

    async def get_server_info(self) -> dict[str, Any]:
        """
        获取服务器运行信息。

        :return: 服务器运行信息字典
        """
        try:
            server_service = self.infrastructure_gateway.get_server_service()
            return {'ok': True, 'server': (await server_service.get_server_monitor_info()).model_dump(by_alias=True)}
        except socket.gaierror:
            try:
                return {'ok': True, 'server': self.server_info_support.build_server_info_fallback()}
            except Exception as exc:
                return {'ok': False, 'message': '读取服务器运行信息失败', 'error': str(exc), 'exit_code': RUNTIME_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '读取服务器运行信息失败', 'error': str(exc), 'exit_code': RUNTIME_ERROR}


OPERATIONS_RUNTIME = OperationsRuntimeService()
