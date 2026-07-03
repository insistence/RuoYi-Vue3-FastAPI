from fastapi import Depends, params
from sqlalchemy.ext.asyncio import AsyncSession

from config.get_db import get_db
from exceptions.exception import PermissionException
from plugins.core.management.dao.dao import PluginDao


class CheckPluginEnabled:
    """
    校验插件路由运行时启用状态。
    """

    def __init__(self, plugin_id: str) -> None:
        """
        初始化插件路由状态校验器。

        :param plugin_id: 插件ID
        """
        self.plugin_id = plugin_id

    async def __call__(self, db: AsyncSession = Depends(get_db)) -> bool:
        """
        执行插件启用状态校验。

        :param db: orm对象
        :return: 是否通过
        """
        plugin = await PluginDao.get_plugin_by_id(db, self.plugin_id)
        if not plugin or getattr(plugin, 'enabled', None) != '0':
            raise PermissionException(data='', message='插件未启用，接口不可访问')
        return True


def PluginEnabledDependency(plugin_id: str) -> params.Depends:  # noqa: N802
    """
    插件路由启用状态依赖。

    :param plugin_id: 插件ID
    :return: 插件启用状态依赖
    """
    return Depends(CheckPluginEnabled(plugin_id))
