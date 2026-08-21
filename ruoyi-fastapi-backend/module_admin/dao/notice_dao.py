from datetime import datetime, time
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.notice_do import SysNotice, SysNoticeRead
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.notice_vo import NoticeModel, NoticePageQueryModel, NoticeReadUserPageQueryModel
from utils.page_util import PageUtil


class NoticeDao:
    """
    通知公告管理模块数据库操作层
    """

    @classmethod
    async def get_notice_detail_by_id(cls, db: AsyncSession, notice_id: int) -> SysNotice | None:
        """
        根据通知公告id获取通知公告详细信息

        :param db: orm对象
        :param notice_id: 通知公告id
        :return: 通知公告信息对象
        """
        notice_info = (await db.execute(select(SysNotice).where(SysNotice.notice_id == notice_id))).scalars().first()

        return notice_info

    @classmethod
    async def get_notice_detail_by_info(cls, db: AsyncSession, notice: NoticeModel) -> SysNotice | None:
        """
        根据通知公告参数获取通知公告信息

        :param db: orm对象
        :param notice: 通知公告参数对象
        :return: 通知公告信息对象
        """
        notice_info = (
            (
                await db.execute(
                    select(SysNotice).where(
                        SysNotice.notice_title == notice.notice_title,
                        SysNotice.notice_type == notice.notice_type,
                        SysNotice.notice_content == notice.notice_content,
                    )
                )
            )
            .scalars()
            .first()
        )

        return notice_info

    @classmethod
    async def get_notice_list(
        cls, db: AsyncSession, query_object: NoticePageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取通知公告列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 通知公告列表信息对象
        """
        query = (
            select(SysNotice)
            .where(
                SysNotice.notice_title.like(f'%{query_object.notice_title}%') if query_object.notice_title else True,
                SysNotice.create_by.like(f'%{query_object.create_by}%') if query_object.create_by else True,
                SysNotice.notice_type == query_object.notice_type if query_object.notice_type else True,
                SysNotice.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
            )
            .order_by(SysNotice.notice_id.desc())
            .distinct()
        )
        notice_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return notice_list

    @classmethod
    async def get_notice_list_with_read_status(cls, db: AsyncSession, user_id: int, limit: int) -> list[dict[str, Any]]:
        """
        查询带当前用户已读状态的正常公告列表

        :param db: orm对象
        :param user_id: 用户ID
        :param limit: 最多返回条数
        :return: 带已读状态的公告列表
        """
        query = (
            select(
                SysNotice.notice_id,
                SysNotice.notice_title,
                SysNotice.notice_type,
                SysNotice.status,
                SysNotice.create_by,
                SysNotice.create_time,
                case((SysNoticeRead.read_id.is_not(None), True), else_=False).label('is_read'),
            )
            .outerjoin(
                SysNoticeRead,
                and_(SysNoticeRead.notice_id == SysNotice.notice_id, SysNoticeRead.user_id == user_id),
            )
            .where(SysNotice.status == '0')
            .order_by(SysNotice.notice_id.desc())
            .limit(limit)
        )
        notice_list = (await db.execute(query)).mappings().all()

        return [dict(notice) for notice in notice_list]

    @classmethod
    async def get_unread_count(cls, db: AsyncSession, user_id: int) -> int:
        """
        查询当前用户未读的正常公告数量

        :param db: orm对象
        :param user_id: 用户ID
        :return: 未读公告数量
        """
        read_exists = (
            select(SysNoticeRead.read_id)
            .where(SysNoticeRead.notice_id == SysNotice.notice_id, SysNoticeRead.user_id == user_id)
            .exists()
        )
        unread_count = (
            await db.execute(select(func.count()).select_from(SysNotice).where(SysNotice.status == '0', ~read_exists))
        ).scalar_one()

        return unread_count

    @classmethod
    async def get_notice_read_user_list(
        cls, db: AsyncSession, query_object: NoticeReadUserPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        查询已阅读指定公告的用户列表

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 已读用户列表
        """
        search_value = query_object.search_value
        query = (
            select(
                SysUser.user_id.label('user_id'),
                SysUser.user_name.label('user_name'),
                SysUser.nick_name.label('nick_name'),
                SysDept.dept_name.label('dept_name'),
                SysUser.phonenumber.label('phonenumber'),
                SysNoticeRead.read_time.label('read_time'),
            )
            .join(SysUser, and_(SysUser.user_id == SysNoticeRead.user_id, SysUser.del_flag == '0'))
            .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
            .where(
                SysNoticeRead.notice_id == query_object.notice_id,
                or_(
                    SysUser.user_name.like(f'%{search_value}%'),
                    SysUser.nick_name.like(f'%{search_value}%'),
                )
                if search_value
                else True,
            )
            .order_by(SysNoticeRead.read_time.desc())
        )

        return await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def add_notice_reads(cls, db: AsyncSession, user_id: int, notice_ids: list[int]) -> None:
        """
        幂等新增公告已读记录

        :param db: orm对象
        :param user_id: 用户ID
        :param notice_ids: 公告ID列表
        :return:
        """
        unique_notice_ids = list(dict.fromkeys(notice_ids))
        if not unique_notice_ids:
            return

        values = [
            {'notice_id': notice_id, 'user_id': user_id, 'read_time': datetime.now()} for notice_id in unique_notice_ids
        ]
        dialect_name = db.get_bind().dialect.name
        if dialect_name == 'mysql':
            statement = mysql_insert(SysNoticeRead).values(values).prefix_with('IGNORE')
            await db.execute(statement)
        elif dialect_name == 'postgresql':
            statement = (
                postgresql_insert(SysNoticeRead)
                .values(values)
                .on_conflict_do_nothing(index_elements=['user_id', 'notice_id'])
            )
            await db.execute(statement)
        elif dialect_name == 'sqlite':
            statement = (
                sqlite_insert(SysNoticeRead)
                .values(values)
                .on_conflict_do_nothing(index_elements=['user_id', 'notice_id'])
            )
            await db.execute(statement)
        else:
            existing_notice_ids = set(
                (
                    await db.execute(
                        select(SysNoticeRead.notice_id).where(
                            SysNoticeRead.user_id == user_id,
                            SysNoticeRead.notice_id.in_(unique_notice_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            db.add_all(
                SysNoticeRead(notice_id=notice_id, user_id=user_id)
                for notice_id in unique_notice_ids
                if notice_id not in existing_notice_ids
            )

    @classmethod
    async def delete_notice_reads(cls, db: AsyncSession, notice_ids: list[int]) -> None:
        """
        根据公告ID列表删除已读记录

        :param db: orm对象
        :param notice_ids: 公告ID列表
        :return:
        """
        if notice_ids:
            await db.execute(delete(SysNoticeRead).where(SysNoticeRead.notice_id.in_(notice_ids)))

    @classmethod
    async def add_notice_dao(cls, db: AsyncSession, notice: NoticeModel) -> SysNotice:
        """
        新增通知公告数据库操作

        :param db: orm对象
        :param notice: 通知公告对象
        :return:
        """
        db_notice = SysNotice(**notice.model_dump(exclude={'create_time', 'update_time'}))
        db.add(db_notice)
        await db.flush()

        return db_notice

    @classmethod
    async def edit_notice_dao(cls, db: AsyncSession, notice: dict) -> None:
        """
        编辑通知公告数据库操作

        :param db: orm对象
        :param notice: 需要更新的通知公告字典
        :return:
        """
        await db.execute(
            update(SysNotice),
            [{key: value for key, value in notice.items() if key not in {'create_time', 'update_time'}}],
        )

    @classmethod
    async def delete_notice_dao(cls, db: AsyncSession, notice: NoticeModel) -> None:
        """
        删除通知公告数据库操作

        :param db: orm对象
        :param notice: 通知公告对象
        :return:
        """
        await db.execute(delete(SysNotice).where(SysNotice.notice_id.in_([notice.notice_id])))
