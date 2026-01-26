from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from exceptions.exception import ServiceException
from module_ai.dao.ai_model_dao import AiModelDao
from module_ai.entity.vo.ai_model_vo import AiModelModel, AiModelPageQueryModel, DeleteAiModelModel
from utils.common_util import CamelCaseUtil
from utils.crypto_util import CryptoUtil


class AiModelService:
    """
    AI模型管理服务层
    """

    @classmethod
    async def get_ai_model_list_services(
        cls,
        query_db: AsyncSession,
        query_object: AiModelPageQueryModel,
        data_scope_sql: ColumnElement,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取AI模型列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: AI模型列表信息对象
        """
        ai_model_list_result = await AiModelDao.get_ai_model_list(query_db, query_object, data_scope_sql, is_page)
        rows = ai_model_list_result.rows if isinstance(ai_model_list_result, PageModel) else ai_model_list_result

        for row in rows:
            if 'apiKey' in row:
                row['apiKey'] = '********' * 3

        return ai_model_list_result

    @classmethod
    async def check_ai_model_data_scope_services(
        cls,
        query_db: AsyncSession,
        model_id: int,
        data_scope_sql: ColumnElement,
    ) -> CrudResponseModel:
        """
        校验用户是否有AI模型数据权限service

        :param query_db: orm对象
        :param model_id: 模型主键
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 校验结果
        """
        ai_models = await AiModelDao.get_ai_model_list(
            query_db, AiModelModel(modelId=model_id), data_scope_sql, is_page=False
        )
        if ai_models:
            return CrudResponseModel(is_success=True, message='校验通过')
        raise ServiceException(message='没有权限访问AI模型数据')

    @classmethod
    async def add_ai_model_services(cls, query_db: AsyncSession, page_object: AiModelModel) -> CrudResponseModel:
        """
        新增AI模型信息service

        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 新增AI模型对象
        :return: 新增AI模型校验结果
        """
        try:
            if page_object.api_key:
                page_object.api_key = CryptoUtil.encrypt(page_object.api_key)
            await AiModelDao.add_ai_model_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def edit_ai_model_services(cls, query_db: AsyncSession, page_object: AiModelModel) -> CrudResponseModel:
        """
        编辑AI模型信息service

        :param query_db: orm对象
        :param page_object: 编辑AI模型对象
        :return: 编辑AI模型校验结果
        """
        edit_ai_model = page_object.model_dump(exclude_unset=True)
        if page_object.api_key:
            if page_object.api_key == '********' * 3:
                if 'api_key' in edit_ai_model:
                    del edit_ai_model['api_key']
            else:
                edit_ai_model['api_key'] = CryptoUtil.encrypt(page_object.api_key)

        ai_model_info = await cls.ai_model_detail_services(query_db, page_object.model_id)
        if ai_model_info.model_id:
            try:
                await AiModelDao.edit_ai_model_dao(query_db, edit_ai_model)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='修改成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='AI模型不存在')

    @classmethod
    async def delete_ai_model_services(
        cls, query_db: AsyncSession, page_object: DeleteAiModelModel
    ) -> CrudResponseModel:
        """
        删除AI模型信息service

        :param query_db: orm对象
        :param page_object: 删除AI模型对象
        :return: 删除AI模型校验结果
        """
        if page_object.model_ids:
            model_id_list = page_object.model_ids.split(',')
            try:
                for model_id in model_id_list:
                    await AiModelDao.delete_ai_model_dao(query_db, AiModelModel(modelId=model_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入AI模型id为空')

    @classmethod
    async def ai_model_detail_services(cls, query_db: AsyncSession, model_id: int) -> AiModelModel:
        """
        获取AI模型详细信息service

        :param query_db: orm对象
        :param model_id: AI模型id
        :return: AI模型id对应的信息
        """
        ai_model = await AiModelDao.get_ai_model_detail_by_id(query_db, model_id=model_id)
        result = AiModelModel(**CamelCaseUtil.transform_result(ai_model)) if ai_model else AiModelModel()

        if result.api_key:
            result.api_key = '********' * 3

        return result
