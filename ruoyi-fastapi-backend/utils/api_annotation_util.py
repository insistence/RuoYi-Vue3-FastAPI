import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from fastapi import Request
from redis import asyncio as aioredis
from typing_extensions import ParamSpec

from common.enums import HttpMethod
from utils.log_util import logger

P = ParamSpec('P')
R = TypeVar('R')


class ApiAnnotationUtil:
    """
    接口装饰器通用工具类
    """

    @classmethod
    def get_request(cls, func: Callable[P, Awaitable[R]], *args: P.args, **kwargs: P.kwargs) -> Request | None:
        """
        从被装饰函数的入参中提取Request对象

        :param func: 被装饰的异步接口函数
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: Request对象，未找到时返回None
        """
        signature = inspect.signature(func)
        bound_arguments = signature.bind_partial(*args, **kwargs)
        for argument in bound_arguments.arguments.values():
            if isinstance(argument, Request):
                return argument

        return None

    @classmethod
    def get_redis_client(cls, request: Request, skip_message: str) -> aioredis.Redis | None:
        """
        从应用状态中获取Redis连接

        :param request: 当前请求对象
        :param skip_message: 未初始化Redis连接时的日志信息
        :return: Redis连接对象，未初始化时返回None
        """
        redis = getattr(request.app.state, 'redis', None)
        if redis is None:
            logger.warning(skip_message)

        return redis

    @classmethod
    def resolve_request_redis(
        cls,
        func: Callable[P, Awaitable[R]],
        skip_message: str,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> tuple[Request | None, aioredis.Redis | None]:
        """
        从被装饰函数入参中同时解析Request与Redis连接

        :param func: 被装饰的异步接口函数
        :param skip_message: 未初始化Redis连接时的日志信息
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: Request对象与Redis连接对象组成的元组
        """
        request = cls.get_request(func, *args, **kwargs)
        if request is None:
            return None, None

        return request, cls.get_redis_client(request, skip_message)

    @classmethod
    def normalize_http_methods(
        cls,
        methods: Sequence[HttpMethod] | None,
        default_methods: Sequence[HttpMethod] | None = None,
    ) -> tuple[str, ...]:
        """
        标准化HTTP请求方法配置

        :param methods: 显式配置的HTTP请求方法
        :param default_methods: methods为空时使用的默认HTTP请求方法
        :return: 去重且标准化后的HTTP请求方法元组
        """
        target_methods = methods if methods is not None else default_methods
        if not target_methods:
            return ()

        normalized_methods: list[str] = []
        for method in target_methods:
            if not isinstance(method, HttpMethod):
                raise TypeError('methods参数仅支持HttpMethod枚举')
            normalized_method = method.value
            if normalized_method not in normalized_methods:
                normalized_methods.append(normalized_method)

        return tuple(normalized_methods)
