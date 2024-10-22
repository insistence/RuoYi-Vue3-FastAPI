from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.vo.job_vo import JobModel, JobPageQueryModel
from utils.page_util import PageUtil


class JobDao:
    """
    定时任务管理模块数据库操作层
    """

    @classmethod
    async def get_job_detail_by_id(cls, db: AsyncSession, job_id: int):
        """
        根据定时任务id获取定时任务详细信息

        :param db: orm对象
        :param job_id: 定时任务id
        :return: 定时任务信息对象
        """
        job_info = (await db.execute(select(SysJob).where(SysJob.job_id == job_id))).scalars().first()

        return job_info

    @classmethod
    async def get_job_detail_by_info(cls, db: AsyncSession, job: JobModel):
        """
        根据定时任务参数获取定时任务信息

        :param db: orm对象
        :param job: 定时任务参数对象
        :return: 定时任务信息对象
        """
        job_info = (
            (
                await db.execute(
                    select(SysJob).where(
                        SysJob.job_name == job.job_name,
                        SysJob.job_group == job.job_group,
                        SysJob.job_executor == job.job_executor,
                        SysJob.invoke_target == job.invoke_target,
                        SysJob.job_args == job.job_args,
                        SysJob.job_kwargs == job.job_kwargs,
                        SysJob.cron_expression == job.cron_expression,
                    )
                )
            )
            .scalars()
            .first()
        )

        return job_info

    @classmethod
    async def get_job_list(cls, db: AsyncSession, query_object: JobPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取定时任务列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务列表信息对象
        """
        query = (
            select(SysJob)
            .where(
                SysJob.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                SysJob.job_group == query_object.job_group if query_object.job_group else True,
                SysJob.status == query_object.status if query_object.status else True,
            )
            .order_by(SysJob.job_id)
            .distinct()
        )
        job_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return job_list

    @classmethod
    async def get_job_list_for_scheduler(cls, db: AsyncSession):
        """
        获取定时任务列表信息

        :param db: orm对象
        :return: 定时任务列表信息对象
        """
        job_list = (await db.execute(select(SysJob).where(SysJob.status == '0').distinct())).scalars().all()

        return job_list

    @classmethod
    async def add_job_dao(cls, db: AsyncSession, job: JobModel):
        """
        新增定时任务数据库操作

        :param db: orm对象
        :param job: 定时任务对象
        :return:
        """
        db_job = SysJob(**job.model_dump())
        db.add(db_job)
        await db.flush()

        return db_job

    @classmethod
    async def edit_job_dao(cls, db: AsyncSession, job: dict):
        """
        编辑定时任务数据库操作

        :param db: orm对象
        :param job: 需要更新的定时任务字典
        :return:
        """
        await db.execute(update(SysJob), [job])

    @classmethod
    async def delete_job_dao(cls, db: AsyncSession, job: JobModel):
        """
        删除定时任务数据库操作

        :param db: orm对象
        :param job: 定时任务对象
        :return:
        """
        await db.execute(delete(SysJob).where(SysJob.job_id.in_([job.job_id])))
