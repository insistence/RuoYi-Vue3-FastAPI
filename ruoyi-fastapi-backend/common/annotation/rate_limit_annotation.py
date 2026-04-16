import hashlib
import json
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Literal, TypeVar

from fastapi import Request
from redis import asyncio as aioredis
from typing_extensions import ParamSpec

from common.context import RequestContext
from common.enums import HttpMethod, RedisInitKeyConfig
from exceptions.exception import LoginException
from module_admin.entity.vo.user_vo import CurrentUserModel
from utils.api_annotation_util import ApiAnnotationUtil
from utils.api_response_header_util import ApiResponseHeaderUtil
from utils.client_ip_util import ClientIPUtil
from utils.log_util import logger
from utils.response_util import ResponseUtil

P = ParamSpec('P')
R = TypeVar('R')
RateLimitScope = Literal['ip', 'user', 'user_or_ip']
RateLimitAlgorithm = Literal['fixed_window', 'sliding_window']
RateLimitFailStrategy = Literal['open', 'closed', 'local_fallback']


@dataclass(frozen=True)
class ApiRateLimitPresetConfig:
    """
    接口限流预设配置
    """

    name: str
    limit: int
    window_seconds: int
    scope: RateLimitScope = 'ip'
    algorithm: RateLimitAlgorithm = 'fixed_window'
    fail_strategy: RateLimitFailStrategy = 'open'
    methods: tuple[HttpMethod, ...] | None = None
    message: str = '请求过于频繁，请稍后再试'


@dataclass(frozen=True)
class ApiRateLimitBypassConfig:
    """
    接口限流角色豁免配置
    """

    roles: tuple[str, ...]


class ApiRateLimitPreset:
    """
    接口限流预设

    ANON_AUTH_LOGIN: 匿名登录类接口限流预设
    ANON_AUTH_REGISTER: 匿名注册类接口限流预设
    ANON_AUTH_CAPTCHA: 匿名验证码类接口限流预设
    ANON_PUBLIC_METADATA: 匿名公开元数据接口限流预设
    COMMON_UPLOAD: 通用上传接口限流预设
    USER_INTERACTIVE_HIGH_FREQ: 用户高频交互接口限流预设
    USER_RESOURCE_EXECUTION: 用户执行类接口限流预设
    USER_COMMON_MUTATION: 用户普通写操作接口限流预设
    USER_SECURITY_MUTATION: 用户安全敏感操作接口限流预设
    USER_DESTRUCTIVE_MUTATION: 用户破坏性操作接口限流预设
    USER_RESOURCE_EXPORT: 用户导出类接口限流预设
    USER_RESOURCE_IMPORT: 用户导入类接口限流预设
    USER_RESOURCE_UPLOAD: 用户上传类接口限流预设
    USER_RESOURCE_GENERATE: 用户生成类接口限流预设
    USER_RESOURCE_DOWNLOAD: 用户下载类接口限流预设
    USER_RESOURCE_SYNC: 用户同步类接口限流预设
    """

    ANON_AUTH_LOGIN = ApiRateLimitPresetConfig(
        name='ANON_AUTH_LOGIN',
        limit=12,
        window_seconds=60,
        algorithm='sliding_window',
        fail_strategy='local_fallback',
    )
    ANON_AUTH_REGISTER = ApiRateLimitPresetConfig(
        name='ANON_AUTH_REGISTER',
        limit=6,
        window_seconds=120,
        algorithm='sliding_window',
        fail_strategy='local_fallback',
    )
    ANON_AUTH_CAPTCHA = ApiRateLimitPresetConfig(
        name='ANON_AUTH_CAPTCHA',
        limit=36,
        window_seconds=60,
        algorithm='sliding_window',
        fail_strategy='local_fallback',
    )
    ANON_PUBLIC_METADATA = ApiRateLimitPresetConfig(
        name='ANON_PUBLIC_METADATA',
        limit=30,
        window_seconds=60,
        algorithm='sliding_window',
        fail_strategy='local_fallback',
    )
    COMMON_UPLOAD = ApiRateLimitPresetConfig(
        name='COMMON_UPLOAD',
        limit=24,
        window_seconds=60,
        scope='user_or_ip',
    )

    USER_INTERACTIVE_HIGH_FREQ = ApiRateLimitPresetConfig(
        name='USER_INTERACTIVE_HIGH_FREQ',
        limit=40,
        window_seconds=60,
        scope='user',
    )
    USER_RESOURCE_EXECUTION = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_EXECUTION',
        limit=12,
        window_seconds=60,
        scope='user',
    )
    USER_COMMON_MUTATION = ApiRateLimitPresetConfig(
        name='USER_COMMON_MUTATION',
        limit=24,
        window_seconds=120,
        scope='user',
    )
    USER_SECURITY_MUTATION = ApiRateLimitPresetConfig(
        name='USER_SECURITY_MUTATION',
        limit=12,
        window_seconds=120,
        scope='user',
    )
    USER_DESTRUCTIVE_MUTATION = ApiRateLimitPresetConfig(
        name='USER_DESTRUCTIVE_MUTATION',
        limit=6,
        window_seconds=120,
        scope='user',
    )
    USER_RESOURCE_EXPORT = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_EXPORT',
        limit=15,
        window_seconds=120,
        scope='user',
    )
    USER_RESOURCE_IMPORT = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_IMPORT',
        limit=8,
        window_seconds=120,
        scope='user',
    )
    USER_RESOURCE_UPLOAD = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_UPLOAD',
        limit=12,
        window_seconds=120,
        scope='user',
    )
    USER_RESOURCE_GENERATE = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_GENERATE',
        limit=8,
        window_seconds=120,
        scope='user',
    )
    USER_RESOURCE_DOWNLOAD = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_DOWNLOAD',
        limit=12,
        window_seconds=60,
        scope='user',
    )
    USER_RESOURCE_SYNC = ApiRateLimitPresetConfig(
        name='USER_RESOURCE_SYNC',
        limit=15,
        window_seconds=120,
        scope='user',
    )


