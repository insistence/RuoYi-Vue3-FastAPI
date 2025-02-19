# -*- coding: utf-8 -*-
"""
@author: peng
@file: ctx.py
@time: 2025/1/17  16:57
"""

import contextvars
from uuid import uuid4

CTX_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar('request-id', default='')


class TraceCtx:
    @staticmethod
    def set_id():
        _id = uuid4().hex
        CTX_REQUEST_ID.set(_id)
        return _id

    @staticmethod
    def get_id():
        return CTX_REQUEST_ID.get()
