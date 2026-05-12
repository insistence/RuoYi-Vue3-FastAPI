from importlib import import_module
from typing import Any


class JobInfrastructureGateway:
    """
    定时任务基础设施网关。

    该对象负责延迟加载数据库会话、Redis、调度器和任务服务依赖，
    供定时任务运行时 facade 与其协作对象统一复用。
    """

    @staticmethod
    def get_page_model() -> Any:
        """
        获取分页模型类型。

        :return: 分页模型类型
        """
        return import_module('common.vo').PageModel

    @staticmethod
    def get_async_session_local() -> Any:
        """
        获取异步数据库会话工厂。

        :return: 异步数据库会话工厂
        """
        return import_module('config.database').AsyncSessionLocal

    @staticmethod
    def get_redis_util() -> Any:
        """
        获取 Redis 工具类。

        :return: Redis 工具类
        """
        return import_module('config.get_redis').RedisUtil

    @staticmethod
    def get_scheduler_util() -> Any:
        """
        获取调度器工具类。

        :return: 调度器工具类
        """
        return import_module('config.get_scheduler').SchedulerUtil

    @staticmethod
    def get_job_vo_module() -> Any:
        """
        获取定时任务 VO 模块。

        :return: 定时任务 VO 模块
        """
        return import_module('module_admin.entity.vo.job_vo')

    @staticmethod
    def get_job_service() -> Any:
        """
        获取定时任务服务类。

        :return: 定时任务服务类
        """
        return import_module('module_admin.service.job_service').JobService

    @staticmethod
    def get_job_log_service() -> Any:
        """
        获取定时任务日志服务类。

        :return: 定时任务日志服务类
        """
        return import_module('module_admin.service.job_log_service').JobLogService
