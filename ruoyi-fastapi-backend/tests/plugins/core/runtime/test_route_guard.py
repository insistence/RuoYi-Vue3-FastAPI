from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from exceptions.exception import PermissionException
from plugins.core.runtime import route_guard
from plugins.core.runtime.route_guard import CheckPluginEnabled


@pytest.mark.asyncio
async def test_plugin_route_guard_allows_enabled_plugin() -> None:
    """
    校验插件路由状态依赖允许启用插件访问。

    :return: None
    """
    with patch.object(route_guard.PluginDao, 'get_plugin_by_id', new=AsyncMock()) as get_plugin_by_id:
        get_plugin_by_id.return_value = SimpleNamespace(enabled='0')

        assert await CheckPluginEnabled('demo')(object()) is True


@pytest.mark.asyncio
async def test_plugin_route_guard_rejects_disabled_plugin() -> None:
    """
    校验插件路由状态依赖拒绝停用插件访问。

    :return: None
    """
    with patch.object(route_guard.PluginDao, 'get_plugin_by_id', new=AsyncMock()) as get_plugin_by_id:
        get_plugin_by_id.return_value = SimpleNamespace(enabled='1')

        with pytest.raises(PermissionException) as exc_info:
            await CheckPluginEnabled('demo')(object())
        assert exc_info.value.message == '插件未启用，接口不可访问'
