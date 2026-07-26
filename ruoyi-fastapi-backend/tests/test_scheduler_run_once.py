import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import get_scheduler
from config.get_scheduler import SchedulerUtil
from module_admin.entity.vo.job_vo import JobModel
from module_admin.service.job_service import JobService


def test_execute_scheduler_job_once_uses_independent_date_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    校验执行一次使用独立 DateTrigger 临时任务，不覆盖原 Cron 任务。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    added_jobs: list[dict[str, object]] = []

    class FakeScheduler:
        """
        模拟 APScheduler。
        """

        @staticmethod
        def add_job(**kwargs: object) -> None:
            """
            捕获新增任务参数。

            :param kwargs: 新增任务参数
            :return: None
            """
            added_jobs.append(kwargs)

    def fake_job() -> None:
        """
        模拟任务函数。

        :return: None
        """

    monkeypatch.setattr(get_scheduler, 'scheduler', FakeScheduler())
    monkeypatch.setattr(SchedulerUtil, '_is_leader', True)
    monkeypatch.setattr(SchedulerUtil, '_run_once_job_log_cache', {})
    monkeypatch.setattr(SchedulerUtil, '_import_function', classmethod(lambda cls, path: fake_job))

    job_info = JobModel(
        jobId=10,
        jobName='执行一次测试',
        jobGroup='sqlalchemy',
        jobExecutor='default',
        invokeTarget='module_task.scheduler_test.job',
        cronExpression='0/5 * * * * ?',
        misfirePolicy='1',
        concurrent='1',
        status='0',
    )

    SchedulerUtil.execute_scheduler_job_once(job_info)

    assert len(added_jobs) == 1
    added_job = added_jobs[0]
    run_once_job_id = str(added_job['id'])
    assert run_once_job_id.startswith(SchedulerUtil._run_once_job_id_prefix)
    assert run_once_job_id != str(job_info.job_id)
    assert type(added_job['trigger']).__name__ == 'DateTrigger'
    assert added_job['jobstore'] == 'default'
    assert SchedulerUtil._run_once_job_log_cache[run_once_job_id]['job_group'] == job_info.job_group


@pytest.mark.asyncio
async def test_execute_job_once_service_does_not_remove_existing_scheduler_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    校验执行一次服务不再删除原调度任务。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    calls: list[str] = []
    job_info = JobModel(jobId=10)

    async def fake_job_detail_services(query_db: object, job_id: int) -> JobModel:
        """
        返回模拟任务详情。

        :param query_db: 数据库会话
        :param job_id: 任务ID
        :return: 模拟任务详情
        """
        assert query_db == 'session'
        assert job_id == job_info.job_id
        return job_info

    monkeypatch.setattr(JobService, 'job_detail_services', fake_job_detail_services)
    monkeypatch.setattr(SchedulerUtil, 'remove_scheduler_job', lambda job_id: calls.append(f'remove:{job_id}'))
    monkeypatch.setattr(SchedulerUtil, 'execute_scheduler_job_once', lambda job_info: calls.append('execute'))

    result = await JobService.execute_job_once_services('session', JobModel(jobId=10))

    assert result.is_success is True
    assert result.message == '执行成功'
    assert calls == ['execute']
