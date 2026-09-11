import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from config.database import DataSourceRegistry, quiet_sql_engine
from config.env import DataBaseConfig
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
from utils.time_util import TimezoneUtil


@dataclass(frozen=True)
class ExecutionClaim:
    """
    实际执行前获得的占用凭据或明确的未执行原因
    """

    accepted: bool
    token: str | None = None
    status: str | None = None
    message: str | None = None


class JobExecutionStore:
    """
    使用独立短事务保存占用、续租和最终执行结果
    """

    LEASE_SECONDS = 30
    HEARTBEAT_SECONDS = 5

    @staticmethod
    def session() -> Session:
        """
        按当前进程的数据源配置创建独立同步会话

        :return: 同步数据库会话
        """
        engine = quiet_sql_engine(DataSourceRegistry.get_sync_engine(DataBaseConfig.db_default_source))
        return Session(engine, expire_on_commit=False)

    @classmethod
    def claim(
        cls,
        execution_id: str,
        job_id: int,
        snapshot: dict[str, Any],
        scheduled_time: datetime,
        *,
        dispatch_token: str | None = None,
    ) -> ExecutionClaim:
        """
        串行检查同一任务的并发占用，再原子标记本次执行开始

        :param execution_id: 执行ID
        :param job_id: 任务ID
        :param snapshot: 任务配置快照
        :param scheduled_time: 计划执行时刻
        :param dispatch_token: 本次派发的领取凭据
        :return: 执行占用结果
        """
        with cls.session() as db, db.begin():
            # 无值变更的 UPDATE 同时适用于 MySQL、PostgreSQL 和 SQLite 的写锁。
            locked = db.execute(
                update(SysJobSync)
                .where(SysJobSync.job_id == job_id)
                .values(
                    config_version=SysJobSync.config_version,
                    update_time=SysJobSync.update_time,
                )
            )
            if not locked.rowcount:
                return ExecutionClaim(False, status='failed', message='任务尚未完成调度状态初始化')
            execution = db.get(SysJobExecution, execution_id)
            if dispatch_token is not None:
                if execution is None or execution.status != 'submitted' or execution.owner_token != dispatch_token:
                    return ExecutionClaim(False, status='cancelled', message='执行请求已取消、已领取或派发凭据已失效')
            elif execution is not None:
                return ExecutionClaim(False, status=execution.status, message='该计划时刻已有执行记录，未重复执行')
            else:
                execution = SysJobExecution(
                    execution_id=execution_id,
                    job_id=job_id,
                    source='cron',
                    status='pending',
                    job_snapshot=snapshot,
                    scheduled_time=scheduled_time,
                )
                db.add(execution)
            job = db.execute(select(SysJob).where(SysJob.job_id == job_id)).scalars().first()
            if job is None or (dispatch_token is None and job.status != '0'):
                message = '任务已删除或已停用，取消尚未开始的定时执行' if dispatch_token is None else '任务已删除'
                cls._stop(execution, 'cancelled', message)
                return ExecutionClaim(False, status='cancelled', message=message)
            active = db.scalar(
                select(func.count())
                .select_from(SysJobExecution)
                .where(
                    SysJobExecution.job_id == job_id,
                    SysJobExecution.status.in_(['running', 'unknown']),
                )
            )
            limit = job.max_instances
            if active >= limit:
                message = f'达到任务并发上限 {limit}，本次未执行'
                cls._stop(execution, 'rejected', message)
                return ExecutionClaim(False, status='rejected', message=message)
            token = uuid4().hex
            execution.status = 'running'
            execution.owner_token = token
            execution.scheduled_time = scheduled_time
            execution.start_time = TimezoneUtil.utc_now()
            execution.lease_until = execution.start_time + timedelta(seconds=cls.LEASE_SECONDS)
            execution.message = None
            return ExecutionClaim(True, token=token, status='running')

    @staticmethod
    def _stop(execution: SysJobExecution, status: str, message: str) -> None:
        """
        保存未执行的终态，不伪造实际执行开始时间和耗时

        :param execution: 执行记录对象
        :param status: 执行状态
        :param message: 执行结果或未执行原因
        :return: None
        """
        execution.status = status
        execution.message = message
        execution.end_time = None
        execution.lease_until = None
        execution.owner_token = None

    @classmethod
    def renew(cls, execution_id: str, token: str) -> bool:
        """
        仅允许当前占用者续租；迟到的旧执行不能更新其他请求

        :param execution_id: 执行ID
        :param token: 当前执行占用凭据
        :return: 是否续租成功
        """
        with cls.session() as db, db.begin():
            result = db.execute(
                update(SysJobExecution)
                .where(
                    SysJobExecution.execution_id == execution_id,
                    SysJobExecution.owner_token == token,
                    SysJobExecution.status.in_(['running', 'unknown']),
                )
                .values(lease_until=TimezoneUtil.utc_now() + timedelta(seconds=cls.LEASE_SECONDS))
            )
            return bool(result.rowcount)

    @classmethod
    def finish(
        cls,
        execution_id: str,
        token: str,
        *,
        failed: bool,
        message: str | None,
        start_time: datetime,
        end_time: datetime,
        run_duration_ms: int,
    ) -> None:
        """
        按占用凭据保存真实执行结果；结果未知的原执行仍可补交最终结果

        :param execution_id: 执行ID
        :param token: 当前执行占用凭据
        :param failed: 是否执行失败
        :param message: 执行结果或未执行原因
        :param start_time: 实际执行开始时刻
        :param end_time: 实际执行结束时刻
        :param run_duration_ms: 实际执行耗时（毫秒）
        :return: None
        """
        with cls.session() as db, db.begin():
            db.execute(
                update(SysJobExecution)
                .where(
                    SysJobExecution.execution_id == execution_id,
                    SysJobExecution.owner_token == token,
                    SysJobExecution.status.in_(['running', 'unknown']),
                )
                .values(
                    status='failed' if failed else 'success',
                    message=(message or '执行成功')[:2000],
                    start_time=start_time,
                    end_time=end_time,
                    run_duration_ms=run_duration_ms,
                    lease_until=None,
                )
            )

    @classmethod
    def record_unstarted(
        cls,
        execution_id: str,
        job_id: int,
        snapshot: dict[str, Any],
        scheduled_time: datetime,
        status: str,
        message: str,
        *,
        dispatch_token: str | None = None,
    ) -> None:
        """
        记录过期或执行器拒绝，已有执行记录保持原状态以避免覆盖结果

        :param execution_id: 执行ID
        :param job_id: 任务ID
        :param snapshot: 任务配置快照
        :param scheduled_time: 计划执行时刻
        :param status: 执行状态
        :param message: 执行结果或未执行原因
        :param dispatch_token: 本次派发的领取凭据
        :return: None
        """
        with cls.session() as db, db.begin():
            locked = db.execute(
                update(SysJobSync)
                .where(SysJobSync.job_id == job_id)
                .values(
                    config_version=SysJobSync.config_version,
                    update_time=SysJobSync.update_time,
                )
            )
            if not locked.rowcount:
                return
            execution = db.get(SysJobExecution, execution_id)
            if execution is None and dispatch_token is None:
                execution = SysJobExecution(
                    execution_id=execution_id,
                    job_id=job_id,
                    source='cron',
                    status=status,
                    job_snapshot=snapshot,
                    scheduled_time=scheduled_time,
                )
                db.add(execution)
            elif execution is None or execution.status != 'submitted' or execution.owner_token != dispatch_token:
                return
            cls._stop(execution, status, message)


