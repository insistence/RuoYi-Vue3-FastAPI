from datetime import datetime, time
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.notice_do import SysNotice
from module_admin.entity.vo.notice_vo import NoticeModel, NoticePageQueryModel
from utils.page_util import PageUtil


class NoticeDao:
    """
    通知公告管理模块数据库操作层
    """

    @classmethod
    async def get_notice_detail_by_id(cls, db: AsyncSession, notice_id: int):
        """
        根据通知公告id获取通知公告详细信息

        :param db: orm对象
        :param notice_id: 通知公告id
        :return: 通知公告信息对象
        """
        notice_info = (await db.execute(select(SysNotice).where(SysNotice.notice_id == notice_id))).scalars().first()

        return notice_info

    @classmethod
    async def get_notice_detail_by_info(cls, db: AsyncSession, notice: NoticeModel):
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
    async def get_notice_list(cls, db: AsyncSession, query_object: NoticePageQueryModel, is_page: bool = False):
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
            .order_by(SysNotice.notice_id)
            .distinct()
        )
        notice_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return notice_list

    @classmethod
    async def add_notice_dao(cls, db: AsyncSession, notice: NoticeModel):
        """
        新增通知公告数据库操作

        :param db: orm对象
        :param notice: 通知公告对象
        :return:
        """
        db_notice = SysNotice(**notice.model_dump())
        db.add(db_notice)
        await db.flush()

        return db_notice

    @classmethod
    async def edit_notice_dao(cls, db: AsyncSession, notice: dict):
        """
        编辑通知公告数据库操作

        :param db: orm对象
        :param notice: 需要更新的通知公告字典
        :return:
        """
        await db.execute(update(SysNotice), [notice])

    @classmethod
    async def delete_notice_dao(cls, db: AsyncSession, notice: NoticeModel):
        """
        删除通知公告数据库操作

        :param db: orm对象
        :param notice: 通知公告对象
        :return:
        """
        await db.execute(delete(SysNotice).where(SysNotice.notice_id.in_([notice.notice_id])))
