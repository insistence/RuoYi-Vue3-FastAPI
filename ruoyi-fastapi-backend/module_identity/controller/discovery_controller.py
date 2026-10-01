from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.router import APIRouterPro
from config.env import OidcConfig
from module_identity.dependencies import require_oidc_protocol_ready
from module_identity.service.discovery_service import DiscoveryService
from module_identity.service.key_service import KeyService, KeyServiceError
from utils.oidc_util import OidcUtil

discovery_controller = APIRouterPro(
    tags=['认证中心发现'], order_num=1, dependencies=[Depends(require_oidc_protocol_ready)]
)
_CACHE_CONTROL = 'public, max-age=300'


def _disabled_response() -> Response:
    """
    返回协议端点关闭时的标准 404 响应

    :return: 协议端点关闭时的标准 404 响应
    """

    return JSONResponse(
        content={'error': 'not_found'}, status_code=404, headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
    )


def _etag_response(request: Request, payload: dict[str, Any]) -> Response:
    """
    按 If-None-Match 返回标准 JSON 或 304 响应

    :param request: 当前 HTTP 请求
    :param payload: 待返回的 JSON 数据
    :return: 标准 JSON 响应或 304 响应
    """

    etag = OidcUtil.json_etag(payload)
    headers = {'Cache-Control': _CACHE_CONTROL, 'ETag': etag}
    if_none_match = request.headers.get('if-none-match', '')
    if '*' in {item.strip() for item in if_none_match.split(',')} or etag in {
        item.strip() for item in if_none_match.split(',')
    }:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)


@discovery_controller.get(
    '/.well-known/openid-configuration',
    summary='获取 OpenID 配置接口',
    description='用于返回 OpenID Connect Discovery 元数据',
    include_in_schema=False,
)
async def openid_configuration(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _disabled_response()
    try:
        payload = await DiscoveryService.openid_metadata_with_scopes(query_db)
    except Exception:
        return JSONResponse(
            content={'error': 'temporarily_unavailable'}, status_code=503, headers={'Cache-Control': 'no-store'}
        )
    return _etag_response(request, payload)


@discovery_controller.get(
    '/.well-known/oauth-authorization-server',
    summary='获取 OAuth 授权服务器元数据接口',
    description='用于返回 OAuth 授权服务器元数据',
    include_in_schema=False,
)
async def oauth_authorization_server_metadata(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _disabled_response()
    try:
        payload = await DiscoveryService.oauth_metadata_with_scopes(query_db)
    except Exception:
        return JSONResponse(
            content={'error': 'temporarily_unavailable'}, status_code=503, headers={'Cache-Control': 'no-store'}
        )
    return _etag_response(request, payload)


@discovery_controller.get(
    '/oauth2/jwks',
    summary='获取签名公钥接口',
    description='用于返回不含私钥材料的签名公钥集合',
    include_in_schema=False,
)
async def jwks(request: Request, query_db: Annotated[AsyncSession, DBSessionDependency()]) -> Response:
    if not OidcConfig.oidc_enabled:
        return _disabled_response()
    try:
        # 仅返回签名公钥，不暴露私钥材料
        payload = await KeyService.build_jwks(query_db)
    except KeyServiceError:
        return JSONResponse(
            content={'error': 'temporarily_unavailable'},
            status_code=503,
            headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
        )
    return _etag_response(request, payload)
