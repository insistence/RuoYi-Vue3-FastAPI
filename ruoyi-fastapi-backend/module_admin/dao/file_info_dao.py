from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, case, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.file_do import (
    SysFileAcl,
    SysFileInfo,
    SysFileReconcileIssue,
    SysFileReconcileRun,
    SysFileReference,
    SysFileRetentionNotice,
)
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.file_vo import (
    FileInfoModel,
    FileInfoPageQueryModel,
    FileReconcileIssuePageQueryModel,
    FileReconcileRunPageQueryModel,
    FileStatsModel,
)
from utils.page_util import PageUtil


class FileInfoDao:
    """
    文件信息数据操作层
    """

    FILE_EXPIRING_DAYS = 7
    ACL_EXPIRING_DAYS = 7

    @classmethod
    async def add_file_info_dao(cls, db: AsyncSession, file_info: FileInfoModel) -> SysFileInfo:
        """
        新增文件信息

        :param db: orm对象
        :param file_info: 文件信息对象
        :return: 文件信息数据库对象
        """
        db_file_info = SysFileInfo(**file_info.model_dump())
        db.add(db_file_info)
        await db.flush()
        return db_file_info

    @classmethod
    async def get_file_info_by_id(
        cls,
        db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement | None = None,
    ) -> SysFileInfo | None:
        """
        根据文件ID获取有效文件信息

        :param db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象
        """
        return (
            (
                await db.execute(
                    select(SysFileInfo).where(
                        SysFileInfo.file_id == file_id,
                        SysFileInfo.status == 'active',
                        SysFileInfo.del_flag == '0',
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def release_stale_runs(cls, db: AsyncSession, stale_before: datetime, current_time: datetime) -> None:
        """
        释放超时未完成的对账任务锁

        :param db: orm对象
        :param stale_before: 超时边界
        :param current_time: 当前时间
        :return: None
        """
        await db.execute(
            update(SysFileReconcileRun)
            .where(
                SysFileReconcileRun.status == 'running',
                SysFileReconcileRun.started_time < stale_before,
            )
            .values(
                status='failed',
                lock_name=None,
                finished_time=current_time,
                error_message='对账任务运行超时，已自动释放运行锁',
            )
        )

    @classmethod
    async def add_reconcile_run(cls, db: AsyncSession, reconcile_run: SysFileReconcileRun) -> None:
        """
        新增文件存储对账任务

        :param db: orm对象
        :param reconcile_run: 对账任务
        :return: None
        """
        db.add(reconcile_run)
        await db.flush()

    @classmethod
    async def get_reconcile_run_by_id(cls, db: AsyncSession, run_id: str) -> SysFileReconcileRun | None:
        """
        根据任务ID获取文件存储对账任务

        :param db: orm对象
        :param run_id: 任务ID
        :return: 对账任务
        """
        return (
            (await db.execute(select(SysFileReconcileRun).where(SysFileReconcileRun.run_id == run_id)))
            .scalars()
            .first()
        )

    @classmethod
    async def has_running_reconcile_run(cls, db: AsyncSession) -> bool:
        """
        判断是否存在运行中的文件存储对账任务

        :param db: orm对象
        :return: 是否正在运行
        """
        return bool(await db.scalar(select(exists().where(SysFileReconcileRun.status == 'running'))))

    @classmethod
    async def get_reconcile_run_list(
        cls,
        db: AsyncSession,
        query_object: FileReconcileRunPageQueryModel,
        is_page: bool = True,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取文件存储对账任务列表

        :param db: orm对象
        :param query_object: 查询参数
        :param is_page: 是否分页
        :return: 对账任务列表
        """
        query = (
            select(
                SysFileReconcileRun.run_id,
                SysFileReconcileRun.trigger_type,
                SysFileReconcileRun.status,
                SysFileReconcileRun.check_hash,
                SysFileReconcileRun.scanned_file_count,
                SysFileReconcileRun.scanned_storage_count,
                SysFileReconcileRun.issue_count,
                SysFileReconcileRun.new_issue_count,
                SysFileReconcileRun.resolved_issue_count,
                SysFileReconcileRun.started_by,
                SysFileReconcileRun.started_time,
                SysFileReconcileRun.finished_time,
                SysFileReconcileRun.error_message,
            )
            .where(
                SysFileReconcileRun.status == query_object.status if query_object.status else True,
                SysFileReconcileRun.trigger_type == query_object.trigger_type if query_object.trigger_type else True,
            )
            .order_by(SysFileReconcileRun.started_time.desc(), SysFileReconcileRun.run_id.desc())
        )
        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def get_all_local_file_infos(cls, db: AsyncSession) -> list[dict[str, Any]]:
        """
        获取全部本地文件存储信息

        :param db: orm对象
        :return: 文件存储信息列表
        """
        rows = (
            (
                await db.execute(
                    select(
                        SysFileInfo.file_id,
                        SysFileInfo.storage_type,
                        SysFileInfo.access_type,
                        SysFileInfo.storage_key,
                        SysFileInfo.stored_name,
                        SysFileInfo.file_size,
                        SysFileInfo.file_hash,
                        SysFileInfo.status,
                        SysFileInfo.del_flag,
                    ).where(SysFileInfo.storage_type == 'local')
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    @classmethod
    async def upsert_reconcile_issues(
        cls,
        db: AsyncSession,
        run_id: str,
        findings: list[dict[str, Any]],
        current_time: datetime,
    ) -> int:
        """
        新增或更新文件存储对账异常

        :param db: orm对象
        :param run_id: 任务ID
        :param findings: 对账异常列表
        :param current_time: 当前时间
        :return: 新增或重新出现异常数
        """
        issue_keys = [finding['issue_key'] for finding in findings]
        issue_map: dict[str, SysFileReconcileIssue] = {}
        for start in range(0, len(issue_keys), 500):
            batch_keys = issue_keys[start : start + 500]
            issue_map.update(
                {
                    issue.issue_key: issue
                    for issue in (
                        (
                            await db.execute(
                                select(SysFileReconcileIssue).where(SysFileReconcileIssue.issue_key.in_(batch_keys))
                            )
                        )
                        .scalars()
                        .all()
                    )
                }
            )

        new_issue_count = 0
        for finding in findings:
            issue = issue_map.get(finding['issue_key'])
            if issue is None:
                db.add(
                    SysFileReconcileIssue(
                        **finding,
                        last_run_id=run_id,
                        status='open',
                        occurrence_count=1,
                        first_seen_time=current_time,
                        last_seen_time=current_time,
                    )
                )
                new_issue_count += 1
                continue
            if issue.status in {'resolved', 'quarantined'}:
                issue.status = 'open'
                issue.handle_action = 'reopened_by_scan'
                issue.handle_reason = '异常在后续扫描中再次出现'
                issue.handled_by = 'system'
                issue.handled_time = current_time
                new_issue_count += 1
            for field_name, value in finding.items():
                if field_name != 'issue_key':
                    setattr(issue, field_name, value)
            issue.last_run_id = run_id
            issue.last_seen_time = current_time
            issue.occurrence_count = (issue.occurrence_count or 0) + 1
        await db.flush()
        return new_issue_count

    @classmethod
    async def resolve_disappeared_issues(
        cls,
        db: AsyncSession,
        run_id: str,
        current_time: datetime,
    ) -> int:
        """
        自动关闭本次扫描未再次出现的异常

        :param db: orm对象
        :param run_id: 任务ID
        :param current_time: 当前时间
        :return: 自动关闭数量
        """
        result = await db.execute(
            update(SysFileReconcileIssue)
            .where(
                SysFileReconcileIssue.status.in_(['open', 'ignored']),
                SysFileReconcileIssue.last_run_id != run_id,
            )
            .values(
                status='resolved',
                handle_action='auto_resolved',
                handle_reason='异常在后续完整扫描中未再次出现',
                handled_by='system',
                handled_time=current_time,
            )
        )
        return int(result.rowcount or 0)

    @classmethod
    async def finish_reconcile_run(
        cls,
        db: AsyncSession,
        run_id: str,
        *,
        status: str,
        finished_time: datetime,
        scanned_file_count: int = 0,
        scanned_storage_count: int = 0,
        issue_count: int = 0,
        new_issue_count: int = 0,
        resolved_issue_count: int = 0,
        error_message: str = '',
    ) -> None:
        """
        完成文件存储对账任务

        :return: None
        """
        await db.execute(
            update(SysFileReconcileRun)
            .where(SysFileReconcileRun.run_id == run_id)
            .values(
                status=status,
                lock_name=None,
                finished_time=finished_time,
                scanned_file_count=scanned_file_count,
                scanned_storage_count=scanned_storage_count,
                issue_count=issue_count,
                new_issue_count=new_issue_count,
                resolved_issue_count=resolved_issue_count,
                error_message=error_message,
            )
        )

    @classmethod
    async def get_reconcile_issue_list(
        cls,
        db: AsyncSession,
        query_object: FileReconcileIssuePageQueryModel,
        is_page: bool = True,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取文件存储对账异常列表

        :param db: orm对象
        :param query_object: 查询参数
        :param is_page: 是否分页
        :return: 对账异常列表
        """
        keyword_condition: ColumnElement | bool = True
        if query_object.keyword:
            keyword = f'%{query_object.keyword}%'
            keyword_condition = or_(
                SysFileReconcileIssue.file_id.like(keyword),
                SysFileInfo.original_name.like(keyword),
                SysFileReconcileIssue.expected_key.like(keyword),
                SysFileReconcileIssue.actual_key.like(keyword),
            )
        query = (
            select(
                *SysFileReconcileIssue.__table__.c,
                SysFileInfo.original_name,
            )
            .outerjoin(SysFileInfo, SysFileInfo.file_id == SysFileReconcileIssue.file_id)
            .where(
                SysFileReconcileIssue.issue_type == query_object.issue_type if query_object.issue_type else True,
                SysFileReconcileIssue.severity == query_object.severity if query_object.severity else True,
                SysFileReconcileIssue.status == query_object.status if query_object.status else True,
                keyword_condition,
            )
            .order_by(
                case(
                    (SysFileReconcileIssue.status == 'open', 0),
                    (SysFileReconcileIssue.status == 'quarantined', 1),
                    (SysFileReconcileIssue.status == 'ignored', 2),
                    else_=3,
                ),
                case((SysFileReconcileIssue.severity == 'critical', 0), else_=1),
                SysFileReconcileIssue.last_seen_time.desc(),
                SysFileReconcileIssue.issue_id.desc(),
            )
        )
        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def get_reconcile_issue_for_update(
        cls,
        db: AsyncSession,
        issue_id: int,
    ) -> SysFileReconcileIssue | None:
        """
        锁定文件存储对账异常

        :param db: orm对象
        :param issue_id: 异常ID
        :return: 对账异常
        """
        return (
            (
                await db.execute(
                    select(SysFileReconcileIssue).where(SysFileReconcileIssue.issue_id == issue_id).with_for_update()
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_file_info_for_reconcile(
        cls,
        db: AsyncSession,
        file_id: str,
    ) -> SysFileInfo | None:
        """
        锁定对账异常关联的文件信息

        :param db: orm对象
        :param file_id: 文件ID
        :return: 文件信息
        """
        return (
            (await db.execute(select(SysFileInfo).where(SysFileInfo.file_id == file_id).with_for_update()))
            .scalars()
            .first()
        )

    @classmethod
    async def resolve_file_integrity_issues(
        cls,
        db: AsyncSession,
        file_id: str,
        current_time: datetime,
        handled_by: str,
        reason: str,
    ) -> None:
        """
        关闭文件大小和摘要不一致异常

        :return: None
        """
        await db.execute(
            update(SysFileReconcileIssue)
            .where(
                SysFileReconcileIssue.file_id == file_id,
                SysFileReconcileIssue.issue_type.in_(['size_mismatch', 'hash_mismatch']),
                SysFileReconcileIssue.status.in_(['open', 'ignored']),
            )
            .values(
                status='resolved',
                handle_action='accept_current',
                handle_reason=reason,
                handled_by=handled_by,
                handled_time=current_time,
            )
        )

    @classmethod
    async def get_reconcile_stats(cls, db: AsyncSession) -> dict[str, Any]:
        """
        获取文件存储对账统计

        :param db: orm对象
        :return: 对账统计
        """
        row = (
            (
                await db.execute(
                    select(
                        func.coalesce(
                            func.sum(case((SysFileReconcileIssue.status == 'open', 1), else_=0)),
                            0,
                        ).label('open_count'),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        (SysFileReconcileIssue.status == 'open')
                                        & (SysFileReconcileIssue.severity == 'critical'),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label('critical_count'),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        (SysFileReconcileIssue.status == 'open')
                                        & (SysFileReconcileIssue.severity == 'warning'),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label('warning_count'),
                        func.coalesce(
                            func.sum(case((SysFileReconcileIssue.status == 'ignored', 1), else_=0)),
                            0,
                        ).label('ignored_count'),
                        func.coalesce(
                            func.sum(case((SysFileReconcileIssue.status == 'quarantined', 1), else_=0)),
                            0,
                        ).label('quarantined_count'),
                    )
                )
            )
            .mappings()
            .one()
        )
        latest_run = (
            (await db.execute(select(SysFileReconcileRun).order_by(SysFileReconcileRun.started_time.desc()).limit(1)))
            .scalars()
            .first()
        )
        return {**dict(row), 'latest_run': latest_run}

    @classmethod
    async def get_file_info_detail_by_id(
        cls,
        db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement | None = None,
    ) -> SysFileInfo | None:
        """
        根据文件ID获取文件详细信息

        :param db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象
        """
        return (
            (
                await db.execute(
                    select(SysFileInfo).where(
                        SysFileInfo.file_id == file_id,
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_file_info_by_id_for_update(
        cls,
        db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement | None = None,
    ) -> SysFileInfo | None:
        """
        根据文件ID锁定有效文件信息

        :param db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象
        """
        return (
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.file_id == file_id,
                        SysFileInfo.status == 'active',
                        SysFileInfo.del_flag == '0',
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_file_infos_by_ids_for_update(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        file_data_scope_sql: ColumnElement | None = None,
    ) -> list[SysFileInfo]:
        """
        根据文件ID列表锁定有效文件信息

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.file_id.in_(file_ids),
                        SysFileInfo.status == 'active',
                        SysFileInfo.del_flag == '0',
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                    .order_by(SysFileInfo.file_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_deleted_file_infos_by_ids_for_update(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        file_data_scope_sql: ColumnElement | None = None,
    ) -> list[SysFileInfo]:
        """
        根据文件ID列表锁定已删除文件信息

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.file_id.in_(file_ids),
                        SysFileInfo.status == 'deleted',
                        SysFileInfo.del_flag == '1',
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                    .order_by(SysFileInfo.file_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_purgeable_file_infos_by_ids_for_update(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        file_data_scope_sql: ColumnElement | None = None,
    ) -> list[SysFileInfo]:
        """
        根据文件ID列表锁定可永久清理的文件信息

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.file_id.in_(file_ids),
                        SysFileInfo.status.in_(['deleted', 'purging']),
                        SysFileInfo.del_flag == '1',
                        file_data_scope_sql if file_data_scope_sql is not None else True,
                    )
                    .order_by(SysFileInfo.file_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_recycle_bin_purge_candidates(
        cls,
        db: AsyncSession,
        deleted_before: datetime,
        batch_size: int,
    ) -> list[SysFileInfo]:
        """
        获取自动清理的回收站文件

        :param db: orm对象
        :param deleted_before: 最晚删除时间
        :param batch_size: 单批处理数量
        :return: 文件信息数据库对象列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.del_flag == '1',
                        or_(
                            SysFileInfo.status == 'purging',
                            (SysFileInfo.status == 'deleted') & (SysFileInfo.deleted_time <= deleted_before),
                        ),
                        or_(SysFileInfo.business_type.is_(None), SysFileInfo.business_id.is_(None)),
                        ~exists(
                            select(SysFileReference.reference_id).where(SysFileReference.file_id == SysFileInfo.file_id)
                        ),
                    )
                    .order_by(
                        case((SysFileInfo.status == 'purging', 0), else_=1),
                        SysFileInfo.deleted_time,
                        SysFileInfo.file_id,
                    )
                    .limit(batch_size)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_file_info_list(
        cls,
        db: AsyncSession,
        query_object: FileInfoPageQueryModel,
        file_data_scope_sql: ColumnElement,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取文件信息列表

        :param db: orm对象
        :param query_object: 文件信息查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 文件信息列表
        """
        current_time = datetime.now()
        acl_summary = (
            select(
                SysFileAcl.file_id.label('acl_file_id'),
                func.min(SysFileAcl.expire_time).label('acl_nearest_expire_time'),
                func.count(SysFileAcl.acl_id).label('acl_entry_count'),
            )
            .where(
                SysFileAcl.del_flag == '0',
                or_(SysFileAcl.expire_time.is_(None), SysFileAcl.expire_time > current_time),
            )
            .group_by(SysFileAcl.file_id)
            .subquery()
        )
        query = (
            select(
                *SysFileInfo.__table__.c,
                SysUser.user_name.label('owner_name'),
                SysDept.dept_name.label('dept_name'),
                acl_summary.c.acl_nearest_expire_time,
                func.coalesce(acl_summary.c.acl_entry_count, 0).label('acl_entry_count'),
            )
            .outerjoin(SysUser, SysUser.user_id == SysFileInfo.owner_user_id)
            .outerjoin(SysDept, SysDept.dept_id == SysFileInfo.dept_id)
            .outerjoin(acl_summary, acl_summary.c.acl_file_id == SysFileInfo.file_id)
            .where(
                file_data_scope_sql,
                *cls._get_file_info_query_conditions(query_object, current_time),
            )
            .order_by(SysFileInfo.create_time.desc(), SysFileInfo.file_id.desc())
        )
        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def get_file_management_detail_by_id(
        cls,
        db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement,
    ) -> dict[str, Any] | None:
        """
        获取包含管理展示字段的文件详情

        :param db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件管理详情
        """
        current_time = datetime.now()
        acl_summary = (
            select(
                SysFileAcl.file_id.label('acl_file_id'),
                func.min(SysFileAcl.expire_time).label('acl_nearest_expire_time'),
                func.count(SysFileAcl.acl_id).label('acl_entry_count'),
            )
            .where(
                SysFileAcl.del_flag == '0',
                or_(SysFileAcl.expire_time.is_(None), SysFileAcl.expire_time > current_time),
            )
            .group_by(SysFileAcl.file_id)
            .subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        *SysFileInfo.__table__.c,
                        SysUser.user_name.label('owner_name'),
                        SysDept.dept_name.label('dept_name'),
                        acl_summary.c.acl_nearest_expire_time,
                        func.coalesce(acl_summary.c.acl_entry_count, 0).label('acl_entry_count'),
                    )
                    .outerjoin(SysUser, SysUser.user_id == SysFileInfo.owner_user_id)
                    .outerjoin(SysDept, SysDept.dept_id == SysFileInfo.dept_id)
                    .outerjoin(acl_summary, acl_summary.c.acl_file_id == SysFileInfo.file_id)
                    .where(SysFileInfo.file_id == file_id, file_data_scope_sql)
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    @classmethod
    async def get_file_stats(
        cls,
        db: AsyncSession,
        query_object: FileInfoPageQueryModel,
        file_data_scope_sql: ColumnElement,
    ) -> FileStatsModel:
        """
        获取文件管理统计信息

        :param db: orm对象
        :param query_object: 文件信息查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件管理统计信息
        """
        current_time = datetime.now()
        acl_expiring_time = current_time + timedelta(days=cls.ACL_EXPIRING_DAYS)
        acl_expiring_files = (
            select(SysFileAcl.file_id)
            .where(
                SysFileAcl.del_flag == '0',
                SysFileAcl.expire_time > current_time,
                SysFileAcl.expire_time <= acl_expiring_time,
            )
            .distinct()
            .subquery()
        )
        row = (
            (
                await db.execute(
                    select(
                        func.count(SysFileInfo.file_id).label('total_count'),
                        func.coalesce(func.sum(SysFileInfo.file_size), 0).label('total_size'),
                        func.coalesce(
                            func.sum(case((SysFileInfo.access_type == 'public', SysFileInfo.file_size), else_=0)),
                            0,
                        ).label('public_size'),
                        func.coalesce(
                            func.sum(case((SysFileInfo.access_type == 'private', SysFileInfo.file_size), else_=0)),
                            0,
                        ).label('private_size'),
                        func.coalesce(func.sum(case((SysFileInfo.status == 'active', 1), else_=0)), 0).label(
                            'active_count'
                        ),
                        func.coalesce(
                            func.sum(case((SysFileInfo.status.in_(['deleted', 'purging']), 1), else_=0)),
                            0,
                        ).label('deleted_count'),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        (SysFileInfo.access_type == 'private')
                                        & (SysFileInfo.status == 'active')
                                        & (SysFileInfo.expire_time.is_not(None))
                                        & (SysFileInfo.expire_time <= current_time),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label('expired_count'),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        (SysFileInfo.access_type == 'private')
                                        & (SysFileInfo.status == 'active')
                                        & (SysFileInfo.expire_time > current_time)
                                        & (
                                            SysFileInfo.expire_time
                                            <= current_time + timedelta(days=cls.FILE_EXPIRING_DAYS)
                                        ),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ).label('retention_expiring_count'),
                        func.count(acl_expiring_files.c.file_id).label('acl_expiring_count'),
                    )
                    .outerjoin(SysUser, SysUser.user_id == SysFileInfo.owner_user_id)
                    .outerjoin(acl_expiring_files, acl_expiring_files.c.file_id == SysFileInfo.file_id)
                    .where(
                        file_data_scope_sql,
                        *cls._get_file_info_query_conditions(query_object, current_time),
                    )
                )
            )
            .mappings()
            .one()
        )
        return FileStatsModel.model_validate(dict(row), by_name=True)

    @classmethod
    def _get_file_info_query_conditions(
        cls,
        query_object: FileInfoPageQueryModel,
        current_time: datetime,
    ) -> list[ColumnElement | bool]:
        """
        构建文件管理查询条件

        :param query_object: 文件信息查询参数
        :param current_time: 当前时间
        :return: 查询条件列表
        """
        expiring_time = current_time + timedelta(days=cls.FILE_EXPIRING_DAYS)
        expiration_condition: ColumnElement | bool = True
        if query_object.expiration_status == 'permanent':
            expiration_condition = SysFileInfo.expire_time.is_(None)
        elif query_object.expiration_status == 'expired':
            expiration_condition = SysFileInfo.expire_time <= current_time
        elif query_object.expiration_status == 'expiring':
            expiration_condition = (SysFileInfo.expire_time > current_time) & (SysFileInfo.expire_time <= expiring_time)
        elif query_object.expiration_status == 'valid':
            expiration_condition = SysFileInfo.expire_time > expiring_time
        return [
            SysFileInfo.original_name.like(f'%{query_object.original_name}%') if query_object.original_name else True,
            SysFileInfo.access_type == query_object.access_type if query_object.access_type else True,
            SysFileInfo.status == query_object.status if query_object.status else True,
            SysFileInfo.create_by.like(f'%{query_object.create_by}%') if query_object.create_by else True,
            or_(
                SysUser.user_name.like(f'%{query_object.owner_name}%'),
                SysUser.nick_name.like(f'%{query_object.owner_name}%'),
            )
            if query_object.owner_name
            else True,
            SysFileInfo.dept_id == query_object.dept_id if query_object.dept_id else True,
            expiration_condition,
            SysFileInfo.create_time.between(
                datetime.strptime(query_object.begin_time, '%Y-%m-%d %H:%M:%S'),
                datetime.strptime(query_object.end_time, '%Y-%m-%d %H:%M:%S'),
            )
            if query_object.begin_time and query_object.end_time
            else True,
        ]

    @classmethod
    async def soft_delete_file_infos(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        update_by: str,
        update_time: datetime,
    ) -> None:
        """
        逻辑删除文件信息

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param update_by: 更新者
        :param update_time: 更新时间
        :return: None
        """
        await db.execute(
            update(SysFileInfo)
            .where(SysFileInfo.file_id.in_(file_ids))
            .values(
                status='deleted',
                del_flag='1',
                update_by=update_by,
                update_time=update_time,
                deleted_time=update_time,
            )
        )

    @classmethod
    async def restore_file_infos(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        update_by: str,
        update_time: datetime,
    ) -> None:
        """
        恢复文件信息

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param update_by: 更新者
        :param update_time: 更新时间
        :return: None
        """
        await db.execute(
            update(SysFileInfo)
            .where(SysFileInfo.file_id.in_(file_ids))
            .values(
                status='active',
                del_flag='0',
                update_by=update_by,
                update_time=update_time,
                deleted_time=None,
            )
        )

    @classmethod
    async def mark_file_infos_purging(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        update_by: str,
        update_time: datetime,
    ) -> None:
        """
        标记文件正在执行永久清理

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param update_by: 更新者
        :param update_time: 更新时间
        :return: None
        """
        await db.execute(
            update(SysFileInfo)
            .where(
                SysFileInfo.file_id.in_(file_ids),
                SysFileInfo.status.in_(['deleted', 'purging']),
                SysFileInfo.del_flag == '1',
            )
            .values(
                status='purging',
                update_by=update_by,
                update_time=update_time,
            )
        )

    @classmethod
    async def purge_file_infos(cls, db: AsyncSession, file_ids: list[str]) -> None:
        """
        永久删除文件元数据及关联管理数据

        :param db: orm对象
        :param file_ids: 文件ID列表
        :return: None
        """
        await db.execute(delete(SysFileAcl).where(SysFileAcl.file_id.in_(file_ids)))
        await db.execute(delete(SysFileReference).where(SysFileReference.file_id.in_(file_ids)))
        await db.execute(delete(SysFileRetentionNotice).where(SysFileRetentionNotice.file_id.in_(file_ids)))
        await db.execute(
            delete(SysFileInfo).where(
                SysFileInfo.file_id.in_(file_ids),
                SysFileInfo.status == 'purging',
                SysFileInfo.del_flag == '1',
            )
        )

    @classmethod
    async def get_transfer_user_by_id(
        cls,
        db: AsyncSession,
        user_id: int,
        user_data_scope_sql: ColumnElement,
    ) -> SysUser | None:
        """
        获取数据权限范围内的文件转移目标用户

        :param db: orm对象
        :param user_id: 用户ID
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :return: 用户信息
        """
        return (
            (
                await db.execute(
                    select(SysUser)
                    .where(
                        SysUser.user_id == user_id,
                        SysUser.status == '0',
                        SysUser.del_flag == '0',
                        user_data_scope_sql,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_transfer_dept_by_id(
        cls,
        db: AsyncSession,
        dept_id: int,
        dept_data_scope_sql: ColumnElement,
    ) -> SysDept | None:
        """
        获取数据权限范围内的文件转移目标部门

        :param db: orm对象
        :param dept_id: 部门ID
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 部门信息
        """
        return (
            (
                await db.execute(
                    select(SysDept)
                    .where(
                        SysDept.dept_id == dept_id,
                        SysDept.status == '0',
                        SysDept.del_flag == '0',
                        dept_data_scope_sql,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def transfer_file_infos(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        owner_user_id: int,
        dept_id: int,
        retain_uploader_access: bool,
        update_by: str,
        update_time: datetime,
    ) -> None:
        """
        批量转移文件所有者和所属部门

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param owner_user_id: 新所有者用户ID
        :param dept_id: 新所属部门ID
        :param retain_uploader_access: 是否保留上传人访问权限
        :param update_by: 更新者
        :param update_time: 更新时间
        :return: None
        """
        await db.execute(
            update(SysFileInfo)
            .where(SysFileInfo.file_id.in_(file_ids))
            .values(
                owner_user_id=owner_user_id,
                dept_id=dept_id,
                uploader_access_enabled='1' if retain_uploader_access else '0',
                acl_version=SysFileInfo.acl_version + 1,
                update_by=update_by,
                update_time=update_time,
            )
        )

    @classmethod
    async def get_file_info_by_storage_key(
        cls,
        db: AsyncSession,
        storage_key: str,
        access_type: str = 'public',
        storage_type: str = 'local',
    ) -> SysFileInfo | None:
        """
        根据存储相对路径获取文件信息

        :param db: orm对象
        :param storage_key: 存储相对路径
        :param access_type: 文件访问类型
        :param storage_type: 文件存储类型
        :return: 文件信息数据库对象
        """
        return (
            (
                await db.execute(
                    select(SysFileInfo).where(
                        SysFileInfo.storage_key == storage_key,
                        SysFileInfo.access_type == access_type,
                        SysFileInfo.storage_type == storage_type,
                    )
                )
            )
            .scalars()
            .first()
        )
