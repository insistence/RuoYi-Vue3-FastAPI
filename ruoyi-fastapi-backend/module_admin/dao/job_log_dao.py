from datetime import datetime, time
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from module_admin.entity.do.job_do import SysJobLog
from module_admin.entity.vo.job_vo import JobLogModel, JobLogPageQueryModel
from utils.page_util import PageUtil


class JobLogDao:
    """
    定时任务日志管理模块数据库操作层
    """

    @classmethod
    async def get_job_log_list(cls, db: AsyncSession, query_object: JobLogPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取定时任务日志列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务日志列表信息对象
        """
        query = (
            select(SysJobLog)
            .where(
                SysJobLog.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                SysJobLog.job_group == query_object.job_group if query_object.job_group else True,
                SysJobLog.status == query_object.status if query_object.status else True,
                SysJobLog.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
            )
            .order_by(desc(SysJobLog.create_time))
            .distinct()
        )
        job_log_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return job_log_list

    @classmethod
    def add_job_log_dao(cls, db: Session, job_log: JobLogModel):
        """
        新增定时任务日志数据库操作

        :param db: orm对象
        :param job_log: 定时任务日志对象
        :return:
        """
        db_job_log = SysJobLog(**job_log.model_dump())
        db.add(db_job_log)
        db.flush()

        return db_job_log

    @classmethod
    async def delete_job_log_dao(cls, db: AsyncSession, job_log: JobLogModel):
        """
        删除定时任务日志数据库操作

        :param db: orm对象
        :param job_log: 定时任务日志对象
        :return:
        """
        await db.execute(delete(SysJobLog).where(SysJobLog.job_log_id.in_([job_log.job_log_id])))

    @classmethod
    async def clear_job_log_dao(cls, db: AsyncSession):
        """
        清除定时任务日志数据库操作

        :param db: orm对象
        :return:
        """
        await db.execute(delete(SysJobLog))
