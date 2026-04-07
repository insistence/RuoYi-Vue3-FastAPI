import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from functools import wraps
from typing import Any, TypeVar

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, ORJSONResponse, Response, StreamingResponse, UJSONResponse
from redis import asyncio as aioredis
from typing_extensions import ParamSpec

from common.constant import HttpStatusConstant
from common.context import RequestContext
from common.enums import RedisInitKeyConfig
from exceptions.exception import LoginException
from utils.log_util import logger

P = ParamSpec('P')
R = TypeVar('R')


class ApiCacheManager:
    """
    接口缓存键与命名空间管理工具类
    """

    @classmethod
    async def clear_namespace(cls, redis: aioredis.Redis, namespace: str) -> int:
        """
        清理指定命名空间下的接口缓存

        :param redis: Redis连接对象
        :param namespace: 缓存命名空间
        :return: 删除的缓存数量
        """
        return await cls._clear_by_pattern(redis, cls.build_namespace_pattern(namespace))

    @classmethod
    async def clear_all(cls, redis: aioredis.Redis) -> int:
        """
        清理所有接口缓存

        :param redis: Redis连接对象
        :return: 删除的缓存数量
        """
        return await cls._clear_by_pattern(redis, cls.build_namespace_pattern('*'))

    @classmethod
    async def clear_namespaces(cls, redis: aioredis.Redis, namespaces: list[str] | tuple[str, ...] | set[str]) -> int:
        """
        批量清理多个命名空间下的接口缓存

        :param redis: Redis连接对象
        :param namespaces: 需要清理的缓存命名空间列表
        :return: 删除的缓存数量
        """
        deleted_count = 0
        for namespace in set(namespaces):
            deleted_count += await cls.clear_namespace(redis, namespace)

        return deleted_count

    @classmethod
    async def clear_namespace_prefix(cls, redis: aioredis.Redis, namespace_prefix: str) -> int:
        """
        按命名空间前缀清理接口缓存

        :param redis: Redis连接对象
        :param namespace_prefix: 缓存命名空间前缀
        :return: 删除的缓存数量
        """
        return await cls._clear_by_pattern(redis, cls.build_namespace_prefix_pattern(namespace_prefix))

    @classmethod
    async def clear_namespace_prefixes(
        cls,
        redis: aioredis.Redis,
        namespace_prefixes: list[str] | tuple[str, ...] | set[str],
    ) -> int:
        """
        批量按命名空间前缀清理接口缓存

        :param redis: Redis连接对象
        :param namespace_prefixes: 需要清理的缓存命名空间前缀列表
        :return: 删除的缓存数量
        """
        deleted_count = 0
        for namespace_prefix in set(namespace_prefixes):
            deleted_count += await cls.clear_namespace_prefix(redis, namespace_prefix)

        return deleted_count

    @classmethod
    def build_namespace_pattern(cls, namespace: str) -> str:
        """
        生成命名空间扫描表达式

        :param namespace: 缓存命名空间
        :return: 缓存键扫描匹配模式
        """
        return f'{RedisInitKeyConfig.API_CACHE.key}:{namespace}:*'

    @classmethod
    def build_namespace_prefix_pattern(cls, namespace_prefix: str) -> str:
        """
        生成命名空间前缀扫描表达式

        :param namespace_prefix: 缓存命名空间前缀
        :return: 缓存键扫描匹配模式
        """
        return f'{RedisInitKeyConfig.API_CACHE.key}:{namespace_prefix}*'

    @classmethod
    async def _clear_by_pattern(cls, redis: aioredis.Redis, pattern: str) -> int:
        """
        根据扫描表达式清理匹配的接口缓存

        :param redis: Redis连接对象
        :param pattern: 缓存键扫描匹配模式
        :return: 删除的缓存数量
        """
        cache_keys = [key async for key in redis.scan_iter(match=pattern)]
        if not cache_keys:
            return 0

        return await redis.delete(*cache_keys)


