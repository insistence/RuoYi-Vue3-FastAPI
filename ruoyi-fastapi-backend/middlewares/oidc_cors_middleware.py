from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config.env import OidcConfig
from module_identity.service.runtime_service import OidcRuntimeService


class OidcCorsMiddleware:
    """
    为 OIDC 协议和认证交互接口提供独立的 CORS 边界。
    """

    _OIDC_PREFIXES = ('/oauth2/', '/.well-known/')
    _INTERACTION_PREFIX = '/auth/interaction/'
    _NO_CORS_PATHS = ('/oauth2/authorize',)
    _PUBLIC_METADATA_PATHS = (
        '/.well-known/openid-configuration',
        '/.well-known/oauth-authorization-server',
        '/oauth2/jwks',
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @classmethod
    def _is_oidc_path(cls, path: str) -> bool:
        """
        判断请求路径是否属于 OIDC 协议端点。

        :param path: 请求路径
        :return: 是否为 OIDC 协议路径
        """
        normalized = path.rstrip('/') or '/'
        return normalized.startswith(cls._OIDC_PREFIXES)

    @classmethod
    def _is_interaction_path(cls, path: str) -> bool:
        """
        判断请求路径是否属于认证交互接口。

        :param path: 请求路径
        :return: 是否为认证交互路径
        """
        normalized = path.rstrip('/') or '/'
        return normalized.startswith(cls._INTERACTION_PREFIX) or normalized == '/oauth2/logout/confirm'

    @staticmethod
    def _issuer_origin() -> str | None:
        """
        从 OIDC issuer 配置中提取无路径的同源 Origin。

        :return: 合法的 HTTP(S) Origin，配置无效时返回 ``None``
        """
        try:
            parsed = urlsplit(str(OidcConfig.oidc_issuer))
            if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.username or parsed.password:
                return None
            return f'{parsed.scheme}://{parsed.netloc}'
        except (AttributeError, TypeError, ValueError):
            return None

    @classmethod
    def _is_authorize_path(cls, path: str) -> bool:
        """
        判断请求路径是否为禁止跨域的授权端点。

        :param path: 请求路径
        :return: 是否为授权端点路径
        """
        normalized = path.rstrip('/') or '/'
        return normalized in cls._NO_CORS_PATHS

    @classmethod
    def _is_public_metadata_path(cls, path: str) -> bool:
        """
        判断请求路径是否为公开的 OIDC 元数据端点。

        :param path: 请求路径
        :return: 是否为公开元数据路径
        """
        normalized = path.rstrip('/') or '/'
        return normalized in cls._PUBLIC_METADATA_PATHS

    @classmethod
    def _allowed_origin(cls, origin: str | None, scope: Scope | None = None) -> bool:
        """
        校验 Origin 是否存在于静态或运行时注册的跨域白名单中。

        :param origin: 请求携带的 Origin
        :param scope: 当前 ASGI 请求作用域，用于读取运行时注册白名单
        :return: Origin 是否被允许
        """
        if not origin:
            return False
        configured = set(OidcConfig.cors_origin_list)
        current_app = scope.get('app') if scope else None
        state = getattr(current_app, 'state', None)
        registered = getattr(state, 'oidc_registered_cors_origins', ())
        if isinstance(registered, (str, bytes)):
            return False
        try:
            configured.update(item for item in registered if isinstance(item, str))
        except TypeError:
            return False
        return origin in configured

    @staticmethod
    def _without_cors(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
        """
        移除响应中的 CORS 头并清理 ``Vary: Origin`` 标记。

        :param headers: ASGI 响应头列表
        :return: 移除 CORS 相关头后的响应头列表
        """
        cleaned: list[tuple[bytes, bytes]] = []
        for name, value in headers:
            lower_name = name.lower()
            if lower_name.startswith(b'access-control-'):
                continue
            if lower_name != b'vary':
                cleaned.append((name, value))
                continue
            vary_values = [item.strip() for item in value.decode('latin-1').split(',')]
            vary_values = [item for item in vary_values if item and item.lower() != 'origin']
            if vary_values:
                cleaned.append((name, ', '.join(vary_values).encode('latin-1')))
        return cleaned

    @classmethod
    def _with_allowed_cors(cls, headers: list[tuple[bytes, bytes]], origin: str) -> list[tuple[bytes, bytes]]:
        """
        为响应追加指定 Origin 的 CORS 头。

        :param headers: 原始 ASGI 响应头列表
        :param origin: 已校验通过的请求 Origin
        :return: 清理旧 CORS 头并追加新 CORS 头后的列表
        """
        clean = cls._without_cors(headers)
        clean.extend(
            [
                (b'access-control-allow-origin', origin.encode('utf-8')),
                (b'access-control-allow-methods', b'GET, POST, OPTIONS'),
                (b'access-control-allow-headers', b'Authorization, Content-Type, X-Requested-With'),
                (b'access-control-expose-headers', b'WWW-Authenticate'),
                (b'vary', b'Origin'),
            ]
        )
        return clean

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        按 OIDC 端点类型校验 Origin 并处理 CORS 响应。

        :param scope: 当前 ASGI 请求作用域
        :param receive: 接收 ASGI 消息的可调用对象
        :param send: 发送 ASGI 消息的可调用对象
        :return: None
        """
        # 注册层已经按 OIDC_ENABLED 控制是否挂载；这里保留运行时保护，
        # 避免测试或动态配置场景下开关关闭后仍处理协议请求。
        if not OidcConfig.oidc_enabled:
            await self.app(scope, receive, send)
            return
        if scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return

        path = str(scope.get('path', ''))
        oidc_path = self._is_oidc_path(path)
        interaction_path = self._is_interaction_path(path)
        if not oidc_path and not interaction_path:
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get('origin')
        authorize = oidc_path and self._is_authorize_path(path)
        public_metadata = oidc_path and self._is_public_metadata_path(path)
        logout_navigation = path.rstrip('/') == '/oauth2/logout' and scope.get('method') in {'GET', 'POST'}
        if (
            origin
            and oidc_path
            and not interaction_path
            and not authorize
            and not public_metadata
            and not logout_navigation
        ):
            await OidcRuntimeService.ensure_cors_snapshot(scope['app'])
        if interaction_path:
            allowed = not origin or origin == self._issuer_origin()
        else:
            allowed = (
                not authorize and not logout_navigation and (public_metadata or self._allowed_origin(origin, scope))
            )

        if authorize and origin:
            response = PlainTextResponse('Authorization Endpoint 不支持 CORS', status_code=403)
            await response(scope, receive, send)
            return
        if interaction_path and origin and not allowed:
            response = PlainTextResponse('认证交互接口仅允许认证中心同源 Origin', status_code=403)
            await response(scope, receive, send)
            return
        if oidc_path and origin and not public_metadata and not logout_navigation and not allowed:
            response = PlainTextResponse('Origin 不被认证中心允许', status_code=403)
            await response(scope, receive, send)
            return

        if str(scope.get('method', '')).upper() == 'OPTIONS' and (oidc_path or interaction_path):
            if not allowed or not origin:
                response = PlainTextResponse('Origin 不被认证中心允许', status_code=403)
                await response(scope, receive, send)
                return
            response = PlainTextResponse('', status_code=200)
            for name, value in self._with_allowed_cors([], origin):
                response.headers[name.decode('latin-1')] = value.decode('latin-1')
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            """
            在下游响应开始消息中应用 OIDC CORS 策略。

            :param message: 下游 ASGI 消息
            :return: None
            """
            if message.get('type') != 'http.response.start':
                await send(message)
                return
            headers = list(message.get('headers', []))
            if authorize or not allowed:
                headers = self._without_cors(headers)
            elif origin:
                headers = self._with_allowed_cors(headers, origin)
            await send({**message, 'headers': headers})

        await self.app(scope, receive, send_wrapper)


def add_oidc_cors_middleware(app: FastAPI) -> None:
    """
    添加 OIDC 专用 CORS 中间件。

    :param app: FastAPI 对象
    """
    app.add_middleware(OidcCorsMiddleware)
