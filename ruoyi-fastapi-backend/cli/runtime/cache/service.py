from typing import Any

from cli.exit_codes import RUNTIME_ERROR

from .gateway import REDIS_TTL_KEY_NOT_FOUND, REDIS_TTL_PERSISTENT, CacheInfrastructureGateway
from .support import CacheDomainSupport, CacheRedisSupport


class CacheRuntimeService:
    """
    缓存运行时服务。

    该服务作为缓存运行时 facade，对外统一暴露缓存统计、键列表、键值、
    TTL 读取，以及缓存清理和预热入口。

    :param infrastructure_gateway: 缓存基础设施网关
    :param domain_support: 缓存领域支持对象
    :param redis_support: 缓存 Redis 访问支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: CacheInfrastructureGateway | None = None,
        domain_support: CacheDomainSupport | None = None,
        redis_support: CacheRedisSupport | None = None,
    ) -> None:
        """
        初始化缓存运行时服务。

        :param infrastructure_gateway: 缓存基础设施网关
        :param domain_support: 缓存领域支持对象
        :param redis_support: 缓存 Redis 访问支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or CacheInfrastructureGateway()
        self.domain_support = domain_support or CacheDomainSupport(self.infrastructure_gateway)
        self.redis_support = redis_support or CacheRedisSupport(self.infrastructure_gateway, self.domain_support)

    async def get_cache_stats(self) -> dict[str, Any]:
        """
        获取缓存统计信息。

        :return: 缓存统计结果
        """
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with self.redis_support.redis_session() as (redis, _redis_util):
                info = await redis.info()
                db_size = await redis.dbsize()
                command_stats_dict = await redis.info('commandstats')
                command_stats = [
                    {'name': key.split('_', 1)[1], 'value': int(value.get('calls', 0))}
                    for key, value in sorted(command_stats_dict.items(), key=lambda item: item[0])
                ]
                return {
                    'ok': True,
                    'dbSize': db_size,
                    'commandStats': command_stats,
                    'cacheNames': self.domain_support.build_cache_name_items(),
                    'info': info,
                }
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('读取缓存统计失败', exc)

    async def list_cache_keys(self, cache_name: str) -> dict[str, Any]:
        """
        列出指定缓存名称下的键名。

        :param cache_name: 缓存名称
        :return: 缓存键名列表结果
        """
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with self.redis_support.redis_session() as (redis, _redis_util):
                cache_keys: list[str] = await redis.keys(self.redis_support.build_cache_name_keys_pattern(cache_name))
                key_items = self.domain_support.extract_cache_key_items(cache_name, cache_keys)
                return {'ok': True, 'cacheName': cache_name, 'count': len(key_items), 'keys': key_items}
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('读取缓存键名失败', exc)

    async def get_cache_value(self, cache_name: str, cache_key: str) -> dict[str, Any]:
        """
        读取指定缓存键值。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :return: 缓存值结果
        """
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        full_cache_key = self.domain_support.build_full_cache_key(cache_name, cache_key)
        try:
            async with self.redis_support.redis_session() as (redis, _redis_util):
                cache_value = await redis.get(full_cache_key)
                if cache_value is None:
                    return self.domain_support.build_missing_cache_result(cache_name, cache_key)
                return {
                    'ok': True,
                    'cacheName': cache_name,
                    'cacheKey': cache_key,
                    'fullCacheKey': full_cache_key,
                    'cacheValue': cache_value,
                }
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('读取缓存内容失败', exc)

    async def get_cache_ttl(self, cache_name: str, cache_key: str) -> dict[str, Any]:
        """
        读取指定缓存键的剩余过期时间。

        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :return: 缓存 TTL 结果
        """
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        full_cache_key = self.domain_support.build_full_cache_key(cache_name, cache_key)
        try:
            async with self.redis_support.redis_session() as (redis, _redis_util):
                ttl_seconds = await redis.ttl(full_cache_key)
                if ttl_seconds == REDIS_TTL_KEY_NOT_FOUND:
                    return self.domain_support.build_missing_cache_result(cache_name, cache_key)
                return {
                    'ok': True,
                    'message': '缓存剩余过期时间读取成功' if ttl_seconds >= 0 else '缓存存在且未设置过期时间',
                    'cacheName': cache_name,
                    'cacheKey': cache_key,
                    'fullCacheKey': full_cache_key,
                    'ttlSeconds': ttl_seconds,
                    'persistent': ttl_seconds == REDIS_TTL_PERSISTENT,
                    'expires': ttl_seconds >= 0,
                }
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('读取缓存剩余过期时间失败', exc)

    async def clear_cache(
        self,
        *,
        cache_name: str = '',
        cache_key: str = '',
        clear_all: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        清理缓存。

        :param cache_name: 需要按缓存名称清理的前缀
        :param cache_key: 需要按缓存键名模糊清理的键
        :param clear_all: 是否清理全部缓存
        :param dry_run: 是否仅演练执行
        :return: 缓存清理结果
        """
        selected_modes = [bool(cache_name), bool(cache_key), clear_all]
        if sum(selected_modes) != 1:
            return {
                'ok': False,
                'message': '必须且只能指定一种清理方式：--cache-name、--cache-key 或 --all',
                'exit_code': RUNTIME_ERROR,
            }

        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with self.redis_support.redis_session() as (redis, redis_util):
                target_pattern = self.redis_support.build_clear_target_pattern(
                    cache_name=cache_name,
                    cache_key=cache_key,
                    clear_all=clear_all,
                )
                if target_pattern is None:
                    target_keys = sorted(await redis.keys())
                else:
                    target_keys = sorted(await redis.keys(target_pattern))

                result = {
                    'ok': True,
                    'dryRun': dry_run,
                    'matchedCount': len(target_keys),
                    'matchedKeys': target_keys,
                    'scope': self.domain_support.build_clear_scope(
                        cache_name=cache_name,
                        cache_key=cache_key,
                        clear_all=clear_all,
                    ),
                }
                if dry_run:
                    result['message'] = '缓存清理演练完成，未执行实际删除'
                    return result

                if target_keys:
                    await redis.delete(*target_keys)

                if clear_all:
                    await redis_util.init_sys_dict(redis)
                    await redis_util.init_sys_config(redis)

                result['message'] = '缓存清理完成'
                return result
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('清理缓存失败', exc)

    async def warmup_cache(self) -> dict[str, Any]:
        """
        预热系统缓存。

        :return: 缓存预热执行结果
        """
        redis_error = self.infrastructure_gateway.get_redis_error_class()
        try:
            async with self.redis_support.redis_session() as (redis, redis_util):
                await redis_util.init_sys_dict(redis)
                await redis_util.init_sys_config(redis)
                return {'ok': True, 'message': '缓存预热完成'}
        except redis_error as exc:
            return self.redis_support.build_redis_error_result('缓存预热失败', exc)


CACHE_RUNTIME = CacheRuntimeService()
