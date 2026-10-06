import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from plugins.core.sdk.context import PluginRequestContext


class PluginLifespanManager:
    """
    通过 ASGI lifespan 协议驱动一个 worker 内的插件实例。
    """

    def __init__(self, app: ASGIApp, *, timeout: float = 30.0, managed: bool = True) -> None:
        """
        初始化当前 worker 的插件生命周期管理器。

        :param app: 插件 ASGI 应用
        :param timeout: 生命周期事件确认的超时时间，单位为秒
        :param managed: 是否由宿主驱动 ASGI 生命周期协议
        :return: None
        """
        self.app = app
        self.timeout = timeout
        self.managed = managed
        self.state: dict[str, Any] = {}
        self.started = False
        self._task: asyncio.Task[None] | None = None
        self._receive: asyncio.Queue[Message] = asyncio.Queue()
        self._send: asyncio.Queue[Message] = asyncio.Queue()

    @property
    def ready(self) -> bool:
        """
        lifespan 意外退出后不再接受业务请求。

        :return: 插件是否已启动且生命周期任务仍然存活
        """
        return self.started and (not self.managed or (self._task is not None and not self._task.done()))

    async def startup(self) -> None:
        """
        只有确认 startup.complete 后才允许接收业务请求。

        :return: None
        """
        if self.started:
            return
        if not self.managed:
            self.started = True
            return
        scope = {'type': 'lifespan', 'asgi': {'version': '3.0', 'spec_version': '2.0'}, 'state': self.state}
        self._task = asyncio.create_task(self.app(scope, self._receive.get, self._send.put))
        try:
            await self._exchange('startup')
            self.started = True
        except BaseException:
            await self._cancel_task()
            raise

    async def shutdown(self) -> None:
        """
        即使协议失败或超时，也回收本 worker 创建的 lifespan task。

        :return: None
        """
        try:
            if self.started and self.managed:
                await self._exchange('shutdown')
                await asyncio.wait_for(asyncio.shield(self._task), timeout=self.timeout)
        finally:
            self.started = False
            await self._cancel_task()

    async def _exchange(self, event: str) -> None:
        """
        发送生命周期事件并等待子应用确认。

        :param event: 生命周期事件名称，支持 startup 和 shutdown
        :return: None
        """
        await self._receive.put({'type': f'lifespan.{event}'})
        response = asyncio.create_task(self._send.get())
        try:
            done, _ = await asyncio.wait(
                (response, self._task), timeout=self.timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if response not in done:
                if self._task in done:
                    self._task.result()
                    raise RuntimeError(f'ASGI 应用在 lifespan.{event} 确认前退出')
                raise TimeoutError(f'ASGI lifespan.{event} 超时')
            message = response.result()
            if message.get('type') != f'lifespan.{event}.complete':
                raise RuntimeError(f'ASGI lifespan.{event} 失败：{message.get("message", message.get("type"))}')
            if event == 'startup' and self._task.done():
                self._task.result()
                raise RuntimeError('ASGI lifespan 在 startup 后提前退出')
        finally:
            response.cancel()
            with suppress(asyncio.CancelledError):
                await response

    async def _cancel_task(self) -> None:
        """
        取消并回收当前 worker 的生命周期任务。

        :return: None
        """
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None


class PluginGatewayASGI:
    """
    HTTP、静态资源和 WebSocket 共用的宿主门禁。

    接受宿主 Bearer 或限定 bundle 的插件会话，由宿主授权器校验。
    静态资源与业务接口都必须经过同一身份门禁。
    """

    def __init__(
        self,
        app: ASGIApp,
        lifespan: PluginLifespanManager,
        authorize: Callable[[Scope], Awaitable[PluginRequestContext]],
    ) -> None:
        """
        初始化插件请求门禁。

        :param app: 受保护的插件 ASGI 应用
        :param lifespan: 当前插件的生命周期管理器
        :param authorize: 根据 ASGI 请求作用域构建宿主身份上下文的异步授权器
        :return: None
        """
        self.app = app
        self.lifespan = lifespan
        self.authorize = authorize

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        校验插件就绪状态及访问权限，并向子应用注入请求上下文。

        :param scope: ASGI 请求作用域
        :param receive: ASGI 消息接收函数
        :param send: ASGI 消息发送函数
        :return: None
        """
        if scope['type'] not in {'http', 'websocket'}:
            raise RuntimeError('插件 lifespan 必须由宿主管理器驱动')
        if not self.lifespan.ready:
            await self._reject(scope, receive, send, 503, '插件尚未就绪')
            return
        try:
            context = await self.authorize(scope)
        except PermissionError:
            await self._reject(scope, receive, send, 403, '插件未启用或没有访问权限')
            return
        except LookupError:
            await self._reject(scope, receive, send, 401, '请先登录')
            return
        child_scope = dict(scope)
        child_scope['state'] = {**scope.get('state', {}), **self.lifespan.state, 'plugin_context': context}
        await self.app(child_scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, status: int, message: str) -> None:
        """
        按请求协议返回拒绝响应或关闭 WebSocket 连接。

        :param scope: ASGI 请求作用域
        :param receive: ASGI 消息接收函数
        :param send: ASGI 消息发送函数
        :param status: HTTP 拒绝响应状态码
        :param message: 拒绝原因
        :return: None
        """
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008, 'reason': message})
        else:
            await JSONResponse({'code': status, 'msg': message}, status_code=status)(scope, receive, send)
