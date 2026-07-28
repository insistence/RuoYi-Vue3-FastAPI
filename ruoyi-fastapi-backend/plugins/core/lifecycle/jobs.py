import json
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.job_dao import JobDao
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.vo.job_vo import JobModel
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginJobManifest
from plugins.core.utils import escape_sql_like


class PluginJobModelBuilder:
    """
    插件任务模型构建器。

    使用 Builder 模式将插件 manifest 中的任务声明转换为系统已有的 `JobModel`，
    让插件任务复用平台原有定时任务表、调度器和日志能力。
    """

    JOB_GROUP = 'default'
    JOB_NAME_MAX_LENGTH = 64
    REMARK_PREFIX = '[plugin-job]'

    @classmethod
    def build(cls, plugin_id: str, job: PluginJobManifest, *, enabled: bool = True) -> JobModel:
        """
        构建系统定时任务模型。

        :param plugin_id: 插件ID
        :param job: 插件定时任务声明
        :param enabled: 任务是否启用
        :return: 系统定时任务模型
        """
        cls._validate_callable_belongs_to_plugin(plugin_id, job.callable)
        return JobModel(
            jobName=cls.build_job_name(plugin_id, job.id),
            jobGroup=cls.JOB_GROUP,
            jobExecutor=job.executor,
            invokeTarget=job.callable,
            jobArgs=json.dumps(job.args, ensure_ascii=False) if job.args else '',
            jobKwargs=json.dumps(job.kwargs, ensure_ascii=False) if job.kwargs else '',
            cronExpression=job.cron_expression,
            misfirePolicy=job.misfire_policy,
            concurrent=job.concurrent,
            status='0' if enabled and job.enabled else '1',
            createBy='plugin',
            updateBy='plugin',
            remark=cls.build_remark(plugin_id, job),
        )

    @classmethod
    def _validate_callable_belongs_to_plugin(cls, plugin_id: str, callable_path: str) -> None:
        """
        校验插件任务 callable 模块归属。

        定时任务由系统调度器直接 importlib 导入执行，需在此二次校验模块前缀归属，
        与 PluginManifest 清单校验形成防御纵深。

        :param plugin_id: 插件ID
        :param callable_path: 任务调用目标
        :return: None
        """
        expected_prefix = f'plugins.{plugin_id}.'
        if not callable_path.startswith(expected_prefix):
            raise ValueError(f'插件任务 callable 必须归属当前插件模块（{expected_prefix}）：{callable_path}')

    @classmethod
    def build_job_name(cls, plugin_id: str, job_id: str) -> str:
        """
        构建插件任务在系统任务表中的任务名称。

        :param plugin_id: 插件ID
        :param job_id: 插件内任务ID
        :return: 系统任务名称
        """
        return f'{plugin_id}:{job_id}'

    @classmethod
    def build_remark(cls, plugin_id: str, job: PluginJobManifest) -> str:
        """
        构建插件任务备注。

        :param plugin_id: 插件ID
        :param job: 插件定时任务声明
        :return: 任务备注
        """
        description = job.description or f'插件 {plugin_id} 声明的定时任务 {job.id}'
        return f'{cls.REMARK_PREFIX} {plugin_id}:{job.id} {description}'[:500]


