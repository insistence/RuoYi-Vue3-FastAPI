import pytest

from cli.runtime.cache import CacheRuntimeService
from cli.runtime.cache.gateway import REDIS_TTL_KEY_NOT_FOUND, CacheInfrastructureGateway
from cli.runtime.cache.support import CacheDomainSupport

EXPECTED_MATCHED_KEY_COUNT = 2


def test_cache_domain_support_extracts_scoped_keys() -> None:
    """
    校验缓存领域支持对象会提取指定缓存名前缀下的相对键名。

    :return: None
    """
    support = CacheDomainSupport(CacheInfrastructureGateway())

    key_items = support.extract_cache_key_items(
        'sys_config',
        ['sys_config:site_name', 'sys_config:logo', 'login_tokens:user:1'],
    )

    assert key_items == ['logo', 'site_name']


def test_cache_domain_support_builds_missing_cache_result() -> None:
    """
    校验缓存领域支持对象会生成统一的缓存不存在结果。

    :return: None
    """
    support = CacheDomainSupport(CacheInfrastructureGateway())

    payload = support.build_missing_cache_result('sys_config', 'site_name')

    assert payload['ok'] is False
    assert payload['fullCacheKey'] == 'sys_config:site_name'
    assert payload['message'] == '缓存不存在：sys_config:site_name'


@pytest.mark.asyncio
async def test_cache_runtime_service_ttl_returns_missing_result() -> None:
    """
    校验缓存运行时在 TTL 返回不存在标记时会输出统一缺失结果。

    :return: None
    """

    class FakeRedis:
        """
        模拟 Redis 客户端。
        """

        @staticmethod
        async def ttl(full_cache_key: str) -> int:
            """
            返回 Redis 键不存在标记。

            :param full_cache_key: 完整缓存键名
            :return: Redis TTL 特殊值
            """
            assert full_cache_key == 'sys_config:site_name'
            return REDIS_TTL_KEY_NOT_FOUND

        @staticmethod
        async def close() -> None:
            """
            关闭客户端。

            :return: None
            """

    class FakeRedisUtil:
        """
        模拟 Redis 工具类。
        """

        @staticmethod
        async def create_redis_pool(*, log_enabled: bool = False) -> FakeRedis:
            """
            返回模拟 Redis 客户端。

            :param log_enabled: 是否启用日志
            :return: 模拟 Redis 客户端
            """
            del log_enabled
            return FakeRedis()

    gateway = CacheInfrastructureGateway()
    service = CacheRuntimeService(infrastructure_gateway=gateway)

    def _fake_get_redis_util() -> FakeRedisUtil:
        return FakeRedisUtil()

    object.__setattr__(gateway, 'get_redis_util', _fake_get_redis_util)

    payload = await service.get_cache_ttl('sys_config', 'site_name')

    assert payload['ok'] is False
    assert payload['fullCacheKey'] == 'sys_config:site_name'


@pytest.mark.asyncio
async def test_cache_runtime_service_clear_cache_dry_run_reports_scope() -> None:
    """
    校验缓存运行时 dry-run 清理会返回匹配键与清理范围。

    :return: None
    """

    class FakeRedis:
        """
        模拟 Redis 客户端。
        """

        @staticmethod
        async def keys(pattern: str) -> list[str]:
            """
            返回匹配键列表。

            :param pattern: 匹配模式
            :return: 匹配结果
            """
            assert pattern == 'sys_config:*'
            return ['sys_config:site_name', 'sys_config:logo']

        @staticmethod
        async def close() -> None:
            """
            关闭客户端。

            :return: None
            """

    class FakeRedisUtil:
        """
        模拟 Redis 工具类。
        """

        @staticmethod
        async def create_redis_pool(*, log_enabled: bool = False) -> FakeRedis:
            """
            返回模拟 Redis 客户端。

            :param log_enabled: 是否启用日志
            :return: 模拟 Redis 客户端
            """
            del log_enabled
            return FakeRedis()

    gateway = CacheInfrastructureGateway()
    service = CacheRuntimeService(infrastructure_gateway=gateway)

    def _fake_get_redis_util() -> FakeRedisUtil:
        return FakeRedisUtil()

    object.__setattr__(gateway, 'get_redis_util', _fake_get_redis_util)

    payload = await service.clear_cache(cache_name='sys_config', dry_run=True)

    assert payload['ok'] is True
    assert payload['matchedCount'] == EXPECTED_MATCHED_KEY_COUNT
    assert payload['scope'] == {'mode': 'cacheName', 'cacheName': 'sys_config'}
    assert payload['message'] == '缓存清理演练完成，未执行实际删除'
