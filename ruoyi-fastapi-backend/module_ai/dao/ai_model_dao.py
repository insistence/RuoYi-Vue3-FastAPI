from typing import Any

from sqlalchemy import ColumnElement, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_ai.entity.do.ai_model_do import AiModels
from module_ai.entity.vo.ai_model_vo import AiModelModel, AiModelPageQueryModel
from utils.page_util import PageUtil


class AiModelDao:
    """
    AI模型管理数据库操作层
    """

    @classmethod
    async def get_ai_model_detail_by_id(cls, db: AsyncSession, model_id: int) -> AiModels | None:
        """
        根据AI模型id获取AI模型详细信息

        :param db: orm对象
        :param model_id: AI模型id
        :return: AI模型信息对象
        """
        ai_model_info = (await db.execute(select(AiModels).where(AiModels.model_id == model_id))).scalars().first()

        return ai_model_info

    @classmethod
    async def get_ai_model_list(
        cls, db: AsyncSession, query_object: AiModelPageQueryModel, data_scope_sql: ColumnElement, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取AI模型列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: AI模型列表信息对象
        """
        query = (
            select(AiModels)
            .where(
                AiModels.model_id == query_object.model_id if query_object.model_id else True,
                AiModels.model_name.like(f'%{query_object.model_name}%') if query_object.model_name else True,
                AiModels.model_code.like(f'%{query_object.model_code}%') if query_object.model_code else True,
                AiModels.provider == query_object.provider if query_object.provider else True,
                AiModels.status == query_object.status if query_object.status else True,
                data_scope_sql,
            )
            .order_by(AiModels.model_sort)
        )
        ai_model_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return ai_model_list

    @classmethod
    async def add_ai_model_dao(cls, db: AsyncSession, ai_model: AiModelModel) -> AiModels:
        """
        新增AI模型数据库操作

        :param db: orm对象
        :param ai_model: AI模型对象
        :return: AI模型信息对象
        """
        db_model = AiModels(**ai_model.model_dump(exclude_unset=True))
        db.add(db_model)
        await db.flush()

        return db_model

    @classmethod
    async def edit_ai_model_dao(cls, db: AsyncSession, ai_model: dict) -> None:
        """
        编辑AI模型数据库操作

        :param db: orm对象
        :param ai_model: 需要更新的AI模型字典
        :return:
        """
        await db.execute(update(AiModels), [ai_model])

    @classmethod
    async def delete_ai_model_dao(cls, db: AsyncSession, ai_model: AiModelModel) -> None:
        """
        删除AI模型数据库操作

        :param db: orm对象
        :param ai_model: AI模型对象
        :return:
        """
        await db.execute(delete(AiModels).where(AiModels.model_id.in_([ai_model.model_id])))
