from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from common.mixin import AuditTimeMixin, CreateTimeMixin
from common.types import DbUtcDateTime
from config.database import Base


class SysJob(AuditTimeMixin, Base):
    """
    定时任务调度表
    """

    __tablename__ = 'sys_job'
    __table_args__ = (
        UniqueConstraint('job_group', 'job_name', name='uq_job_group_name'),
        CheckConstraint('max_instances >= 1', name='ck_job_max_instances'),
        CheckConstraint('misfire_grace_time IS NULL OR misfire_grace_time >= 1', name='ck_job_misfire_grace'),
        {'comment': '定时任务调度表'},
    )

    job_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务ID')
    job_name = Column(String(64), nullable=False, comment='任务名称（同一业务分组内唯一）')
    job_group = Column(String(64), nullable=False, server_default='default', comment='业务分组')
    job_store = Column(String(64), nullable=False, server_default='default', comment='调度存储')
    job_executor = Column(String(64), nullable=True, server_default='default', comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(JSON, nullable=False, default=list, comment='位置参数（JSON数组）')
    job_kwargs = Column(JSON, nullable=False, default=dict, comment='关键字参数（JSON对象）')
    cron_expression = Column(String(255), nullable=True, server_default="''", comment='cron执行表达式')
    time_zone = Column(String(64), nullable=False, comment='cron时区（IANA）')
    misfire_grace_time = Column(
        Integer().evaluates_none(), nullable=True, default=1, comment='允许延迟秒数，NULL表示不限'
    )
    coalesce = Column(Boolean, nullable=False, default=False, comment='积压时是否只执行最近一次')
    max_instances = Column(Integer, nullable=False, server_default='1', comment='任务最大并发数')
    status = Column(CHAR(1), nullable=False, server_default='1', comment='状态（0正常 1暂停）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    remark = Column(String(500), nullable=True, server_default="''", comment='备注信息')


class SysJobLog(CreateTimeMixin, Base):
    """
    定时任务调度日志表
    """

    __tablename__ = 'sys_job_log'
    __table_args__ = (
        Index('ix_job_log_job_id', 'job_id', 'create_time'),
        Index('ix_job_log_execution_id', 'execution_id'),
        {'comment': '定时任务调度日志表'},
    )

    job_log_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务日志ID')
    job_id = Column(BigInteger, nullable=True, comment='逻辑任务ID，历史未关联日志可为空')
    execution_id = Column(String(32), nullable=True, comment='执行ID，历史未关联日志可为空')
    job_name = Column(String(64), nullable=False, comment='任务名称')
    job_group = Column(String(64), nullable=False, comment='任务组名')
    job_store = Column(String(64), nullable=True, comment='调度存储快照')
    job_executor = Column(String(64), nullable=False, comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(JSON, nullable=True, comment='位置参数快照（JSON数组）')
    job_kwargs = Column(JSON, nullable=True, comment='关键字参数快照（JSON对象）')
    job_trigger = Column(String(255), nullable=True, server_default="''", comment='任务触发器')
    time_zone = Column(String(64), nullable=True, comment='任务时区快照（IANA）')
    job_message = Column(String(500), nullable=True, comment='日志信息')
    status = Column(CHAR(1), nullable=True, server_default='0', comment='执行状态（0正常 1失败）')
    exception_info = Column(String(2000), nullable=True, server_default="''", comment='异常信息')
    scheduled_time = Column(DbUtcDateTime(), nullable=True, comment='计划执行时刻')
    start_time = Column(DbUtcDateTime(), nullable=True, comment='执行开始时间')
    end_time = Column(DbUtcDateTime(), nullable=True, comment='执行结束时间')
    run_duration_ms = Column(BigInteger, nullable=True, comment='实际执行耗时（毫秒）')
