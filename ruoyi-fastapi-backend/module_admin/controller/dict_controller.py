from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.enums import BusinessType
from config.get_db import get_db
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
from module_admin.service.login_service import LoginService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil

dict_controller = APIRouter(prefix='/system/dict', dependencies=[Depends(LoginService.get_current_user)])


@dict_controller.get(
    '/type/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:list'))]
)
async def get_system_dict_type_list(
    request: Request,
    dict_type_page_query: Annotated[DictTypePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取分页数据
    dict_type_page_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, dict_type_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=dict_type_page_query_result)


@dict_controller.post('/type', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:add'))])
@ValidateFields(validate_model='add_dict_type')
@Log(title='字典类型', business_type=BusinessType.INSERT)
async def add_system_dict_type(
    request: Request,
    add_dict_type: DictTypeModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    add_dict_type.create_by = current_user.user.user_name
    add_dict_type.create_time = datetime.now()
    add_dict_type.update_by = current_user.user.user_name
    add_dict_type.update_time = datetime.now()
    add_dict_type_result = await DictTypeService.add_dict_type_services(request, query_db, add_dict_type)
    logger.info(add_dict_type_result.message)

    return ResponseUtil.success(msg=add_dict_type_result.message)


@dict_controller.put('/type', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:edit'))])
@ValidateFields(validate_model='edit_dict_type')
@Log(title='字典类型', business_type=BusinessType.UPDATE)
async def edit_system_dict_type(
    request: Request,
    edit_dict_type: DictTypeModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    edit_dict_type.update_by = current_user.user.user_name
    edit_dict_type.update_time = datetime.now()
    edit_dict_type_result = await DictTypeService.edit_dict_type_services(request, query_db, edit_dict_type)
    logger.info(edit_dict_type_result.message)

    return ResponseUtil.success(msg=edit_dict_type_result.message)


@dict_controller.delete('/type/refreshCache', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@Log(title='字典类型', business_type=BusinessType.UPDATE)
async def refresh_system_dict(request: Request, query_db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    refresh_dict_result = await DictTypeService.refresh_sys_dict_services(request, query_db)
    logger.info(refresh_dict_result.message)

    return ResponseUtil.success(msg=refresh_dict_result.message)


@dict_controller.delete('/type/{dict_ids}', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@Log(title='字典类型', business_type=BusinessType.DELETE)
async def delete_system_dict_type(
    request: Request,
    dict_ids: Annotated[str, Path(description='需要删除的字典主键')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    delete_dict_type = DeleteDictTypeModel(dictIds=dict_ids)
    delete_dict_type_result = await DictTypeService.delete_dict_type_services(request, query_db, delete_dict_type)
    logger.info(delete_dict_type_result.message)

    return ResponseUtil.success(msg=delete_dict_type_result.message)


@dict_controller.get('/type/optionselect', response_model=list[DictTypeModel])
async def query_system_dict_type_options(
    request: Request, query_db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    dict_type_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, DictTypePageQueryModel(), is_page=False
    )
    logger.info('获取成功')

    return ResponseUtil.success(data=dict_type_query_result)


@dict_controller.get(
    '/type/{dict_id}', response_model=DictTypeModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:query'))]
)
async def query_detail_system_dict_type(
    request: Request,
    dict_id: Annotated[int, Path(description='字典主键')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    dict_type_detail_result = await DictTypeService.dict_type_detail_services(query_db, dict_id)
    logger.info(f'获取dict_id为{dict_id}的信息成功')

    return ResponseUtil.success(data=dict_type_detail_result)


@dict_controller.post('/type/export', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:export'))])
@Log(title='字典类型', business_type=BusinessType.EXPORT)
async def export_system_dict_type_list(
    request: Request,
    dict_type_page_query: Annotated[DictTypePageQueryModel, Form()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取全量数据
    dict_type_query_result = await DictTypeService.get_dict_type_list_services(
        query_db, dict_type_page_query, is_page=False
    )
    dict_type_export_result = await DictTypeService.export_dict_type_list_services(dict_type_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(dict_type_export_result))


@dict_controller.get('/data/type/{dict_type}')
async def query_system_dict_type_data(
    request: Request,
    dict_type: Annotated[str, Path(description='字典类型')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取全量数据
    dict_data_query_result = await DictDataService.query_dict_data_list_from_cache_services(
        request.app.state.redis, dict_type
    )
    logger.info('获取成功')

    return ResponseUtil.success(data=dict_data_query_result)


@dict_controller.get(
    '/data/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:list'))]
)
async def get_system_dict_data_list(
    request: Request,
    dict_data_page_query: Annotated[DictDataPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取分页数据
    dict_data_page_query_result = await DictDataService.get_dict_data_list_services(
        query_db, dict_data_page_query, is_page=True
    )
    logger.info('获取成功')

    return ResponseUtil.success(model_content=dict_data_page_query_result)


@dict_controller.post('/data', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:add'))])
@ValidateFields(validate_model='add_dict_data')
@Log(title='字典数据', business_type=BusinessType.INSERT)
async def add_system_dict_data(
    request: Request,
    add_dict_data: DictDataModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    add_dict_data.create_by = current_user.user.user_name
    add_dict_data.create_time = datetime.now()
    add_dict_data.update_by = current_user.user.user_name
    add_dict_data.update_time = datetime.now()
    add_dict_data_result = await DictDataService.add_dict_data_services(request, query_db, add_dict_data)
    logger.info(add_dict_data_result.message)

    return ResponseUtil.success(msg=add_dict_data_result.message)


@dict_controller.put('/data', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:edit'))])
@ValidateFields(validate_model='edit_dict_data')
@Log(title='字典数据', business_type=BusinessType.UPDATE)
async def edit_system_dict_data(
    request: Request,
    edit_dict_data: DictDataModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    edit_dict_data.update_by = current_user.user.user_name
    edit_dict_data.update_time = datetime.now()
    edit_dict_data_result = await DictDataService.edit_dict_data_services(request, query_db, edit_dict_data)
    logger.info(edit_dict_data_result.message)

    return ResponseUtil.success(msg=edit_dict_data_result.message)


@dict_controller.delete('/data/{dict_codes}', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@Log(title='字典数据', business_type=BusinessType.DELETE)
async def delete_system_dict_data(
    request: Request,
    dict_codes: Annotated[str, Path(description='需要删除的字典编码')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    delete_dict_data = DeleteDictDataModel(dictCodes=dict_codes)
    delete_dict_data_result = await DictDataService.delete_dict_data_services(request, query_db, delete_dict_data)
    logger.info(delete_dict_data_result.message)

    return ResponseUtil.success(msg=delete_dict_data_result.message)


@dict_controller.get(
    '/data/{dict_code}',
    response_model=DictDataModel,
    dependencies=[Depends(CheckUserInterfaceAuth('system:dict:query'))],
)
async def query_detail_system_dict_data(
    request: Request,
    dict_code: Annotated[int, Path(description='字典编码')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    detail_dict_data_result = await DictDataService.dict_data_detail_services(query_db, dict_code)
    logger.info(f'获取dict_code为{dict_code}的信息成功')

    return ResponseUtil.success(data=detail_dict_data_result)


@dict_controller.post('/data/export', dependencies=[Depends(CheckUserInterfaceAuth('system:dict:export'))])
@Log(title='字典数据', business_type=BusinessType.EXPORT)
async def export_system_dict_data_list(
    request: Request,
    dict_data_page_query: Annotated[DictDataPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取全量数据
    dict_data_query_result = await DictDataService.get_dict_data_list_services(
        query_db, dict_data_page_query, is_page=False
    )
    dict_data_export_result = await DictDataService.export_dict_data_list_services(dict_data_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(dict_data_export_result))
