import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Depends, HTTPException, Request, params
from jwt.exceptions import PyJWTError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_session import DBSessionDependency
from config.env import OidcConfig
from exceptions.exception import OAuthProtocolException, OidcInteractionException
from module_identity.dao.oidc_key_dao import OidcKeyDao
from module_identity.security.client_auth import ClientAuthenticationError
from module_identity.security.jwt_profile import JwtProfileError, decode_access_token
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.interaction_service import InteractionService
from module_identity.service.runtime_service import OidcRuntimeService
from module_identity.service.token_service import TokenService
from utils.time_util import TimezoneUtil

_MAX_PROTOCOL_FORM_BYTES = 16 * 1024
_INVALID_PERCENT_ESCAPE = re.compile(r'%(?![0-9A-Fa-f]{2})')


@dataclass(frozen=True, slots=True)
class AccessTokenContext:
    """
    已验签且绑定 UserInfo audience 的 Access Token 快照
    """

    token: str
    claims: dict[str, Any]


_JWT_DOT_COUNT = 2
_REMOTE_KEY_HEADERS = frozenset({'jku', 'x5u', 'jwk', 'x5c'})


async def load_access_verification_key(
    token: str,
    query_db: AsyncSession,
    *,
    now: datetime | None = None,
) -> RSAPublicKey:
    """
    按 Access Token header kid 加载发布窗口内的本地公钥

    :param token: 待验证的 JWT；仅用于读取 header kid，不信任其中的公钥材料
    :param query_db: 异步数据库会话
    :param now: 可注入的统一项目当前时间
    :return: 数据库记录对应的 RSA 公钥对象
    :raises JwtProfileError: Header、kid 或本地公钥不可用
    """

    try:
        header = jwt.get_unverified_header(token)
    except (PyJWTError, TypeError, ValueError) as exc:
        raise JwtProfileError('invalid JWT header') from exc
    if _REMOTE_KEY_HEADERS.intersection(header) or header.get('alg') != 'RS256' or header.get('typ') != 'at+jwt':
        raise JwtProfileError('unsupported JWT header')
    kid = header.get('kid')
    if not isinstance(kid, str) or not kid:
        raise JwtProfileError('kid is required')
    current = _utc_datetime(now or TimezoneUtil.utc_now())
    record = await OidcKeyDao.get_verifying(query_db, kid, current)
    if record is None or not isinstance(record.public_jwk, dict):
        raise JwtProfileError('unknown kid')
    try:
        return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(record.public_jwk, separators=(',', ':')))
    except (TypeError, ValueError, KeyError) as exc:
        raise JwtProfileError('public key is invalid') from exc


def _disabled() -> None:
    """
    在 OIDC 关闭时返回本地 404，不执行协议认证
    """

    if not OidcConfig.oidc_enabled:
        raise HTTPException(
            status_code=404,
            detail='Not found',
            headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'},
        )


async def require_oidc_protocol_ready(
    request: Request,
    query_db: AsyncSession = DBSessionDependency(),
) -> None:
    """
    在 OIDC 已启用但签名能力尚未就绪时阻断公共协议端点

    OIDC 关闭时仍由各控制器维持原有本地 404 行为；启用但缺少有效
    active 密钥时统一返回标准 OAuth 503，不影响后台管理接口。

    :param request: 当前 HTTP 请求
    :param query_db: 异步数据库会话
    :return: None
    :raises OAuthProtocolException: OIDC 协议尚未具备签名能力
    """

    if not OidcConfig.oidc_enabled:
        return
    readiness = await OidcRuntimeService.cached_readiness(request.app, query_db)
    if not readiness.ready:
        raise OAuthProtocolException(
            'temporarily_unavailable',
            'Authorization server is not ready',
            503,
        )


def _redis(request: Request) -> Redis:
    """
    读取应用生命周期创建的 Redis 客户端

    :param request: 当前HTTP请求
    :return: 应用生命周期创建的Redis客户端
    """

    value = getattr(request.app.state, 'redis', None)
    if value is None:
        raise HTTPException(status_code=503, detail='Service unavailable')
    return value


async def read_form(request: Request) -> dict[str, str]:
    """
    严格读取 URL encoded 表单并拒绝重复字段

    :param request: 当前 HTTP 请求
    :return: 唯一字段映射
    :raises HTTPException: Content-Type 错误或字段重复
    """

    _disabled()
    content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if content_type != 'application/x-www-form-urlencoded':
        raise HTTPException(status_code=415, detail='Unsupported media type')
    content_length = request.headers.get('content-length')
    declared_length: int | None = None
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=413, detail='Request body too large') from exc
        if declared_length < 0 or declared_length > _MAX_PROTOCOL_FORM_BYTES:
            raise HTTPException(status_code=413, detail='Request body too large')
    chunks: list[bytes] = []
    actual_length = 0
    async for chunk in request.stream():
        actual_length += len(chunk)
        if actual_length > _MAX_PROTOCOL_FORM_BYTES:
            raise HTTPException(status_code=413, detail='Request body too large')
        chunks.append(chunk)
    if declared_length is not None and actual_length != declared_length:
        raise HTTPException(status_code=413, detail='Request body too large')
    try:
        decoded_body = b''.join(chunks).decode('utf-8')
        if _INVALID_PERCENT_ESCAPE.search(decoded_body):
            raise ValueError('invalid percent escape')
        form_items = parse_qsl(
            decoded_body,
            keep_blank_values=True,
            strict_parsing=True,
            encoding='utf-8',
            errors='strict',
            max_num_fields=64,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail='Invalid form') from exc
    result: dict[str, str] = {}
    for key, value in form_items:
        if key in result:
            raise HTTPException(status_code=400, detail='Invalid form')
        result[key] = value
    return result


