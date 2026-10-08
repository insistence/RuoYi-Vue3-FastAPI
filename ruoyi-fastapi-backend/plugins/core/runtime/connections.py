import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal

from starlette import status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from plugins.core.sdk.context import PluginRequestContext
from utils.log_util import logger

RECHECK_INTERVAL_SECONDS = 15.0
RECHECK_TIMEOUT_SECONDS = 5.0
CANCEL_TIMEOUT_SECONDS = 5.0
STREAM_CLOSED_EVENT = 'ruoyi.plugin.closed'
CONNECTION_OUTCOME_KEY = 'ruoyi.plugin.connection_outcome'
AUTH_RECHECK_KEY = 'ruoyi.plugin.auth_recheck'


@dataclass(frozen=True)
class ConnectionClosure:
    """
    可公开的连接关闭原因，不携带凭证或底层异常详情。

    :param code: 对应的 HTTP 状态
    :param reason: 稳定的机器可读原因
    :param message: WebSocket 关闭提示
    :param outcome: 运行观测的终态分类
    :param websocket_code: WebSocket 关闭码
    """

    code: int
    reason: str
    message: str
    outcome: Literal['rejected', 'failed', 'cancelled']
    websocket_code: int


LOGIN_EXPIRED = ConnectionClosure(401, 'session_expired', '登录已失效', 'rejected', status.WS_1008_POLICY_VIOLATION)
ACCESS_REVOKED = ConnectionClosure(403, 'access_revoked', '访问权限已变更', 'rejected', status.WS_1008_POLICY_VIOLATION)
CHECK_UNAVAILABLE = ConnectionClosure(
    503, 'authorization_unavailable', '暂时无法复核访问权限', 'failed', status.WS_1011_INTERNAL_ERROR
)
CHECK_TIMED_OUT = ConnectionClosure(
    503, 'authorization_timeout', '访问权限复核超时', 'failed', status.WS_1011_INTERNAL_ERROR
)
PLUGIN_SHUTDOWN = ConnectionClosure(503, 'plugin_shutdown', '插件正在关闭', 'cancelled', status.WS_1012_SERVICE_RESTART)
CLIENT_DISCONNECTED = ConnectionClosure(
    499, 'client_disconnected', '客户端已断开', 'cancelled', status.WS_1001_GOING_AWAY
)


def _user_id(context: PluginRequestContext) -> Any:
    """
    读取宿主身份中的用户标识，兼容不含用户的隔离测试上下文。

    :param context: 宿主签发的请求上下文
    :return: 用户标识；无身份时为 None
    """
    return getattr(getattr(context.user, 'user', None), 'user_id', None)