class ApiRateLimit:
    """
    接口限流装饰器，支持Redis固定窗口、滑动窗口及本地应急兜底。

    `local_fallback` 仅作为Redis异常场景下的进程内应急保护，能提供单进程内的
    基础限流能力，但不保证多 worker / 多实例部署下的全局一致性。

    `ip` 维度限流通过 `ClientIPUtil` 提取客户端地址，仅当请求来源命中
    `APP_TRUSTED_PROXY_IPS` 且 `APP_TRUSTED_PROXY_HOPS` 大于0时，才会解析
    `X-Forwarded-For` / `X-Real-IP` 请求头；否则回退到直接连接来源地址。
    """

    _SUPPORTED_SCOPES: tuple[RateLimitScope, ...] = ('ip', 'user', 'user_or_ip')
    _SUPPORTED_ALGORITHMS: tuple[RateLimitAlgorithm, ...] = ('fixed_window', 'sliding_window')
    _SUPPORTED_FAIL_STRATEGIES: tuple[RateLimitFailStrategy, ...] = ('open', 'closed', 'local_fallback')
    _FIXED_WINDOW_LUA_SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    local ttl = redis.call('PTTL', KEYS[1])
    if current == 1 or ttl < 0 then
        redis.call('PEXPIRE', KEYS[1], ARGV[1])
        ttl = redis.call('PTTL', KEYS[1])
    end
    local limit = tonumber(ARGV[2])
    local remaining = limit - current
    if remaining < 0 then
        remaining = 0
    end
    local allowed = 0
    if current <= limit then
        allowed = 1
    end
    return {allowed, current, remaining, ttl}
    """
    _SLIDING_WINDOW_LUA_SCRIPT = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, tonumber(ARGV[1]) - tonumber(ARGV[2]))
    local current = redis.call('ZCARD', KEYS[1])
    local limit = tonumber(ARGV[4])
    local ttl = ARGV[2]
    if current >= limit then
        local earliest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
        if earliest[2] ~= nil then
            ttl = tonumber(ARGV[2]) - (tonumber(ARGV[1]) - tonumber(earliest[2]))
        end
        if ttl < 1 then
            ttl = 1
        end
        return {0, current, 0, ttl}
    end
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[3])
    redis.call('PEXPIRE', KEYS[1], ARGV[2])
    current = current + 1
    local remaining = limit - current
    if remaining < 0 then
        remaining = 0
    end
    local earliest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    if earliest[2] ~= nil then
        ttl = tonumber(ARGV[2]) - (tonumber(ARGV[1]) - tonumber(earliest[2]))
    end
    if ttl < 1 then
        ttl = 1
    end
    return {1, current, remaining, ttl}
    """
    # 仅用于Redis异常时的单进程本地兜底，不承担分布式一致性职责。
    _LOCAL_FALLBACK_STORE: dict[str, deque[int]] = {}

    def __init__(
        self,
        namespace: str,
        limit: int | None = None,
        window_seconds: int | None = None,
        scope: RateLimitScope | None = None,
        algorithm: RateLimitAlgorithm | None = None,
        fail_strategy: RateLimitFailStrategy | None = None,
        bypass: ApiRateLimitBypassConfig | None = None,
        methods: Sequence[HttpMethod] | None = None,
        message: str | None = None,
        preset: ApiRateLimitPresetConfig | None = None,
    ) -> None:
        """
        初始化接口限流装饰器

        :param namespace: 限流命名空间，用于区分不同接口
        :param limit: 窗口内允许的最大请求次数，可覆盖预设
        :param window_seconds: 限流窗口时长，单位秒，可覆盖预设
        :param scope: 限流作用域，ip: 按客户端IP限流，客户端IP由可信代理配置控制提取，user: 仅按当前登录用户限流，未登录请求跳过限流，user_or_ip: 已登录按用户限流，未登录按客户端IP限流，可覆盖预设
        :param algorithm: 限流算法，fixed_window: 固定窗口，sliding_window: 滑动窗口，可覆盖预设
        :param fail_strategy: 限流组件异常时的故障策略，open: 放行，closed: 直接拦截，local_fallback: 使用进程内内存做应急兜底限流，仅保证单进程内生效，可覆盖预设
        :param bypass: 角色豁免配置，仅在显式传入时生效
        :param methods: 需要限流的HttpMethod枚举列表，为None时默认限制所有方法，可覆盖预设
        :param message: 触发限流后的提示信息，可覆盖预设
        :param preset: 限流预设配置
        """
        resolved_limit = limit if limit is not None else preset.limit if preset else None
        resolved_window_seconds = (
            window_seconds if window_seconds is not None else preset.window_seconds if preset else None
        )
        resolved_scope = scope if scope is not None else preset.scope if preset else 'ip'
        resolved_algorithm = algorithm if algorithm is not None else preset.algorithm if preset else 'fixed_window'
        resolved_fail_strategy = (
            fail_strategy if fail_strategy is not None else preset.fail_strategy if preset else 'open'
        )
        resolved_methods = methods if methods is not None else preset.methods if preset else None
        resolved_message = message if message is not None else preset.message if preset else '请求过于频繁，请稍后再试'
        resolved_preset_name = preset.name if preset else 'CUSTOM'

        if not namespace:
            raise ValueError('ApiRateLimit的namespace不能为空')
        if resolved_limit is None or resolved_limit <= 0:
            raise ValueError('ApiRateLimit的limit必须大于0')
        if resolved_window_seconds is None or resolved_window_seconds <= 0:
            raise ValueError('ApiRateLimit的window_seconds必须大于0')
        if resolved_scope not in self._SUPPORTED_SCOPES:
            raise ValueError(f'ApiRateLimit的scope仅支持: {", ".join(self._SUPPORTED_SCOPES)}')
        if resolved_algorithm not in self._SUPPORTED_ALGORITHMS:
            raise ValueError(f'ApiRateLimit的algorithm仅支持: {", ".join(self._SUPPORTED_ALGORITHMS)}')
        if resolved_fail_strategy not in self._SUPPORTED_FAIL_STRATEGIES:
            raise ValueError(f'ApiRateLimit的fail_strategy仅支持: {", ".join(self._SUPPORTED_FAIL_STRATEGIES)}')
        if bypass and resolved_scope == 'ip':
            raise ValueError('ApiRateLimit在scope=ip时不支持角色豁免配置')

        self.namespace = namespace
        self.preset_name = resolved_preset_name
        self.limit = resolved_limit
        self.window_seconds = resolved_window_seconds
        self.scope = resolved_scope
        self.algorithm = resolved_algorithm
        self.fail_strategy = resolved_fail_strategy
        self.bypass_roles = self._normalize_bypass_roles(bypass.roles if bypass else None)
        self.methods = ApiAnnotationUtil.normalize_http_methods(resolved_methods)
        self.message = resolved_message

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """
        为目标异步接口函数增加接口限流能力

        :param func: 需要限流的异步接口函数
        :return: 包装后的异步接口函数
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            request = ApiAnnotationUtil.get_request(func, *args, **kwargs)
            if request is None:
                return await func(*args, **kwargs)
            if not self._is_request_method_allowed(request):
                return await func(*args, **kwargs)
            bypass_role = self._match_bypass_role()
            if bypass_role is not None:
                self._log_rate_limit_bypass(request, bypass_role)
                return await func(*args, **kwargs)

            rate_limit_result: dict[str, int | bool] | None = None
            redis = getattr(request.app.state, 'redis', None)
            if redis is None:
                rate_limit_result = self._resolve_failed_rate_limit(
                    request, reason='redis_unavailable', error_message='redis client is not initialized'
                )
                if rate_limit_result is None:
                    return await func(*args, **kwargs)
            else:
                try:
                    rate_limit_result = await self._acquire_rate_limit(redis, request)
                except Exception as exc:
                    rate_limit_result = self._resolve_failed_rate_limit(
                        request, reason='redis_error', error_message=str(exc)
                    )
                    if rate_limit_result is None:
                        return await func(*args, **kwargs)
            if rate_limit_result is None:
                return await func(*args, **kwargs)

            headers = self._build_rate_limit_headers(rate_limit_result)
            if not rate_limit_result['allowed']:
                self._log_rate_limit_hit(request, rate_limit_result)
                return ResponseUtil.too_many_requests(msg=self.message, headers=headers)  # type: ignore[return-value]

            ApiResponseHeaderUtil.merge_headers(request, headers)
            result = await func(*args, **kwargs)
            return result

        return wrapper

    def _is_request_method_allowed(self, request: Request) -> bool:
        """
        判断当前请求方法是否启用限流

        :param request: 当前请求对象
        :return: 是否启用限流
        """
        return not self.methods or request.method.upper() in self.methods

    def _normalize_bypass_roles(self, bypass_roles: Sequence[str] | None) -> tuple[str, ...]:
        """
        标准化角色豁免配置

        :param bypass_roles: 原始角色标识列表
        :return: 去重后的角色标识元组
        """
        if not bypass_roles:
            return ()

        normalized_roles: list[str] = []
        for role in bypass_roles:
            normalized_role = role.strip()
            if not normalized_role:
                raise ValueError('ApiRateLimit的bypass_roles不能包含空角色标识')
            if normalized_role not in normalized_roles:
                normalized_roles.append(normalized_role)

        return tuple(normalized_roles)

    def _match_bypass_role(self) -> str | None:
        """
        判断当前登录用户是否命中角色豁免

        :return: 命中的角色标识，未命中时返回None
        """
        if not self.bypass_roles:
            return None

        current_user = self._get_current_user()
        if current_user is None:
            return None

        user_roles = {str(role).strip() for role in current_user.roles if str(role).strip()}
        for role in self.bypass_roles:
            if role in user_roles:
                return role

        return None

    async def _acquire_rate_limit(self, redis: aioredis.Redis, request: Request) -> dict[str, int | bool] | None:
        """
        获取当前请求的限流计数结果

        :param redis: Redis连接对象
        :param request: 当前请求对象
        :return: 限流结果，当前请求不适用限流时返回None
        """
        current_time_ms = int(time.time() * 1000)
        rate_limit_key = self._build_rate_limit_key(request, current_time_ms)
        if rate_limit_key is None:
            return None
        if self.algorithm == 'sliding_window':
            allowed, current, remaining, reset_after_ms = await redis.eval(
                self._SLIDING_WINDOW_LUA_SCRIPT,
                1,
                rate_limit_key,
                current_time_ms,
                self.window_seconds * 1000,
                f'{current_time_ms}-{time.time_ns()}-{uuid.uuid4().hex}',
                self.limit,
            )
        else:
            window_ms = self.window_seconds * 1000
            window_bucket = current_time_ms // window_ms
            window_end_ms = (window_bucket + 1) * window_ms
            ttl_ms = max(window_end_ms - current_time_ms, 1)
            allowed, current, remaining, reset_after_ms = await redis.eval(
                self._FIXED_WINDOW_LUA_SCRIPT, 1, rate_limit_key, ttl_ms, self.limit
            )
        reset_after_ms = max(int(reset_after_ms), 1)

        return {
            'allowed': bool(int(allowed)),
            'current': int(current),
            'remaining': int(remaining),
            'reset_after_seconds': max((reset_after_ms + 999) // 1000, 1),
            'reset_at': (current_time_ms + reset_after_ms + 999) // 1000,
        }

    def _build_rate_limit_key(
        self, request: Request, current_time_ms: int, include_window_bucket: bool = True
    ) -> str | None:
        """
        构建当前请求的限流键

        :param request: 当前请求对象
        :param current_time_ms: 当前时间戳，单位毫秒
        :return: 限流键，当前请求不适用限流时返回None
        """
        scope_value = self._get_scope_value(request)
        if scope_value is None:
            return None

        key_material = {
            'method': request.method.upper(),
            'path': self._get_route_path(request),
            'scope': self.scope,
            'scope_value': scope_value,
        }
        key_digest = hashlib.sha256(
            json.dumps(
                key_material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            ).encode('utf-8')
        ).hexdigest()

        key_prefix = f'{RedisInitKeyConfig.API_RATE_LIMIT.key}:{self.namespace}:{self.algorithm}:{key_digest}'
        if self.algorithm == 'fixed_window' and include_window_bucket:
            window_bucket = current_time_ms // (self.window_seconds * 1000)
            return f'{key_prefix}:{window_bucket}'

        return key_prefix

    def _resolve_failed_rate_limit(
        self, request: Request, reason: str, error_message: str
    ) -> dict[str, int | bool] | None:
        """
        处理Redis不可用或执行异常时的限流故障策略

        :param request: 当前请求对象
        :param reason: 降级原因
        :param error_message: 错误详情
        :return: 限流结果，为None时表示按策略放行
        """
        self._log_rate_limit_degrade(request, reason, error_message)
        if self.fail_strategy == 'open':
            return None
        if self.fail_strategy == 'closed':
            return self._build_closed_rate_limit_result()

        return self._acquire_local_fallback_rate_limit(request)

    def _acquire_local_fallback_rate_limit(self, request: Request) -> dict[str, int | bool] | None:
        """
        使用进程内内存进行应急兜底限流，仅在Redis异常时启用

        该兜底能力仅在当前进程内生效，不保证多 worker / 多实例场景下的
        全局一致限流，更适合作为短时故障期间的降级保护。

        :param request: 当前请求对象
        :return: 限流结果，当前请求不适用限流时返回None
        """
        current_time_ms = int(time.time() * 1000)
        rate_limit_key = self._build_rate_limit_key(request, current_time_ms, include_window_bucket=False)
        if rate_limit_key is None:
            return None

        window_ms = self.window_seconds * 1000
        window_start_ms = current_time_ms - window_ms
        local_window = self._LOCAL_FALLBACK_STORE.setdefault(rate_limit_key, deque())
        while local_window and local_window[0] <= window_start_ms:
            local_window.popleft()
        if not local_window:
            self._LOCAL_FALLBACK_STORE.pop(rate_limit_key, None)
            local_window = deque()
            self._LOCAL_FALLBACK_STORE[rate_limit_key] = local_window

        current = len(local_window)
        if current >= self.limit:
            reset_after_ms = max(local_window[0] + window_ms - current_time_ms, 1) if local_window else window_ms
            return {
                'allowed': False,
                'current': current,
                'remaining': 0,
                'reset_after_seconds': max((reset_after_ms + 999) // 1000, 1),
                'reset_at': (current_time_ms + reset_after_ms + 999) // 1000,
            }

        local_window.append(current_time_ms)
        current += 1
        reset_after_ms = max(local_window[0] + window_ms - current_time_ms, 1)

        return {
            'allowed': True,
            'current': current,
            'remaining': max(self.limit - current, 0),
            'reset_after_seconds': max((reset_after_ms + 999) // 1000, 1),
            'reset_at': (current_time_ms + reset_after_ms + 999) // 1000,
        }

    def _build_closed_rate_limit_result(self) -> dict[str, int | bool]:
        """
        构建故障关闭策略下的拦截结果

        :return: 限流结果
        """
        reset_after_seconds = max(self.window_seconds, 1)
        current_time_ms = int(time.time() * 1000)
        reset_after_ms = reset_after_seconds * 1000
        return {
            'allowed': False,
            'current': self.limit,
            'remaining': 0,
            'reset_after_seconds': reset_after_seconds,
            'reset_at': (current_time_ms + reset_after_ms + 999) // 1000,
        }

    def _get_route_path(self, request: Request) -> str:
        """
        获取当前请求的路由模板路径

        :param request: 当前请求对象
        :return: 路由模板路径
        """
        route = request.scope.get('route')
        route_path = getattr(route, 'path', None)
        return route_path or request.url.path

    def _get_scope_value(self, request: Request) -> str | None:
        """
        获取当前请求的限流作用域值

        :param request: 当前请求对象
        :return: 作用域值，当前请求不适用限流时返回None
        """
        if self.scope == 'ip':
            return f'ip:{self._get_client_ip(request)}'

        current_user_id = self._get_current_user_id()
        if current_user_id is not None:
            return f'user:{current_user_id}'

        if self.scope == 'user':
            return None

        return f'ip:{self._get_client_ip(request)}'

    def _get_current_user_id(self) -> int | None:
        """
        获取当前登录用户ID

        :return: 用户ID，未登录时返回None
        """
        current_user = self._get_current_user()
        return current_user.user.user_id if current_user and current_user.user else None

    def _get_current_user(self) -> CurrentUserModel | None:
        """
        获取当前登录用户

        :return: 当前登录用户，未登录时返回None
        """
        try:
            return RequestContext.get_current_user()
        except LoginException:
            return None

    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端IP地址

        :param request: 当前请求对象
        :return: 客户端IP地址
        """
        return ClientIPUtil.get_client_ip(request)

    def _build_rate_limit_headers(self, rate_limit_result: dict[str, int | bool]) -> dict[str, str]:
        """
        构建限流响应头

        :param rate_limit_result: 限流结果
        :return: 限流响应头
        """
        headers = {
            'X-RateLimit-Limit': str(self.limit),
            'X-RateLimit-Remaining': str(rate_limit_result['remaining']),
            'X-RateLimit-Reset': str(rate_limit_result['reset_at']),
        }
        if not rate_limit_result['allowed']:
            headers['Retry-After'] = str(rate_limit_result['reset_after_seconds'])

        return headers

    def _log_rate_limit_hit(self, request: Request, rate_limit_result: dict[str, int | bool]) -> None:
        """
        记录限流命中日志

        :param request: 当前请求对象
        :param rate_limit_result: 限流结果
        :return: None
        """
        logger.warning(
            '接口限流命中: namespace={} preset={} algorithm={} fail_strategy={} method={} path={} scope={} scope_value={} current={} limit={} retry_after={}s',
            self.namespace,
            self.preset_name,
            self.algorithm,
            self.fail_strategy,
            request.method.upper(),
            self._get_route_path(request),
            self.scope,
            self._get_scope_value(request),
            rate_limit_result['current'],
            self.limit,
            rate_limit_result['reset_after_seconds'],
        )

    def _log_rate_limit_degrade(self, request: Request, reason: str, error_message: str) -> None:
        """
        记录限流组件异常时的降级日志

        :param request: 当前请求对象
        :param reason: 降级原因
        :param error_message: 错误详情
        :return: None
        """
        log_message = (
            '接口限流降级: namespace={} preset={} algorithm={} fail_strategy={} '
            'method={} path={} scope={} reason={} error={}'
        )
        log_args: list[str] = [
            self.namespace,
            self.preset_name,
            self.algorithm,
            self.fail_strategy,
            request.method.upper(),
            self._get_route_path(request),
            self.scope,
            reason,
            error_message,
        ]
        if self.fail_strategy == 'local_fallback':
            log_message += ' local_fallback_scope={}'
            log_args.append('process_local_only')

        logger.warning(log_message, *log_args)

    def _log_rate_limit_bypass(self, request: Request, bypass_role: str) -> None:
        """
        记录角色豁免限流日志

        :param request: 当前请求对象
        :param bypass_role: 命中的角色标识
        :return: None
        """
        logger.info(
            '接口限流绕过: namespace={} preset={} method={} path={} scope={} bypass_role={}',
            self.namespace,
            self.preset_name,
            request.method.upper(),
            self._get_route_path(request),
            self.scope,
            bypass_role,
        )
