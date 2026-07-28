import pytest

from exceptions.exception import PermissionException
from plugins.core.runtime.route_guard import CheckPluginEnabled


class FakePluginRouteStateGateway:
    """
    测试用插件路由状态网关。
    """

    def __init__(self, *, enabled: bool) -> None:
        """初始化测试网关。"""
        self.enabled = enabled
        self.calls: list[tuple[object, str]] = []

    async def is_plugin_enabled(self, db: object, plugin_id: str) -> bool:
        """判断插件是否启用。"""
        self.calls.append((db, plugin_id))
        return self.enabled


@pytest.mark.asyncio
async def test_plugin_route_guard_allows_enabled_plugin() -> None:
    """校验插件路由状态依赖允许启用插件访问。"""
    db = object()
    state_gateway = FakePluginRouteStateGateway(enabled=True)

    assert await CheckPluginEnabled('demo', state_gateway)(db) is True
    assert state_gateway.calls == [(db, 'demo')]


@pytest.mark.asyncio
async def test_plugin_route_guard_rejects_disabled_plugin() -> None:
    """校验插件路由状态依赖拒绝停用插件访问。"""
    state_gateway = FakePluginRouteStateGateway(enabled=False)

    with pytest.raises(PermissionException) as exc_info:
        await CheckPluginEnabled('demo', state_gateway)(object())
    assert exc_info.value.message == '插件未启用，接口不可访问'
