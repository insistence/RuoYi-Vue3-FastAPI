import hashlib
import hmac
from base64 import b64encode
from collections.abc import Iterable
from html import escape
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
from module_identity.service.logout_confirmation_service import LogoutConfirmationService
from module_identity.service.session_service import LogoutService, LogoutServiceError, SsoSessionService

authorization_controller = APIRouterPro(
    tags=['认证中心协议'], order_num=4, dependencies=[Depends(require_oidc_protocol_ready)]
)
_NO_STORE = {'Cache-Control': 'no-store', 'Pragma': 'no-cache'}
_AUTHORIZE_RATE_LIMIT = 30
_AUTHORIZE_RATE_WINDOW_SECONDS = 60
_LOGOUT_STYLE = """
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;color:#1f2937;background:#f3f4f6}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px}
main{width:100%;max-width:480px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:36px}
.brand{font-size:14px;color:#4b5563;margin:0 0 24px}h1{font-size:26px;line-height:1.4;margin:0 0 16px}
p{font-size:16px;line-height:1.75;margin:0 0 28px;color:#4b5563}form{display:flex;gap:12px;flex-wrap:wrap}
button{flex:1;min-height:44px;padding:10px 16px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;
color:#1f2937;font:inherit;font-size:15px;cursor:pointer}button:hover{background:#f3f4f6}
button:focus-visible{outline:3px solid #2563eb;outline-offset:3px}
button[value=confirm]{background:#b91c1c;border-color:#b91c1c;color:#fff}button[value=confirm]:hover{background:#991b1b}
@media(max-width:400px){body{padding:16px}main{padding:24px}form{flex-direction:column}}
"""
_LOGOUT_STYLE_HASH = b64encode(hashlib.sha256(_LOGOUT_STYLE.encode()).digest()).decode()
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


def _logout_page(title: str, body: str, *, redirect_origin: str | None = None) -> HTMLResponse:
    """
    构造仅包含服务端固定内容的退出页面

    :param title: 页面标题
    :param body: 服务端生成的页面正文
    :param redirect_origin: 已校验的客户端回调源地址
    :return: 带有内容安全策略的退出页面响应
    """

    form_sources = "'self'" + (f' {redirect_origin}' if redirect_origin else '')
    content = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(title)}</title><style>{_LOGOUT_STYLE}</style></head>'
        '<body><main><div class="brand">统一认证中心</div>'
        f'<h1>{escape(title)}</h1>{body}</main></body></html>'
    )

    return HTMLResponse(
        content,
        headers={
            **_NO_STORE,
            'Content-Security-Policy': (
                f"default-src 'none'; style-src 'sha256-{_LOGOUT_STYLE_HASH}'; "
                f"form-action {form_sources}; base-uri 'none'; frame-ancestors 'none'"
            ),
            'Referrer-Policy': 'strict-origin',
            'X-Frame-Options': 'DENY',
        },
    )


def _confirmation_response(token: str, redirect_origin: str | None = None) -> HTMLResponse:
    """
    构造绑定一次性凭据的退出确认页面

    :param token: 一次性退出确认凭据
    :param redirect_origin: 已校验的客户端回调源地址
    :return: 退出确认页面响应
    """

    return _logout_page(
        '退出认证中心？',
        (
            '<p>确认后，此次登录以及关联应用的离线访问授权将失效。'
            '你可以取消，继续保持登录。</p>'
            '<form method="post" action="/oauth2/logout/confirm">'
            f'<input type="hidden" name="confirmation" value="{escape(token, quote=True)}">'
            '<button name="decision" value="cancel" type="submit" autofocus>取消，保持登录</button>'
            '<button name="decision" value="confirm" type="submit">确认退出</button>'
            '</form>'
        ),
        redirect_origin=redirect_origin,
    )


def _local_response(_request: Request) -> HTMLResponse:
    """
    构造不回显退出参数的同源完成页

    :param _request: 当前 HTTP 请求
    :return: 同源退出完成页
    """

    return _logout_page('已退出', '<p>此次登录已结束，可以关闭此页面。</p>')


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


@authorization_controller.api_route(
    '/oauth2/logout',
    methods=['GET', 'POST'],
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
        token, nonce = await LogoutConfirmationService.issue(
            redis, parameters, request.cookies.get(OidcConfig.oidc_sso_cookie_name)
        )
        redirect_origin = await LogoutConfirmationService.form_redirect_origin(query_db, parameters)
        response = _confirmation_response(token, redirect_origin)
        response.set_cookie(
            LogoutConfirmationService.COOKIE_NAME,
            nonce,
            max_age=LogoutConfirmationService.TTL_SECONDS,
            path='/',
            secure=True,
            httponly=True,
            samesite='strict',
        )
        return response
    except RateLimitExceeded as exc:
        headers = dict(_NO_STORE)
        headers['Retry-After'] = str(exc.retry_after)
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=429, headers=headers)
    except RateLimitUnavailable:
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
    except Exception:
        return JSONResponse(content={'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)


@authorization_controller.post(
    '/oauth2/logout/confirm',
    summary='确认退出认证中心接口',
    description='用于确认或取消当前浏览器的认证中心退出请求',
    include_in_schema=False,
)
async def confirm_logout(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not OidcConfig.oidc_enabled:
        return _oidc_not_found_response()
    issuer = urlsplit(OidcConfig.oidc_issuer)
    if request.headers.get('origin') != f'{issuer.scheme}://{issuer.netloc}':
        return JSONResponse({'error': 'invalid_request'}, status_code=403, headers=_NO_STORE)
    try:
        form = await read_form(request)
        if set(form) != {'confirmation', 'decision'} or form['decision'] not in {'confirm', 'cancel'}:
            raise ValueError('Invalid confirmation')
        redis = request.app.state.redis
        parameters = await LogoutConfirmationService.consume(
            redis,
            form['confirmation'],
            request.cookies.get(OidcConfig.oidc_sso_cookie_name),
            request.cookies.get(LogoutConfirmationService.COOKIE_NAME),
        )
    except (HTTPException, ValueError, KeyError, TypeError):
        return JSONResponse({'error': 'invalid_request'}, status_code=400, headers=_NO_STORE)
    except Exception:
        return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
    if form['decision'] == 'cancel':
        response = _logout_page('已取消退出', '<p>登录状态保持不变，可以关闭此页面。</p>')
    else:
        try:
            result = await LogoutService.execute_logout(
                query_db,
                redis,
                confirmed=True,
                id_token_hint=parameters.get('id_token_hint'),
                cookie=request.cookies.get(OidcConfig.oidc_sso_cookie_name),
                post_logout_redirect_uri=parameters.get('post_logout_redirect_uri'),
                state=parameters.get('state'),
            )
        except Exception:
            return JSONResponse({'error': 'temporarily_unavailable'}, status_code=503, headers=_NO_STORE)
        response = (
            _local_response(request)
            if result.redirect_uri is None
            else RedirectResponse(_append_state(result.redirect_uri, result.state), status_code=303, headers=_NO_STORE)
        )
        response.delete_cookie(**SsoSessionService.cookie_parameters())
    response.delete_cookie(
        LogoutConfirmationService.COOKIE_NAME, path='/', secure=True, httponly=True, samesite='strict'
    )

    return response
