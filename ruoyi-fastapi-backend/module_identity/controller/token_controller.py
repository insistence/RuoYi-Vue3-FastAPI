from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from jwt.exceptions import PyJWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.constant import OidcAuditEvent
from common.router import APIRouterPro
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.dependencies import (
    AccessTokenContext,
    OidcAccessTokenDependency,
    load_access_verification_key,
    read_form,
    require_oidc_protocol_ready,
)
from module_identity.redis_keys import OidcRedisKey
from module_identity.security.client_auth import ClientAuthenticationError, parse_client_secret_basic
from module_identity.security.jwt_profile import JwtProfileError
from module_identity.service.audit_service import AuditService
from module_identity.service.infrastructure_service import OidcRateLimiter, RateLimitExceeded, RateLimitUnavailable
from module_identity.service.token_protocol_service import (
    IntrospectionService,
    RevocationError,
    RevocationService,
    UserInfoService,
)
from module_identity.service.token_service import RefreshTokenReuseDetected, TokenService

token_controller = APIRouterPro(tags=['认证中心协议'], order_num=2, dependencies=[Depends(require_oidc_protocol_ready)])
_NO_STORE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
_FORM_LIMITS = {
    'grant_type': 50,
    'client_id': 64,
    'client_secret': 512,
    'code': 4096,
    'redirect_uri': 1000,
    'code_verifier': 128,
    'refresh_token': 4096,
    'scope': 2000,
    'resource': 1000,
    'token': 8192,
    'token_type_hint': 32,
}
_RATE_LIMIT = 60
_RATE_WINDOW_SECONDS = 60
_JWT_DOT_COUNT = 2
_NOT_FOUND = 404


def _invalid_userinfo_response() -> JSONResponse:
    """
    构造不泄露原因的 UserInfo 401 响应

    :return: 不泄露校验细节的 UserInfo 401 响应
    """
    # 不向客户端泄露 UserInfo 校验失败原因
    return JSONResponse(
        content={'error': 'invalid_token'},
        status_code=401,
        headers={**_NO_STORE, 'WWW-Authenticate': 'Bearer error="invalid_token"'},
    )


def _request_redis(request: Request) -> Redis:
    """
    读取应用 Redis 客户端

    :param request: 当前 HTTP 请求
    :return: Redis 客户端
    :raises OAuthProtocolException: Redis 客户端不可用时抛出
    """
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise OAuthProtocolException('server_error', 'Token endpoint is unavailable', 503)
    return cast('Redis', redis)


async def _pre_auth_rate_limit(request: Request, redis: Redis, form: dict[str, str], endpoint: str) -> None:
    """
    在 Client Secret 校验前按可见 Client ID 限流

    :param request: 当前 HTTP 请求
    :param redis: Redis 客户端
    :param form: 已解析的协议表单
    :param endpoint: 当前协议端点标识
    :return: 无返回值
    :raises RateLimitExceeded: 请求超过限流阈值时抛出
    :raises RateLimitUnavailable: 限流服务不可用时抛出
    """
    # 在 Client Secret 校验前按可见 Client ID 限流
    client_id = form.get('client_id')
    authorization = request.headers.get('authorization')
    if authorization:
        try:
            client_id, _ = parse_client_secret_basic(authorization)
        except ClientAuthenticationError:
            client_id = None
    if not isinstance(client_id, str) or not client_id:
        client_id = 'anonymous'
    key_builders = {
        'token': OidcRedisKey.token_client_rate_limit,
        'revoke': OidcRedisKey.revoke_client_rate_limit,
        'introspect': OidcRedisKey.introspect_client_rate_limit,
    }
    try:
        key = key_builders[endpoint](client_id)
    except (KeyError, TypeError, ValueError):
        key = key_builders[endpoint]('anonymous')
    await OidcRateLimiter.enforce(redis, key, limit=_RATE_LIMIT, window_seconds=_RATE_WINDOW_SECONDS)


def _validate_protocol_form(form: dict[str, str], allowed: set[str]) -> None:
    """
    校验协议表单字段白名单和长度

    :param form: 已解析的协议表单
    :param allowed: 当前端点允许的字段集合
    :return: 无返回值
    :raises OAuthProtocolException: 包含未知字段或超长字段时抛出
    """
    # 拒绝未知或超长的协议表单字段
    if any(key not in allowed for key in form) or any(
        key in _FORM_LIMITS and len(value) > _FORM_LIMITS[key] for key, value in form.items()
    ):
        raise OAuthProtocolException('invalid_request', 'Invalid request', 400)


