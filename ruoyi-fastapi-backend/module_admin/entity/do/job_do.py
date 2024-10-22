from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String
from config.database import Base


class SysJob(Base):
    """
    定时任务调度表
    """

    __tablename__ = 'sys_job'

    job_id = Column(Integer, primary_key=True, autoincrement=True, comment='任务ID')
    job_name = Column(String(64), nullable=True, default='', comment='任务名称')
    job_group = Column(String(64), nullable=True, default='default', comment='任务组名')
    job_executor = Column(String(64), nullable=True, default='default', comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(String(255), nullable=True, default='', comment='位置参数')
    job_kwargs = Column(String(255), nullable=True, default='', comment='关键字参数')
    cron_expression = Column(String(255), nullable=True, default='', comment='cron执行表达式')
    misfire_policy = Column(
        String(20),
        nullable=True,
        default='3',
        comment='计划执行错误策略（1立即执行 2执行一次 3放弃执行）',
    )
    concurrent = Column(String(1), nullable=True, default='1', comment='是否并发执行（0允许 1禁止）')
    status = Column(String(1), nullable=True, default='0', comment='状态（0正常 1暂停）')
    create_by = Column(String(64), nullable=True, default='', comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, default='', comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(String(500), nullable=True, default='', comment='备注信息')


class SysJobLog(Base):
    """
    定时任务调度日志表
    """

    __tablename__ = 'sys_job_log'

    job_log_id = Column(Integer, primary_key=True, autoincrement=True, comment='任务日志ID')
    job_name = Column(String(64), nullable=False, comment='任务名称')
    job_group = Column(String(64), nullable=False, comment='任务组名')
    job_executor = Column(String(64), nullable=False, comment='任务执行器')
    invoke_target = Column(String(500), nullable=False, comment='调用目标字符串')
    job_args = Column(String(255), nullable=True, default='', comment='位置参数')
    job_kwargs = Column(String(255), nullable=True, default='', comment='关键字参数')
    job_trigger = Column(String(255), nullable=True, default='', comment='任务触发器')
    job_message = Column(String(500), nullable=True, default='', comment='日志信息')
    status = Column(String(1), nullable=True, default='0', comment='执行状态（0正常 1失败）')
    exception_info = Column(String(2000), nullable=True, default='', comment='异常信息')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
