import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from common.constant import LockConstant  # noqa: E402
from plugins.core.runtime.application import PluginApplicationRuntime  # noqa: E402


class FakeRedis:
    """
    测试用 Redis。
    """

    def __init__(self, values: dict[str, str] | None = None) -> None:
        """
        初始化测试 Redis。

        :param values: 初始 key-value
        :return: None
        """
        self.values = values or {}
        self.deleted_keys: list[str] = []
        self.expires: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        """
        获取 Redis 值。

        :param key: Redis key
        :return: Redis value
        """
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """
        写入 Redis 值。

        :param key: Redis key
        :param value: Redis value
        :param ex: 过期时间
        :return: None
        """
        self.values[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def delete(self, key: str) -> None:
        """
        删除 Redis key。

        :param key: Redis key
        :return: None
        """
        self.deleted_keys.append(key)
        self.values.pop(key, None)


def build_app(redis: FakeRedis) -> FastAPI:
    """
    构建测试 FastAPI app。

    :param redis: 测试 Redis
    :return: FastAPI app
    """
    app = FastAPI()
    app.state.redis = redis
    return app


def test_plugin_application_runtime_binds_startup_manager() -> None:
    """
    校验应用插件运行时会绑定启动协调器。

    :return: None
    """
    app = FastAPI()
    startup_manager = MagicMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)

    runtime.bind_app(app)

    assert app.state.plugin_application_runtime is runtime
    startup_manager.bind_app.assert_called_once_with(app)


def test_prepare_metadata_delegates_builtin_entity_import() -> None:
    """
    校验插件平台元数据准备委托启动协调器导入内置实体。

    :return: None
    """
    app = FastAPI()
    startup_manager = MagicMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)

    runtime.prepare_metadata(app)

    startup_manager.bind_app.assert_called_once_with(app)
    startup_manager.import_builtin_entities.assert_called_once_with()


@pytest.mark.asyncio
async def test_startup_writer_creates_plugin_tables_installs_resources_and_marks_ready() -> None:
    """
    校验启动写入 worker 会执行插件二次建表、安装资源并标记 ready。

    :return: None
    """
    redis = FakeRedis({LockConstant.APP_STARTUP_LOCK_KEY: 'worker-1'})
    app = build_app(redis)
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock()
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)

    await runtime.startup(app, startup_write_enabled=True, create_tables=create_tables)

    assert runtime.ready_key in redis.deleted_keys
    startup_manager.prepare_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    create_tables.assert_awaited_once_with()
    startup_manager.activate_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=True)
    assert redis.values[runtime.ready_key] == 'worker-1'
    assert redis.expires[runtime.ready_key] == LockConstant.PLUGIN_STARTUP_READY_EXPIRE_SECONDS


@pytest.mark.asyncio
async def test_startup_reader_waits_ready_then_activates_without_writes() -> None:
    """
    校验非启动写入 worker 等待 ready 后只做本地激活。

    :return: None
    """
    redis = FakeRedis(
        {
            LockConstant.APP_STARTUP_LOCK_KEY: 'worker-1',
            LockConstant.PLUGIN_STARTUP_READY_KEY: 'worker-1',
        }
    )
    app = build_app(redis)
    calls = []
    startup_manager = MagicMock()
    startup_manager.prepare_enabled_plugins = AsyncMock(side_effect=lambda *args, **kwargs: calls.append('prepare'))
    startup_manager.activate_enabled_plugins = AsyncMock()
    create_tables = AsyncMock()
    runtime = PluginApplicationRuntime(startup_manager=startup_manager)
    runtime.wait_startup_ready = AsyncMock(side_effect=lambda *args, **kwargs: calls.append('wait'))

    await runtime.startup(app, startup_write_enabled=False, create_tables=create_tables)

    assert calls == ['wait', 'prepare']
    runtime.wait_startup_ready.assert_awaited_once_with(app)
    startup_manager.prepare_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=False)
    create_tables.assert_not_awaited()
    startup_manager.activate_enabled_plugins.assert_awaited_once_with(app, startup_write_enabled=False)


@pytest.mark.asyncio
async def test_wait_startup_ready_times_out_when_writer_not_ready() -> None:
    """
    校验非启动写入 worker 等待插件 ready 超时会失败。

    :return: None
    """
    redis = FakeRedis({LockConstant.APP_STARTUP_LOCK_KEY: 'worker-1'})
    app = build_app(redis)
    runtime = PluginApplicationRuntime(
        startup_manager=MagicMock(),
        ready_wait_timeout_seconds=0,
        ready_wait_interval_seconds=0,
    )

    with pytest.raises(TimeoutError, match='等待插件启动 ready 超时'):
        await runtime.wait_startup_ready(app)
