import pytest

from cli.runtime.job import JobRuntimeService
from cli.runtime.job.gateway import JobInfrastructureGateway
from cli.runtime.job.support import JobDomainSupport, JobSchedulerSupport

MISSING_JOB_ID = 99


def test_job_domain_support_builds_operation_metadata() -> None:
    """
    校验任务领域支持对象会返回统一的任务操作元数据。

    :return: None
    """
    support = JobDomainSupport(JobInfrastructureGateway())

    payload = support.build_job_operation_metadata('pause')

    assert payload == {
        'operationLabel': '暂停任务',
        'successMessage': '定时任务已暂停',
    }


def test_job_domain_support_serializes_model_dump_items() -> None:
    """
    校验任务领域支持对象会序列化带 `model_dump` 的任务项。

    :return: None
    """

    class FakeJobModel:
        """
        模拟任务模型。
        """

        @staticmethod
        def model_dump(*, by_alias: bool = False, exclude_none: bool = False) -> dict[str, object]:
            """
            返回模拟序列化结果。

            :param by_alias: 是否按别名输出
            :param exclude_none: 是否排除空值
            :return: 模拟序列化结果
            """
            assert by_alias is True
            assert exclude_none is True
            return {'jobId': 1, 'jobName': 'sync-job'}

    support = JobDomainSupport(JobInfrastructureGateway())

    payload = support.serialize_job_item(FakeJobModel())

    assert payload == {'jobId': 1, 'jobName': 'sync-job'}


@pytest.mark.asyncio
async def test_job_scheduler_support_closes_scheduler_and_redis() -> None:
    """
    校验任务调度支持对象会关闭调度器和 Redis 资源。

    :return: None
    """
    close_events: list[str] = []

    class FakeRedis:
        """
        模拟 Redis 客户端。
        """

        @staticmethod
        async def close() -> None:
            """
            记录 Redis 关闭事件。

            :return: None
            """
            close_events.append('redis')

    class FakeSchedulerUtil:
        """
        模拟调度器工具。
        """

        @staticmethod
        async def close_system_scheduler() -> None:
            """
            记录调度器关闭事件。

            :return: None
            """
            close_events.append('scheduler')

    gateway = JobInfrastructureGateway()
    support = JobSchedulerSupport(gateway)

    def _fake_get_scheduler_util() -> FakeSchedulerUtil:
        return FakeSchedulerUtil()

    object.__setattr__(gateway, 'get_scheduler_util', _fake_get_scheduler_util)

    await support.close_scheduler_context(FakeRedis())

    assert close_events == ['scheduler', 'redis']


@pytest.mark.asyncio
async def test_job_runtime_service_reports_missing_job_detail() -> None:
    """
    校验任务运行时在任务详情不存在时会返回统一结果。

    :return: None
    """

    class FakeSession:
        """
        模拟异步会话。
        """

        async def __aenter__(self) -> 'FakeSession':
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object,
        ) -> None:
            del exc_type, exc, tb

    class FakeSessionFactory:
        """
        模拟异步会话工厂。
        """

        def __call__(self) -> FakeSession:
            return FakeSession()

    class FakeJobService:
        """
        模拟任务服务。
        """

        @staticmethod
        async def job_detail_services(session: FakeSession, job_id: int) -> dict[str, object]:
            """
            返回不存在任务的空结果。

            :param session: 数据库会话
            :param job_id: 任务 ID
            :return: 空结果
            """
            assert isinstance(session, FakeSession)
            assert job_id == MISSING_JOB_ID
            return {}

    gateway = JobInfrastructureGateway()
    service = JobRuntimeService(infrastructure_gateway=gateway)

    def _fake_get_async_session_local() -> FakeSessionFactory:
        return FakeSessionFactory()

    def _fake_get_job_service() -> FakeJobService:
        return FakeJobService()

    object.__setattr__(gateway, 'get_async_session_local', _fake_get_async_session_local)
    object.__setattr__(gateway, 'get_job_service', _fake_get_job_service)

    payload = await service.get_job_detail(MISSING_JOB_ID)

    assert payload['ok'] is False
    assert payload['jobId'] == MISSING_JOB_ID
    assert payload['message'] == f'定时任务不存在：{MISSING_JOB_ID}'
