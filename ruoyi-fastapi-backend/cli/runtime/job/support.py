from typing import Any

from .gateway import JobInfrastructureGateway


class JobDomainSupport:
    """
    定时任务领域支持对象。

    该对象负责任务序列化、分页结果规整和任务操作元数据定义，
    避免主运行时服务继续承载细碎领域规则。

    :param infrastructure_gateway: 定时任务基础设施网关
    """

    def __init__(self, infrastructure_gateway: JobInfrastructureGateway) -> None:
        """
        初始化定时任务领域支持对象。

        :param infrastructure_gateway: 定时任务基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway

    @staticmethod
    def serialize_job_item(job_item: Any) -> dict[str, Any]:
        """
        序列化单个定时任务模型。

        :param job_item: 原始定时任务模型或字典
        :return: 可输出的定时任务字典
        """
        if hasattr(job_item, 'model_dump'):
            return dict(job_item.model_dump(by_alias=True, exclude_none=True))
        return dict(job_item)

    def serialize_job_items(self, job_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        序列化任务列表结果。

        :param job_items: 原始任务列表
        :return: 可输出的任务列表
        """
        return [self.serialize_job_item(item) for item in job_items]

    @staticmethod
    def build_job_operation_metadata(operation: str) -> dict[str, str]:
        """
        构建任务操作的统一元数据。

        :param operation: 操作名称
        :return: 操作元数据字典
        :raises ValueError: 操作名称不受支持时抛出异常
        """
        metadata_mapping = {
            'run-once': {
                'operationLabel': '执行一次任务',
                'successMessage': '定时任务已触发一次执行',
            },
            'pause': {
                'operationLabel': '暂停任务',
                'successMessage': '定时任务已暂停',
            },
            'resume': {
                'operationLabel': '恢复任务',
                'successMessage': '定时任务已恢复',
            },
        }
        if operation not in metadata_mapping:
            raise ValueError(f'不支持的任务操作：{operation}')
        return metadata_mapping[operation]

    def build_filters(
        self,
        *,
        job_name: str = '',
        job_group: str = '',
        status: str | None = None,
        begin_date: str = '',
        end_date: str = '',
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        构建任务列表或日志查询过滤条件。

        :param job_name: 任务名称
        :param job_group: 任务分组
        :param status: 状态
        :param begin_date: 开始日期
        :param end_date: 结束日期
        :param paged: 是否分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 过滤条件字典
        """
        filters = {
            'jobName': job_name,
            'jobGroup': job_group,
            'status': status,
            'paged': paged,
            'pageNum': page_num,
            'pageSize': page_size,
        }
        if begin_date or end_date:
            filters['beginDate'] = begin_date
            filters['endDate'] = end_date
        return filters

    def build_list_payload(
        self,
        result: Any,
        *,
        filters: dict[str, Any],
        paged: bool,
    ) -> dict[str, Any]:
        """
        统一构建任务列表或日志列表返回结构。

        :param result: 原始结果对象
        :param filters: 查询过滤条件
        :param paged: 是否分页
        :return: 可输出结果
        """
        if paged and isinstance(result, self.infrastructure_gateway.get_page_model()):
            page_payload = result.model_dump(by_alias=True)
            page_payload['rows'] = self.serialize_job_items(page_payload.get('rows', []))
            return {'ok': True, 'filters': filters, 'page': page_payload}

        items = self.serialize_job_items(result)
        return {'ok': True, 'filters': filters, 'count': len(items), 'items': items}


class JobSchedulerSupport:
    """
    定时任务调度上下文支持对象。

    该对象负责统一关闭调度器上下文资源，避免调度型操作在 facade 中
    持续堆叠资源清理细节。

    :param infrastructure_gateway: 定时任务基础设施网关
    """

    def __init__(self, infrastructure_gateway: JobInfrastructureGateway) -> None:
        """
        初始化定时任务调度上下文支持对象。

        :param infrastructure_gateway: 定时任务基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway

    async def close_scheduler_context(self, redis: Any) -> None:
        """
        安全关闭任务调度相关资源。

        :param redis: Redis 客户端实例
        :return: None
        """
        scheduler_util = self.infrastructure_gateway.get_scheduler_util()
        try:
            await scheduler_util.close_system_scheduler()
        except Exception:
            pass

        if redis is None:
            return

        try:
            await redis.close()
        except Exception:
            pass
