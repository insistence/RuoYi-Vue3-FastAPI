from .catalog import (
    PluginCatalogDatabaseStatePayload,
    PluginCatalogInfoPayload,
    PluginCatalogListPayload,
    PluginCatalogPayloadMixin,
    PluginCatalogSummaryPayload,
)
from .legacy import (
    PluginNotFoundPayload,
)
from .legacy import (
    PluginPayloadBuilder as PluginLegacyPayloadBuilder,
)
from .plan import PluginPlanPayload, PluginPlanPayloadMixin, PluginUpgradeDryRunPayload
from .validation import (
    PluginCheckItemPayload,
    PluginCheckPayload,
    PluginDependencyCheckPayload,
    PluginValidationPayloadMixin,
)


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
    'PluginCatalogDatabaseStatePayload',
    'PluginCatalogInfoPayload',
    'PluginCatalogListPayload',
    'PluginCatalogSummaryPayload',
    'PluginCheckItemPayload',
    'PluginCheckPayload',
    'PluginDependencyCheckPayload',
    'PluginNotFoundPayload',
    'PluginPayloadBuilder',
    'PluginPlanPayload',
    'PluginUpgradeDryRunPayload',
]
