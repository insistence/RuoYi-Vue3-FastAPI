from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from common.vo import PageModel
from module_admin.entity.do.job_do import SysJobLog
from module_admin.entity.vo.job_vo import JobLogModel, JobLogPageQueryModel
from utils.page_util import PageUtil
from utils.time_util import TimezoneUtil


class JobLogDao:
    """
    定时任务日志管理模块数据库操作层
    """

    @classmethod
    async def get_job_log_list(
        cls, db: AsyncSession, query_object: JobLogPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取定时任务日志列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务日志列表信息对象
        """
        time_range = TimezoneUtil.local_date_strings_to_utc(
            query_object.begin_time, query_object.end_time, timezone_name=TimezoneUtil.get_request_timezone()
        )
        query = (
            select(SysJobLog)
            .where(
                SysJobLog.job_id == query_object.job_id if query_object.job_id is not None else True,
                SysJobLog.execution_id == query_object.execution_id if query_object.execution_id else True,
                SysJobLog.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                SysJobLog.job_group == query_object.job_group if query_object.job_group else True,
                SysJobLog.status == query_object.status if query_object.status else True,
                SysJobLog.create_time >= time_range[0] if time_range and time_range[0] is not None else True,
                SysJobLog.create_time < time_range[1] if time_range and time_range[1] is not None else True,
            )
            .order_by(desc(SysJobLog.create_time))
        )
        job_log_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return job_log_list

    @classmethod
    def add_job_log_dao(cls, db: Session, job_log: JobLogModel) -> SysJobLog:
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
    async def delete_job_log_dao(cls, db: AsyncSession, job_log: JobLogModel) -> None:
        """
        删除定时任务日志数据库操作

        :param db: orm对象
        :param job_log: 定时任务日志对象
        :return:
        """
        await db.execute(delete(SysJobLog).where(SysJobLog.job_log_id.in_([job_log.job_log_id])))

    @classmethod
    async def clear_job_log_dao(cls, db: AsyncSession) -> None:
        """
        清除定时任务日志数据库操作

        :param db: orm对象
        :return:
        """
        await db.execute(delete(SysJobLog))
