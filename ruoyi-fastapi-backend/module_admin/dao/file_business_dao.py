from datetime import datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.file_do import (
    SysFileInfo,
    SysFileReference,
    SysFileRetentionNotice,
    SysFileRetentionPolicy,
)
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.file_vo import FileRetentionNoticePageQueryModel
from utils.page_util import PageUtil


class FileReferenceDao:
    """
    文件业务引用数据操作层
    """

    @classmethod
    async def get_file_reference_list(cls, db: AsyncSession, file_id: str) -> list[SysFileReference]:
        """
        获取文件业务引用列表

        :param db: orm对象
        :param file_id: 文件ID
        :return: 文件业务引用列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileReference)
                    .where(SysFileReference.file_id == file_id)
                    .order_by(
                        SysFileReference.business_type,
                        SysFileReference.business_id,
                        SysFileReference.reference_id,
                    )
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_file_reference_list_for_update(cls, db: AsyncSession, file_id: str) -> list[SysFileReference]:
        """
        锁定文件业务引用列表

        :param db: orm对象
        :param file_id: 文件ID
        :return: 文件业务引用列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileReference)
                    .where(SysFileReference.file_id == file_id)
                    .order_by(SysFileReference.reference_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def delete_file_references(cls, db: AsyncSession, file_id: str) -> None:
        """
        删除文件的全部业务引用

        :param db: orm对象
        :param file_id: 文件ID
        :return: None
        """
        await db.execute(delete(SysFileReference).where(SysFileReference.file_id == file_id))

    @classmethod
    async def get_file_reference_count_map(cls, db: AsyncSession, file_ids: list[str]) -> dict[str, int]:
        """
        获取文件业务引用数量映射

        :param db: orm对象
        :param file_ids: 文件ID列表
        :return: 文件ID和业务引用数量映射
        """
        if not file_ids:
            return {}
        rows = (
            (
                await db.execute(
                    select(
                        SysFileReference.file_id,
                        func.count(SysFileReference.reference_id).label('reference_count'),
                    )
                    .where(SysFileReference.file_id.in_(file_ids))
                    .group_by(SysFileReference.file_id)
                )
            )
            .mappings()
            .all()
        )
        return {str(row['file_id']): int(row['reference_count']) for row in rows}

    @classmethod
    async def replace_business_file_references(
        cls,
        db: AsyncSession,
        business_type: str,
        business_id: str,
        file_reference_list: list[SysFileReference],
    ) -> None:
        """
        替换业务对象的文件引用

        :param db: orm对象
        :param business_type: 业务类型
        :param business_id: 业务ID
        :param file_reference_list: 文件业务引用列表
        :return: None
        """
        old_reference_list = list(
            (
                await db.execute(
                    select(SysFileReference).where(
                        SysFileReference.business_type == business_type,
                        SysFileReference.business_id == business_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        old_file_ids = [reference.file_id for reference in old_reference_list]
        cls._preserve_later_retention_expire_times(old_reference_list, file_reference_list)
        affected_file_ids = sorted(set(old_file_ids).union(reference.file_id for reference in file_reference_list))
        file_info_map = {}
        if affected_file_ids:
            file_info_list = list(
                (
                    await db.execute(
                        select(SysFileInfo)
                        .where(SysFileInfo.file_id.in_(affected_file_ids))
                        .order_by(SysFileInfo.file_id)
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            file_info_map = {file_info.file_id: file_info for file_info in file_info_list}

        await db.execute(
            delete(SysFileReference).where(
                SysFileReference.business_type == business_type,
                SysFileReference.business_id == business_id,
            )
        )
        await db.execute(
            update(SysFileInfo)
            .where(
                SysFileInfo.business_type == business_type,
                SysFileInfo.business_id == business_id,
            )
            .values(business_type=None, business_id=None)
        )
        if file_reference_list:
            db.add_all(file_reference_list)
            await db.flush()
        await cls._refresh_file_expire_times(db, affected_file_ids, file_info_map)

    @staticmethod
    def _preserve_later_retention_expire_times(
        old_reference_list: list[SysFileReference],
        new_reference_list: list[SysFileReference],
    ) -> None:
        """保留同一业务引用已经延长的更晚到期时间。"""
        old_reference_map = {reference.file_id: reference for reference in old_reference_list}
        for reference in new_reference_list:
            old_reference = old_reference_map.get(reference.file_id)
            if (
                old_reference
                and old_reference.retention_expire_time
                and reference.retention_expire_time
                and old_reference.retention_expire_time > reference.retention_expire_time
            ):
                reference.retention_expire_time = old_reference.retention_expire_time

    @classmethod
    async def _refresh_file_expire_times(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        file_info_map: dict[str, SysFileInfo],
    ) -> None:
        """根据业务引用重新计算文件过期时间。"""
        if not file_ids:
            return
        rows = (
            await db.execute(
                select(
                    SysFileReference.file_id,
                    SysFileReference.retention_expire_time,
                ).where(SysFileReference.file_id.in_(file_ids))
            )
        ).all()
        retention_map: dict[str, list] = {file_id: [] for file_id in file_ids}
        for file_id, retention_expire_time in rows:
            retention_map[str(file_id)].append(retention_expire_time)

        for file_id in file_ids:
            file_info = file_info_map.get(file_id)
            if file_info is None:
                continue
            retention_expire_times = retention_map[file_id]
            has_legacy_reference = bool(file_info.business_type and file_info.business_id)
            if has_legacy_reference or any(expire_time is None for expire_time in retention_expire_times):
                file_info.expire_time = None
            else:
                file_info.expire_time = max(retention_expire_times, default=None)
            await FileRetentionNoticeDao.invalidate_changed_expire_time_notices(
                db,
                file_id,
                file_info.expire_time,
            )


class FileRetentionPolicyDao:
    """
    文件业务保留策略数据操作层
    """

    @classmethod
    async def get_file_retention_policy_list(cls, db: AsyncSession) -> list[SysFileRetentionPolicy]:
        """
        获取文件业务保留策略列表

        :param db: orm对象
        :return: 文件业务保留策略列表
        """
        return list(
            (await db.execute(select(SysFileRetentionPolicy).order_by(SysFileRetentionPolicy.business_type)))
            .scalars()
            .all()
        )

    @classmethod
    async def get_file_retention_policy_by_business_type(
        cls,
        db: AsyncSession,
        business_type: str,
        enabled_only: bool = False,
    ) -> SysFileRetentionPolicy | None:
        """
        根据业务类型获取文件业务保留策略

        :param db: orm对象
        :param business_type: 业务类型
        :param enabled_only: 是否只查询启用策略
        :return: 文件业务保留策略
        """
        return (
            (
                await db.execute(
                    select(SysFileRetentionPolicy).where(
                        SysFileRetentionPolicy.business_type == business_type,
                        SysFileRetentionPolicy.status == '0' if enabled_only else True,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def add_file_retention_policy(
        cls,
        db: AsyncSession,
        policy: SysFileRetentionPolicy,
    ) -> None:
        """
        新增文件业务保留策略

        :param db: orm对象
        :param policy: 文件业务保留策略
        :return: None
        """
        db.add(policy)
        await db.flush()

    @classmethod
    async def edit_file_retention_policy(
        cls,
        db: AsyncSession,
        business_type: str,
        policy: dict,
    ) -> None:
        """
        修改文件业务保留策略

        :param db: orm对象
        :param business_type: 业务类型
        :param policy: 文件业务保留策略
        :return: None
        """
        await db.execute(
            update(SysFileRetentionPolicy)
            .where(SysFileRetentionPolicy.business_type == business_type)
            .values(**{key: value for key, value in policy.items() if key not in {'create_time', 'update_time'}})
        )

    @classmethod
    async def delete_file_retention_policy(cls, db: AsyncSession, business_type: str) -> None:
        """
        删除文件业务保留策略

        :param db: orm对象
        :param business_type: 业务类型
        :return: None
        """
        await db.execute(delete(SysFileRetentionPolicy).where(SysFileRetentionPolicy.business_type == business_type))


class FileRetentionNoticeDao:
    """
    文件保留期限提醒数据操作层
    """

    @classmethod
    async def get_missing_notice_candidates(
        cls,
        db: AsyncSession,
        notice_type: Literal['expiring', 'expired'],
        current_time: datetime,
        reminder_deadline: datetime,
        batch_size: int,
        file_data_scope_sql: ColumnElement | bool = True,
    ) -> list[SysFileInfo]:
        """
        获取尚未生成当前到期提醒的文件

        :param db: orm对象
        :param notice_type: 提醒类型
        :param current_time: 当前时间
        :param reminder_deadline: 提醒截止时间
        :param batch_size: 单批处理数量
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件信息数据库对象列表
        """
        expire_condition = (
            SysFileInfo.expire_time <= current_time
            if notice_type == 'expired'
            else and_(
                SysFileInfo.expire_time > current_time,
                SysFileInfo.expire_time <= reminder_deadline,
            )
        )
        current_notice_exists = exists(
            select(SysFileRetentionNotice.notice_id).where(
                SysFileRetentionNotice.file_id == SysFileInfo.file_id,
                SysFileRetentionNotice.notice_type == notice_type,
                SysFileRetentionNotice.expire_time == SysFileInfo.expire_time,
                SysFileRetentionNotice.status.in_(['0', '1']),
            )
        )
        return list(
            (
                await db.execute(
                    select(SysFileInfo)
                    .where(
                        SysFileInfo.access_type == 'private',
                        SysFileInfo.status == 'active',
                        SysFileInfo.del_flag == '0',
                        SysFileInfo.expire_time.is_not(None),
                        expire_condition,
                        ~current_notice_exists,
                        file_data_scope_sql,
                    )
                    .order_by(SysFileInfo.expire_time, SysFileInfo.file_id)
                    .limit(batch_size)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def add_file_retention_notices(
        cls,
        db: AsyncSession,
        notice_list: list[SysFileRetentionNotice],
    ) -> None:
        """
        批量新增文件保留期限提醒

        :param db: orm对象
        :param notice_list: 提醒对象列表
        :return: None
        """
        if notice_list:
            db.add_all(notice_list)
            await db.flush()

    @classmethod
    async def invalidate_expiring_notices(cls, db: AsyncSession, file_ids: list[str]) -> None:
        """
        将已经到期文件的即将到期提醒标记为失效

        :param db: orm对象
        :param file_ids: 文件ID列表
        :return: None
        """
        if not file_ids:
            return
        await db.execute(
            update(SysFileRetentionNotice)
            .where(
                SysFileRetentionNotice.file_id.in_(file_ids),
                SysFileRetentionNotice.notice_type == 'expiring',
                SysFileRetentionNotice.status.in_(['0', '1']),
            )
            .values(status='2')
        )

    @classmethod
    async def invalidate_changed_expire_time_notices(
        cls,
        db: AsyncSession,
        file_id: str,
        expire_time: datetime | None,
    ) -> None:
        """
        将与文件当前到期时间不一致的未读提醒标记为失效

        :param db: orm对象
        :param file_id: 文件ID
        :param expire_time: 文件当前到期时间
        :return: None
        """
        expire_condition = (
            True
            if expire_time is None
            else or_(
                SysFileRetentionNotice.expire_time != expire_time,
                SysFileRetentionNotice.expire_time.is_(None),
            )
        )
        await db.execute(
            update(SysFileRetentionNotice)
            .where(
                SysFileRetentionNotice.file_id == file_id,
                SysFileRetentionNotice.status.in_(['0', '1']),
                expire_condition,
            )
            .values(status='2')
        )

    @classmethod
    async def get_file_retention_notice_list(
        cls,
        db: AsyncSession,
        query_object: FileRetentionNoticePageQueryModel,
        file_data_scope_sql: ColumnElement,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取文件保留期限提醒列表

        :param db: orm对象
        :param query_object: 查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 文件保留期限提醒列表
        """
        current_time = datetime.now()
        reference_count = (
            select(func.count(SysFileReference.reference_id))
            .where(SysFileReference.file_id == SysFileInfo.file_id)
            .correlate(SysFileInfo)
            .scalar_subquery()
        )
        blocking_reference_exists = exists(
            select(SysFileReference.reference_id).where(
                SysFileReference.file_id == SysFileInfo.file_id,
                or_(
                    SysFileReference.retention_expire_time.is_(None),
                    SysFileReference.retention_expire_time > current_time,
                ),
            )
        )
        query = (
            select(
                *SysFileRetentionNotice.__table__.c,
                SysFileInfo.original_name,
                SysUser.user_name.label('owner_name'),
                SysDept.dept_name.label('dept_name'),
                reference_count.label('reference_count'),
                and_(
                    SysFileInfo.expire_time <= current_time,
                    SysFileInfo.business_type.is_(None),
                    SysFileInfo.business_id.is_(None),
                    ~blocking_reference_exists,
                ).label('can_dispose'),
            )
            .join(SysFileInfo, SysFileInfo.file_id == SysFileRetentionNotice.file_id)
            .outerjoin(SysUser, SysUser.user_id == SysFileInfo.owner_user_id)
            .outerjoin(SysDept, SysDept.dept_id == SysFileInfo.dept_id)
            .where(
                SysFileInfo.access_type == 'private',
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
                SysFileInfo.expire_time == SysFileRetentionNotice.expire_time,
                SysFileRetentionNotice.status.in_(['0', '1']),
                file_data_scope_sql,
                SysFileInfo.original_name.like(f'%{query_object.original_name}%')
                if query_object.original_name
                else True,
                SysFileRetentionNotice.notice_type == query_object.notice_type if query_object.notice_type else True,
                SysFileRetentionNotice.status == query_object.status if query_object.status else True,
            )
            .order_by(
                SysFileRetentionNotice.status,
                SysFileRetentionNotice.expire_time,
                SysFileRetentionNotice.notice_id.desc(),
            )
        )
        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def get_file_retention_notice_context_for_update(
        cls,
        db: AsyncSession,
        notice_id: int,
        file_data_scope_sql: ColumnElement,
    ) -> tuple[SysFileRetentionNotice, SysFileInfo] | None:
        """
        锁定数据权限范围内的有效提醒和文件

        :param db: orm对象
        :param notice_id: 提醒ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 提醒和文件数据库对象
        """
        row = (
            await db.execute(
                select(SysFileRetentionNotice, SysFileInfo)
                .join(SysFileInfo, SysFileInfo.file_id == SysFileRetentionNotice.file_id)
                .where(
                    SysFileRetentionNotice.notice_id == notice_id,
                    SysFileRetentionNotice.status.in_(['0', '1']),
                    SysFileInfo.access_type == 'private',
                    SysFileInfo.status == 'active',
                    SysFileInfo.del_flag == '0',
                    SysFileInfo.expire_time == SysFileRetentionNotice.expire_time,
                    file_data_scope_sql,
                )
                .with_for_update()
            )
        ).first()
        return (row[0], row[1]) if row else None

    @classmethod
    async def get_notice_ids_in_data_scope_for_update(
        cls,
        db: AsyncSession,
        notice_ids: list[int],
        file_data_scope_sql: ColumnElement,
    ) -> list[int]:
        """
        锁定数据权限范围内的有效提醒

        :param db: orm对象
        :param notice_ids: 提醒ID列表
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 提醒ID列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileRetentionNotice.notice_id)
                    .join(SysFileInfo, SysFileInfo.file_id == SysFileRetentionNotice.file_id)
                    .where(
                        SysFileRetentionNotice.notice_id.in_(notice_ids),
                        SysFileRetentionNotice.status.in_(['0', '1']),
                        SysFileInfo.access_type == 'private',
                        SysFileInfo.status == 'active',
                        SysFileInfo.del_flag == '0',
                        SysFileInfo.expire_time == SysFileRetentionNotice.expire_time,
                        file_data_scope_sql,
                    )
                    .order_by(SysFileRetentionNotice.notice_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def mark_file_retention_notices_read(
        cls,
        db: AsyncSession,
        notice_ids: list[int],
        read_by: str,
        read_time: datetime,
    ) -> None:
        """
        标记文件保留期限提醒为已读

        :param db: orm对象
        :param notice_ids: 提醒ID列表
        :param read_by: 读取者
        :param read_time: 读取时间
        :return: None
        """
        await db.execute(
            update(SysFileRetentionNotice)
            .where(
                SysFileRetentionNotice.notice_id.in_(notice_ids),
                SysFileRetentionNotice.status == '0',
            )
            .values(status='1', read_by=read_by, read_time=read_time)
        )

    @classmethod
    async def invalidate_file_retention_notices(cls, db: AsyncSession, file_id: str) -> None:
        """
        将文件当前有效的保留期限提醒标记为失效

        :param db: orm对象
        :param file_id: 文件ID
        :return: None
        """
        await db.execute(
            update(SysFileRetentionNotice)
            .where(
                SysFileRetentionNotice.file_id == file_id,
                SysFileRetentionNotice.status.in_(['0', '1']),
            )
            .values(status='2')
        )
