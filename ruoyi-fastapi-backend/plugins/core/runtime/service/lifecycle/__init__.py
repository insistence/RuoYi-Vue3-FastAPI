from .enable import PluginEnableOperationMixin
from .install import PluginInstallOperationMixin
from .purge import PluginPurgeOperationMixin
from .upgrade import PluginUpgradeOperationMixin


class PluginLifecycleOperationMixin(
    PluginInstallOperationMixin,
    PluginUpgradeOperationMixin,
    PluginEnableOperationMixin,
    PluginPurgeOperationMixin,
):
    """
    插件安装、升级、启停、卸载和物理清理操作。
    """


__all__ = [
    'PluginLifecycleOperationMixin',
]
