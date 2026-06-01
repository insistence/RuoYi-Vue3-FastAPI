from .catalog import PluginCatalogPayloadMixin
from .legacy import PluginPayloadBuilder as PluginLegacyPayloadBuilder
from .plan import PluginPlanPayloadMixin
from .validation import PluginValidationPayloadMixin


class PluginPayloadBuilder(
    PluginCatalogPayloadMixin,
    PluginValidationPayloadMixin,
    PluginPlanPayloadMixin,
    PluginLegacyPayloadBuilder,
):
    """
    插件运行时负载构建器。

    使用 mixin 组合插件目录、校验、计划和生命周期动作等纯负载构建能力。
    """


__all__ = [
    'PluginPayloadBuilder',
]
