import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from server import (  # noqa: E402
    _get_plugin_runtime_startup,
    _initialize_application_runtime,
    create_app,
)

EXPECTED_CREATE_TABLE_CALL_COUNT = 2


def test_create_app_registers_builtin_routes_and_binds_plugin_startup() -> None:
    """
    校验 create_app 保持内置路由注册，并绑定插件启动协调器。

    :return: None
    """
    fake_startup = MagicMock()

    with (
        patch('server.APIDocsUtil.setup_docs_static_resources'),
        patch('server.APIDocsUtil.custom_api_docs_router'),
        patch('server.handle_sub_applications'),
        patch('server.handle_middleware'),
        patch('server.handle_exception'),
        patch('server.auto_register_routers') as auto_register_routers,
        patch('server.PluginRuntimeStartupManager', return_value=fake_startup),
    ):
        app = create_app()

    auto_register_routers.assert_called_once_with(app)
    fake_startup.bind_app.assert_called_once_with(app)


@pytest.mark.asyncio
async def test_initialize_application_runtime_delegates_plugin_steps() -> None:
    """
    校验应用启动流程保留原系统初始化，并只委托插件专属步骤。

    :return: None
    """
    fake_app = MagicMock()
    fake_startup = MagicMock()
    fake_startup.prepare_enabled_plugins = AsyncMock()
    fake_startup.activate_enabled_plugins = AsyncMock()

    with (
        patch('server._get_plugin_runtime_startup', return_value=fake_startup),
        patch('server.init_create_table', new_callable=AsyncMock) as init_create_table,
        patch('server.RedisUtil.check_redis_connection', new_callable=AsyncMock) as check_redis_connection,
        patch('server.RedisUtil.init_sys_dict', new_callable=AsyncMock) as init_sys_dict,
        patch('server.RedisUtil.init_sys_config', new_callable=AsyncMock) as init_sys_config,
        patch('server._start_background_tasks', new_callable=AsyncMock) as start_background_tasks,
    ):
        await _initialize_application_runtime(fake_app, startup_log_enabled=True)

    fake_startup.import_builtin_entities.assert_called_once_with()
    assert init_create_table.await_count == EXPECTED_CREATE_TABLE_CALL_COUNT
    fake_startup.prepare_enabled_plugins.assert_awaited_once_with(fake_app)
    fake_startup.activate_enabled_plugins.assert_awaited_once_with(fake_app)
    check_redis_connection.assert_awaited_once_with(fake_app.state.redis, log_enabled=True)
    init_sys_dict.assert_awaited_once_with(fake_app.state.redis)
    init_sys_config.assert_awaited_once_with(fake_app.state.redis)
    start_background_tasks.assert_awaited_once_with(fake_app)


def test_get_plugin_runtime_startup_lazily_binds_manager() -> None:
    """
    校验缺少插件启动协调器时会延迟创建并绑定。

    :return: None
    """
    fake_app = MagicMock()
    fake_app.state.plugin_runtime_startup = None
    fake_startup = MagicMock()

    with patch('server.PluginRuntimeStartupManager', return_value=fake_startup):
        result = _get_plugin_runtime_startup(fake_app)

    assert result is fake_startup
    fake_startup.bind_app.assert_called_once_with(fake_app)