def _rate_limit_error(error: RateLimitExceeded | RateLimitUnavailable) -> JSONResponse:
    """
    构造协议限流错误响应

    :param error: 限流异常
    :return: 裸标准限流错误响应
    """
    # 限流响应不回显敏感字段
    if isinstance(error, RateLimitExceeded):
        response = JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=429, headers=_NO_STORE)
        response.headers['Retry-After'] = str(error.retry_after)
        return response
    return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)


async def _record_independent_audit(db: AsyncSession, event_type: str, **fields: object) -> None:
    """
    尝试记录协议失败审计，审计异常不改变标准错误响应

    :param db: 异步数据库会话
    :param event_type: 审计事件类型
    :param fields: 审计字段
    :return: 无返回值
    """
    try:
        await AuditService.record_independent(db, event_type, 'failure', **fields)
    except Exception:
        return


async def _verification_key_or_none(token: str, query_db: AsyncSession) -> object:
    """
    为 JWT 撤销和内省加载本地公钥

    :param token: 待读取的访问令牌
    :param query_db: 异步数据库会话
    :return: 本地公钥或 None
    """
    # Opaque Token 保持幂等语义，JWT 校验失败按无公钥处理
    if not isinstance(token, str) or token.count('.') != _JWT_DOT_COUNT:
        return None
    try:
        return await load_access_verification_key(token, query_db)
    except (JwtProfileError, PyJWTError, TypeError, ValueError):
        return None


async def _verification_key_loader(query_db: AsyncSession, token: str) -> object:
    """
    提供给 Service 事务入口的本地公钥加载回调

    :param query_db: 异步数据库会话
    :param token: 待读取的访问令牌
    :return: 本地公钥或 None
    """
    return await _verification_key_or_none(token, query_db)


def _oauth_error(error: OAuthProtocolException) -> JSONResponse:
    """
    生成裸标准 OAuth 错误响应

    :param error: OAuth 协议异常
    :return: 裸标准 OAuth 错误响应
    """
    content = {'error': error.error}
    if error.error_description:
        content['error_description'] = error.error_description
    headers = dict(_NO_STORE)
    if error.error == 'invalid_client':
        headers['WWW-Authenticate'] = 'Basic realm="oauth2/token"'
    headers.update(error.headers)
    return JSONResponse(content=content, status_code=error.status_code, headers=headers)


def _http_error(error: HTTPException) -> JSONResponse:
    """
    将输入边界 HTTP 错误转换为裸 JSON 响应

    :param error: 输入边界 HTTP 异常
    :return: 裸 JSON 错误响应
    """
    code = 'not_found' if error.status_code == _NOT_FOUND else 'invalid_request'
    return JSONResponse(content={'error': code}, status_code=error.status_code, headers=_NO_STORE)


