from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

_MAX_BACKCHANNEL_RESPONSE_BYTES = 64 * 1024
_HTTP_CLIENT_ERROR_MIN = 400
_HTTP_SERVER_ERROR_MIN = 500
_HTTP_REQUEST_TIMEOUT = 408
_HTTP_TOO_MANY_REQUESTS = 429


class PermanentBackchannelError(ValueError):
    """
    表示 Back-Channel 请求永久失败且不应继续重试
    """

    def __init__(self, failure_code: str, message: str | None = None) -> None:
        """分别保存稳定的审计错误码和中文异常说明。"""
        self.failure_code = failure_code
        self.message = message or '后端退出通知永久失败'
        super().__init__(self.message)


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """
    保持注册域名的 TLS 和 SNI，同时将 TCP 连接固定到已验证 IP
    """

    def __init__(self, hostname: str, addresses: set[str]) -> None:
        """
        初始化固定目标地址的网络后端

        :param hostname: 已验证的注册主机名
        :param addresses: 已验证的公网 IP 集合
        :return: None
        """

        self._hostname = hostname
        self._addresses = addresses
        self._backend = AutoBackend()

    async def connect_tcp(self, host: str, port: int, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        """
        连接已验证主机对应的固定公网地址

        :param host: HTTP Core 请求的原始主机名
        :param port: 目标 TCP 端口
        :param kwargs: HTTP Core 连接参数
        :return: 已建立的异步网络流
        :raises OSError: 主机未验证、地址为空或全部地址连接失败
        """

        if host != self._hostname or not self._addresses:
            raise OSError('网络目标未通过安全校验')
        # 逐个尝试已验证地址，网络库仍以原始 origin 处理 TLS SNI 和 Host
        last_error: OSError | None = None
        for address in sorted(self._addresses):
            try:
                return await self._backend.connect_tcp(address, port, **kwargs)
            except OSError as exc:  # noqa: PERF203
                last_error = exc
        raise last_error or OSError('没有通过安全校验的网络目标')


class PinnedHttpxTransport(httpx.AsyncBaseTransport):
    """
    单次请求使用的 IP 固定 HTTPX Transport
    """

    def __init__(self, hostname: str, addresses: set[str]) -> None:
        """
        初始化使用固定网络后端的连接池

        :param hostname: 已验证的注册主机名
        :param addresses: 已验证的公网 IP 集合
        :return: None
        """

        self._pool = httpcore.AsyncConnectionPool(network_backend=_PinnedNetworkBackend(hostname, addresses))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """
        通过固定地址连接池发送异步 HTTP 请求

        :param request: HTTPX 异步请求
        :return: 限制响应体大小的 HTTPX 响应
        """

        request_stream = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = await self._pool.handle_async_request(request_stream)

        class ResponseStream(httpx.AsyncByteStream):
            """
            限制 Back-Channel 响应体大小的异步字节流
            """

            def __init__(self) -> None:
                """
                初始化已接收字节计数器

                :return: None
                """

                self._received = 0

            async def __aiter__(self) -> Any:
                """
                逐块读取响应并执行大小限制

                :return: HTTP 响应字节块异步迭代器
                :raises OSError: 响应体超过大小限制
                """

                async for chunk in response.stream:
                    self._received += len(chunk)
                    if self._received > _MAX_BACKCHANNEL_RESPONSE_BYTES:
                        await response.aclose()
                        raise OSError('后端退出通知响应大小超过限制')
                    yield chunk

            async def aclose(self) -> None:
                """
                关闭底层 HTTP Core 响应流

                :return: None
                """

                await response.aclose()

        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=ResponseStream(),
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        """
        关闭固定地址连接池

        :return: None
        """

        await self._pool.aclose()


BackchannelNotifier = Callable[[str, str], Awaitable[None]]


async def send_backchannel_once(
    uri: str,
    token: str,
    notifier: BackchannelNotifier | None,
    timeout_seconds: float,
    *,
    addresses: set[str] | None = None,
) -> None:
    """
    发送单次 Back-Channel 请求并分类永久失败

    :param uri: 已验证的 Back-Channel URI
    :param token: 待发送的 Logout Token
    :param notifier: 可选的外部通知器
    :param timeout_seconds: 请求超时秒数
    :param addresses: 已验证的公网 IP 集合
    :return: None
    :raises PermanentBackchannelError: 收到不可重试的 HTTP 客户端错误
    :raises OSError: 未提供安全地址或网络传输失败
    """

    if notifier is not None:
        try:
            await notifier(uri, token)
        except httpx.HTTPStatusError as exc:
            _raise_permanent_http_error(exc)
        return

    parsed = urlsplit(uri)
    hostname = parsed.hostname or ''
    if not addresses:
        raise OSError('后端退出通知目标不是公网地址')
    transport = PinnedHttpxTransport(hostname, addresses)
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=False,
        transport=transport,
    ) as client:
        response = await client.post(uri, data={'logout_token': token})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_permanent_http_error(exc)


def _raise_permanent_http_error(exc: httpx.HTTPStatusError) -> None:
    """
    将不可重试的 HTTP 客户端错误转换为永久失败

    :param exc: HTTPX 状态码异常
    :return: None
    :raises PermanentBackchannelError: 状态码属于不可重试的客户端错误
    :raises httpx.HTTPStatusError: 状态码仍允许调用方重试
    """

    status = exc.response.status_code
    if _HTTP_CLIENT_ERROR_MIN <= status < _HTTP_SERVER_ERROR_MIN and status not in {
        _HTTP_REQUEST_TIMEOUT,
        _HTTP_TOO_MANY_REQUESTS,
    }:
        raise PermanentBackchannelError(f'http_{status}', f'后端退出通知被接收方拒绝（HTTP {status}）') from None
    raise exc
