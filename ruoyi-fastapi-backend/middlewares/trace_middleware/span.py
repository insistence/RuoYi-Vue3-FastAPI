from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from starlette.types import Message, Scope

from .ctx import TraceCtx


class Span:
    """
    整个http生命周期：
        request(before) --> request(after) --> response(before) --> response(after)
    """

    def __init__(self, scope: Scope) -> None:
        self.scope = scope

    async def request_before(self) -> None:
        """
        request_before: 处理header信息等, 如记录请求体信息
        """
        TraceCtx.set_trace_id()
        TraceCtx.set_request_id()
        TraceCtx.set_span_id()
        TraceCtx.set_request_path(self.scope.get('path', ''))
        TraceCtx.set_request_method(self.scope.get('method', ''))

    async def request_after(self, message: Message) -> Message:
        """
        request_after: 处理请求bytes， 如记录请求参数

        example:
            message: {'type': 'http.request', 'body': b'{\r\n    "name": "\xe8\x8b\x8f\xe8\x8b\x8f\xe8\x8b\x8f"\r\n}', 'more_body': False}
        """
        return message

    async def response(self, message: Message) -> Message:
        """
        if message['type'] == "http.response.start":   -----> request-before
            pass
        if message['type'] == "http.response.body":    -----> request-after
            message.get('body', b'')
            pass
        """
        if message['type'] == 'http.response.start':
            message['headers'].append((b'request-id', TraceCtx.get_request_id().encode()))
            message['headers'].append((b'trace-id', TraceCtx.get_trace_id().encode()))
            message['headers'].append((b'span-id', TraceCtx.get_span_id().encode()))
        return message


@asynccontextmanager
async def get_current_span(scope: Scope) -> AsyncGenerator[Span, None]:
    yield Span(scope)
