from collections.abc import Callable
from typing import Any

from config.scheduler.job_adapter import JobAdapter
from config.scheduler.jobs import SchedulerJobs
from config.scheduler.resources import SchedulerResources
from module_admin.dao.job_dao import JobDao
from module_admin.dao.job_runtime_dao import JobRuntimeDao
from utils.log_util import logger
from utils.time_util import TimezoneUtil


class SchedulerSynchronizer:
    """
    数据库任务配置校准和已应用版本管理
    """

    def __init__(self, jobs: SchedulerJobs, resources: SchedulerResources) -> None:
        """
        初始化配置同步所需的任务管理器和数据库资源

        :param jobs: 本地任务管理器
        :param resources: 调度数据库资源
        :return: None
        """
        self.jobs = jobs
        self.resources = resources
        self.applied_jobs: dict[int, dict[str, Any]] = {}

    async def sync_jobs(
        self,
        job_ids: set[int] | None = None,
        *,
        is_leader: Callable[[], bool],
        raise_errors: bool = False,
    ) -> dict[str, Any]:
        """
        按最新数据库配置同步指定任务，未指定 ID 时执行完整校准。

        :param job_ids: 需要同步的逻辑任务 ID，None 表示完整校准
        :param is_leader: 检查当前进程是否仍持有Leader租约
        :param raise_errors: 完整扫描失败时是否阻止调度器启动
        :return: 每个任务的应用结果及总体同步状态
        """
        if not is_leader():
            return self.result(
                [{'jobId': job_id, 'syncStatus': 'pending'} for job_id in sorted(job_ids or [])], default='pending'
            )
        full = job_ids is None
        scanned_jobs = {}
        pending_ids = set()
        try:
            if full:
                async with self.resources.session() as session:
                    rows = await JobDao.get_all_job_list_for_scheduler(session)
                    scanned_jobs = {row.job_id: JobAdapter.from_record(row) for row in rows}
                    pending_ids = await JobRuntimeDao.pending_sync_ids(session)
                job_ids = (
                    set(scanned_jobs)
                    | pending_ids
                    | {int(job.id) for job in self.jobs.scheduler.get_jobs() if job.id.isdecimal()}
                )
        except Exception as exc:
            if raise_errors:
                raise
            logger.exception('读取任务同步配置失败')
            return {'syncStatus': 'failed', 'jobs': [], 'syncError': str(exc)[:2000]}
        results = []
        for job_id in sorted(job_ids):
            if not is_leader():
                results.append({'jobId': job_id, 'syncStatus': 'pending'})
                continue
            job_info = scanned_jobs.get(job_id)
            cached = self.applied_jobs.get(job_id)
            if full and job_info and cached and job_id not in pending_ids:
                current = self.jobs.scheduler.get_job(str(job_id))
                try:
                    matches = (
                        self.jobs.is_config_current(current, job_info)
                        if current and job_info.status == '0'
                        else (current is None and job_info.status != '0')
                    )
                    if matches and cached.get('configHash') == JobAdapter.config_hash(job_info):
                        results.append({key: value for key, value in cached.items() if key != 'configHash'})
                        continue
                except Exception:
                    # 配置不再可用时进入单任务同步，持久化具体失败原因。
                    pass
            try:
                results.append(await self.sync_job(job_id, is_leader=is_leader))
            except Exception as exc:
                logger.exception(f'同步任务 {job_id} 的数据库操作失败')
                results.append({'jobId': job_id, 'syncStatus': 'failed', 'syncError': str(exc)[:2000]})
        return self.result(results)

    async def sync_job(self, job_id: int, *, is_leader: Callable[[], bool]) -> dict[str, Any]:
        """
        锁定并应用一个任务的最新配置，独立保存成功或失败状态

        :param job_id: 任务ID
        :param is_leader: 检查当前进程是否仍持有Leader租约
        :return: 任务同步结果
        """
        async with self.resources.session() as session:
            db_job, state = await JobRuntimeDao.lock_job(session, job_id)
            if not is_leader():
                await session.commit()
                return {'jobId': job_id, 'syncStatus': 'pending'}
            job_info = JobAdapter.from_record(db_job) if db_job else None
            try:
                if job_info is None or job_info.status != '0':
                    for current in self.jobs.scheduler.get_jobs():
                        if current.id == str(job_id):
                            self.jobs.scheduler.remove_job(current.id, jobstore=current._jobstore_alias)
                    self.jobs.forget_update_time(str(job_id))
                    if job_info is None:
                        await JobRuntimeDao.cancel_unstarted(session, [job_id])
                else:
                    current = self.jobs.scheduler.get_job(str(job_id), jobstore=job_info.job_store)
                    if current is None or not self.jobs.is_config_current(current, job_info):
                        self.jobs.register_job(job_info)
                    # 清理旧存储中残留的同 ID 定义；独立手动请求不参与此过程。
                    for other in self.jobs.scheduler.get_jobs():
                        if other.id == str(job_id) and other._jobstore_alias != job_info.job_store:
                            self.jobs.scheduler.remove_job(other.id, jobstore=other._jobstore_alias)
                    self.jobs.record_update_time(str(job_id), job_info.update_time)
                state.applied_version = state.config_version
                state.sync_status = 'applied'
                state.sync_error = None
                state.applied_time = TimezoneUtil.utc_now()
                current = self.jobs.scheduler.get_job(str(job_id))
                state.next_run_time = getattr(current, 'next_run_time', None)
                state.schedule_observed_time = state.applied_time
            except Exception as exc:
                state.sync_status = 'failed'
                state.sync_error = str(exc)[:2000]
                state.next_run_time = None
                state.schedule_observed_time = None
                logger.exception(f'应用任务 {job_id} 的调度配置失败')
            await session.commit()
            result = JobRuntimeDao.state_result(state)
            if state.sync_status == 'applied':
                self.applied_jobs[job_id] = {**result, 'configHash': state.config_hash}
            else:
                self.applied_jobs.pop(job_id, None)
            return result

    @staticmethod
    def result(jobs: list[dict[str, Any]], *, default: str = 'applied') -> dict[str, Any]:
        """
        汇总逐任务结果，失败和待同步状态不会被当成全部生效

        :param jobs: 各任务的同步结果
        :param default: 没有任务结果时使用的同步状态
        :return: 汇总后的同步结果
        """
        states = {job['syncStatus'] for job in jobs}
        status = 'failed' if 'failed' in states else ('pending' if 'pending' in states else default)
        return {'syncStatus': status, 'jobs': jobs}
