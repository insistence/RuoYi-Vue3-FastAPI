from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.data_scope import DataScopeDependency
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_ai.entity.do.ai_model_do import AiModels
from module_ai.entity.vo.ai_model_vo import AiModelModel, AiModelPageQueryModel, DeleteAiModelModel
from module_ai.service.ai_model_service import AiModelService
from utils.log_util import logger
from utils.response_util import ResponseUtil

ai_model_controller = APIRouterPro(
    prefix='/ai/model', order_num=18, tags=['AI管理-模型管理'], dependencies=[PreAuthDependency()]
)


@ai_model_controller.get(
    '/list',
    summary='获取AI模型分页列表接口',
    description='用于获取AI模型分页列表',
    response_model=PageResponseModel[AiModelModel],
    dependencies=[UserInterfaceAuthDependency('ai:model:list')],
)
async def get_ai_model_list(
    request: Request,
    ai_model_page_query: Annotated[AiModelPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AiModels)],
) -> Response:
    # 获取分页数据
    result = await AiModelService.get_ai_model_list_services(
        query_db, ai_model_page_query, data_scope_sql, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=result)


@ai_model_controller.get(
    '/all',
    summary='获取AI模型不分页列表接口',
    description='用于获取AI模型不分页列表',
    response_model=DataResponseModel[AiModelModel],
)
async def get_ai_model_all(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AiModels)],
) -> Response:
    # 获取不分页数据
    ai_model_page_query = AiModelPageQueryModel(status='0')
    result = await AiModelService.get_ai_model_list_services(
        query_db, ai_model_page_query, data_scope_sql, is_page=False
    )
    logger.info('获取成功')

    return ResponseUtil.success(data=result)


@ai_model_controller.post(
    '',
    summary='新增AI模型接口',
    description='用于新增AI模型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:add')],
)
@ValidateFields(validate_model='add_ai_model')
@Log(title='AI模型管理', business_type=BusinessType.INSERT)
async def add_ai_model(
    request: Request,
    add_ai_model: AiModelModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_ai_model.user_id = current_user.user.user_id
    add_ai_model.dept_id = current_user.user.dept_id
    add_ai_model.create_by = current_user.user.user_name
    add_ai_model.create_time = datetime.now()
    add_ai_model.update_by = current_user.user.user_name
    add_ai_model.update_time = datetime.now()
    add_ai_model_result = await AiModelService.add_ai_model_services(query_db, add_ai_model)
    logger.info(add_ai_model_result.message)

    return ResponseUtil.success(msg=add_ai_model_result.message)


@ai_model_controller.put(
    '',
    summary='编辑AI模型接口',
    description='用于编辑AI模型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:edit')],
)
@ValidateFields(validate_model='edit_ai_model')
@Log(title='AI模型管理', business_type=BusinessType.UPDATE)
async def edit_ai_model(
    request: Request,
    edit_ai_model: AiModelModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AiModels)],
) -> Response:
    if not current_user.user.admin:
        await AiModelService.check_ai_model_data_scope_services(query_db, edit_ai_model.model_id, data_scope_sql)
    edit_ai_model.update_by = current_user.user.user_name
    edit_ai_model.update_time = datetime.now()
    edit_ai_model_result = await AiModelService.edit_ai_model_services(query_db, edit_ai_model)
    logger.info(edit_ai_model_result.message)

    return ResponseUtil.success(msg=edit_ai_model_result.message)


@ai_model_controller.delete(
    '/{model_ids}',
    summary='删除AI模型接口',
    description='用于删除AI模型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:remove')],
)
@Log(title='AI模型管理', business_type=BusinessType.DELETE)
async def delete_ai_model(
    request: Request,
    model_ids: Annotated[str, Path(description='需要删除的模型ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AiModels)],
) -> Response:
    model_id_list = model_ids.split(',')
    for model_id in model_id_list:
        if not current_user.user.admin:
            await AiModelService.check_ai_model_data_scope_services(query_db, int(model_id), data_scope_sql)
    delete_ai_model = DeleteAiModelModel(modelIds=model_ids)
    delete_ai_model_result = await AiModelService.delete_ai_model_services(query_db, delete_ai_model)
    logger.info(delete_ai_model_result.message)

    return ResponseUtil.success(msg=delete_ai_model_result.message)


@ai_model_controller.get(
    '/{model_id}',
    summary='获取AI模型详情接口',
    description='用于获取指定AI模型的详细信息',
    response_model=DataResponseModel[AiModelModel],
    dependencies=[UserInterfaceAuthDependency('ai:model:query')],
)
async def get_ai_model_detail(
    request: Request,
    model_id: Annotated[int, Path(description='模型ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AiModels)],
) -> Response:
    if not current_user.user.admin:
        await AiModelService.check_ai_model_data_scope_services(query_db, model_id, data_scope_sql)
    ai_model_detail_result = await AiModelService.ai_model_detail_services(query_db, model_id)
    logger.info(f'获取model_id为{model_id}的信息成功')

    return ResponseUtil.success(data=ai_model_detail_result)