class PluginJobRepository:
    """
    插件任务仓储。

    插件任务复用系统 `sys_job` 表，但插件专用查询和批量清理逻辑收敛在插件模块内，
    避免向原任务 DAO 暴露插件语义。
    """

    def __init__(self, query_db: AsyncSession) -> None:
        """
        初始化插件任务仓储。

        :param query_db: orm对象
        :return: None
        """
        self.query_db = query_db

    async def get_job_detail_by_name_group(self, job_name: str, job_group: str) -> SysJob | None:
        """
        根据任务名称和任务组获取插件任务。

        :param job_name: 任务名称
        :param job_group: 任务组名
        :return: 定时任务信息对象
        """
        return (
            (
                await self.query_db.execute(
                    select(SysJob).where(
                        SysJob.job_name == job_name,
                        SysJob.job_group == job_group,
                    )
                )
            )
            .scalars()
            .first()
        )

    async def pause_jobs_by_name_prefix(self, job_name_prefix: str) -> None:
        """
        根据任务名称前缀暂停插件任务。

        :param job_name_prefix: 任务名称前缀
        :return: None
        """
        escaped_prefix = escape_sql_like(job_name_prefix)
        escaped_remark_prefix = escape_sql_like(f'{PluginJobModelBuilder.REMARK_PREFIX} {job_name_prefix}')
        await self.query_db.execute(
            update(SysJob)
            .where(
                SysJob.job_name.like(f'{escaped_prefix}%', escape='\\'),
                SysJob.remark.like(f'{escaped_remark_prefix}%', escape='\\'),
            )
            .values(status='1')
        )

    async def count_jobs_by_name_prefix(self, job_name_prefix: str) -> int:
        """
        根据任务名称前缀统计插件任务。

        :param job_name_prefix: 任务名称前缀
        :return: 定时任务数量
        """
        escaped_prefix = escape_sql_like(job_name_prefix)
        escaped_remark_prefix = escape_sql_like(f'{PluginJobModelBuilder.REMARK_PREFIX} {job_name_prefix}')
        job_count = (
            await self.query_db.execute(
                select(func.count())
                .select_from(SysJob)
                .where(
                    SysJob.job_name.like(f'{escaped_prefix}%', escape='\\'),
                    SysJob.remark.like(f'{escaped_remark_prefix}%', escape='\\'),
                )
            )
        ).scalar_one()

        return int(job_count)

    async def delete_jobs_by_name_prefix(self, job_name_prefix: str) -> None:
        """
        根据任务名称前缀删除插件任务。

        :param job_name_prefix: 任务名称前缀
        :return: None
        """
        escaped_prefix = escape_sql_like(job_name_prefix)
        escaped_remark_prefix = escape_sql_like(f'{PluginJobModelBuilder.REMARK_PREFIX} {job_name_prefix}')
        await self.query_db.execute(
            delete(SysJob).where(
                SysJob.job_name.like(f'{escaped_prefix}%', escape='\\'),
                SysJob.remark.like(f'{escaped_remark_prefix}%', escape='\\'),
            )
        )

    async def delete_plugin_jobs_except(self, plugin_id: str, desired_job_names: set[str]) -> None:
        """
        删除不再由插件 manifest 声明的插件任务。

        仅删除同时满足插件任务名称空间和平台 ownership remark 的记录，避免误删用户手工
        创建的同名前缀任务。

        :param plugin_id: 插件ID
        :param desired_job_names: manifest 当前声明的完整任务名称集合
        :return: None
        """
        job_name_prefix = f'{plugin_id}:'
        escaped_prefix = escape_sql_like(job_name_prefix)
        escaped_remark_prefix = escape_sql_like(f'{PluginJobModelBuilder.REMARK_PREFIX} {job_name_prefix}')
        query = delete(SysJob).where(
            SysJob.job_name.like(f'{escaped_prefix}%', escape='\\'),
            SysJob.remark.like(f'{escaped_remark_prefix}%', escape='\\'),
        )
        if desired_job_names:
            query = query.where(SysJob.job_name.not_in(sorted(desired_job_names)))
        await self.query_db.execute(query)


class PluginJobInstaller:
    """
    插件定时任务安装器。

    使用 Installer 模式负责将启用插件的任务声明幂等写入 `sys_job`，并在插件停用或
    出错时暂停对应任务。
    """

    def __init__(self, query_db: AsyncSession) -> None:
        """
        初始化插件定时任务安装器。

        :param query_db: orm对象
        :return: None
        """
        self.query_db = query_db
        self.repository = PluginJobRepository(query_db)

    async def install_plugin_jobs(self, discovered_plugin: DiscoveredPlugin, *, enabled: bool = True) -> list[JobModel]:
        """
        安装单个插件声明的定时任务。

        :param discovered_plugin: 已发现插件对象
        :param enabled: 插件是否启用
        :return: 已写入的任务模型列表
        """
        installed_jobs = []
        manifest = discovered_plugin.manifest
        desired_job_names = {PluginJobModelBuilder.build_job_name(manifest.id, job.id) for job in manifest.backend.jobs}
        await self.repository.delete_plugin_jobs_except(manifest.id, desired_job_names)
        for job in manifest.backend.jobs:
            job_model = PluginJobModelBuilder.build(manifest.id, job, enabled=enabled)
            await self.upsert_plugin_job(job_model)
            installed_jobs.append(job_model)

        return installed_jobs

    async def upsert_plugin_job(self, job_model: JobModel) -> SysJob:
        """
        幂等写入系统任务。

        :param job_model: 系统定时任务模型
        :return: 写入后的系统任务对象
        """
        existing_job = await self.repository.get_job_detail_by_name_group(job_model.job_name, job_model.job_group)
        now = datetime.now()
        if existing_job:
            ownership_prefix = f'{PluginJobModelBuilder.REMARK_PREFIX} {job_model.job_name}'
            if not str(existing_job.remark or '').startswith(ownership_prefix):
                raise ValueError(f'插件任务与非插件任务重名，拒绝覆盖：{job_model.job_name}（{job_model.job_group}）')
            await self.query_db.execute(
                update(SysJob)
                .where(
                    SysJob.job_id == existing_job.job_id,
                    SysJob.job_name == existing_job.job_name,
                    SysJob.job_group == existing_job.job_group,
                )
                .values(
                    job_executor=job_model.job_executor,
                    invoke_target=job_model.invoke_target,
                    job_args=job_model.job_args,
                    job_kwargs=job_model.job_kwargs,
                    cron_expression=job_model.cron_expression,
                    misfire_policy=job_model.misfire_policy,
                    concurrent=job_model.concurrent,
                    status=job_model.status,
                    update_by=job_model.update_by,
                    update_time=now,
                    remark=job_model.remark,
                )
            )
            return existing_job

        job_model.create_time = now
        job_model.update_time = now
        return await JobDao.add_job_dao(self.query_db, job_model)

    async def pause_plugin_jobs(self, plugin_id: str) -> None:
        """
        暂停指定插件的所有任务。

        :param plugin_id: 插件ID
        :return: None
        """
        await self.repository.pause_jobs_by_name_prefix(f'{plugin_id}:')
