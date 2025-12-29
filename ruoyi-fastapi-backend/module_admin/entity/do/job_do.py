from datetime import datetime

from sqlalchemy import CHAR, DOUBLE, BigInteger, Column, DateTime, Float, Index, LargeBinary, String, Unicode

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysJob(Base):
    """
    定时任务调度表
    """

    __tablename__ = 'sys_job'
    __table_args__ = {'comment': '定时任务调度表'}

    job_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务ID')
    job_name = Column(String(64), primary_key=True, nullable=False, server_default="''", comment='任务名称')
    job_group = Column(String(64), primary_key=True, nullable=False, server_default='default', comment='任务组名')
    job_executor = Column(String(64), nullable=True, server_default='default', comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(String(255), nullable=True, server_default="''", comment='位置参数')
    job_kwargs = Column(String(255), nullable=True, server_default="''", comment='关键字参数')
    cron_expression = Column(String(255), nullable=True, server_default="''", comment='cron执行表达式')
    misfire_policy = Column(
        String(20),
        nullable=True,
        server_default='3',
        comment='计划执行错误策略（1立即执行 2执行一次 3放弃执行）',
    )
    concurrent = Column(CHAR(1), nullable=True, server_default='1', comment='是否并发执行（0允许 1禁止）')
    status = Column(CHAR(1), nullable=True, server_default='0', comment='状态（0正常 1暂停）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(String(500), nullable=True, server_default="''", comment='备注信息')


class SysJobLog(Base):
    """
    定时任务调度日志表
    """

    __tablename__ = 'sys_job_log'
    __table_args__ = {'comment': '定时任务调度日志表'}

    job_log_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务日志ID')
    job_name = Column(String(64), nullable=False, comment='任务名称')
    job_group = Column(String(64), nullable=False, comment='任务组名')
    job_executor = Column(String(64), nullable=False, comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(String(255), nullable=True, server_default="''", comment='位置参数')
    job_kwargs = Column(String(255), nullable=True, server_default="''", comment='关键字参数')
    job_trigger = Column(String(255), nullable=True, server_default="''", comment='任务触发器')
    job_message = Column(String(500), nullable=True, comment='日志信息')
    status = Column(CHAR(1), nullable=True, server_default='0', comment='执行状态（0正常 1失败）')
    exception_info = Column(String(2000), nullable=True, server_default="''", comment='异常信息')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')


class ApschedulerJobs(Base):
    """
    定时任务调度任务表
    """

    __tablename__ = 'apscheduler_jobs'

    id = Column(Unicode(191), primary_key=True, nullable=False)
    next_run_time = Column(
        DOUBLE if DataBaseConfig.db_type == 'mysql' else Float(25),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
    )
    job_state = Column(LargeBinary, nullable=False)

    idx_sys_logininfor_s = Index('ix_apscheduler_jobs_next_run_time', next_run_time)