class _ApiCacheSupport:
    """
    接口缓存装饰器共用工具基类
    """

    def _get_request(self, func: Callable[P, Awaitable[R]], *args: P.args, **kwargs: P.kwargs) -> Request | None:
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

    def _get_redis_client(self, request: Request, skip_message: str) -> aioredis.Redis | None:
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

    def _resolve_request_redis(
        self,
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
        request = self._get_request(func, *args, **kwargs)
        if request is None:
            return None, None

        return request, self._get_redis_client(request, skip_message)

    def _load_json_content(self, response_body: str) -> Any | None:
        """
        解析JSON响应体内容

        :param response_body: JSON字符串响应体
        :return: 解析后的Python对象，解析失败时返回None
        """
        try:
            return json.loads(response_body)
        except json.JSONDecodeError:
            return None

    def _extract_json_response_content(self, result: Any) -> Any | None:
        """
        提取响应中的JSON内容

        :param result: 原始接口返回结果
        :return: 解析后的JSON内容，无法提取时返回None
        """
        if result is None or isinstance(result, StreamingResponse):
            return None

        if isinstance(result, (JSONResponse, ORJSONResponse, UJSONResponse)):
            return self._load_json_content(result.body.decode('utf-8'))

        if isinstance(result, Response):
            return None

        return jsonable_encoder(result)

    def _match_response_codes(self, response_content: Any, response_codes: set[int]) -> bool:
        """
        判断响应内容中的业务响应码是否匹配

        :param response_content: JSON响应内容
        :param response_codes: 允许的业务响应码集合
        :return: 是否匹配
        """
        if not isinstance(response_content, dict):
            return True

        response_code = response_content.get('code')
        if response_code is None:
            return True

        return response_code in response_codes

    def _get_matched_response_content(self, result: Any, response_codes: set[int]) -> Any | None:
        """
        提取并校验满足业务响应码要求的JSON响应内容

        :param result: 原始接口返回结果
        :param response_codes: 允许的业务响应码集合
        :return: 匹配成功的JSON响应内容，不匹配时返回None
        """
        response_content = self._extract_json_response_content(result)
        if response_content is None or not self._match_response_codes(response_content, response_codes):
            return None

        return response_content


class ApiCache(_ApiCacheSupport):
    """
    接口缓存装饰器，仅用于幂等且返回JSON的接口
    """

    def __init__(
        self,
        namespace: str,
        expire_seconds: int = 10,
        vary_by_user: bool = True,
        methods: Sequence[str] | None = None,
        cache_response_codes: set[int] | None = None,
    ) -> None:
        """
        初始化接口缓存装饰器

        :param namespace: 缓存命名空间，用于区分不同接口类型
        :param expire_seconds: 缓存过期时间，单位秒
        :param vary_by_user: 是否按当前登录用户隔离缓存
        :param methods: 允许启用缓存的HTTP方法列表，为None时默认仅缓存GET请求
        :param cache_response_codes: 允许缓存的业务响应码，为None时默认仅缓存成功响应
        """
        self.namespace = namespace
        self.expire_seconds = expire_seconds
        self.vary_by_user = vary_by_user
        self.methods = tuple(dict.fromkeys(method.upper() for method in methods)) if methods else ('GET',)
        self.cache_response_codes = (
            cache_response_codes if cache_response_codes is not None else {HttpStatusConstant.SUCCESS}
        )

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """
        为目标异步接口函数增加接口缓存能力

        :param func: 需要被缓存的异步接口函数
        :return: 包装后的异步接口函数
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            request, redis = self._resolve_request_redis(
                func, '当前应用未初始化Redis连接，跳过接口缓存', *args, **kwargs
            )
            if request is None or redis is None:
                return await func(*args, **kwargs)
            if not self._is_request_method_allowed(request):
                return await func(*args, **kwargs)

            cache_key = await self._build_cache_key(request)
            cached_response = await redis.get(cache_key)
            if cached_response:
                return self._build_cached_response(cached_response)  # type: ignore[return-value]

            result = await func(*args, **kwargs)
            await self._cache_response(redis, cache_key, result)
            self._append_cache_header(result, cache_status='MISS')

            return result

        return wrapper

    def _is_request_method_allowed(self, request: Request) -> bool:
        """
        判断当前请求方法是否允许启用接口缓存

        :param request: 当前请求对象
        :return: 是否允许缓存
        """
        return request.method.upper() in self.methods

    async def _build_cache_key(self, request: Request) -> str:
        """
        根据当前请求生成稳定缓存键

        :param request: 当前请求对象
        :return: 接口缓存键
        """
        request_body = await request.body()
        user_scope = self._get_user_scope(request) if self.vary_by_user else ''
        key_material = {
            'method': request.method,
            'path': request.url.path,
            'path_params': dict(sorted(request.path_params.items())),
            'query_params': sorted(request.query_params.multi_items()),
            'body_digest': hashlib.sha256(request_body).hexdigest() if request_body else '',
            'user_scope': user_scope,
        }
        key_digest = hashlib.sha256(
            json.dumps(
                key_material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
                default=str,
            ).encode('utf-8')
        ).hexdigest()

        return f'{RedisInitKeyConfig.API_CACHE.key}:{self.namespace}:{key_digest}'

    def _get_user_scope(self, request: Request) -> str:
        """
        获取用户隔离维度

        优先使用当前登录用户ID，未登录时回退到Authorization摘要。

        :param request: 当前请求对象
        :return: 用户隔离字符串
        """
        try:
            current_user = RequestContext.get_current_user()
            return str(current_user.user.user_id)
        except LoginException:
            authorization = request.headers.get('Authorization', '')
            return hashlib.sha256(authorization.encode('utf-8')).hexdigest() if authorization else ''

    def _serialize_response(self, result: Any) -> str | None:
        """
        将响应对象序列化为可存入缓存的字符串

        :param result: 原始接口返回结果
        :return: 序列化后的缓存内容，不可缓存时返回None
        """
        response_payload = self._extract_response_payload(result)
        if response_payload is None:
            return None

        return json.dumps(response_payload, ensure_ascii=False)

    def _extract_response_payload(self, result: Any) -> dict[str, Any] | None:
        """
        提取可缓存的响应载荷

        :param result: 原始接口返回结果
        :return: 可缓存的响应载荷，不可缓存时返回None
        """
        if isinstance(result, StreamingResponse):
            return None

        if isinstance(result, (JSONResponse, ORJSONResponse, UJSONResponse)):
            # 命中缓存时无法安全复放后台任务，因此带有后台任务的响应不参与缓存
            if getattr(result, 'background', None) is not None:
                return None

            content = self._get_matched_response_content(result, self.cache_response_codes)
            if content is None:
                return None

            return {
                'content': content,
                'status_code': result.status_code,
                'media_type': result.media_type,
                'headers': self._filter_response_headers(result.headers),
            }

        if isinstance(result, Response):
            return None

        json_content = self._get_matched_response_content(result, self.cache_response_codes)
        if json_content is None:
            return None

        return {
            'content': json_content,
            'status_code': HttpStatusConstant.SUCCESS,
            'media_type': 'application/json',
            'headers': {},
        }

    def _build_cached_response(self, cached_response: str) -> JSONResponse:
        """
        根据缓存内容重建JSON响应对象

        :param cached_response: 缓存中读取到的响应字符串
        :return: 重建后的JSON响应对象
        """
        cached_payload = json.loads(cached_response)
        cached_content = self._refresh_response_time(cached_payload['content'])
        response = JSONResponse(
            status_code=cached_payload['status_code'],
            content=jsonable_encoder(cached_content),
            headers=cached_payload.get('headers'),
            media_type=cached_payload.get('media_type'),
        )
        response.headers['X-Api-Cache'] = 'HIT'

        return response

    async def _cache_response(self, redis: aioredis.Redis, cache_key: str, result: Any) -> None:
        """
        将接口响应写入接口缓存

        :param redis: Redis连接对象
        :param cache_key: 接口缓存键
        :param result: 原始接口返回结果
        :return: None
        """
        serialized_response = self._serialize_response(result)
        if serialized_response is None:
            return

        await redis.set(cache_key, serialized_response, ex=self.expire_seconds)
        logger.debug(f'接口缓存写入成功: {cache_key}')

    def _append_cache_header(self, result: Any, cache_status: str) -> None:
        """
        为响应对象追加接口缓存命中状态响应头

        :param result: 原始接口返回结果
        :param cache_status: 缓存状态标识
        :return: None
        """
        if isinstance(result, Response):
            result.headers['X-Api-Cache'] = cache_status

    def _filter_response_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """
        过滤不适合直接回放的响应头

        :param headers: 原始响应头
        :return: 过滤后的响应头
        """
        excluded_headers = {'content-length', 'content-type', 'set-cookie'}
        return {key: value for key, value in headers.items() if key.lower() not in excluded_headers}

    def _refresh_response_time(self, response_content: Any) -> Any:
        """
        刷新项目统一响应体中的time字段

        :param response_content: JSON响应内容
        :return: 刷新time后的响应内容
        """
        if not isinstance(response_content, dict):
            return response_content

        if {'code', 'msg', 'success', 'time'}.issubset(response_content):
            refreshed_content = response_content.copy()
            refreshed_content['time'] = datetime.now()
            return refreshed_content

        return response_content


class ApiCacheEvict(_ApiCacheSupport):
    """
    接口缓存失效装饰器，用于在写操作成功后统一清理相关缓存
    """

    def __init__(
        self,
        namespaces: Sequence[str] | None = None,
        namespace_prefixes: Sequence[str] | None = None,
        evict_response_codes: set[int] | None = None,
    ) -> None:
        """
        初始化接口缓存失效装饰器

        :param namespaces: 需要失效的缓存命名空间列表
        :param namespace_prefixes: 需要失效的缓存命名空间前缀列表
        :param evict_response_codes: 允许触发失效的业务响应码，默认为仅成功响应触发
        """
        self.namespaces = tuple(dict.fromkeys(namespaces or ()))
        self.namespace_prefixes = tuple(dict.fromkeys(namespace_prefixes or ()))
        if not self.namespaces and not self.namespace_prefixes:
            raise ValueError('ApiCacheEvict至少需要指定namespaces或namespace_prefixes')

        self.evict_response_codes = (
            evict_response_codes if evict_response_codes is not None else {HttpStatusConstant.SUCCESS}
        )

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """
        为目标异步接口函数增加缓存失效能力

        :param func: 需要在成功后触发缓存失效的异步接口函数
        :return: 包装后的异步接口函数
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            result = await func(*args, **kwargs)
            _, redis = self._resolve_request_redis(func, '当前应用未初始化Redis连接，跳过接口缓存失效', *args, **kwargs)
            if redis is None:
                return result

            if self._should_evict(result):
                await self._evict_cache(redis)

            return result

        return wrapper

    async def _evict_cache(self, redis: aioredis.Redis) -> None:
        """
        根据配置统一执行接口缓存失效

        :param redis: Redis连接对象
        :return: None
        """
        if self.namespaces:
            await ApiCacheManager.clear_namespaces(redis, self.namespaces)

        if self.namespace_prefixes:
            await ApiCacheManager.clear_namespace_prefixes(redis, self.namespace_prefixes)

    def _should_evict(self, result: Any) -> bool:
        """
        判断当前响应是否应触发缓存失效

        :param result: 原始接口返回结果
        :return: 是否触发缓存失效
        """
        return self._get_matched_response_content(result, self.evict_response_codes) is not None
