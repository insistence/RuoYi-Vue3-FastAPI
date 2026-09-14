from typing import Annotated, Literal

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
from module_identity.entity.vo.oidc_key_vo import OidcKeyRotateModel, OidcKeyViewModel
from module_identity.service.key_service import OidcKeyManagementService
from module_identity.service.runtime_service import OidcRuntimeService
from utils.response_util import ResponseUtil

oidc_key_controller = APIRouterPro(
    prefix='/system/oauth/key', order_num=24, tags=['系统管理-OIDC 签名密钥'], dependencies=[PreAuthDependency()]
)


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


@oidc_key_controller.get(
    '/list',
    summary='获取 OIDC 签名密钥分页列表接口',
    description='用于获取 OIDC 签名密钥分页列表',
    response_model=PageResponseModel[OidcKeyViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthKey:list')],
)
async def list_oidc_keys(
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    status: Annotated[Literal['pending', 'active', 'retiring', 'retired', 'compromised'] | None, Query()] = None,
    page_num: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 10,
) -> Response:
    rows, total = await OidcKeyManagementService.list_page(query_db, status, page_num, page_size)
    readiness = await OidcRuntimeService.inspect_readiness(query_db)

    return ResponseUtil.success(rows=rows, dict_content={'total': total, **readiness.as_dict()})


@oidc_key_controller.post(
    '/rotate',
    summary='轮换 OIDC 签名密钥接口',
    description='用于轮换 OIDC 签名密钥',
    response_model=DataResponseModel[OidcKeyViewModel],
    dependencies=[UserInterfaceAuthDependency('system:oauthKey:rotate')],
)
@Log(title='OIDC 签名密钥', business_type=BusinessType.INSERT)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_KEY_ROTATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
async def rotate_oidc_key(
    payload: OidcKeyRotateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OidcKeyManagementService.rotate(query_db, payload, _actor(current_user))

    return ResponseUtil.success(msg='OIDC 签名密钥创建成功', data=result)


@oidc_key_controller.put(
    '/{kid}/activate',
    summary='激活 OIDC 签名密钥接口',
    description='用于激活 OIDC 签名密钥',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthKey:activate')],
)
@Log(title='OIDC 签名密钥', business_type=BusinessType.UPDATE)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_KEY_ACTIVATE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
async def activate_oidc_key(
    kid: Annotated[str, Path(min_length=1, max_length=100)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OidcKeyManagementService.activate(
        query_db, kid, _actor(current_user), getattr(request.app.state, 'redis', None)
    )
    await OidcRuntimeService.refresh_readiness(request.app, query_db)

    return ResponseUtil.success(msg='OIDC 签名密钥已激活', data={'changed': result})


@oidc_key_controller.put(
    '/{kid}/retire',
    summary='退役 OIDC 签名密钥接口',
    description='用于退役 OIDC 签名密钥',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthKey:retire')],
)
@Log(title='OIDC 签名密钥', business_type=BusinessType.UPDATE)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_KEY_RETIRE, preset=ApiRateLimitPreset.USER_SECURITY_MUTATION)
async def retire_oidc_key(
    kid: Annotated[str, Path(min_length=1, max_length=100)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OidcKeyManagementService.retire(query_db, kid, _actor(current_user))

    return ResponseUtil.success(msg='OIDC 签名密钥已退役', data={'changed': result})


@oidc_key_controller.delete(
    '/{kid}',
    summary='删除 OIDC 签名密钥接口',
    description='用于删除 OIDC 签名密钥',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:oauthKey:retire')],
)
@Log(title='OIDC 签名密钥', business_type=BusinessType.DELETE)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_OAUTH_KEY_DELETE, preset=ApiRateLimitPreset.USER_DESTRUCTIVE_MUTATION)
async def delete_oidc_key(
    kid: Annotated[str, Path(min_length=1, max_length=100)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    request: Request,
) -> Response:
    result = await OidcKeyManagementService.delete(query_db, kid, _actor(current_user))

    return ResponseUtil.success(msg='OIDC 签名密钥已删除', data={'changed': result})
