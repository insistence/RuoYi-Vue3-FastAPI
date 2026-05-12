import socket
from types import SimpleNamespace

import pytest

from cli.runtime.ops import OperationsRuntimeService
from cli.runtime.ops.gateway import OperationsInfrastructureGateway
from cli.runtime.ops.support import OperationsDependencyInspector, OperationsServerInfoSupport


def test_operations_dependency_inspector_reports_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    校验运维依赖检查器会报告缺失的必需依赖。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    inspector = OperationsDependencyInspector()
    monkeypatch.setattr(
        inspector,
        'read_package_version',
        lambda distribution_name: None if distribution_name == 'fastapi' else '1.0.0',
    )

    payload = inspector.inspect()

    assert payload['ok'] is False
    assert payload['missingRequired'] == ['fastapi']
    assert payload['packages']['python']['installed'] is True


def test_operations_server_info_support_resolves_non_loopback_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    校验服务器信息支持对象会在主机名解析失败时回退到网卡地址。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """

    class FakePsutil:
        """
        模拟 psutil 模块。
        """

        @staticmethod
        def net_if_addrs() -> dict[str, list[SimpleNamespace]]:
            """
            返回模拟网卡地址。

            :return: 模拟网卡地址映射
            """
            return {
                'en0': [
                    SimpleNamespace(family=socket.AF_INET, address='127.0.0.1'),
                    SimpleNamespace(family=socket.AF_INET, address='192.168.1.8'),
                ]
            }

    gateway = OperationsInfrastructureGateway()
    support = OperationsServerInfoSupport(gateway)

    def _fake_get_psutil_module() -> FakePsutil:
        return FakePsutil()

    def _fake_gethostbyname(hostname: str) -> str:
        del hostname
        raise OSError('boom')

    monkeypatch.setattr(gateway, 'get_psutil_module', _fake_get_psutil_module)
    monkeypatch.setattr(socket, 'gethostbyname', _fake_gethostbyname)

    resolved_ip = support.resolve_server_ip('demo-host')

    assert resolved_ip == '192.168.1.8'


@pytest.mark.asyncio
async def test_operations_runtime_service_sync_jobs_closes_resources_on_success() -> None:
    """
    校验运维运行时在同步调度成功后会关闭调度器和 Redis 资源。

    :return: None
    """
    close_events: list[str] = []

    class FakeRedis:
        """
        模拟 Redis 客户端。
        """

        @staticmethod
        async def close() -> None:
            """
            记录关闭事件。

            :return: None
            """
            close_events.append('redis')

    class FakeRedisUtil:
        """
        模拟 Redis 工具。
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

    class FakeSchedulerUtil:
        """
        模拟调度器工具。
        """

        _is_leader = True

        @staticmethod
        async def init_system_scheduler(redis: FakeRedis) -> None:
            """
            初始化调度器。

            :param redis: Redis 客户端
            :return: None
            """
            assert isinstance(redis, FakeRedis)

        @staticmethod
        async def request_scheduler_sync() -> None:
            """
            发送调度同步请求。

            :return: None
            """

        @staticmethod
        async def close_system_scheduler() -> None:
            """
            记录调度器关闭事件。

            :return: None
            """
            close_events.append('scheduler')

    gateway = OperationsInfrastructureGateway()
    service = OperationsRuntimeService(infrastructure_gateway=gateway)

    def _fake_get_redis_util() -> FakeRedisUtil:
        return FakeRedisUtil()

    def _fake_get_scheduler_util() -> FakeSchedulerUtil:
        return FakeSchedulerUtil()

    object.__setattr__(gateway, 'get_redis_util', _fake_get_redis_util)
    object.__setattr__(gateway, 'get_scheduler_util', _fake_get_scheduler_util)

    payload = await service.sync_jobs()

    assert payload['ok'] is True
    assert payload['schedulerSyncRequested'] is True
    assert payload['isLeader'] is True
    assert close_events == ['scheduler', 'redis']
