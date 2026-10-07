import asyncio
import math
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from plugins.core.runtime.connections import (
    CANCEL_TIMEOUT_SECONDS,
    RECHECK_INTERVAL_SECONDS,
    RECHECK_TIMEOUT_SECONDS,
    PluginConnectionManager,
)
from plugins.core.runtime.task_cleanup import cancel_plugin_tasks
from plugins.core.sdk.context import PluginRequestContext
from utils.log_util import logger


class PluginLifespanManager:
    """
    通过 ASGI lifespan 协议驱动一个 worker 内的插件实例。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout: float = 30.0,
        managed: bool = True,
        cancel_timeout: float = CANCEL_TIMEOUT_SECONDS,
    ) -> None:
        """
        初始化当前 worker 的插件生命周期管理器。

        :param app: 插件 ASGI 应用
        :param timeout: 生命周期事件确认的超时时间，单位为秒
        :param managed: 是否由宿主驱动 ASGI 生命周期协议
        :param cancel_timeout: 生命周期任务取消的等待上限秒数
        :return: None
        """
        if any(not math.isfinite(value) or value <= 0 for value in (timeout, cancel_timeout)):
            raise ValueError('生命周期等待时间必须大于零')
        self.app = app
        self.timeout = timeout
        self.cancel_timeout = cancel_timeout
        self.managed = managed
        self.state: dict[str, Any] = {}
        self.started = False
        self._stopping = False
        self._operation_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._receive: asyncio.Queue[Message] = asyncio.Queue()
        self._send: asyncio.Queue[Message] = asyncio.Queue()

    @property
    def has_pending_task(self) -> bool:
        """
        判断上一次生命周期是否仍占用资源，防止重试创建重叠实例。

        :return: 是否存在尚未退出的生命周期任务
        """
        return self._task is not None and not self._task.done()

    @property
    def ready(self) -> bool:
        """
        lifespan 意外退出后不再接受业务请求。

        :return: 插件是否已启动且生命周期任务仍然存活
        """
        return self.started and not self._stopping and (not self.managed or self.has_pending_task)

    async def startup(self) -> None:
        """
        只有确认 startup.complete 后才允许接收业务请求。

        :return: None
        """
        async with self._operation_lock:
            self._stopping = False
            await self._startup()

    async def _startup(self) -> None:
        """
        串行启动新一轮协议，旧任务退出后才允许重试。

        :return: None
        """
        if self.started:
            return
        if self.has_pending_task:
            raise RuntimeError('上一次插件生命周期尚未退出，不能重新启动')
        self.state = {}
        self._receive = asyncio.Queue()
        self._send = asyncio.Queue()
        if not self.managed:
            self.started = True
            return
        scope = {'type': 'lifespan', 'asgi': {'version': '3.0', 'spec_version': '2.0'}, 'state': self.state}
        self._task = asyncio.create_task(self._invoke(scope))
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
        self._stopping = True
        async with self._operation_lock:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """
        串行发送关闭消息，避免并发调用消费同一个协议确认。

        :return: None
        """
        was_started = self.started
        self.started = False
        try:
            if was_started and self.managed:
                await self._exchange('shutdown')
                done, _ = await asyncio.wait({self._task}, timeout=self.timeout)
                if not done:
                    raise TimeoutError('ASGI lifespan.shutdown 确认后未退出')
                self._check_task_result()
        finally:
            await self._cancel_task()

    async def _invoke(self, scope: Scope) -> None:
        """
        在独立协程中等待 ASGI 应用返回的任意 awaitable。

        :param scope: 当前启动轮次的独立生命周期作用域
        :return: None
        """
        await self.app(scope, self._receive.get, self._send.put)

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
                    self._check_task_result()
                    raise RuntimeError(f'ASGI 应用在 lifespan.{event} 确认前退出')
                raise TimeoutError(f'ASGI lifespan.{event} 超时')
            message = response.result()
            if message.get('type') != f'lifespan.{event}.complete':
                raise RuntimeError(f'ASGI lifespan.{event} 失败：{message.get("message", message.get("type"))}')
            if event == 'startup' and self._task.done():
                self._check_task_result()
                raise RuntimeError('ASGI lifespan 在 startup 后提前退出')
        finally:
            response.cancel()
            with suppress(asyncio.CancelledError):
                await response

    def _check_task_result(self) -> None:
        """
        将子应用自行取消作为协议失败，保留宿主调用者自身的取消语义。

        :return: None
        """
        if self._task.cancelled():
            raise RuntimeError('ASGI 生命周期任务自行取消')
        self._task.result()

    async def _cancel_task(self) -> None:
        """
        取消并回收当前 worker 的生命周期任务。

        :return: None
        """
        if self._task is None:
            return
        if await cancel_plugin_tasks({self._task}, timeout=self.cancel_timeout):
            logger.warning('插件生命周期未响应取消；保留任务并拒绝重启，等待任务自行退出')
        else:
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
        *,
        recheck_interval: float = RECHECK_INTERVAL_SECONDS,
        recheck_timeout: float = RECHECK_TIMEOUT_SECONDS,
        cancel_timeout: float = CANCEL_TIMEOUT_SECONDS,
    ) -> None:
        """
        初始化插件请求门禁。

        :param app: 受保护的插件 ASGI 应用
        :param lifespan: 当前插件的生命周期管理器
        :param authorize: 根据 ASGI 请求作用域构建宿主身份上下文的异步授权器
        :param recheck_interval: 已建立长连接的身份复核间隔秒数
        :param recheck_timeout: 每次长连接身份复核的超时秒数
        :param cancel_timeout: 长连接任务取消的等待秒数
        :return: None
        """
        self.app = app
        self.lifespan = lifespan
        self.authorize = authorize
        self.connections = PluginConnectionManager(
            authorize,
            lambda: lifespan.ready,
            recheck_interval=recheck_interval,
            recheck_timeout=recheck_timeout,
            cancel_timeout=cancel_timeout,
        )

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
        if not self.lifespan.ready or self.connections.closing:
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
        await self.connections.run(self.app, scope, child_scope, context, receive, send)

    async def drain(self) -> None:
        """
        在释放插件资源前停止当前 worker 的 SSE 与 WebSocket。

        :return: None
        """
        await self.connections.drain()

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
