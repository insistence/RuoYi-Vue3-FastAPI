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
from module_admin.entity.vo.config_vo import ConfigModel, ConfigPageQueryModel, DeleteConfigModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.config_service import ConfigService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

config_controller = APIRouterPro(
    prefix='/system/config', order_num=9, tags=['系统管理-参数管理'], dependencies=[PreAuthDependency()]
)


@config_controller.get(
    '/list',
    summary='获取参数分页列表接口',
    description='用于获取参数分页列表',
    response_model=PageResponseModel[ConfigModel],
    dependencies=[UserInterfaceAuthDependency('system:config:list')],
)
async def get_system_config_list(
    request: Request,
    config_page_query: Annotated[ConfigPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    config_page_query_result = await ConfigService.get_config_list_services(query_db, config_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=config_page_query_result)


@config_controller.post(
    '',
    summary='新增参数接口',
    description='用于新增参数',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:config:add')],
)
@ValidateFields(validate_model='add_config')
@Log(title='参数管理', business_type=BusinessType.INSERT)
async def add_system_config(
    request: Request,
    add_config: ConfigModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_config.create_by = current_user.user.user_name
    add_config.create_time = datetime.now()
    add_config.update_by = current_user.user.user_name
    add_config.update_time = datetime.now()
    add_config_result = await ConfigService.add_config_services(request, query_db, add_config)
    logger.info(add_config_result.message)

    return ResponseUtil.success(msg=add_config_result.message)


@config_controller.put(
    '',
    summary='编辑参数接口',
    description='用于编辑参数',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:config:edit')],
)
@ValidateFields(validate_model='edit_config')
@Log(title='参数管理', business_type=BusinessType.UPDATE)
async def edit_system_config(
    request: Request,
    edit_config: ConfigModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_config.update_by = current_user.user.user_name
    edit_config.update_time = datetime.now()
    edit_config_result = await ConfigService.edit_config_services(request, query_db, edit_config)
    logger.info(edit_config_result.message)

    return ResponseUtil.success(msg=edit_config_result.message)


@config_controller.delete(
    '/refreshCache',
    summary='刷新参数缓存接口',
    description='用于刷新参数缓存',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:config:remove')],
)
@Log(title='参数管理', business_type=BusinessType.UPDATE)
async def refresh_system_config(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    refresh_config_result = await ConfigService.refresh_sys_config_services(request, query_db)
    logger.info(refresh_config_result.message)

    return ResponseUtil.success(msg=refresh_config_result.message)


@config_controller.delete(
    '/{config_ids}',
    summary='删除参数接口',
    description='用于删除参数',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:config:remove')],
)
@Log(title='参数管理', business_type=BusinessType.DELETE)
async def delete_system_config(
    request: Request,
    config_ids: Annotated[str, Path(description='需要删除的参数主键')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_config = DeleteConfigModel(configIds=config_ids)
    delete_config_result = await ConfigService.delete_config_services(request, query_db, delete_config)
    logger.info(delete_config_result.message)

    return ResponseUtil.success(msg=delete_config_result.message)


@config_controller.get(
    '/{config_id}',
    summary='获取参数详情接口',
    description='用于获取指定参数的详细信息',
    response_model=DataResponseModel[ConfigModel],
    dependencies=[UserInterfaceAuthDependency('system:config:query')],
)
async def query_detail_system_config(
    request: Request,
    config_id: Annotated[int, Path(description='参数主键')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    config_detail_result = await ConfigService.config_detail_services(query_db, config_id)
    logger.info(f'获取config_id为{config_id}的信息成功')

    return ResponseUtil.success(data=config_detail_result)


@config_controller.get(
    '/configKey/{config_key}',
    summary='根据参数键查询参数值接口',
    description='用于根据参数键从缓存中查询参数值',
    response_model=ResponseBaseModel,
)
async def query_system_config(request: Request, config_key: str) -> Response:
    # 获取全量数据
    config_query_result = await ConfigService.query_config_list_from_cache_services(request.app.state.redis, config_key)
    logger.info('获取成功')

    return ResponseUtil.success(msg=config_query_result)


@config_controller.post(
    '/export',
    summary='导出参数列表接口',
    description='用于导出当前符合查询条件的参数列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回参数列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:config:export')],
)
@Log(title='参数管理', business_type=BusinessType.EXPORT)
async def export_system_config_list(
    request: Request,
    config_page_query: Annotated[ConfigPageQueryModel, Form()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取全量数据
    config_query_result = await ConfigService.get_config_list_services(query_db, config_page_query, is_page=False)
    config_export_result = await ConfigService.export_config_list_services(config_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(config_export_result))
