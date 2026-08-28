from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.aspect.db_session import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.constant import ApiNamespace
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from exceptions.exception import ServiceException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_identity.entity.vo.oauth_resource_vo import (
    ResourceCreateModel,
    ResourcePageQueryModel,
    ResourceStatusModel,
    ResourceUpdateModel,
    ResourceViewModel,
    ScopeModel,
    ScopePageQueryModel,
    ScopeStatusModel,
)
from module_identity.service.oauth_management_service import OAuthResourceManagementService
from module_identity.service.runtime_service import OidcRuntimeService
from utils.log_util import logger
from utils.response_util import ResponseUtil

oauth_resource_controller = APIRouterPro(
    prefix='/system/oauth/resource', order_num=22, tags=['系统管理-OAuth Resource'], dependencies=[PreAuthDependency()]
)
oauth_scope_controller = APIRouterPro(
    prefix='/system/oauth/scope', order_num=23, tags=['系统管理-OAuth Scope'], dependencies=[PreAuthDependency()]
)
_MAX_BATCH_SIZE = 100


def _actor(current_user: CurrentUserModel) -> str:
    """
    提取管理操作者标识

    :param current_user: 当前登录用户
    :return: 安全截断后的用户名
    :raises ServiceException: 当前用户不可用
    """
    value = getattr(getattr(current_user, 'user', None), 'user_name', None)
    if not isinstance(value, str) or not value.strip():
        raise ServiceException(message='当前操作者不可用')
    return value[:64]


def _split_batch(value: str, field_name: str) -> list[str]:
    """
    校验并拆分批量操作参数

    :param value: 逗号分隔的批量参数
    :param field_name: 参数字段名称
    :return: 去除空白后的参数列表
    :raises ServiceException: 参数为空、超出数量限制、包含非法字符或重复值
    """
    items = value.split(',') if isinstance(value, str) else []
    if not items or len(items) > _MAX_BATCH_SIZE:
        raise ServiceException(message=f'{field_name} 参数无效')
    result: list[str] = []
    for raw_item in items:
        item = raw_item.strip()
        if not item or '%' in item or '/' in item or '\\' in item or any(char.isspace() for char in item):
            raise ServiceException(message=f'{field_name} 参数无效')
        if item in result:
            raise ServiceException(message=f'{field_name} 参数重复')
        result.append(item)
    return result


