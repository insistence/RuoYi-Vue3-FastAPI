from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.file_do import SysFileAccessLog, SysFileAcl
from module_admin.entity.do.role_do import SysRole
from module_admin.entity.do.user_do import SysUser, SysUserRole
from module_admin.entity.vo.file_vo import (
    FileAccessLogModel,
    FileAccessLogPageQueryModel,
)
from utils.page_util import PageUtil


class FileAclDao:
    """
    文件访问控制数据操作层
    """

    @classmethod
    async def get_effective_file_acl_list(
        cls,
        db: AsyncSession,
        file_id: str,
        current_time: datetime,
    ) -> list[SysFileAcl]:
        """
        获取文件有效访问控制列表

        :param db: orm对象
        :param file_id: 文件ID
        :param current_time: 当前时间
        :return: 文件访问控制列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileAcl).where(
                        SysFileAcl.file_id == file_id,
                        SysFileAcl.permission == 'download',
                        SysFileAcl.del_flag == '0',
                        or_(SysFileAcl.expire_time.is_(None), SysFileAcl.expire_time > current_time),
                    )
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_file_acl_list(cls, db: AsyncSession, file_id: str) -> list[SysFileAcl]:
        """
        获取文件访问控制列表

        :param db: orm对象
        :param file_id: 文件ID
        :return: 文件访问控制列表
        """
        return list(
            (
                await db.execute(
                    select(SysFileAcl)
                    .where(SysFileAcl.file_id == file_id, SysFileAcl.del_flag == '0')
                    .order_by(SysFileAcl.subject_type, SysFileAcl.subject_id, SysFileAcl.acl_id)
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_acl_dept_list(cls, db: AsyncSession, dept_data_scope_sql: ColumnElement) -> list[SysDept]:
        """
        获取文件授权可选部门列表

        :param db: orm对象
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 部门列表
        """
        return list(
            (
                await db.execute(
                    select(SysDept)
                    .where(SysDept.status == '0', SysDept.del_flag == '0', dept_data_scope_sql)
                    .order_by(SysDept.order_num, SysDept.dept_id)
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def replace_file_acl_list(cls, db: AsyncSession, file_id: str, file_acl_list: list[SysFileAcl]) -> None:
        """
        替换文件访问控制列表

        :param db: orm对象
        :param file_id: 文件ID
        :param file_acl_list: 文件访问控制列表
        :return: None
        """
        await db.execute(delete(SysFileAcl).where(SysFileAcl.file_id == file_id))
        if file_acl_list:
            db.add_all(file_acl_list)
            await db.flush()

    @classmethod
    async def replace_file_acl_lists(
        cls,
        db: AsyncSession,
        file_ids: list[str],
        file_acl_list: list[SysFileAcl],
    ) -> None:
        """
        批量替换文件访问控制列表

        :param db: orm对象
        :param file_ids: 文件ID列表
        :param file_acl_list: 文件访问控制列表
        :return: None
        """
        await db.execute(delete(SysFileAcl).where(SysFileAcl.file_id.in_(file_ids)))
        if file_acl_list:
            db.add_all(file_acl_list)
            await db.flush()

    @classmethod
    async def get_acl_subject_name_map(
        cls,
        db: AsyncSession,
        subject_ids: dict[str, set[int]],
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
    ) -> dict[tuple[str, int], str]:
        """
        获取访问控制主体名称映射

        :param db: orm对象
        :param subject_ids: 按主体类型分组的主体ID
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 主体名称映射
        """
        subject_name_map = {}
        user_ids = subject_ids.get('user', set())
        if user_ids:
            user_rows = (
                await db.execute(
                    select(SysUser.user_id, SysUser.user_name, SysUser.nick_name).where(
                        SysUser.user_id.in_(user_ids),
                        SysUser.status == '0',
                        SysUser.del_flag == '0',
                        user_data_scope_sql,
                    )
                )
            ).all()
            for user_id, user_name, nick_name in user_rows:
                display_name = f'{nick_name}（{user_name}）' if nick_name and nick_name != user_name else user_name
                subject_name_map[('user', user_id)] = display_name

        role_ids = subject_ids.get('role', set())
        if role_ids:
            role_rows = (
                await db.execute(
                    select(SysRole.role_id, SysRole.role_name).where(
                        SysRole.role_id != 1,
                        SysRole.role_id.in_(role_ids),
                        SysRole.status == '0',
                        SysRole.del_flag == '0',
                    )
                )
            ).all()
            role_rows = await cls._filter_role_rows_by_data_scope(db, role_rows, user_data_scope_sql)
            subject_name_map.update({('role', role_id): role_name for role_id, role_name in role_rows})

        dept_ids = subject_ids.get('dept', set())
        if dept_ids:
            dept_rows = (
                await db.execute(
                    select(SysDept.dept_id, SysDept.dept_name).where(
                        SysDept.dept_id.in_(dept_ids),
                        SysDept.status == '0',
                        SysDept.del_flag == '0',
                        dept_data_scope_sql,
                    )
                )
            ).all()
            subject_name_map.update({('dept', dept_id): dept_name for dept_id, dept_name in dept_rows})

        return subject_name_map

    @classmethod
    async def search_acl_subjects(
        cls,
        db: AsyncSession,
        subject_type: str,
        keyword: str | None,
        limit: int,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
    ) -> list[dict[str, Any]]:
        """
        查询访问控制主体选项

        :param db: orm对象
        :param subject_type: 主体类型
        :param keyword: 查询关键字
        :param limit: 返回数量限制
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 主体选项列表
        """
        keyword_pattern = f'%{keyword}%'
        if subject_type == 'user':
            query = select(SysUser.user_id, SysUser.user_name, SysUser.nick_name, SysUser.dept_id).where(
                SysUser.status == '0',
                SysUser.del_flag == '0',
                user_data_scope_sql,
                or_(SysUser.user_name.like(keyword_pattern), SysUser.nick_name.like(keyword_pattern))
                if keyword
                else True,
            )
            rows = (await db.execute(query.order_by(SysUser.user_id).limit(limit))).all()
            return [
                {
                    'subject_id': user_id,
                    'subject_name': f'{nick_name}（{user_name}）'
                    if nick_name and nick_name != user_name
                    else user_name,
                    'dept_id': dept_id,
                }
                for user_id, user_name, nick_name, dept_id in rows
            ]
        if subject_type == 'role':
            query = select(SysRole.role_id, SysRole.role_name).where(
                SysRole.role_id != 1,
                SysRole.status == '0',
                SysRole.del_flag == '0',
                SysRole.role_name.like(keyword_pattern) if keyword else True,
            )
            rows = (await db.execute(query.order_by(SysRole.role_id))).all()
            rows = await cls._filter_role_rows_by_data_scope(db, rows, user_data_scope_sql)
            rows = rows[:limit]
            return [{'subject_id': role_id, 'subject_name': role_name} for role_id, role_name in rows]

        query = select(SysDept.dept_id, SysDept.dept_name).where(
            SysDept.status == '0',
            SysDept.del_flag == '0',
            dept_data_scope_sql,
            SysDept.dept_name.like(keyword_pattern) if keyword else True,
        )
        rows = (await db.execute(query.order_by(SysDept.order_num, SysDept.dept_id).limit(limit))).all()
        return [{'subject_id': dept_id, 'subject_name': dept_name} for dept_id, dept_name in rows]

    @classmethod
    async def _filter_role_rows_by_data_scope(
        cls,
        db: AsyncSession,
        role_rows: list[Any],
        user_data_scope_sql: ColumnElement,
    ) -> list[Any]:
        """
        过滤包含数据权限范围外成员的角色

        :param db: orm对象
        :param role_rows: 候选角色列表
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :return: 数据权限范围内的角色列表
        """
        role_ids = {role_id for role_id, _ in role_rows}
        if not role_ids:
            return []

        all_member_rows = (
            await db.execute(
                select(SysUserRole.role_id, SysUserRole.user_id)
                .join(SysUser, SysUser.user_id == SysUserRole.user_id)
                .where(
                    SysUserRole.role_id.in_(role_ids),
                    SysUser.del_flag == '0',
                )
            )
        ).all()
        visible_member_rows = (
            await db.execute(
                select(SysUserRole.role_id, SysUserRole.user_id)
                .join(SysUser, SysUser.user_id == SysUserRole.user_id)
                .where(
                    SysUserRole.role_id.in_(role_ids),
                    SysUser.del_flag == '0',
                    user_data_scope_sql,
                )
            )
        ).all()

        all_member_ids = {}
        for role_id, user_id in all_member_rows:
            all_member_ids.setdefault(role_id, set()).add(user_id)
        visible_member_ids = {}
        for role_id, user_id in visible_member_rows:
            visible_member_ids.setdefault(role_id, set()).add(user_id)

        return [
            role_row
            for role_row in role_rows
            if all_member_ids.get(role_row[0], set()).issubset(visible_member_ids.get(role_row[0], set()))
        ]


class FileAccessLogDao:
    """
    文件访问审计数据操作层
    """

    @classmethod
    async def add_file_access_log_dao(cls, db: AsyncSession, file_access_log: FileAccessLogModel) -> SysFileAccessLog:
        """
        新增文件访问审计记录

        :param db: orm对象
        :param file_access_log: 文件访问审计对象
        :return: 文件访问审计数据库对象
        """
        db_file_access_log = SysFileAccessLog(**file_access_log.model_dump(exclude={'audit_id'}))
        db.add(db_file_access_log)
        await db.flush()
        return db_file_access_log

    @classmethod
    async def get_file_access_log_list(
        cls,
        db: AsyncSession,
        file_id: str,
        query_object: FileAccessLogPageQueryModel,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取文件访问审计列表

        :param db: orm对象
        :param file_id: 文件ID
        :param query_object: 文件访问审计查询参数
        :param is_page: 是否开启分页
        :return: 文件访问审计列表
        """
        query = (
            select(SysFileAccessLog)
            .where(
                SysFileAccessLog.file_id == file_id,
                SysFileAccessLog.action == query_object.action if query_object.action else True,
                SysFileAccessLog.result == query_object.result if query_object.result else True,
                SysFileAccessLog.actor_name.like(f'%{query_object.actor_name}%') if query_object.actor_name else True,
                SysFileAccessLog.access_time.between(
                    datetime.strptime(query_object.begin_time, '%Y-%m-%d %H:%M:%S'),
                    datetime.strptime(query_object.end_time, '%Y-%m-%d %H:%M:%S'),
                )
                if query_object.begin_time and query_object.end_time
                else True,
            )
            .order_by(SysFileAccessLog.access_time.desc(), SysFileAccessLog.audit_id.desc())
        )
        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
