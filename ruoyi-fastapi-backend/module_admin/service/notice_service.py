from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import CommonConstant
from common.vo import CrudResponseModel, PageModel
from exceptions.exception import ServiceException
from module_admin.dao.notice_dao import NoticeDao
from module_admin.entity.vo.notice_vo import (
    DeleteNoticeModel,
    NoticeModel,
    NoticePageQueryModel,
    NoticeTopModel,
    NoticeTopResponseModel,
)
from utils.common_util import CamelCaseUtil


class NoticeService:
    """
    通知公告管理模块服务层
    """

    TOP_NOTICE_LIMIT = 5

    @classmethod
    async def get_notice_list_services(
        cls, query_db: AsyncSession, query_object: NoticePageQueryModel, is_page: bool = True
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取通知公告列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 通知公告列表信息对象
        """
        notice_list_result = await NoticeDao.get_notice_list(query_db, query_object, is_page)

        return notice_list_result

    @classmethod
    async def get_notice_top_services(cls, query_db: AsyncSession, user_id: int) -> NoticeTopResponseModel:
        """
        获取首页顶部通知公告及当前用户已读状态

        :param query_db: orm对象
        :param user_id: 用户ID
        :return: 首页顶部通知公告响应对象
        """
        notice_list = await NoticeDao.get_notice_list_with_read_status(query_db, user_id, cls.TOP_NOTICE_LIMIT)
        notice_models = [NoticeTopModel(**CamelCaseUtil.transform_result(notice)) for notice in notice_list]
        unread_count = sum(not notice.is_read for notice in notice_models)

        return NoticeTopResponseModel(data=notice_models, unreadCount=unread_count)

    @classmethod
    async def mark_notice_read_services(
        cls, query_db: AsyncSession, user_id: int, notice_ids: list[int]
    ) -> CrudResponseModel:
        """
        标记通知公告已读

        :param query_db: orm对象
        :param user_id: 用户ID
        :param notice_ids: 公告ID列表
        :return: 操作结果
        """
        try:
            await NoticeDao.add_notice_reads(query_db, user_id, notice_ids)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='标记成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    def parse_notice_ids(cls, notice_ids: str) -> list[int]:
        """
        解析逗号分隔的公告ID

        :param notice_ids: 逗号分隔的公告ID
        :return: 去重后的公告ID列表
        """
        try:
            return list(
                dict.fromkeys(int(notice_id.strip()) for notice_id in notice_ids.split(',') if notice_id.strip())
            )
        except ValueError as exc:
            raise ServiceException(message='公告ID格式不正确') from exc

    @classmethod
    async def check_notice_unique_services(cls, query_db: AsyncSession, page_object: NoticeModel) -> bool:
        """
        校验通知公告是否存在service

        :param query_db: orm对象
        :param page_object: 通知公告对象
        :return: 校验结果
        """
        notice_id = -1 if page_object.notice_id is None else page_object.notice_id
        notice = await NoticeDao.get_notice_detail_by_info(query_db, page_object)
        if notice and notice.notice_id != notice_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_notice_services(cls, query_db: AsyncSession, page_object: NoticeModel) -> CrudResponseModel:
        """
        新增通知公告信息service

        :param query_db: orm对象
        :param page_object: 新增通知公告对象
        :return: 新增通知公告校验结果
        """
        if not await cls.check_notice_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增通知公告{page_object.notice_title}失败，通知公告已存在')
        try:
            await NoticeDao.add_notice_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def edit_notice_services(cls, query_db: AsyncSession, page_object: NoticeModel) -> CrudResponseModel:
        """
        编辑通知公告信息service

        :param query_db: orm对象
        :param page_object: 编辑通知公告对象
        :return: 编辑通知公告校验结果
        """
        edit_notice = page_object.model_dump(exclude_unset=True)
        notice_info = await cls.notice_detail_services(query_db, page_object.notice_id)
        if notice_info.notice_id:
            if not await cls.check_notice_unique_services(query_db, page_object):
                raise ServiceException(message=f'修改通知公告{page_object.notice_title}失败，通知公告已存在')
            try:
                await NoticeDao.edit_notice_dao(query_db, edit_notice)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='更新成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='通知公告不存在')

    @classmethod
    async def delete_notice_services(cls, query_db: AsyncSession, page_object: DeleteNoticeModel) -> CrudResponseModel:
        """
        删除通知公告信息service

        :param query_db: orm对象
        :param page_object: 删除通知公告对象
        :return: 删除通知公告校验结果
        """
        if page_object.notice_ids:
            notice_id_list = cls.parse_notice_ids(page_object.notice_ids)
            try:
                await NoticeDao.delete_notice_reads(query_db, notice_id_list)
                for notice_id in notice_id_list:
                    await NoticeDao.delete_notice_dao(query_db, NoticeModel(noticeId=notice_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入通知公告id为空')

    @classmethod
    async def notice_detail_services(cls, query_db: AsyncSession, notice_id: int) -> NoticeModel:
        """
        获取通知公告详细信息service

        :param query_db: orm对象
        :param notice_id: 通知公告id
        :return: 通知公告id对应的信息
        """
        notice = await NoticeDao.get_notice_detail_by_id(query_db, notice_id=notice_id)
        result = NoticeModel(**CamelCaseUtil.transform_result(notice)) if notice else NoticeModel()

        return result
