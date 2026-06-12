from .catalog import (
    PluginCatalogDatabaseStatePayload,
    PluginCatalogDatabaseStatePayloadDict,
    PluginCatalogInfoPayload,
    PluginCatalogListPayload,
    PluginCatalogPayloadBuilderProtocol,
    PluginCatalogPayloadMixin,
    PluginCatalogSummaryPayload,
    PluginCatalogSummaryPayloadDict,
    PluginManifestConfigItemPayload,
    PluginManifestJobItemPayload,
    PluginMenuDiagnosticPlanItemPayload,
    PluginMenuDiagnosticPlanPayload,
)
from .legacy import (
    PluginNotFoundPayload,
    PluginNotFoundPayloadDict,
)
from .legacy import (
    PluginPayloadBuilder as PluginLegacyPayloadBuilder,
)
from .plan import (
    ActionPayload,
    CommandResultPayload,
    DependencyInstallPlanItemPayload,
    DependencyInstallResultPayload,
    PluginPlanBlockerPayload,
    PluginPlanItemPayload,
    PluginPlanPayload,
    PluginPlanPayloadBuilderProtocol,
    PluginPlanPayloadDict,
    PluginPlanPayloadMixin,
    PluginPlanResponsePayload,
    PluginUpgradeDryRunPayload,
    PurgePlanItemPayload,
    PurgePlanPayload,
    UpgradeDryRunPayloadContext,
    UpgradeDryRunPayloadDict,
    VersionStatePayload,
)
from .validation import (
    DependencyItemPayload,
    MenuConflictItemPayload,
    PluginCheckItemPayload,
    PluginCheckItemPayloadDict,
    PluginCheckPayload,
    PluginCheckPayloadDict,
    PluginDependencyCheckPayload,
    PluginDependencyCheckPayloadDict,
    PluginDependencyItemPayload,
    PluginValidationPayloadBuilderProtocol,
    PluginValidationPayloadMixin,
    StructureItemPayload,
    ValidationIssuePayload,
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
    'ActionPayload',
    'CommandResultPayload',
    'DependencyInstallPlanItemPayload',
    'DependencyInstallResultPayload',
    'DependencyItemPayload',
    'MenuConflictItemPayload',
    'PluginCatalogDatabaseStatePayload',
    'PluginCatalogDatabaseStatePayloadDict',
    'PluginCatalogInfoPayload',
    'PluginCatalogListPayload',
    'PluginCatalogPayloadBuilderProtocol',
    'PluginCatalogSummaryPayload',
    'PluginCatalogSummaryPayloadDict',
    'PluginCheckItemPayload',
    'PluginCheckItemPayloadDict',
    'PluginCheckPayload',
    'PluginCheckPayloadDict',
    'PluginDependencyCheckPayload',
    'PluginDependencyCheckPayloadDict',
    'PluginDependencyItemPayload',
    'PluginManifestConfigItemPayload',
    'PluginManifestJobItemPayload',
    'PluginMenuDiagnosticPlanItemPayload',
    'PluginMenuDiagnosticPlanPayload',
    'PluginNotFoundPayload',
    'PluginNotFoundPayloadDict',
    'PluginPayloadBuilder',
    'PluginPlanBlockerPayload',
    'PluginPlanItemPayload',
    'PluginPlanPayload',
    'PluginPlanPayloadBuilderProtocol',
    'PluginPlanPayloadDict',
    'PluginPlanResponsePayload',
    'PluginUpgradeDryRunPayload',
    'PluginValidationPayloadBuilderProtocol',
    'PurgePlanItemPayload',
    'PurgePlanPayload',
    'StructureItemPayload',
    'UpgradeDryRunPayloadContext',
    'UpgradeDryRunPayloadDict',
    'ValidationIssuePayload',
    'VersionStatePayload',
]
