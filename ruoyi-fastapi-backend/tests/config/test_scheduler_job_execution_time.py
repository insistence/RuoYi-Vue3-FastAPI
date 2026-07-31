from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.dialects import mysql, postgresql

from config.get_scheduler import SchedulerUtil
from module_admin.entity.do.job_do import SysJobLog
from module_admin.entity.vo.job_vo import JobLogModel, JobModel


def _build_job() -> JobModel:
    return JobModel(
        jobId=1,
        jobName='执行时间测试',
        jobGroup='default',
        jobExecutor='default',
        invokeTarget='module_task.scheduler_test.job',
        cronExpression='0/10 * * * * ?',
        misfirePolicy='3',
        concurrent='1',
        status='0',
    )


@pytest.mark.asyncio
async def test_async_job_records_execution_start_and_end_time() -> None:
    async def async_job() -> None:
        return None

    with patch.object(SchedulerUtil, '_record_job_execution_log') as record_job_log:
        await SchedulerUtil._execute_async_job_with_log(async_job, _build_job(), [], {})

    record_args = record_job_log.call_args.args
    assert isinstance(record_args[4], datetime)
    assert isinstance(record_args[5], datetime)
    assert record_args[4] <= record_args[5]


def test_job_log_model_exports_execution_time_aliases() -> None:
    start_time = datetime(2026, 3, 20, 10, 0, 0)
    end_time = datetime(2026, 3, 20, 10, 0, 1)

    payload = JobLogModel(startTime=start_time, endTime=end_time).model_dump(by_alias=True)

    assert payload['startTime'] == start_time
    assert payload['endTime'] == end_time


def test_job_log_execution_time_columns_use_millisecond_precision() -> None:
    start_time_type = SysJobLog.__table__.c.start_time.type
    end_time_type = SysJobLog.__table__.c.end_time.type

    assert str(start_time_type.compile(dialect=mysql.dialect())).lower() == 'datetime(3)'
    assert str(end_time_type.compile(dialect=mysql.dialect())).lower() == 'datetime(3)'
    assert str(start_time_type.compile(dialect=postgresql.dialect())).lower() == 'timestamp(3) without time zone'
    assert str(end_time_type.compile(dialect=postgresql.dialect())).lower() == 'timestamp(3) without time zone'
