from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.vo.job_vo import JobModel, JobPageQueryModel
from utils.page_util import PageUtil


class JobDao:
    """
    定时任务管理模块数据库操作层
    """

    @classmethod
    async def get_job_detail_by_id(cls, db: AsyncSession, job_id: int) -> SysJob | None:
        """
        根据定时任务id获取定时任务详细信息

        :param db: orm对象
        :param job_id: 定时任务id
        :return: 定时任务信息对象
        """
        job_info = (await db.execute(select(SysJob).where(SysJob.job_id == job_id))).scalars().first()

        return job_info

    @classmethod
    async def get_job_detail_by_name_group(cls, db: AsyncSession, job_name: str, job_group: str) -> SysJob | None:
        """
        根据任务名称和任务组获取定时任务详细信息。

        :param db: orm对象
        :param job_name: 任务名称
        :param job_group: 任务组名
        :return: 定时任务信息对象
        """
        job_info = (
            (
                await db.execute(
                    select(SysJob).where(
                        SysJob.job_name == job_name,
                        SysJob.job_group == job_group,
                    )
                )
            )
            .scalars()
            .first()
        )

        return job_info

    @classmethod
    async def get_job_detail_by_info(cls, db: AsyncSession, job: JobModel) -> SysJob | None:
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
    async def get_job_list(
        cls, db: AsyncSession, query_object: JobPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
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
        job_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return job_list

    @classmethod
    async def get_job_list_for_scheduler(cls, db: AsyncSession) -> Sequence[SysJob]:
        """
        获取定时任务列表信息

        :param db: orm对象
        :return: 定时任务列表信息对象
        """
        job_list = (await db.execute(select(SysJob).where(SysJob.status == '0').distinct())).scalars().all()

        return job_list

    @classmethod
    async def get_all_job_list_for_scheduler(cls, db: AsyncSession) -> Sequence[SysJob]:
        """
        获取全部定时任务列表信息

        :param db: orm对象
        :return: 定时任务列表信息对象
        """
        job_list = (await db.execute(select(SysJob).distinct())).scalars().all()

        return job_list

    @classmethod
    async def add_job_dao(cls, db: AsyncSession, job: JobModel) -> SysJob:
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
    async def edit_job_dao(cls, db: AsyncSession, job: dict, old_job: JobModel) -> None:
        """
        编辑定时任务数据库操作

        :param db: orm对象
        :param job: 需要更新的定时任务字典
        :param old_job: 原定时任务对象
        :return:
        """
        await db.execute(
            update(SysJob)
            .where(
                SysJob.job_id == old_job.job_id,
                SysJob.job_name == old_job.job_name,
                SysJob.job_group == old_job.job_group,
            )
            .values(**job)
        )

    @classmethod
    async def delete_job_dao(cls, db: AsyncSession, job: JobModel) -> None:
        """
        删除定时任务数据库操作

        :param db: orm对象
        :param job: 定时任务对象
        :return:
        """
        await db.execute(delete(SysJob).where(SysJob.job_id.in_([job.job_id])))

    @classmethod
    async def pause_jobs_by_name_prefix(cls, db: AsyncSession, job_name_prefix: str) -> None:
        """
        根据任务名称前缀暂停定时任务。

        :param db: orm对象
        :param job_name_prefix: 任务名称前缀
        :return: None
        """
        await db.execute(update(SysJob).where(SysJob.job_name.like(f'{job_name_prefix}%')).values(status='1'))

    @classmethod
    async def count_jobs_by_name_prefix(cls, db: AsyncSession, job_name_prefix: str) -> int:
        """
        根据任务名称前缀统计定时任务。

        :param db: orm对象
        :param job_name_prefix: 任务名称前缀
        :return: 定时任务数量
        """
        job_list = (
            (await db.execute(select(SysJob).where(SysJob.job_name.like(f'{job_name_prefix}%')))).scalars().all()
        )

        return len(job_list)

    @classmethod
    async def delete_jobs_by_name_prefix(cls, db: AsyncSession, job_name_prefix: str) -> None:
        """
        根据任务名称前缀删除定时任务。

        :param db: orm对象
        :param job_name_prefix: 任务名称前缀
        :return: None
        """
        await db.execute(delete(SysJob).where(SysJob.job_name.like(f'{job_name_prefix}%')))

    @classmethod
    async def pause_plugin_jobs_except(cls, db: AsyncSession, enabled_plugin_ids: set[str]) -> None:
        """
        暂停不在启用集合内的插件定时任务。

        :param db: orm对象
        :param enabled_plugin_ids: 启用插件ID集合
        :return: None
        """
        query = update(SysJob).where(SysJob.remark.like('[plugin-job]%'))
        for plugin_id in enabled_plugin_ids:
            query = query.where(SysJob.job_name.not_like(f'{plugin_id}:%'))
        await db.execute(query.values(status='1'))
