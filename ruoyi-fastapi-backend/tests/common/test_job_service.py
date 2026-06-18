import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from exceptions.exception import ServiceException  # noqa: E402
from module_admin.entity.vo.job_vo import JobModel  # noqa: E402
from module_admin.service.job_service import JobService  # noqa: E402


@pytest.mark.asyncio
async def test_add_job_rejects_plugin_invoke_target_from_system_job_form() -> None:
    """
    校验系统定时任务入口不会放开到整个 plugins 包。

    :return: None
    """
    job = JobModel(
        jobName='plugin-core-task',
        jobGroup='default',
        jobExecutor='default',
        invokeTarget='plugins.core.lifecycle.jobs.PluginJobInstaller.pause_plugin_jobs',
        cronExpression='0/5 * * * * ?',
        misfirePolicy='3',
        concurrent='1',
        status='1',
    )

    with pytest.raises(ServiceException) as exc_info:
        await JobService.add_job_services(object(), job)

    assert '目标字符串不在白名单内' in exc_info.value.message