class PluginConnectionManager:
    """
    复核当前 worker 的 SSE 与 WebSocket，关闭前先取消业务任务。
    """

    def __init__(
        self,
        authorize: Callable[[Scope], Awaitable[PluginRequestContext]],
        ready: Callable[[], bool],
        *,
        recheck_interval: float = RECHECK_INTERVAL_SECONDS,
        recheck_timeout: float = RECHECK_TIMEOUT_SECONDS,
        cancel_timeout: float = CANCEL_TIMEOUT_SECONDS,
    ) -> None:
        """
        初始化连接管理器，普通 HTTP 响应不会启动复核任务。

        :param authorize: 使用独立数据库会话重新鉴权的授权器
        :param ready: 当前插件是否仍然就绪
        :param recheck_interval: 相邻复核的等待秒数
        :param recheck_timeout: 单次复核的超时秒数
        :param cancel_timeout: 业务取消及关闭消息发送分别允许的等待秒数
        :return: None
        """
        if any(not math.isfinite(value) or value <= 0 for value in (recheck_interval, recheck_timeout, cancel_timeout)):
            raise ValueError('连接复核和关闭时间必须大于零')
        self.authorize = authorize
        self.ready = ready
        self.recheck_interval = recheck_interval
        self.recheck_timeout = recheck_timeout
        self.cancel_timeout = cancel_timeout
        self.closing = False
        self.connections: set[_PluginConnection] = set()
        self._unfinished: set[asyncio.Task[Any]] = set()

    def connection_counts(self) -> dict[str, int]:
        """
        读取当前已打开的协议连接数量，不公开作用域、身份或请求头。

        :return: SSE 与 WebSocket 的当前连接数量
        """
        return {
            'sse': sum(connection.scope['type'] == 'http' for connection in self.connections),
            'websocket': sum(connection.scope['type'] == 'websocket' for connection in self.connections),
        }

    def pending_tasks(self) -> frozenset[asyncio.Task[Any]]:
        """
        为宿主诊断提供尚未结束的取消超时任务快照，不改变任务或清理集合。

        :return: 当前仍被连接回收器保留的任务集合，只供宿主统计使用
        """
        return frozenset(task for task in self._unfinished if not task.done())

    async def run(
        self,
        app: ASGIApp,
        scope: Scope,
        child_scope: Scope,
        context: PluginRequestContext,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        执行业务应用，在开始事件流或接受 WebSocket 后登记连接。

        :param app: 插件 ASGI 应用
        :param scope: 宿主请求作用域，接收可观测的关闭原因
        :param child_scope: 注入请求上下文的子应用作用域
        :param context: 首次鉴权所得的权限快照
        :param receive: 原始 ASGI 消息接收函数
        :param send: 原始 ASGI 消息发送函数
        :return: None
        """
        connection = _PluginConnection(self, scope, context, receive, send)
        await connection.run(app, child_scope)

    async def drain(self) -> None:
        """
        拒绝新连接并并发关闭当前流，在有限时间内等待请求退出。

        :return: None
        """
        self.closing = True
        connections = tuple(self.connections)
        for connection in connections:
            connection.stop(PLUGIN_SHUTDOWN)
        owners = {connection.owner for connection in connections if connection.owner is not asyncio.current_task()}
        if owners:
            _, pending = await asyncio.wait(owners, timeout=self.cancel_timeout * 2 + 1)
            if pending:
                logger.warning('插件连接关闭等待超时：{} 个请求尚未退出', len(pending))

    async def cancel_task(self, task: asyncio.Task[Any]) -> None:
        """
        有界等待协作式取消，保留未退出任务并回收它们最终的异常。

        :param task: 需要停止的异步任务
        :return: None
        """
        if not task.done():
            task.cancel()
            await asyncio.wait({task}, timeout=self.cancel_timeout)
        if task.done():
            with suppress(asyncio.CancelledError, Exception):
                task.result()
        else:
            self._unfinished.add(task)
            task.add_done_callback(self._finish_task)
            logger.warning('插件连接任务未响应取消；输出已隔离，等待任务自行退出')

    def _finish_task(self, task: asyncio.Task[Any]) -> None:
        """
        释放迟到任务并读取异常，避免未处理任务异常告警。

        :param task: 已完成的迟到任务
        :return: None
        """
        self._unfinished.discard(task)
        with suppress(asyncio.CancelledError, Exception):
            task.result()


class _PluginConnection:
    """
    单条请求的收发状态及权限复核任务。
    """

    def __init__(
        self,
        manager: PluginConnectionManager,
        scope: Scope,
        context: PluginRequestContext,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        保留首次授权的请求信息，避免子应用修改路由作用域影响复核。

        :param manager: 当前插件的连接管理器
        :param scope: 宿主请求作用域
        :param context: 初始权限快照
        :param receive: 原始接收函数
        :param send: 原始发送函数
        :return: None
        """
        self.manager = manager
        self.scope = scope
        self.auth_scope = {**scope, 'headers': list(scope.get('headers', [])), AUTH_RECHECK_KEY: True}
        self.context = context
        self.receive = receive
        self.send = send
        self.owner = asyncio.current_task()
        self.closed: asyncio.Future[ConnectionClosure] = asyncio.get_running_loop().create_future()
        self.checker: asyncio.Task[None] | None = None
        self.started = False
        self.completed = False
        self.disconnected = False
        self.line_ended = True

    def stop(self, reason: ConnectionClosure) -> None:
        """
        记录首次关闭原因并阻止后续业务消息进入连接。

        :param reason: 已脱敏的关闭原因
        :return: None
        """
        if not self.closed.done() and not self.completed:
            self.closed.set_result(reason)

    def _open(self) -> None:
        """
        仅为事件流及已接受的 WebSocket 启动周期复核。

        :return: None
        """
        if self.manager.closing:
            self.stop(PLUGIN_SHUTDOWN)
            raise asyncio.CancelledError
        if self.checker is not None:
            return
        self.manager.connections.add(self)
        self.checker = asyncio.create_task(self._check())

    async def _check(self) -> None:
        """
        定期重新鉴权；权限减配、用户变化或无法确认身份时关闭连接。

        :return: None
        """
        try:
            while True:
                await asyncio.sleep(self.manager.recheck_interval)
                if not self.manager.ready():
                    self.stop(CHECK_UNAVAILABLE)
                    return
                current = await asyncio.wait_for(
                    self.manager.authorize(self.auth_scope), timeout=self.manager.recheck_timeout
                )
                if _user_id(current) != _user_id(self.context) or (
                    '*:*:*' not in current.permissions and not self.context.permissions.issubset(current.permissions)
                ):
                    self.stop(ACCESS_REVOKED)
                    return
        except PermissionError:
            self.stop(ACCESS_REVOKED)
        except LookupError:
            self.stop(LOGIN_EXPIRED)
        except (TimeoutError, asyncio.TimeoutError):
            self.stop(CHECK_TIMED_OUT)
        except Exception:
            self.stop(CHECK_UNAVAILABLE)

    async def _receive(self) -> Message:
        """
        转发客户端消息，在断开后取消剩余业务处理。

        :return: 原始 ASGI 消息
        """
        message = await self.receive()
        if message['type'] in {'http.disconnect', 'websocket.disconnect'}:
            self.disconnected = True
            if self.started:
                self.stop(CLIENT_DISCONNECTED)
        return message

    async def _send(self, message: Message) -> None:
        """
        识别长连接并隔离已撤销连接的迟到输出。

        :param message: 插件发送的 ASGI 消息
        :return: None
        """
        if self.closed.done():
            raise asyncio.CancelledError
        kind = message['type']
        if kind == 'websocket.accept':
            self._open()
            self.started = True
        elif kind == 'http.response.start':
            headers = {key.lower(): value for key, value in message.get('headers', [])}
            if headers.get(b'content-type', b'').split(b';')[0].strip().lower() == b'text/event-stream':
                self._open()
                self.started = True
        if self.started and kind == 'http.response.body' and message.get('body'):
            self.line_ended = message['body'][-1:] in {b'\r', b'\n'}
        await self.send(message)
        if kind == 'websocket.close' or (kind == 'http.response.body' and not message.get('more_body', False)):
            self.completed = True
            self.manager.connections.discard(self)
            if self.checker is not None:
                self.checker.cancel()

    async def run(self, app: ASGIApp, child_scope: Scope) -> None:
        """
        协调业务完成、身份撤销及外部取消，并清理复核任务。

        :param app: 插件 ASGI 应用
        :param child_scope: 已注入宿主上下文的请求作用域
        :return: None
        """
        task = asyncio.create_task(self._invoke(app, child_scope))
        try:
            await asyncio.wait({task, self.closed}, return_when=asyncio.FIRST_COMPLETED)
            if self.closed.done() and not self.completed:
                reason = self.closed.result()
                self.scope[CONNECTION_OUTCOME_KEY] = reason
                await self.manager.cancel_task(task)
                if not self.disconnected:
                    await self._close_response(reason)
            else:
                await task
        except asyncio.CancelledError:
            # 服务器取消也必须隔离输出，业务即使吞掉 CancelledError 仍不能迟到写入。
            self.disconnected = True
            if not self.closed.done():
                self.closed.set_result(CLIENT_DISCONNECTED)
            raise
        finally:
            if self.checker is not None:
                await self.manager.cancel_task(self.checker)
            if not task.done() and task not in self.manager._unfinished:
                await self.manager.cancel_task(task)
            self.manager.connections.discard(self)

    async def _invoke(self, app: ASGIApp, child_scope: Scope) -> None:
        """
        在独立任务中等待 ASGI callable 返回的任意可等待对象。

        :param app: 插件 ASGI 应用
        :param child_scope: 已注入宿主上下文的请求作用域
        :return: None
        """
        await app(child_scope, self._receive, self._send)

    async def _close_response(self, reason: ConnectionClosure) -> None:
        """
        发送协议内的终止消息；SSE 控制事件由宿主适配器转换为失败。

        :param reason: 首次记录的关闭原因
        :return: None
        """
        if self.scope['type'] == 'websocket':
            message = {'type': 'websocket.close', 'code': reason.websocket_code, 'reason': reason.message}
        elif self.started:
            data = json.dumps({'code': reason.code, 'reason': reason.reason}, separators=(',', ':'))
            # 覆盖未完成事件的类型，不额外补空行将半条业务数据提前分发。
            prefix = '' if self.line_ended else '\n'
            body = f'{prefix}event: {STREAM_CLOSED_EVENT}\ndata: {data}\n\n'.encode()
            message = {'type': 'http.response.body', 'body': body, 'more_body': False}
        else:
            # 关闭与响应开始同时发生时尚未发送头部，正常返回 503。
            await JSONResponse({'code': reason.code, 'msg': reason.message}, status_code=reason.code)(
                self.scope, self.receive, self.send
            )
            return
        sender = asyncio.create_task(self.send(message))
        try:
            done, _ = await asyncio.wait({sender}, timeout=self.manager.cancel_timeout)
            if sender in done:
                with suppress(OSError):
                    sender.result()
        finally:
            await self.manager.cancel_task(sender)
