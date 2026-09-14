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
from module_identity.entity.vo.oauth_session_vo import (
    GrantModel,
    GrantPageQueryModel,
    SessionPageQueryModel,
    SessionRevokeModel,
    SsoSessionModel,
)
from module_identity.service.oauth_session_management_service import OAuthSessionManagementService
from utils.response_util import ResponseUtil

oauth_session_controller = APIRouterPro(
    prefix='/system/oauth/session', order_num=22, tags=['系统管理-OAuth Session'], dependencies=[PreAuthDependency()]
)
oauth_grant_controller = APIRouterPro(
    prefix='/system/oauth/grant', order_num=23, tags=['系统管理-OAuth Grant'], dependencies=[PreAuthDependency()]
)
_MAX_BATCH_SIZE = 100


def _actor(user: CurrentUserModel) -> str:
    """
    提取管理操作者标识

    :param user: 当前登录用户
    :return: 安全截断后的用户名
    :raises ServiceException: 当前用户不可用
    """

    value = getattr(getattr(user, 'user', None), 'user_name', None)
    if not isinstance(value, str) or not value.strip():
        raise ServiceException(message='当前操作者不可用')
    return value[:64]


def _split(value: str, name: str) -> list[str]:
    """
    校验并拆分批量会话参数

    :param value: 逗号分隔的会话或授权标识
    :param name: 参数字段名称
    :return: 去除空白后的参数列表
    :raises ServiceException: 参数为空、超出数量限制、包含非法字符或重复值
    """

    values = [item.strip() for item in value.split(',')] if isinstance(value, str) else []
    if (
        not values
        or len(values) > _MAX_BATCH_SIZE
        or any(
            not item or '/' in item or '\\' in item or '%' in item or any(char.isspace() for char in item)
            for item in values
        )
    ):
        raise ServiceException(message=f'{name} 参数无效')
    if len(set(values)) != len(values):
        raise ServiceException(message=f'{name} 参数重复')
    return values


@oauth_session_controller.get(
    '/list',
    summary='获取 OAuth 会话分页列表接口',
    description='用于获取 OAuth 会话分页列表',
    response_model=PageResponseModel[SsoSessionModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthSession:list')],
)
async def list_oauth_sessions(
    query: Annotated[SessionPageQueryModel, Query()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    rows, total = await OAuthSessionManagementService.list_sessions(query_db, query)

    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_session_controller.delete(
    '/user/{user_id}',
    summary='撤销用户 OAuth 会话接口',
    description='用于撤销指定用户的 OAuth 会话',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthSession:revoke')],
)
@ApiRateLimit(
    namespace=ApiNamespace.SYSTEM_OAUTH_SESSION_USER_REVOKE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION
)
@Log(title='OAuth Session管理', business_type=BusinessType.DELETE)
async def revoke_user_oauth_sessions(
    request: Request,
    user_id: Annotated[int, Path(gt=0)],
    payload: SessionRevokeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    count = await OAuthSessionManagementService.revoke_user(
        query_db, request.app.state.redis, user_id, _actor(current_user), payload.reason
    )

    return ResponseUtil.success(msg='SSO Session 已撤销', data={'count': count})


@oauth_session_controller.get(
    '/{sid}',
    summary='查询 OAuth 会话详情接口',
    description='用于查询 OAuth 会话详情',
    response_model=DataResponseModel[SsoSessionModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthSession:list')],
)
async def get_oauth_session(
    sid: Annotated[str, Path(min_length=1, max_length=64)], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    data = await OAuthSessionManagementService.get_session(query_db, sid)
    if data is None:
        raise ServiceException(message='Session 不存在')
    return ResponseUtil.success(data=data)


@oauth_session_controller.delete(
    '/{sids}',
    summary='批量撤销 OAuth 会话接口',
    description='用于批量撤销 OAuth 会话',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthSession:revoke')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_SESSION_REVOKE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='OAuth Session管理', business_type=BusinessType.DELETE)
async def revoke_oauth_sessions(
    request: Request,
    sids: Annotated[str, Path(min_length=1, max_length=6500)],
    payload: SessionRevokeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    count = await OAuthSessionManagementService.revoke_sessions(
        query_db, request.app.state.redis, _split(sids, 'sids'), _actor(current_user), payload.reason
    )

    return ResponseUtil.success(msg='SSO Session 已撤销', data={'count': count})


@oauth_grant_controller.get(
    '/list',
    summary='获取 OAuth 授权分页列表接口',
    description='用于获取 OAuth 授权分页列表',
    response_model=PageResponseModel[GrantModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthGrant:list')],
)
async def list_oauth_grants(
    query: Annotated[GrantPageQueryModel, Query()], query_db: Annotated[AsyncSession, DBSessionDependency()]
) -> Response:
    rows, total = await OAuthSessionManagementService.list_grants(query_db, query)

    return ResponseUtil.success(rows=rows, dict_content={'total': total})


@oauth_grant_controller.get(
    '/{grant_id}',
    summary='查询 OAuth 授权详情接口',
    description='用于查询 OAuth 授权详情',
    response_model=DataResponseModel[GrantModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthGrant:list')],
)
async def get_oauth_grant(
    grant_id: Annotated[str, Path(min_length=1, max_length=64)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    data = await OAuthSessionManagementService.get_grant(query_db, grant_id)
    if data is None:
        raise ServiceException(message='Grant 不存在')
    return ResponseUtil.success(data=data)


@oauth_grant_controller.delete(
    '/{grant_ids}',
    summary='批量撤销 OAuth 授权接口',
    description='用于批量撤销 OAuth 授权',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthGrant:revoke')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_GRANT_REVOKE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
@Log(title='OAuth Grant管理', business_type=BusinessType.DELETE)
async def revoke_oauth_grants(
    request: Request,
    grant_ids: Annotated[str, Path(min_length=1, max_length=6500)],
    payload: SessionRevokeModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    count = await OAuthSessionManagementService.revoke_grants(
        query_db, _split(grant_ids, 'grant_ids'), _actor(current_user), payload.reason
    )

    return ResponseUtil.success(msg='OAuth Grant 已撤销', data={'count': count})