class ExecutionHeartbeat:
    """
    在同步、异步和进程池任务运行期间独立续租，退出时停止续租
    """

    def __init__(self, execution_id: str, token: str) -> None:
        """
        保存执行凭据，线程只在任务真正开始后创建

        :param execution_id: 执行ID
        :param token: 当前执行占用凭据
        :return: None
        """
        self.execution_id = execution_id
        self.token = token
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._renew, name=f'job-lease-{execution_id[:8]}', daemon=True)

    def start(self) -> None:
        """
        启动占用续租

        :return: None
        """
        self._thread.start()

    def stop(self) -> None:
        """
        通知续租线程退出，避免任务完成后继续持有占用

        :return: None
        """
        self._stop.set()

    def _renew(self) -> None:
        """
        周期续租；连接故障交由过期状态处理，不自动重放业务调用

        :return: None
        """
        while not self._stop.wait(JobExecutionStore.HEARTBEAT_SECONDS):
            if not self._renew_once():
                return

    def _renew_once(self) -> bool:
        """
        尝试续租一次，暂时断连后允许下一轮恢复连接

        :return: 是否继续续租
        """
        try:
            return JobExecutionStore.renew(self.execution_id, self.token)
        except Exception:
            logging.getLogger(__name__).exception('任务执行占用续租失败：%s', self.execution_id)
            return True
