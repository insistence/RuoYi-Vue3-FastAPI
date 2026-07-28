from typing import Protocol, runtime_checkable

from fastapi import Depends, params
from sqlalchemy.ext.asyncio import AsyncSession

from config.get_db import get_db
from exceptions.exception import PermissionException


@runtime_checkable
class PluginRouteStateGateway(Protocol):
    """
    插件路由状态读取端口。
    """

    async def is_plugin_enabled(self, db: AsyncSession, plugin_id: str) -> bool:
        """
        判断插件路由是否允许访问。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件是否启用
        """


class UnavailablePluginRouteStateGateway:
    """
    不可用的插件路由状态读取端口。
    """

    @staticmethod
    async def is_plugin_enabled(db: AsyncSession, plugin_id: str) -> bool:
        """
        判断插件路由是否允许访问。

        :param db: orm对象
        :param plugin_id: 插件ID
        :return: 插件是否启用
        :raises RuntimeError: 默认端口不提供状态读取能力
        """
        raise RuntimeError('插件路由状态适配器不可用')


class CheckPluginEnabled:
    """
    校验插件路由运行时启用状态。
    """

    def __init__(self, plugin_id: str, state_gateway: PluginRouteStateGateway | None = None) -> None:
        """
        初始化插件路由状态校验器。

        :param plugin_id: 插件ID
        :param state_gateway: 插件路由状态读取端口
        """
        self.plugin_id = plugin_id
        self.state_gateway = state_gateway or UnavailablePluginRouteStateGateway()

    async def __call__(self, db: AsyncSession = Depends(get_db)) -> bool:
        """
        执行插件启用状态校验。

        :param db: orm对象
        :return: 是否通过
        """
        if not await self.state_gateway.is_plugin_enabled(db, self.plugin_id):
            raise PermissionException(data='', message='插件未启用，接口不可访问')
        return True


def PluginEnabledDependency(  # noqa: N802
    plugin_id: str,
    state_gateway: PluginRouteStateGateway | None = None,
) -> params.Depends:
    """
    插件路由启用状态依赖。

    :param plugin_id: 插件ID
    :param state_gateway: 插件路由状态读取端口
    :return: 插件启用状态依赖
    """
    return Depends(CheckPluginEnabled(plugin_id, state_gateway))
