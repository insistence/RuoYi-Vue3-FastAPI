import hashlib
import hmac
from collections.abc import Iterable
from typing import Annotated, Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from common.constant import OidcAuditEvent
from common.router import APIRouterPro
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException
from module_identity.dependencies import read_form, require_oidc_protocol_ready
from module_identity.redis_keys import OidcRedisKey
from module_identity.service.audit_service import AuditService
from module_identity.service.authorization_service import AuthorizationService
from module_identity.service.infrastructure_service import OidcRateLimiter, RateLimitExceeded, RateLimitUnavailable
from module_identity.service.session_service import LogoutService, LogoutServiceError, SsoSessionService

authorization_controller = APIRouterPro(
    tags=['认证中心协议'], order_num=4, dependencies=[Depends(require_oidc_protocol_ready)]
)
_NO_STORE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
_AUTHORIZE_RATE_LIMIT = 30
_AUTHORIZE_RATE_WINDOW_SECONDS = 60
_LOCAL_LOGOUT_HTML = (
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
    '<title>退出成功</title></head><body><h1>已退出</h1></body></html>'
)
_LOGOUT_QUERY_LIMITS = {'id_token_hint': 8192, 'post_logout_redirect_uri': 1000, 'state': 2048}
_LOGOUT_QUERY_FIELDS = frozenset(_LOGOUT_QUERY_LIMITS)
_LOGOUT_RATE_PEPPER_MIN_BYTES = 32


def _read_authorization_query(request: Request) -> dict[str, str]:
    """
    读取并拒绝重复授权 Query 参数

    :param request: 当前 HTTP 请求
    :return: 唯一 Query 参数映射
    :raises OAuthProtocolException: Query 参数重复时抛出
    """
    values: dict[str, str] = {}
    # 拒绝重复授权参数
    for key, value in request.query_params.multi_items():
        if key in values:
            raise OAuthProtocolException('invalid_request', 'Duplicate authorization parameter')
        values[key] = value
    return values


def _authorization_redis(request: Request) -> Redis:
    """
    读取应用生命周期创建的 Redis 客户端

    :param request: 当前 HTTP 请求
    :return: Redis 客户端
    :raises OAuthProtocolException: Redis 客户端不可用时抛出
    """
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise OAuthProtocolException('server_error', 'Authorization service is unavailable', 503)
    return cast('Redis', redis)


async def _enforce_authorization_rate_limit(request: Request, redis: Redis) -> None:
    """
    按 HMAC-IP 固定窗口执行授权请求限流

    :param request: 当前 HTTP 请求
    :param redis: Redis 客户端
    :return: 无返回值
    :raises OAuthProtocolException: 客户端地址缺失、请求超限或限流服务不可用时抛出
    """
    # 使用 HMAC-IP 固定窗口限流，Redirect 校验前不执行外跳
    client = request.client
    ip_address = getattr(client, 'host', None) if client is not None else None
    if not isinstance(ip_address, str) or not ip_address:
        raise OAuthProtocolException('temporarily_unavailable', 'Authorization service is unavailable', 503)
    ip_hash = OidcRedisKey.hash_sensitive_identifier(ip_address, OidcConfig.oidc_token_hash_pepper)
    try:
        await OidcRateLimiter.enforce(
            redis,
            OidcRedisKey.authorize_ip_rate_limit(ip_hash),
            limit=_AUTHORIZE_RATE_LIMIT,
            window_seconds=_AUTHORIZE_RATE_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise OAuthProtocolException(
            'slow_down', 'Too many authorization requests', 429, headers={'Retry-After': str(exc.retry_after)}
        ) from exc
    except RateLimitUnavailable as exc:
        raise OAuthProtocolException('temporarily_unavailable', 'Authorization service is unavailable', 503) from exc


async def _record_authorization_failure_audit(db: AsyncSession, **fields: Any) -> None:
    """
    尝试记录授权失败审计，审计异常不影响原协议错误

    :param db: 异步数据库会话
    :param fields: 审计字段
    :return: 无返回值
    """
    try:
        await AuditService.record_independent(
            db, OidcAuditEvent.AUTHORIZE_DENIED, 'failure', risk_level='high', **fields
        )
    except Exception:
        return


def _oidc_not_found_response() -> Response:
    """
    构造 OIDC 关闭时的本地 404 响应

    :return: OIDC 未启用时的本地 404 响应
    """
    return JSONResponse(content={'error': 'not_found'}, status_code=404, headers=_NO_STORE)


def _append_state(redirect_uri: str, state: str | None) -> str:
    """
    为已验证的退出回调地址附加状态参数

    :param redirect_uri: 服务端已验证的退出回调地址
    :param state: 原始退出状态参数
    :return: 附加状态参数后的回调地址
    """
    if state is None:
        return redirect_uri
    parsed = urlsplit(redirect_uri)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != 'state']
    query.append(('state', state))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _local_response(_request: Request) -> HTMLResponse:
    """
    构造不回显退出参数的同源完成页

    :param _request: 当前 HTTP 请求
    :return: 同源退出完成页
    """
    return HTMLResponse(content=_LOCAL_LOGOUT_HTML, status_code=200, headers=_NO_STORE)


