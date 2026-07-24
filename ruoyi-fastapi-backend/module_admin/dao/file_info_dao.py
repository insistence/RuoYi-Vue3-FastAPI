from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, case, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.file_do import SysFileAcl, SysFileInfo, SysFileReference, SysFileRetentionNotice
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.file_vo import (
    FileInfoModel,
    FileInfoPageQueryModel,
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
        update_by: str,
        update_time: datetime,
    ) -> None:
        """
        批量转移文件所有者和所属部门

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param owner_user_id: 新所有者用户ID
        :param dept_id: 新所属部门ID
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
