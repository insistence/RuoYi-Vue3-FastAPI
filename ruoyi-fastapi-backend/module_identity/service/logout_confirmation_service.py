import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import urlsplit

import jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.service.session_service import LogoutService
from utils.time_util import TimezoneUtil


class LogoutConfirmationService:
    """
    认证中心退出确认服务层
    """

    COOKIE_NAME = '__Host-oidc_logout_confirmation'
    TTL_SECONDS = 300
    _TOKEN_LENGTH = 43
    _CONSUME = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""

    @classmethod
    def _binding(cls, sso_cookie: str | None, browser_nonce: str) -> str:
        """
        生成退出确认凭据的浏览器绑定摘要

        :param sso_cookie: 首次退出请求携带的SSO Cookie
        :param browser_nonce: 绑定浏览器的一次性随机数
        :return: 浏览器绑定的HMAC摘要
        """

        pepper = OidcConfig.oidc_token_hash_pepper
        key = pepper.encode() if isinstance(pepper, str) else pepper

        return hmac.new(key, ((sso_cookie or '') + '\\0' + browser_nonce).encode(), hashlib.sha256).hexdigest()

    @classmethod
    async def issue(cls, redis: Redis, parameters: dict[str, str], sso_cookie: str | None) -> tuple[str, str]:
        """
        签发短期有效且仅可使用一次的退出确认凭据

        :param redis: Redis连接对象
        :param parameters: 已校验的退出请求参数
        :param sso_cookie: 首次退出请求携带的SSO Cookie
        :return: 退出确认凭据和浏览器随机数
        :raises RuntimeError: 确认记录保存失败
        """

        token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        record = json.dumps(
            {'parameters': parameters, 'binding': cls._binding(sso_cookie, nonce), 'sso_bound': sso_cookie is not None},
            separators=(',', ':'),
        )
        stored = await redis.set(
            'oidc:logout:confirmation:' + hashlib.sha256(token.encode()).hexdigest(),
            record,
            ex=cls.TTL_SECONDS,
            nx=True,
        )
        if not stored:
            raise RuntimeError('Logout confirmation unavailable')
        return token, nonce

    @classmethod
    async def consume(
        cls, redis: Redis, token: str, sso_cookie: str | None, browser_nonce: str | None
    ) -> dict[str, str]:
        """
        消费一次性退出确认凭据并校验浏览器归属

        :param redis: Redis连接对象
        :param token: 用户提交的退出确认凭据
        :param sso_cookie: 确认请求携带的SSO Cookie
        :param browser_nonce: 确认请求携带的浏览器随机数
        :return: 原始退出请求参数
        :raises ValueError: 凭据无效、已使用、已过期或浏览器绑定不匹配
        """

        if not isinstance(token, str) or len(token) != cls._TOKEN_LENGTH or not browser_nonce:
            raise ValueError('Invalid logout confirmation')
        raw = await redis.eval(
            cls._CONSUME, 1, 'oidc:logout:confirmation:' + hashlib.sha256(token.encode()).hexdigest()
        )
        if raw is None:
            raise ValueError('Expired or already used logout confirmation')
        record = json.loads(raw)
        # 跨站首次POST可能不携带Lax会话Cookie，随机数仍绑定当前浏览器
        # 同源确认时仅校验并撤销当前浏览器的会话
        bound_sso = sso_cookie if record.get('sso_bound', True) else None
        if not hmac.compare_digest(record['binding'], cls._binding(bound_sso, browser_nonce)):
            raise ValueError('Logout confirmation browser changed')
        return record['parameters']

    @classmethod
    async def form_redirect_origin(cls, db: AsyncSession, parameters: dict[str, str]) -> str | None:
        """
        获取退出确认页内容安全策略允许的客户端回调源

        校验ID Token提示，并精确匹配已启用的注册回调地址。

        :param db: orm对象
        :param parameters: 已校验的退出请求参数
        :return: 允许的回调源地址，校验失败时返回None
        """

        hint = parameters.get('id_token_hint')
        uri = parameters.get('post_logout_redirect_uri')
        if not hint or not LogoutService._safe_post_logout_uri(uri):
            return None
        parsed = urlsplit(uri)
        hostname = parsed.hostname.encode('idna').decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9.:-]+', hostname):
            return None
        try:
            _claims, client = await LogoutService._validate_id_token_hint(db, hint, TimezoneUtil.utc_now())
        except (ValueError, jwt.PyJWTError):
            return None
        registered = await OAuthClientDao.find_exact_uri(db, client.client_pk, 'post_logout', uri)
        if registered is None or registered.status != '0':
            return None
        host = f'[{hostname}]' if ':' in hostname else hostname
        port = f':{parsed.port}' if parsed.port is not None else ''

        return f'{parsed.scheme}://{host}{port}'
