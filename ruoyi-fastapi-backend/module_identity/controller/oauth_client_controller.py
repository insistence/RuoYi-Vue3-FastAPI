from typing import Annotated

from fastapi import Body, Path, Query, Request, Response
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
from module_identity.entity.vo.oauth_client_vo import (
    ClientCreateModel,
    ClientPageQueryModel,
    ClientSecretResponseModel,
    ClientStatusModel,
    ClientUpdateModel,
    ClientUriModel,
    ClientViewModel,
    SecretRotationModel,
)
from module_identity.service.oauth_management_service import OAuthClientManagementService
from module_identity.service.runtime_service import OidcRuntimeService
from utils.log_util import logger
from utils.oidc_util import OidcUtil
from utils.response_util import ResponseUtil

oauth_client_controller = APIRouterPro(
    prefix='/system/oauth/client', order_num=21, tags=['系统管理-OAuth Client'], dependencies=[PreAuthDependency()]
)
_MAX_BATCH_SIZE = 100


def _actor(current_user: CurrentUserModel) -> str:
    """
    提取管理操作者标识

    :param current_user: 当前登录用户
    :return: 安全截断后的用户名
    :raises ServiceException: 当前用户不可用
    """

    try:
        return OidcUtil.actor_name(
            getattr(getattr(current_user, 'user', None), 'user_name', None), error_message='当前操作者不可用'
        )
    except ValueError as exc:
        raise ServiceException(message=str(exc)) from exc


@oauth_client_controller.get(
    '/list',
    summary='获取 OAuth 客户端分页列表接口',
    description='用于获取 OAuth 客户端分页列表',
    response_model=PageResponseModel[ClientViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:list')],
)
async def get_system_oauth_client_list(
    client_query: Annotated[ClientPageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    rows = await OAuthClientManagementService.list_clients(query_db, client_query)
    total = await OAuthClientManagementService.count_clients(query_db, client_query)
    logger.info('OAuth 客户端列表查询成功')

    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_client_controller.get(
    '/{client_id}',
    summary='查询 OAuth 客户端详情接口',
    description='用于查询 OAuth 客户端详情',
    response_model=DataResponseModel[ClientViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:query')],
)
async def query_system_oauth_client(
    client_id: Annotated[str, Path(min_length=1, max_length=64)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    return ResponseUtil.success(data=await OAuthClientManagementService.detail(query_db, client_id))


@oauth_client_controller.post(
    '',
    summary='新增 OAuth 客户端接口',
    description='用于新增 OAuth 客户端',
    response_model=DataResponseModel[ClientViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:add')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_CREATE, preset=ApiRateLimitPreset.USER_COMMON_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.INSERT)
async def add_system_oauth_client(
    request: Request,
    payload: ClientCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.create_client(
        query_db,
        payload,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )
    logger.info('OAuth 客户端创建成功')

    return ResponseUtil.success(data=result)


@oauth_client_controller.put(
    '',
    summary='编辑 OAuth 客户端接口',
    description='用于编辑 OAuth 客户端',
    response_model=DataResponseModel[ClientViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_UPDATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.UPDATE)
async def edit_system_oauth_client(
    request: Request,
    payload: ClientUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.update_client(
        query_db,
        payload,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(data=result)


@oauth_client_controller.delete(
    '/{client_ids}',
    summary='批量停用 OAuth 客户端接口',
    description='用于批量停用 OAuth 客户端',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:remove')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_DISABLE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.DELETE)
async def delete_system_oauth_clients(
    request: Request,
    client_ids: Annotated[str, Path(min_length=1, max_length=6500)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    actor = _actor(current_user)
    try:
        batch_ids = OidcUtil.split_batch(client_ids, 'client_ids', max_size=_MAX_BATCH_SIZE)
    except ValueError as exc:
        raise ServiceException(message=str(exc)) from exc
    await OAuthClientManagementService.disable_clients(
        query_db,
        batch_ids,
        actor,
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(msg='OAuth 客户端已停用')


@oauth_client_controller.put(
    '/changeStatus',
    summary='启停 OAuth 客户端接口',
    description='用于启用或停用 OAuth 客户端',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_STATUS, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.UPDATE)
async def change_system_oauth_client_status(
    request: Request,
    payload: ClientStatusModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.change_client_status(
        query_db,
        payload,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(data=result)


@oauth_client_controller.post(
    '/{client_id}/secret',
    summary='轮换 OAuth 客户端密钥接口',
    description='用于轮换 OAuth 客户端密钥',
    response_model=DataResponseModel[ClientSecretResponseModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:rotateSecret')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_SECRET_ROTATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION
)
@Log(title='OAuth 客户端密钥管理', business_type=BusinessType.UPDATE)
async def rotate_system_oauth_client_secret(
    request: Request,
    client_id: Annotated[str, Path(min_length=1, max_length=64)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    payload: SecretRotationModel = Body(default_factory=SecretRotationModel),
) -> Response:
    result = await OAuthClientManagementService.rotate_secret(
        query_db,
        client_id,
        actor=_actor(current_user),
        not_before=payload.not_before,
        expires_at=payload.expires_at,
        retirement_seconds=payload.retirement_seconds,
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(msg='客户端密钥生成成功，请立即保存', data=result)


@oauth_client_controller.delete(
    '/{client_id}/secret/{secret_id}',
    summary='撤销 OAuth 客户端密钥接口',
    description='用于撤销 OAuth 客户端密钥',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:rotateSecret')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_SECRET_REVOKE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION
)
@Log(title='OAuth 客户端密钥管理', business_type=BusinessType.DELETE)
async def revoke_system_oauth_client_secret(
    request: Request,
    client_id: Annotated[str, Path(min_length=1, max_length=64)],
    secret_id: Annotated[str, Path(min_length=1, max_length=64)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.revoke_secret(
        query_db,
        client_id,
        secret_id,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(data=result, msg='客户端密钥已撤销')


@oauth_client_controller.post(
    '/{client_id}/uri',
    summary='新增 OAuth 客户端 URI 接口',
    description='用于新增 OAuth 客户端 URI',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_URI_ADD, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.INSERT)
async def add_system_oauth_client_uri(
    request: Request,
    client_id: Annotated[str, Path(min_length=1, max_length=64)],
    payload: ClientUriModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.add_uri(
        query_db,
        client_id,
        payload,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(data=result, msg='客户端 URI 已增加')


@oauth_client_controller.delete(
    '/{client_id}/uri/{uri_id}',
    summary='停用 OAuth 客户端 URI 接口',
    description='用于停用 OAuth 客户端 URI',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthClient:edit')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_CLIENT_URI_REMOVE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
@Log(title='OAuth 客户端管理', business_type=BusinessType.DELETE)
async def delete_system_oauth_client_uri(
    request: Request,
    client_id: Annotated[str, Path(min_length=1, max_length=64)],
    uri_id: Annotated[int, Path(gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await OAuthClientManagementService.remove_uri(
        query_db,
        client_id,
        uri_id,
        _actor(current_user),
        after_commit=OidcRuntimeService.cors_snapshot_callback(request.app),
    )

    return ResponseUtil.success(data=result, msg='客户端 URI 已停用')