@token_controller.post(
    '/oauth2/token',
    summary='获取 OAuth Token 接口',
    description='用于签发 OAuth Token',
    include_in_schema=False,
)
async def token(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    try:
        form = await read_form(request)
        _validate_protocol_form(
            form,
            {
                'grant_type',
                'client_id',
                'client_secret',
                'code',
                'redirect_uri',
                'code_verifier',
                'refresh_token',
                'scope',
                'resource',
            },
        )
        redis = _request_redis(request)
        await _pre_auth_rate_limit(request, redis, form, 'token')
        client_secret = form.pop('client_secret', None)
        result = await TokenService.issue_token_request(
            query_db,
            redis,
            form,
            authorization=request.headers.get('authorization'),
            client_id=form.get('client_id'),
            client_secret=client_secret,
        )
        return JSONResponse(content=result.as_dict(), headers=_NO_STORE)
    except RefreshTokenReuseDetected as exc:
        return _oauth_error(exc)
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        return _rate_limit_error(exc)
    except OAuthProtocolException as exc:
        await _record_independent_audit(
            query_db,
            OidcAuditEvent.INVALID_CLIENT if exc.error == 'invalid_client' else OidcAuditEvent.TOKEN_FAILED,
            failure_code=exc.error,
        )
        return _oauth_error(exc)
    except HTTPException as exc:
        return _http_error(exc)
    except Exception:
        await _record_independent_audit(query_db, OidcAuditEvent.TOKEN_FAILED, failure_code='server_error')
        return JSONResponse(
            content={'error': 'server_error', 'error_description': 'Token endpoint is unavailable'},
            status_code=500,
            headers=_NO_STORE,
        )


@token_controller.post(
    '/oauth2/revoke',
    summary='撤销 OAuth Token 接口',
    description='用于撤销 OAuth Token',
    include_in_schema=False,
)
async def revoke(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    try:
        form = await read_form(request)
        _validate_protocol_form(form, {'client_id', 'client_secret', 'token', 'token_type_hint'})
        redis = _request_redis(request)
        await _pre_auth_rate_limit(request, redis, form, 'revoke')
        committed = await RevocationService.revoke_request(
            query_db,
            redis,
            form.get('token', ''),
            authorization=request.headers.get('authorization'),
            client_id=form.get('client_id'),
            client_secret=form.get('client_secret'),
            verification_key_loader=_verification_key_loader,
            token_type_hint=form.get('token_type_hint'),
        )
        if not committed:
            return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
        return Response(status_code=200, headers=_NO_STORE)
    except OAuthProtocolException as exc:
        await _record_independent_audit(
            query_db,
            OidcAuditEvent.INVALID_CLIENT if exc.error == 'invalid_client' else OidcAuditEvent.TOKEN_FAILED,
            failure_code=exc.error,
        )
        return _oauth_error(exc)
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        return _rate_limit_error(exc)
    except RevocationError as exc:
        await _record_independent_audit(
            query_db,
            OidcAuditEvent.INVALID_CLIENT if exc.error == 'invalid_client' else OidcAuditEvent.TOKEN_FAILED,
            failure_code=exc.error,
        )
        headers = dict(_NO_STORE)
        if exc.error == 'invalid_client':
            headers['WWW-Authenticate'] = 'Basic realm="oauth2/token"'
        return JSONResponse(
            content={'error': exc.error, 'error_description': exc.description},
            status_code=401 if exc.error == 'invalid_client' else 400,
            headers=headers,
        )
    except HTTPException as exc:
        return _http_error(exc)
    except Exception:
        await _record_independent_audit(query_db, OidcAuditEvent.TOKEN_FAILED, failure_code='server_error')
        return JSONResponse(content={'error': 'server_error'}, status_code=500, headers=_NO_STORE)


@token_controller.post(
    '/oauth2/introspect',
    summary='查询 OAuth Token 状态接口',
    description='用于查询 OAuth Token 状态',
    include_in_schema=False,
)
async def introspect(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    try:
        form = await read_form(request)
        _validate_protocol_form(form, {'client_id', 'client_secret', 'token', 'token_type_hint'})
        redis = _request_redis(request)
        await _pre_auth_rate_limit(request, redis, form, 'introspect')
        result = await IntrospectionService.introspect_request(
            query_db,
            redis,
            form.get('token', ''),
            authorization=request.headers.get('authorization'),
            client_id=form.get('client_id'),
            client_secret=form.get('client_secret'),
            verification_key_loader=_verification_key_loader,
            token_type_hint=form.get('token_type_hint'),
        )
        return JSONResponse(content=result, headers=_NO_STORE)
    except OAuthProtocolException as exc:
        await _record_independent_audit(
            query_db,
            OidcAuditEvent.INVALID_CLIENT if exc.error == 'invalid_client' else OidcAuditEvent.TOKEN_FAILED,
            failure_code=exc.error,
        )
        return _oauth_error(exc)
    except (RateLimitExceeded, RateLimitUnavailable) as exc:
        return _rate_limit_error(exc)
    except HTTPException as exc:
        return _http_error(exc)
    except Exception:
        await _record_independent_audit(query_db, OidcAuditEvent.TOKEN_FAILED, failure_code='server_error')
        return JSONResponse(content={'error': 'server_error'}, status_code=500, headers=_NO_STORE)


@token_controller.get(
    '/oauth2/userinfo',
    summary='获取 UserInfo 接口',
    description='用于返回当前访问令牌对应的用户信息',
    include_in_schema=False,
)
@token_controller.post(
    '/oauth2/userinfo',
    summary='获取 UserInfo 接口',
    description='用于返回当前访问令牌对应的用户信息',
    include_in_schema=False,
)
async def userinfo(
    request: Request,
    token_context: Annotated[AccessTokenContext, OidcAccessTokenDependency()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return JSONResponse(content={'error': 'not_found'}, status_code=404, headers=_NO_STORE)
    try:
        claims = token_context.claims
        output = await UserInfoService.build(query_db, claims, getattr(request.app.state, 'redis', None))
        return JSONResponse(content=output, headers=_NO_STORE)
    except Exception:
        return _invalid_userinfo_response()
