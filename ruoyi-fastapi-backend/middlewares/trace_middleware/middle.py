# -*- coding: utf-8 -*-
"""
@author: peng
@file: middle.py
@time: 2025/1/17  16:57
"""

from functools import wraps
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from .span import get_current_span, Span


class TraceASGIMiddleware:
    """
    fastapi-example:
        app = FastAPI()
        app.add_middleware(TraceASGIMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    async def my_receive(receive: Receive, span: Span):
        await span.request_before()

        @wraps(receive)
        async def my_receive():
            message = await receive()
            await span.request_after(message)
            return message

        return my_receive

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        async with get_current_span(scope) as span:
            handle_outgoing_receive = await self.my_receive(receive, span)

            async def handle_outgoing_request(message: 'Message') -> None:
                await span.response(message)
                await send(message)

            await self.app(scope, handle_outgoing_receive, handle_outgoing_request)