async def _logout_parameters(request: Request) -> dict[str, str] | None:
    """
    读取并校验 GET Query 或 POST Form 退出参数

    :param request: 当前 HTTP 请求
    :return: 通过校验的退出参数，校验失败时返回 None
    """
    if request.method == 'POST':
        try:
            values = await read_form(request)
        except HTTPException:
            return None
        return values if _valid_logout_parameters(values.items()) else None
    seen: set[str] = set()
    for key, value in request.query_params.multi_items():
        if key not in _LOGOUT_QUERY_FIELDS or key in seen or len(value) > _LOGOUT_QUERY_LIMITS[key]:
            return None
        seen.add(key)
    return dict(request.query_params.multi_items())


def _valid_logout_parameters(values: Iterable[tuple[str, str]]) -> bool:
    """
    校验退出参数的字段白名单和长度

    :param values: 待校验的退出参数
    :return: 参数是否全部通过校验
    """
    return all(key in _LOGOUT_QUERY_FIELDS and len(value) <= _LOGOUT_QUERY_LIMITS[key] for key, value in values)


def _logout_rate_scope(request: Request) -> str:
    """
    生成退出限流使用的 HMAC 主体摘要

    :param request: 当前 HTTP 请求
    :return: 退出限流主体摘要
    """
    address = getattr(getattr(request, 'client', None), 'host', None) or 'anonymous'
    pepper = getattr(OidcConfig, 'oidc_token_hash_pepper', '')
    raw_pepper = pepper.encode() if isinstance(pepper, str) else pepper
    if not isinstance(raw_pepper, bytes) or len(raw_pepper) < _LOGOUT_RATE_PEPPER_MIN_BYTES:
        raw_pepper = hashlib.sha256(b'oidc-logout-rate-limit-fallback').digest()
    return hmac.new(raw_pepper, str(address).encode(), hashlib.sha256).hexdigest()


@authorization_controller.get(
    '/oauth2/authorize',
    summary='OAuth 授权接口',
    description='用于处理 OAuth 授权请求并返回认证交互或客户端回调',
    include_in_schema=False,
)
async def authorize(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _oidc_not_found_response()
    raw = _read_authorization_query(request)
    redis = _authorization_redis(request)
    try:
        await _enforce_authorization_rate_limit(request, redis)
    except OAuthProtocolException as exc:
        await _record_authorization_failure_audit(query_db, client_id=raw.get('client_id'), failure_code=exc.error)
        raise
    try:
        result = await AuthorizationService.process_authorization_request(
            query_db,
            redis,
            raw,
            sso_cookie=request.cookies.get(OidcConfig.oidc_sso_cookie_name),
        )
    except OAuthProtocolException as exc:
        if exc.error == 'not_found' and not exc.can_redirect:
            return _oidc_not_found_response()
        raise
    return RedirectResponse(result.location, status_code=result.status_code, headers=_NO_STORE)


@authorization_controller.post(
    '/oauth2/logout',
    summary='退出认证中心接口',
    description='用于退出认证中心登录',
    include_in_schema=False,
)
async def logout(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _oidc_not_found_response()
    parameters = await _logout_parameters(request)
    if parameters is None:
        return JSONResponse(content={'error': 'invalid_request'}, status_code=400, headers=_NO_STORE)
    redis = getattr(request.app.state, 'redis', None)
    try:
        if redis is None:
            raise LogoutServiceError('logout service unavailable')
        await OidcRateLimiter.enforce(
            redis, OidcRedisKey.logout_rate_limit(_logout_rate_scope(request)), limit=60, window_seconds=60
        )
        result = await LogoutService.execute_logout(
            query_db,
            redis,
            id_token_hint=parameters.get('id_token_hint'),
            cookie=request.cookies.get(OidcConfig.oidc_sso_cookie_name),
            post_logout_redirect_uri=parameters.get('post_logout_redirect_uri'),
            state=parameters.get('state'),
        )
    except RateLimitExceeded as exc:
        headers = dict(_NO_STORE)
        headers['Retry-After'] = str(exc.retry_after)
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=429, headers=headers)
    except RateLimitUnavailable:
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
    except Exception:
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
    if result.redirect_uri is None:
        response = _local_response(request)
    else:
        location = _append_state(result.redirect_uri, result.state)
        response = RedirectResponse(url=location, status_code=303, headers=_NO_STORE)
    try:
        response.delete_cookie(**SsoSessionService.cookie_parameters())
    except Exception:
        return response
    return response
