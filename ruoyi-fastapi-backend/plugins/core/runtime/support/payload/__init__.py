from .catalog import (
    PluginCatalogDatabaseStatePayload,
    PluginCatalogDatabaseStatePayloadDict,
    PluginCatalogPayloadMixin,
    PluginCatalogSummaryPayload,
    PluginCatalogSummaryPayloadDict,
    PluginManifestConfigItemPayload,
    PluginManifestJobItemPayload,
    PluginMenuDiagnosticPlanItemPayload,
    PluginMenuDiagnosticPlanPayload,
)
from .common import PluginCommonPayloadMixin, PluginNotFoundPayload, PluginNotFoundPayloadDict
from .dependencies import (
    DependencyInstallReturnCodePayload,
    PluginDependencyInstallPayloadBuilder,
    PluginDependencyInstallPayloadDict,
)
from .plan import (
    ActionPayload,
    CommandResultPayload,
    DependencyInstallPlanItemPayload,
    DependencyInstallResultPayload,
    PluginPlanBlockerPayload,
    PluginPlanItemPayload,
    PluginPlanPayload,
    PluginPlanPayloadDict,
    PluginPlanPayloadMixin,
    PluginPlanResponsePayload,
    PurgePlanItemPayload,
    PurgePlanPayload,
    UpgradeDryRunPayload,
    UpgradeDryRunPayloadContext,
    UpgradeDryRunPayloadDict,
    VersionStatePayload,
)
from .validation import (
    DependencyItemPayload,
    MenuConflictItemPayload,
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
    PluginCommonPayloadMixin,
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
    'DependencyInstallReturnCodePayload',
    'DependencyItemPayload',
    'MenuConflictItemPayload',
    'PluginCatalogDatabaseStatePayload',
    'PluginCatalogDatabaseStatePayloadDict',
    'PluginCatalogSummaryPayload',
    'PluginCatalogSummaryPayloadDict',
    'PluginCheckItemPayloadDict',
    'PluginCheckPayload',
    'PluginCheckPayloadDict',
    'PluginDependencyCheckPayload',
    'PluginDependencyCheckPayloadDict',
    'PluginDependencyInstallPayloadBuilder',
    'PluginDependencyInstallPayloadDict',
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
    'PluginPlanPayloadDict',
    'PluginPlanResponsePayload',
    'PluginValidationPayloadBuilderProtocol',
    'PurgePlanItemPayload',
    'PurgePlanPayload',
    'StructureItemPayload',
    'UpgradeDryRunPayload',
    'UpgradeDryRunPayloadContext',
    'UpgradeDryRunPayloadDict',
    'ValidationIssuePayload',
    'VersionStatePayload',
]