@oauth_resource_controller.get(
    '/list',
    summary='获取 OAuth 资源分页列表接口',
    description='用于获取 OAuth 资源分页列表',
    response_model=PageResponseModel[ResourceViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:list')],
)
async def get_system_oauth_resource_list(
    resource_query: Annotated[ResourcePageQueryModel, Query()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    rows = await OAuthResourceManagementService.list_resources(query_db, resource_query)
    total = await OAuthResourceManagementService.count_resources(query_db, resource_query)
    logger.info('OAuth Resource 列表查询成功')
    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_resource_controller.get(
    '/{resource_id}',
    summary='查询 OAuth 资源详情接口',
    description='用于查询 OAuth 资源详情',
    response_model=DataResponseModel[ResourceViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:list')],
)
async def query_system_oauth_resource(
    resource_id: Annotated[str, Path(min_length=1, max_length=64)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    return ResponseUtil.success(data=await OAuthResourceManagementService.detail_resource(query_db, resource_id))


@oauth_resource_controller.post(
    '',
    summary='新增 OAuth 资源接口',
    description='用于新增 OAuth 资源',
    response_model=DataResponseModel[ResourceViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:add')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_RESOURCE_CREATE, preset=ApiRateLimitPreset.USER_COMMON_MUTATION)
@Log(title='OAuth Resource管理', business_type=BusinessType.INSERT)
async def add_system_oauth_resource(
    payload: ResourceCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    return ResponseUtil.success(
        data=await OAuthResourceManagementService.create_resource(
            query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
        )
    )


@oauth_resource_controller.put(
    '',
    summary='编辑 OAuth 资源接口',
    description='用于编辑 OAuth 资源',
    response_model=DataResponseModel[ResourceViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_RESOURCE_UPDATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth Resource管理', business_type=BusinessType.UPDATE)
async def edit_system_oauth_resource(
    payload: ResourceUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    return ResponseUtil.success(
        data=await OAuthResourceManagementService.update_resource(
            query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
        )
    )


@oauth_resource_controller.delete(
    '/{resource_ids}',
    summary='批量停用 OAuth 资源接口',
    description='用于批量停用 OAuth 资源',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:remove')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_RESOURCE_DISABLE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='OAuth Resource管理', business_type=BusinessType.DELETE)
async def delete_system_oauth_resources(
    resource_ids: Annotated[str, Path(min_length=1, max_length=6500)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    actor = _actor(current_user)
    await OAuthResourceManagementService.disable_resources(
        query_db,
        _split_batch(resource_ids, 'resource_ids'),
        actor,
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )
    return ResponseUtil.success(msg='OAuth Resource 已停用')


@oauth_resource_controller.put(
    '/changeStatus',
    summary='启停 OAuth 资源接口',
    description='用于启用或停用 OAuth 资源',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthResource:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_RESOURCE_STATUS, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth Resource管理', business_type=BusinessType.UPDATE)
async def change_system_oauth_resource_status(
    payload: ResourceStatusModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OAuthResourceManagementService.change_resource_status(
        query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
    )
    return ResponseUtil.success(data=result)


@oauth_scope_controller.get(
    '/list',
    summary='获取 OAuth 作用域分页列表接口',
    description='用于获取 OAuth 作用域分页列表',
    response_model=PageResponseModel[ScopeModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:list')],
)
async def get_system_oauth_scope_list(
    scope_query: Annotated[ScopePageQueryModel, Query()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    rows = await OAuthResourceManagementService.list_scopes(query_db, scope_query)
    total = await OAuthResourceManagementService.count_scopes(query_db, scope_query)
    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_scope_controller.get(
    '/{scope_code}',
    summary='查询 OAuth 作用域详情接口',
    description='用于查询 OAuth 作用域详情',
    response_model=DataResponseModel[ScopeModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:list')],
)
async def query_system_oauth_scope(
    scope_code: Annotated[str, Path(min_length=1, max_length=100)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    return ResponseUtil.success(data=await OAuthResourceManagementService.detail_scope(query_db, scope_code))


@oauth_scope_controller.post(
    '',
    summary='新增 OAuth 作用域接口',
    description='用于新增 OAuth 作用域',
    response_model=DataResponseModel[ScopeModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:add')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_SCOPE_CREATE, preset=ApiRateLimitPreset.USER_COMMON_MUTATION)
@Log(title='OAuth Scope管理', business_type=BusinessType.INSERT)
async def add_system_oauth_scope(
    payload: ScopeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    return ResponseUtil.success(
        data=await OAuthResourceManagementService.create_scope(
            query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
        )
    )


@oauth_scope_controller.put(
    '',
    summary='编辑 OAuth 作用域接口',
    description='用于编辑 OAuth 作用域',
    response_model=DataResponseModel[ScopeModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_SCOPE_UPDATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth Scope管理', business_type=BusinessType.UPDATE)
async def edit_system_oauth_scope(
    payload: ScopeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    return ResponseUtil.success(
        data=await OAuthResourceManagementService.update_scope(
            query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
        )
    )


@oauth_scope_controller.delete(
    '/{scope_codes}',
    summary='批量停用 OAuth 作用域接口',
    description='用于批量停用 OAuth 作用域',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:remove')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_SCOPE_DISABLE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='OAuth Scope管理', business_type=BusinessType.DELETE)
async def delete_system_oauth_scopes(
    scope_codes: Annotated[str, Path(min_length=1, max_length=10000)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    actor = _actor(current_user)
    await OAuthResourceManagementService.disable_scopes(
        query_db,
        _split_batch(scope_codes, 'scope_codes'),
        actor,
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )
    return ResponseUtil.success(msg='OAuth Scope 已停用')


@oauth_scope_controller.put(
    '/changeStatus',
    summary='启停 OAuth 作用域接口',
    description='用于启用或停用 OAuth 作用域',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthScope:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_SCOPE_STATUS, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth Scope管理', business_type=BusinessType.UPDATE)
async def change_system_oauth_scope_status(
    payload: ScopeStatusModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OAuthResourceManagementService.change_scope_status(
        query_db, payload, _actor(current_user), after_commit=OidcRuntimeService.cors_snapshot_callback(request.app)
    )
    return ResponseUtil.success(data=result)
