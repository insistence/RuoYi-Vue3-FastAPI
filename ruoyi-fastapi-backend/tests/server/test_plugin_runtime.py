import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.runtime.application import (  # noqa: E402
    get_plugin_application_runtime as get_runtime_plugin_application_runtime,
)
from server import (  # noqa: E402
    _initialize_application_runtime,
    create_app,
    get_plugin_application_runtime,
)


def test_server_reuses_plugin_application_runtime_getter() -> None:
    """
    校验 server 入口不直接装配插件管理适配器。

    :return: None
    """
    assert get_plugin_application_runtime is get_runtime_plugin_application_runtime


def test_create_app_registers_builtin_routes_and_binds_plugin_runtime() -> None:
    """
    校验 create_app 保持内置路由注册，并绑定插件应用运行时。

    :return: None
    """
    fake_plugin_runtime = MagicMock()

    with (
        patch('server.APIDocsUtil.setup_docs_static_resources'),
        patch('server.APIDocsUtil.custom_api_docs_router'),
        patch('server.handle_sub_applications'),
        patch('server.handle_middleware'),
        patch('server.handle_exception'),
        patch('server.auto_register_routers') as auto_register_routers,
        patch('server.get_plugin_application_runtime', return_value=fake_plugin_runtime),
    ):
        app = create_app()

    auto_register_routers.assert_called_once_with(app)
    fake_plugin_runtime.bind_app.assert_called_once_with(app)


@pytest.mark.asyncio
async def test_initialize_application_runtime_delegates_plugin_steps() -> None:
    """
    校验应用启动流程保留原系统初始化，并只委托插件专属步骤。

    :return: None
    """
    fake_app = MagicMock()
    fake_plugin_runtime = MagicMock()
    fake_plugin_runtime.startup = AsyncMock()

    with (
        patch('server.get_plugin_application_runtime', return_value=fake_plugin_runtime),
        patch('server.init_create_table', new_callable=AsyncMock) as init_create_table,
        patch('server.RedisUtil.check_redis_connection', new_callable=AsyncMock) as check_redis_connection,
        patch('server.RedisUtil.init_sys_dict', new_callable=AsyncMock) as init_sys_dict,
        patch('server.RedisUtil.init_sys_config', new_callable=AsyncMock) as init_sys_config,
        patch('server._start_background_tasks', new_callable=AsyncMock) as start_background_tasks,
    ):
        await _initialize_application_runtime(fake_app, startup_log_enabled=True)

    fake_plugin_runtime.prepare_metadata.assert_called_once_with(fake_app)
    init_create_table.assert_awaited_once_with()
    fake_plugin_runtime.startup.assert_awaited_once_with(
        fake_app,
        startup_write_enabled=True,
        create_tables=init_create_table,
    )
    check_redis_connection.assert_awaited_once_with(fake_app.state.redis, log_enabled=True)
    init_sys_dict.assert_awaited_once_with(fake_app.state.redis)
    init_sys_config.assert_awaited_once_with(fake_app.state.redis)
    start_background_tasks.assert_awaited_once_with(fake_app)