async def get_oidc_client(
    request: Request,
    query_db: AsyncSession = DBSessionDependency(),
) -> OAuthClientPrincipal:
    """
    验证 Basic 或 Public Client 表单认证

    :param request: 当前 HTTP 请求
    :param query_db: 异步数据库会话
    :return: 已完成认证的 Client Principal
    """

    form = await read_form(request)
    authorization = request.headers.get('authorization')
    try:
        _, principal = await TokenService.authenticate_client(
            query_db,
            authorization=authorization,
            client_id=form.get('client_id'),
            client_secret=form.get('client_secret'),
        )
    except (ClientAuthenticationError, ValueError, OAuthProtocolException):
        raise HTTPException(
            status_code=401,
            detail='Client authentication failed',
            headers={'WWW-Authenticate': 'Basic realm="oauth2/token"'},
        ) from None
    return principal


async def _load_access_context(request: Request, query_db: AsyncSession) -> AccessTokenContext:
    """
    按 JWT header kid 查询数据库公钥并验证严格 Access Token Profile

    :param request: 当前HTTP请求
    :param query_db: orm对象
    :return: 已校验的访问令牌及声明上下文
    """

    _disabled()
    authorization = request.headers.get('authorization', '')
    if not authorization.startswith('Bearer ') or ',' in authorization:
        raise _invalid_token()
    token = authorization[7:].strip()
    if not token or token.count('.') != _JWT_DOT_COUNT:
        raise _invalid_token()
    try:
        key = await load_access_verification_key(token, query_db)
        issuer = OidcConfig.oidc_issuer.rstrip('/')
        claims = decode_access_token(
            token,
            verification_key=key,
            issuer=issuer,
            audience=f'{issuer}/oauth2/userinfo',
            clock_skew=OidcConfig.oidc_allowed_clock_skew_seconds,
        )
        scope = claims.get('scope', '').split()
        if (
            'openid' not in scope
            or not isinstance(claims.get('sid'), str)
            or claims.get('sub', '').startswith('client:')
        ):
            raise JwtProfileError('token is not a user access token')
        if isinstance(claims.get('ver'), bool) or not isinstance(claims.get('ver'), int) or claims['ver'] < 1:
            raise JwtProfileError('auth version is invalid')
        return AccessTokenContext(token, claims)
    except (JwtProfileError, PyJWTError, TypeError, ValueError, KeyError):
        raise _invalid_token() from None


async def get_oidc_access_token(
    request: Request,
    query_db: AsyncSession = DBSessionDependency(),
) -> AccessTokenContext:
    """
    验证 UserInfo 使用的 Bearer Access Token

    :param request: 当前HTTP请求
    :param query_db: orm对象
    :return: UserInfo使用的访问令牌上下文
    """

    return await _load_access_context(request, query_db)


async def get_interaction_csrf(
    request: Request,
    interaction_id: str,
) -> dict[str, Any]:
    """
    验证 Interaction CSRF Header，并返回内部状态记录

    :param request: 当前 HTTP 请求
    :param interaction_id: 路径中的 Interaction 标识
    :return: 已验证的内部 Interaction 记录
    """

    _disabled()
    redis = _redis(request)
    csrf_token = request.headers.get('x-csrf-token')
    if not csrf_token or ',' in csrf_token:
        raise HTTPException(status_code=403, detail='CSRF validation failed')
    try:
        record = await InteractionService.get_record(redis, interaction_id)
    except (OidcInteractionException, RedisError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail='Interaction not found') from None
    if not InteractionService.verify_csrf(record, csrf_token, pepper=OidcConfig.oidc_token_hash_pepper):
        raise HTTPException(status_code=403, detail='CSRF validation failed')
    return record


def _invalid_token() -> HTTPException:
    """
    构造不泄露验证细节的 Bearer 401
    """

    return HTTPException(
        status_code=401, detail='Invalid access token', headers={'WWW-Authenticate': 'Bearer error="invalid_token"'}
    )


def OidcClientDependency() -> params.Depends:  # noqa: N802
    """
    返回 Client Authentication 依赖
    """

    return Depends(get_oidc_client)


def OidcAccessTokenDependency() -> params.Depends:  # noqa: N802
    """
    返回严格 Access Token 依赖
    """

    return Depends(get_oidc_access_token)


def InteractionCsrfDependency() -> params.Depends:  # noqa: N802
    """
    返回 Interaction CSRF 依赖
    """

    return Depends(get_interaction_csrf)


def _utc_datetime(value: datetime) -> datetime:
    """
    规范化数据库时间为项目使用的带时区的 UTC 时间

    :param value: 待转换的数据库时间
    :return: 带UTC时区的时间
    """

    return TimezoneUtil.to_utc(value)
