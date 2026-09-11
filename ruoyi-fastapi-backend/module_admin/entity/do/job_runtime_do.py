from sqlalchemy import JSON, BigInteger, Boolean, Column, Index, String, Text

from common.mixin import AuditTimeMixin
from common.types import DbUtcDateTime
from config.database import Base


class SysJobSync(AuditTimeMixin, Base):
    """
    任务配置版本和应用状态，删除任务后保留删除同步记录
    """

    __tablename__ = 'sys_job_sync'
    __table_args__ = (
        Index('ix_job_sync_status', 'sync_status', 'update_time'),
        {'comment': '任务调度同步状态'},
    )

    job_id = Column(BigInteger, primary_key=True, autoincrement=False, comment='逻辑任务ID')
    config_version = Column(BigInteger, nullable=False, default=1, comment='最新配置版本')
    applied_version = Column(BigInteger, nullable=False, default=0, comment='已应用版本')
    config_hash = Column(String(64), nullable=False, comment='最新配置摘要')
    deleted = Column(Boolean, nullable=False, default=False, comment='任务是否已删除')
    sync_status = Column(String(16), nullable=False, default='pending', comment='pending/applied/failed')
    sync_error = Column(String(2000), nullable=True, comment='最近同步错误')
    applied_time = Column(DbUtcDateTime(), nullable=True, comment='最近应用时刻')
    next_run_time = Column(DbUtcDateTime(), nullable=True, comment='最近观测的实际下次调度时刻')
    schedule_observed_time = Column(DbUtcDateTime(), nullable=True, comment='Leader调度观测时刻')


class SysJobExecution(AuditTimeMixin, Base):
    """
    手动执行请求及定时执行记录，运行记录同时承担跨进程并发占用
    """

    __tablename__ = 'sys_job_execution'
    __table_args__ = (
        Index('ix_job_execution_dispatch', 'status', 'create_time'),
        Index('ix_job_execution_active', 'job_id', 'status'),
        {'comment': '任务执行请求与状态'},
    )

    execution_id = Column(String(32), primary_key=True, comment='执行ID')
    job_id = Column(BigInteger, nullable=False, comment='逻辑任务ID')
    source = Column(String(10), nullable=False, comment='manual/cron')
    status = Column(String(16), nullable=False, default='pending', comment='执行状态')
    job_snapshot = Column(JSON, nullable=False, comment='提交时任务配置快照')
    owner_token = Column(String(64), nullable=True, comment='派发或执行占用凭据')
    lease_until = Column(DbUtcDateTime(), nullable=True, comment='执行占用租约截止时刻')
    scheduled_time = Column(DbUtcDateTime(), nullable=True, comment='计划执行时刻')
    start_time = Column(DbUtcDateTime(), nullable=True, comment='实际开始时刻')
    end_time = Column(DbUtcDateTime(), nullable=True, comment='实际结束时刻')
    run_duration_ms = Column(BigInteger, nullable=True, comment='实际执行耗时（毫秒）')
    message = Column(Text, nullable=True, comment='执行结果或未执行原因')
    requested_by = Column(String(64), nullable=True, comment='手动执行提交者')
