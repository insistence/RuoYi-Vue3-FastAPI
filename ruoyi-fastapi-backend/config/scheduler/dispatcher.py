import asyncio
import time
from collections.abc import Callable

from sqlalchemy import update

from config.scheduler.jobs import SchedulerJobs
from config.scheduler.resources import SchedulerResources
from config.scheduler.synchronization import SchedulerSynchronizer
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from module_admin.entity.do.job_runtime_do import SysJobSync
from module_admin.entity.vo.job_vo import JobModel
from utils.log_util import logger
from utils.time_util import TimezoneUtil


class SchedulerDispatcher:
    """
    持久化执行请求领取、派发和下次调度时刻观测
    """

    def __init__(self, jobs: SchedulerJobs, resources: SchedulerResources, synchronizer: SchedulerSynchronizer) -> None:
        """
        初始化请求派发所需的任务、数据库和配置同步对象

        :param jobs: 本地任务管理器
        :param resources: 调度数据库资源
        :param synchronizer: 已应用配置管理器
        :return: None
        """
        self.jobs = jobs
        self.resources = resources
        self.synchronizer = synchronizer
        self.lock = asyncio.Lock()
        self._observed_at = 0.0

    async def refresh_observations(self, *, is_leader: Callable[[], bool]) -> None:
        """
        定期保存Leader观测的下次调度时刻，供其他worker读取

        :param is_leader: 检查当前进程是否仍持有Leader租约
        :return: None
        """
        now = time.monotonic()
        interval_seconds = 5
        if not is_leader() or now - self._observed_at < interval_seconds:
            return
        observed_time = TimezoneUtil.utc_now()
        observations = []
        for job_id, cached in self.synchronizer.applied_jobs.items():
            job = self.jobs.scheduler.get_job(str(job_id))
            observations.append((job_id, cached['appliedVersion'], getattr(job, 'next_run_time', None)))
        async with self.resources.session() as session:
            for job_id, version, next_run_time in observations:
                await session.execute(
                    update(SysJobSync)
                    .where(
                        SysJobSync.job_id == job_id,
                        SysJobSync.config_version == version,
                        SysJobSync.applied_version == version,
                        SysJobSync.sync_status == 'applied',
                    )
                    .values(next_run_time=next_run_time, schedule_observed_time=observed_time)
                )
            await session.commit()
        self._observed_at = now

    async def dispatch_pending(self, *, is_leader: Callable[[], bool]) -> None:
        """
        分批领取待执行请求，派发只在领取事务提交后进行

        :param is_leader: 检查当前进程是否仍持有Leader租约
        :return: None
        """
        if not is_leader() or self.lock.locked():
            return
        async with self.lock:
            await self.refresh_observations(is_leader=is_leader)
            async with self.resources.session() as session:
                await JobRuntimeDao.recover_expired(session)
                await session.commit()
                pending = await JobRuntimeDao.pending_ids(session)
            for execution_id, job_id in pending:
                if not is_leader():
                    return
                async with self.resources.session() as session:
                    execution = await JobRuntimeDao.claim_request(session, execution_id, job_id)
                    snapshot = execution.job_snapshot if execution is not None else None
                    token = execution.owner_token if execution is not None else None
                    await session.commit()
                if execution is None:
                    continue
                if not is_leader():
                    # 尚未开始的领取租约过期后由新 Leader 重新派发。
                    return
                try:
                    self.jobs.execute_once(
                        JobModel.model_validate(snapshot), execution_id=execution_id, dispatch_token=token
                    )
                except Exception as exc:
                    logger.exception(f'注册手动执行请求失败：{execution_id}')
                    async with self.resources.session() as session:
                        await JobRuntimeDao.fail_dispatch(session, execution_id, token, str(exc))
                        await session.commit()
