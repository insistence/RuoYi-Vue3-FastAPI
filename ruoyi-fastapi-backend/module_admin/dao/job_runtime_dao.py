from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from config.scheduler.job_adapter import JobAdapter
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.do.job_runtime_do import SysJobExecution, SysJobSync
from module_admin.entity.vo.job_runtime_vo import JobExecutionQueryModel, JobSyncQueryModel
from module_admin.entity.vo.job_vo import JobModel
from utils.page_util import PageUtil
from utils.time_util import TimezoneUtil


class JobRuntimeDao:
    """
    在业务事务内维护版本、删除记录和手动执行请求
    """

    LEASE_SECONDS = 30

    @staticmethod
    async def ensure_state(db: AsyncSession, job_id: int) -> None:
        """
        原子建立状态行，避免两个事务首次接触同一任务时重复插入

        :param db: orm对象
        :param job_id: 任务ID
        :return: None
        """
        values = {
            'job_id': job_id,
            'config_version': 0,
            'applied_version': 0,
            'config_hash': '',
            'deleted': False,
            'sync_status': 'pending',
        }
        dialect = db.get_bind().dialect.name
        if dialect == 'mysql':
            statement = mysql_insert(SysJobSync).values(**values).on_duplicate_key_update(job_id=SysJobSync.job_id)
        elif dialect == 'postgresql':
            statement = postgres_insert(SysJobSync).values(**values).on_conflict_do_nothing(index_elements=['job_id'])
        elif dialect == 'sqlite':
            statement = sqlite_insert(SysJobSync).values(**values).on_conflict_do_nothing(index_elements=['job_id'])
        else:
            raise ValueError(f'任务状态不支持数据库方言：{dialect}')
        await db.execute(statement)

    @classmethod
    async def lock_job(cls, db: AsyncSession, job_id: int) -> tuple[SysJob | None, SysJobSync | None]:
        """
        按同步状态、任务记录的固定顺序加锁，并为已有任务建立初始状态

        :param db: orm对象
        :param job_id: 任务ID
        :return: 任务记录和同步状态
        """
        await cls.ensure_state(db, job_id)
        state = (
            await db.execute(select(SysJobSync).where(SysJobSync.job_id == job_id).with_for_update())
        ).scalar_one_or_none()
        job = (await db.execute(select(SysJob).where(SysJob.job_id == job_id).with_for_update())).scalars().first()
        state = await cls.record_configuration(db, job_id, JobAdapter.from_record(job) if job else None)
        return job, state

    @classmethod
    async def record_configuration(cls, db: AsyncSession, job_id: int, job: JobModel | None) -> SysJobSync:
        """
        在业务提交前记录最新配置版本，任务删除后仍保留同步状态

        :param db: orm对象
        :param job_id: 任务ID
        :param job: 任务对象信息
        :return: 最新任务同步状态
        """
        await cls.ensure_state(db, job_id)
        state = (
            await db.execute(select(SysJobSync).where(SysJobSync.job_id == job_id).with_for_update())
        ).scalar_one_or_none()
        digest = JobAdapter.config_hash(job)
        if state is None:
            state = SysJobSync(
                job_id=job_id,
                config_version=1,
                applied_version=0,
                config_hash=digest,
                deleted=job is None,
                sync_status='pending',
            )
            db.add(state)
        elif state.config_hash != digest:
            state.config_version += 1
            state.config_hash = digest
            state.deleted = job is None
            state.sync_status = 'pending'
            state.sync_error = None
            state.next_run_time = None
            state.schedule_observed_time = None
        await db.flush()
        return state

    @staticmethod
    def state_result(state: SysJobSync) -> dict[str, Any]:
        """
        构造可供接口返回的同步状态，避免暴露 ORM 对象

        :param state: 任务同步状态对象
        :return: 任务同步状态字典
        """
        return {
            'jobId': state.job_id,
            'configVersion': state.config_version,
            'appliedVersion': state.applied_version,
            'syncStatus': state.sync_status,
            'syncError': state.sync_error,
            'deleted': state.deleted,
            'appliedTime': state.applied_time,
            'nextRunTime': state.next_run_time,
            'scheduleObservedTime': state.schedule_observed_time,
        }

    @classmethod
    async def get_states(cls, db: AsyncSession, job_ids: list[int]) -> dict[int, dict[str, Any]]:
        """
        批量读取任务同步状态，供列表和变更响应使用

        :param db: orm对象
        :param job_ids: 任务ID集合
        :return: 任务ID与同步状态的映射
        """
        if not job_ids:
            return {}
        states = (
            (
                await db.execute(
                    select(SysJobSync).where(SysJobSync.job_id.in_(job_ids)).execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return {state.job_id: cls.state_result(state) for state in states}

    @classmethod
    async def all_sync_ids(cls, db: AsyncSession) -> set[int]:
        """
        收集任务与删除记录，支持完整校准和删除同步重试

        :param db: orm对象
        :return: 需要校准的任务ID集合
        """
        job_ids = (await db.execute(select(SysJob.job_id))).scalars().all()
        state_ids = (
            (await db.execute(select(SysJobSync.job_id).where(SysJobSync.sync_status != 'applied'))).scalars().all()
        )
        return set(job_ids) | set(state_ids)

    @staticmethod
    async def pending_sync_ids(db: AsyncSession) -> set[int]:
        """
        读取需要重试的同步状态，包括已经删除的任务

        :param db: orm对象
        :return: 待同步任务ID集合
        """
        return set(
            (await db.execute(select(SysJobSync.job_id).where(SysJobSync.sync_status != 'applied'))).scalars().all()
        )

    @staticmethod
    async def cancel_unstarted(db: AsyncSession, job_ids: list[int]) -> None:
        """
        删除任务时取消未开始的手动请求，保留运行中的执行记录

        :param db: orm对象
        :param job_ids: 任务ID集合
        :return: None
        """
        await db.execute(
            update(SysJobExecution)
            .where(SysJobExecution.job_id.in_(job_ids), SysJobExecution.status.in_(['pending', 'submitted']))
            .values(
                status='cancelled',
                message='任务已删除，取消尚未开始的执行',
                end_time=None,
                owner_token=None,
                lease_until=None,
            )
        )

    @classmethod
    async def create_request(cls, db: AsyncSession, job: JobModel, requested_by: str | None) -> SysJobExecution:
        """
        在事务内保存手动请求及配置快照，派发必须发生在提交之后

        :param db: orm对象
        :param job: 任务对象信息
        :param requested_by: 手动执行提交者
        :return: 新建的手动执行请求
        """
        request = SysJobExecution(
            execution_id=uuid4().hex,
            job_id=job.job_id,
            source='manual',
            status='pending',
            job_snapshot=job.model_dump(mode='json', by_alias=True),
            requested_by=requested_by,
        )
        db.add(request)
        await db.flush()
        return request

    @staticmethod
    async def get_execution(db: AsyncSession, execution_id: str) -> SysJobExecution | None:
        """
        按执行 ID 查询手动或定时执行结果

        :param db: orm对象
        :param execution_id: 执行ID
        :return: 执行记录，不存在时返回None
        """
        return await db.get(SysJobExecution, execution_id)

    @staticmethod
    async def execution_page(db: AsyncSession, query: JobExecutionQueryModel) -> PageModel:
        """
        分页查询执行状态，排除配置参数和内部占用凭据

        :param db: orm对象
        :param query: 查询参数对象
        :return: 执行记录分页信息
        """
        fields = [
            getattr(SysJobExecution, name)
            for name in (
                'execution_id',
                'job_id',
                'source',
                'status',
                'message',
                'requested_by',
                'create_time',
                'scheduled_time',
                'start_time',
                'end_time',
                'run_duration_ms',
            )
        ]
        statement = (
            select(*fields, SysJobExecution.job_snapshot['jobName'].as_string().label('job_name'))
            .where(
                SysJobExecution.job_id == query.job_id if query.job_id is not None else True,
                SysJobExecution.execution_id == query.execution_id if query.execution_id else True,
                SysJobExecution.status == query.status if query.status else True,
                SysJobExecution.source == query.source if query.source else True,
            )
            .order_by(SysJobExecution.create_time.desc(), SysJobExecution.execution_id.desc())
        )
        return await PageUtil.paginate(db, statement, query.page_num, query.page_size, is_page=True)

    @staticmethod
    async def sync_page(db: AsyncSession, query: JobSyncQueryModel) -> PageModel:
        """
        分页查询同步状态，删除任务后仍能查看结果和发起重试

        :param db: orm对象
        :param query: 查询参数对象
        :return: 同步状态分页信息
        """
        fields = [
            getattr(SysJobSync, name)
            for name in (
                'job_id',
                'config_version',
                'applied_version',
                'sync_status',
                'sync_error',
                'deleted',
                'applied_time',
                'update_time',
            )
        ]
        statement = (
            select(*fields)
            .where(
                SysJobSync.job_id == query.job_id if query.job_id is not None else True,
                SysJobSync.sync_status == query.sync_status if query.sync_status else True,
            )
            .order_by(SysJobSync.update_time.desc(), SysJobSync.job_id.desc())
        )
        return await PageUtil.paginate(db, statement, query.page_num, query.page_size, is_page=True)

    @staticmethod
    def execution_result(execution: SysJobExecution) -> dict[str, Any]:
        """
        返回执行状态和必要的时间信息，不返回调用参数快照

        :param execution: 执行记录对象
        :return: 执行状态及时间信息
        """
        return {
            'executionId': execution.execution_id,
            'jobId': execution.job_id,
            'jobName': execution.job_snapshot.get('jobName'),
            'source': execution.source,
            'status': execution.status,
            'message': execution.message,
            'requestedBy': execution.requested_by,
            'createTime': execution.create_time,
            'scheduledTime': execution.scheduled_time,
            'startTime': execution.start_time,
            'endTime': execution.end_time,
            'runDurationMs': execution.run_duration_ms,
        }

    @staticmethod
    async def recover_expired(db: AsyncSession) -> None:
        """
        重试尚未开始的过期派发；已开始的过期执行标记未知，禁止自动重放

        :param db: orm对象
        :return: None
        """
        now = TimezoneUtil.utc_now()
        await db.execute(
            update(SysJobExecution)
            .where(SysJobExecution.status == 'submitted', SysJobExecution.lease_until < now)
            .values(status='pending', owner_token=None, lease_until=None, message='派发租约过期，等待重新派发')
        )
        await db.execute(
            update(SysJobExecution)
            .where(SysJobExecution.status == 'running', SysJobExecution.lease_until < now)
            .values(status='unknown', message='执行租约过期，结果待确认；未自动重试')
        )

    @staticmethod
    async def pending_ids(db: AsyncSession, limit: int = 50) -> list[tuple[str, int]]:
        """
        按提交顺序读取一批待派发执行，不持有跨任务的行锁

        :param db: orm对象
        :param limit: 本次读取的最大请求数
        :return: 执行ID和任务ID列表
        """
        rows = (
            await db.execute(
                select(SysJobExecution.execution_id, SysJobExecution.job_id)
                .where(SysJobExecution.status == 'pending')
                .order_by(SysJobExecution.create_time, SysJobExecution.execution_id)
                .limit(limit)
            )
        ).all()
        return [(row.execution_id, row.job_id) for row in rows]

    @classmethod
    async def claim_request(cls, db: AsyncSession, execution_id: str, job_id: int) -> SysJobExecution | None:
        """
        原子领取尚未开始的手动请求，并绑定本次派发凭据

        :param db: orm对象
        :param execution_id: 执行ID
        :param job_id: 任务ID
        :return: 已领取的执行请求，未领取时返回None
        """
        job, _state = await cls.lock_job(db, job_id)
        execution = (
            await db.execute(
                select(SysJobExecution).where(SysJobExecution.execution_id == execution_id).with_for_update()
            )
        ).scalar_one_or_none()
        if execution is None or execution.status != 'pending':
            return None
        if job is None:
            execution.status = 'cancelled'
            execution.message = '任务已删除，取消尚未开始的执行'
            execution.end_time = TimezoneUtil.utc_now()
            return None
        execution.status = 'submitted'
        execution.owner_token = uuid4().hex
        execution.lease_until = TimezoneUtil.utc_now() + timedelta(seconds=cls.LEASE_SECONDS)
        execution.message = None
        return execution

    @staticmethod
    async def fail_dispatch(db: AsyncSession, execution_id: str, token: str, message: str) -> None:
        """
        记录确定未成功注册的派发失败，保留错误供用户查询

        :param db: orm对象
        :param execution_id: 执行ID
        :param token: 当前执行占用凭据
        :param message: 执行结果或未执行原因
        :return: None
        """
        await db.execute(
            update(SysJobExecution)
            .where(
                SysJobExecution.execution_id == execution_id,
                SysJobExecution.owner_token == token,
                SysJobExecution.status == 'submitted',
            )
            .values(status='failed', message=message[:2000], end_time=TimezoneUtil.utc_now(), lease_until=None)
        )
