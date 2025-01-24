# -*- coding: utf-8 -*-
"""
@author: peng
@file: span.py
@time: 2025/1/17  16:57
"""

from contextlib import asynccontextmanager
from starlette.types import Scope, Message
from .ctx import TraceCtx


class Span:
    """
    整个http生命周期：
        request(before) --> request(after) --> response(before) --> response(after)
    """

    def __init__(self, scope: Scope):
        self.scope = scope

    async def request_before(self):
        """
        request_before: 处理header信息等, 如记录请求体信息
        """
        TraceCtx.set_id()

    async def request_after(self, message: Message):
        """
        request_after: 处理请求bytes， 如记录请求参数

        example:
            message: {'type': 'http.request', 'body': b'{\r\n    "name": "\xe8\x8b\x8f\xe8\x8b\x8f\xe8\x8b\x8f"\r\n}', 'more_body': False}
        """
        return message

    async def response(self, message: Message):
        """
        if message['type'] == "http.response.start":   -----> request-before
            pass
        if message['type'] == "http.response.body":    -----> request-after
            message.get('body', b'')
            pass
        """
        if message['type'] == 'http.response.start':
            message['headers'].append((b'request-id', TraceCtx.get_id().encode()))
        return message


@asynccontextmanager
async def get_current_span(scope: Scope):
    yield Span(scope)
