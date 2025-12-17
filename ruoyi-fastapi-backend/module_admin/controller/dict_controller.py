from datetime import datetime
from typing import Annotated

from fastapi import Form, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from module_admin.entity.vo.dict_vo import (
    DeleteDictDataModel,
    DeleteDictTypeModel,
    DictDataModel,
    DictDataPageQueryModel,
    DictTypeModel,
    DictTypePageQueryModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.dict_service import DictDataService, DictTypeService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

dict_controller = APIRouterPro(
    prefix='/system/dict', order_num=8, tags=['系统管理-字典管理'], dependencies=[PreAuthDependency()]
)


@dict_controller.get(
    '/type/list',
    summary='获取字典类型分页列表接口',
    description='用于获取字典类型分页列表',
    response_model=PageResponseModel[DictTypeModel],
    dependencies=[UserInterfaceAuthDependency('system:dict:list')],
)
async def get_system_dict_type_list(
    request: Request,
    dict_type_page_query: Annotated[DictTypePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    dict_type_page_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, dict_type_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=dict_type_page_query_result)


@dict_controller.post(
    '/type',
    summary='新增字典类型接口',
    description='用于新增字典类型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:add')],
)
@ValidateFields(validate_model='add_dict_type')
@Log(title='字典类型', business_type=BusinessType.INSERT)
async def add_system_dict_type(
    request: Request,
    add_dict_type: DictTypeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_dict_type.create_by = current_user.user.user_name
    add_dict_type.create_time = datetime.now()
    add_dict_type.update_by = current_user.user.user_name
    add_dict_type.update_time = datetime.now()
    add_dict_type_result = await DictTypeService.add_dict_type_services(request, query_db, add_dict_type)
    logger.info(add_dict_type_result.message)

    return ResponseUtil.success(msg=add_dict_type_result.message)


@dict_controller.put(
    '/type',
    summary='编辑字典类型接口',
    description='用于编辑字典类型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:edit')],
)
@ValidateFields(validate_model='edit_dict_type')
@Log(title='字典类型', business_type=BusinessType.UPDATE)
async def edit_system_dict_type(
    request: Request,
    edit_dict_type: DictTypeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_dict_type.update_by = current_user.user.user_name
    edit_dict_type.update_time = datetime.now()
    edit_dict_type_result = await DictTypeService.edit_dict_type_services(request, query_db, edit_dict_type)
    logger.info(edit_dict_type_result.message)

    return ResponseUtil.success(msg=edit_dict_type_result.message)


@dict_controller.delete(
    '/type/refreshCache',
    summary='刷新字典缓存接口',
    description='用于刷新字典缓存',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:remove')],
)
@Log(title='字典类型', business_type=BusinessType.UPDATE)
async def refresh_system_dict(request: Request, query_db: Annotated[AsyncSession, DBSessionDependency()]) -> Response:
    refresh_dict_result = await DictTypeService.refresh_sys_dict_services(request, query_db)
    logger.info(refresh_dict_result.message)

    return ResponseUtil.success(msg=refresh_dict_result.message)


@dict_controller.delete(
    '/type/{dict_ids}',
    summary='删除字典类型接口',
    description='用于删除字典类型',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:remove')],
)
@Log(title='字典类型', business_type=BusinessType.DELETE)
async def delete_system_dict_type(
    request: Request,
    dict_ids: Annotated[str, Path(description='需要删除的字典主键')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_dict_type = DeleteDictTypeModel(dictIds=dict_ids)
    delete_dict_type_result = await DictTypeService.delete_dict_type_services(request, query_db, delete_dict_type)
    logger.info(delete_dict_type_result.message)

    return ResponseUtil.success(msg=delete_dict_type_result.message)


@dict_controller.get(
    '/type/optionselect',
    summary='获取字典类型下拉列表接口',
    description='用于获取字典类型下拉列表',
    response_model=DataResponseModel[list[DictTypeModel]],
)
async def query_system_dict_type_options(
    request: Request, query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    dict_type_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, DictTypePageQueryModel(), is_page=False
    )
    logger.info('获取成功')

    return ResponseUtil.success(data=dict_type_query_result)


@dict_controller.get(
    '/type/{dict_id}',
    summary='获取字典类型详情接口',
    description='用于获取指定字典类型的详细信息',
    response_model=DataResponseModel[DictTypeModel],
    dependencies=[UserInterfaceAuthDependency('system:dict:query')],
)
async def query_detail_system_dict_type(
    request: Request,
    dict_id: Annotated[int, Path(description='字典主键')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    dict_type_detail_result = await DictTypeService.dict_type_detail_services(query_db, dict_id)
    logger.info(f'获取dict_id为{dict_id}的信息成功')

    return ResponseUtil.success(data=dict_type_detail_result)


@dict_controller.post(
    '/type/export',
    summary='导出字典类型列表接口',
    description='用于导出当前符合查询条件的字典类型列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回字典类型列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:dict:export')],
)
@Log(title='字典类型', business_type=BusinessType.EXPORT)
async def export_system_dict_type_list(
    request: Request,
    dict_type_page_query: Annotated[DictTypePageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    dict_type_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, dict_type_page_query, is_page=False
    )
    dict_type_export_result = await DictTypeService.export_dict_type_list_services(dict_type_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(dict_type_export_result))


@dict_controller.get(
    '/data/type/{dict_type}',
    summary='获取指定字典类型的数据列表接口',
    description='用于从缓存中获取指定字典类型的所有数据项',
    response_model=DataResponseModel[list[DictDataModel]],
)
async def query_system_dict_type_data(
    request: Request,
    dict_type: Annotated[str, Path(description='字典类型')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    dict_data_query_result = await DictDataService.query_dict_data_list_from_cache_services(
        request.app.state.redis, dict_type
    )
    logger.info('获取成功')

    return ResponseUtil.success(data=dict_data_query_result)


@dict_controller.get(
    '/data/list',
    summary='获取字典数据分页列表接口',
    description='用于获取字典数据分页列表',
    response_model=PageResponseModel[DictDataModel],
    dependencies=[UserInterfaceAuthDependency('system:dict:list')],
)
async def get_system_dict_data_list(
    request: Request,
    dict_data_page_query: Annotated[DictDataPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    dict_data_page_query_result = await DictDataService.get_dict_data_list_services(
        query_db, dict_data_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=dict_data_page_query_result)


@dict_controller.post(
    '/data',
    summary='新增字典数据接口',
    description='用于新增字典数据',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:add')],
)
@ValidateFields(validate_model='add_dict_data')
@Log(title='字典数据', business_type=BusinessType.INSERT)
async def add_system_dict_data(
    request: Request,
    add_dict_data: DictDataModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_dict_data.create_by = current_user.user.user_name
    add_dict_data.create_time = datetime.now()
    add_dict_data.update_by = current_user.user.user_name
    add_dict_data.update_time = datetime.now()
    add_dict_data_result = await DictDataService.add_dict_data_services(request, query_db, add_dict_data)
    logger.info(add_dict_data_result.message)

    return ResponseUtil.success(msg=add_dict_data_result.message)


@dict_controller.put(
    '/data',
    summary='编辑字典数据接口',
    description='用于编辑字典数据',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:edit')],
)
@ValidateFields(validate_model='edit_dict_data')
@Log(title='字典数据', business_type=BusinessType.UPDATE)
async def edit_system_dict_data(
    request: Request,
    edit_dict_data: DictDataModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_dict_data.update_by = current_user.user.user_name
    edit_dict_data.update_time = datetime.now()
    edit_dict_data_result = await DictDataService.edit_dict_data_services(request, query_db, edit_dict_data)
    logger.info(edit_dict_data_result.message)

    return ResponseUtil.success(msg=edit_dict_data_result.message)


@dict_controller.delete(
    '/data/{dict_codes}',
    summary='删除字典数据接口',
    description='用于删除字典数据',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:dict:remove')],
)
@Log(title='字典数据', business_type=BusinessType.DELETE)
async def delete_system_dict_data(
    request: Request,
    dict_codes: Annotated[str, Path(description='需要删除的字典编码')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_dict_data = DeleteDictDataModel(dictCodes=dict_codes)
    delete_dict_data_result = await DictDataService.delete_dict_data_services(request, query_db, delete_dict_data)
    logger.info(delete_dict_data_result.message)

    return ResponseUtil.success(msg=delete_dict_data_result.message)


@dict_controller.get(
    '/data/{dict_code}',
    summary='获取字典数据详情接口',
    description='用于获取指定字典数据的详细信息',
    response_model=DataResponseModel[DictDataModel],
    dependencies=[UserInterfaceAuthDependency('system:dict:query')],
)
async def query_detail_system_dict_data(
    request: Request,
    dict_code: Annotated[int, Path(description='字典编码')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    detail_dict_data_result = await DictDataService.dict_data_detail_services(query_db, dict_code)
    logger.info(f'获取dict_code为{dict_code}的信息成功')

    return ResponseUtil.success(data=detail_dict_data_result)


@dict_controller.post(
    '/data/export',
    summary='导出字典数据列表接口',
    description='用于导出当前符合查询条件的字典数据列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回字典数据列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:dict:export')],
)
@Log(title='字典数据', business_type=BusinessType.EXPORT)
async def export_system_dict_data_list(
    request: Request,
    dict_data_page_query: Annotated[DictDataPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    dict_data_query_result = await DictDataService.get_dict_data_list_services(
        query_db, dict_data_page_query, is_page=False
    )
    dict_data_export_result = await DictDataService.export_dict_data_list_services(dict_data_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(dict_data_export_result))
