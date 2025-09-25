# -*- coding: utf-8 -*-
"""
@author: peng
@file: span.py
@time: 2025/1/17  16:57
@modifier: left666
@modify_time: 2025/9/25  9:58
"""
import time
from contextlib import asynccontextmanager
from starlette.types import Scope, Message
from .ctx import TraceCtx
from utils.log_util import logger


class Span:
    """
    整个http生命周期：
        request(before) --> request(after) --> response(before) --> response(after)
    """

    def __init__(self, scope: Scope):
        self.scope = scope
        self.client_ip = scope.get('client')[0]
        self.start_time = time.time()
        self.status_code = None

    async def request_before(self):
        """
        request_before: 处理header信息等, 如记录请求体信息
        """
        TraceCtx.set_id()
        # 安全获取客户端真实IP
        if x_forwarded_for := [v.decode() for k, v in self.scope.get('headers', []) if k.lower() == b'x-forwarded-for']:
            self.client_ip = x_forwarded_for[0].split(',')[0].strip()

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
            self.status_code = message['status']  # 存储状态码
        elif message['type'] == 'http.response.body':
            if not message.get('more_body', False):  # 是最后一部分响应体时
                # 计算请求处理时间
                duration = round((time.time() - self.start_time) * 1000)
                with logger.contextualize(status_code=self.status_code, duration=duration):
                    logger.log("request", f"{self.client_ip} {self.scope.get('method')} {self.scope.get('path')}")
        return message


@asynccontextmanager
async def get_current_span(scope: Scope):
    yield Span(scope)
