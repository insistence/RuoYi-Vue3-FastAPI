from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, TypedDict

from plugins.core.runtime.support import (
    BatchFailedPayload,
    BatchItemReportPayload,
    BatchOperationResultPayload,
    BatchSummaryPayload,
    PluginAuditSnapshotFailurePayloadDict,
    PluginAuditSnapshotPayloadDict,
    PluginCatalogSummaryPayloadDict,
    PluginCheckPayloadDict,
    PluginConfigExportFailurePayloadDict,
    PluginConfigExportPayloadDict,
    PluginConfigImportPayloadDict,
    PluginConfigStatePayloadDict,
    PluginDependencyCheckPayloadDict,
    PluginDependencyInstallPayloadDict,
    PluginDocumentationPayloadDict,
    PluginEnableStatePayloadDict,
    PluginEnableUpdateFailurePayloadDict,
    PluginLifecyclePayloadDict,
    PluginNotFoundPayloadDict,
    PluginPlanResponsePayload,
    PluginPurgeStatePayloadDict,
    PluginRuntimeBatchItemUnsupportedPayloadDict,
    PluginRuntimeDiagnoseFailurePayloadDict,
    PluginRuntimeDiagnosePayloadDict,
    PluginRuntimeExceptionPayloadDict,
    PluginRuntimeHealthResponsePayloadDict,
    PluginRuntimeInvalidOperationPayloadDict,
    PluginRuntimePrecheckPayloadDict,
    PluginRuntimeUpgradeBlockerPayloadDict,
    PluginSafeUninstallPayloadDict,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class PluginCatalogListResponseDict(TypedDict):
    """
    插件列表响应 payload。
    """

    ok: bool
    count: int
    plugins: list[PluginCatalogSummaryPayloadDict]


class PluginCatalogInfoResponseDict(TypedDict):
    """
    插件详情响应 payload。
    """

    ok: bool
    plugin: Mapping[str, object]


class PluginBatchRunResponseDict(TypedDict, total=False):
    """
    插件批量执行响应 payload。
    """

    ok: bool
    message: str
    dryRun: bool
    continueOnError: bool
    executed: list[BatchItemReportPayload]
    failed: BatchFailedPayload | None
    summary: BatchSummaryPayload
    exit_code: int


class PluginRuntimeBlockedPayloadDict(TypedDict, total=False):
    """
    插件运行模式阻断响应 payload。
    """

    ok: bool
    status: str
    operation: str
    pluginId: str
    message: str
    suggestion: str
    capability: dict[str, object]
    dryRun: bool
    exit_code: int


PluginRuntimeBlockedResponse: TypeAlias = PluginRuntimeBlockedPayloadDict
PluginRuntimeFailureResponse: TypeAlias = (
    PluginNotFoundPayloadDict
    | PluginRuntimeExceptionPayloadDict
    | PluginRuntimeInvalidOperationPayloadDict
    | PluginRuntimeBlockedResponse
)
PluginCatalogListResponse: TypeAlias = PluginCatalogListResponseDict | PluginRuntimeExceptionPayloadDict
PluginCatalogInfoResponse: TypeAlias = PluginCatalogInfoResponseDict | PluginRuntimeFailureResponse
PluginCheckResponse: TypeAlias = PluginCheckPayloadDict | PluginRuntimeFailureResponse
PluginDependencyCheckResponse: TypeAlias = PluginDependencyCheckPayloadDict | PluginRuntimeFailureResponse
PluginHealthResponse: TypeAlias = PluginRuntimeHealthResponsePayloadDict | PluginRuntimeFailureResponse
PluginConfigStateResponse: TypeAlias = PluginConfigStatePayloadDict | PluginRuntimeFailureResponse
PluginConfigExportResponse: TypeAlias = PluginConfigExportPayloadDict | PluginConfigExportFailurePayloadDict
PluginConfigImportResponse: TypeAlias = PluginConfigImportPayloadDict
PluginPrecheckResponse: TypeAlias = PluginRuntimePrecheckPayloadDict | PluginRuntimeFailureResponse
PluginPlanResponse: TypeAlias = PluginPlanResponsePayload | PluginRuntimeInvalidOperationPayloadDict
PluginBatchResponse: TypeAlias = PluginPlanResponse | PluginBatchRunResponseDict | PluginRuntimeExceptionPayloadDict
PluginBatchItemExecutionResponse: TypeAlias = (
    BatchOperationResultPayload
    | PluginLifecyclePayloadDict
    | PluginEnableStatePayloadDict
    | PluginRuntimeBatchItemUnsupportedPayloadDict
    | PluginRuntimeExceptionPayloadDict
)
PluginDependencyInstallResponse: TypeAlias = PluginDependencyInstallPayloadDict | PluginRuntimeFailureResponse
PluginLifecycleResponse: TypeAlias = (
    PluginLifecyclePayloadDict
    | PluginEnableStatePayloadDict
    | PluginEnableUpdateFailurePayloadDict
    | PluginSafeUninstallPayloadDict
    | PluginPurgeStatePayloadDict
    | PluginRuntimeUpgradeBlockerPayloadDict
    | PluginRuntimeFailureResponse
)
PluginDocumentationResponse: TypeAlias = (
    PluginDocumentationPayloadDict | PluginNotFoundPayloadDict | PluginRuntimeExceptionPayloadDict
)
PluginAuditSnapshotResponse: TypeAlias = PluginAuditSnapshotPayloadDict | PluginAuditSnapshotFailurePayloadDict
PluginDiagnoseResponse: TypeAlias = (
    PluginRuntimeDiagnosePayloadDict | PluginRuntimeDiagnoseFailurePayloadDict | PluginRuntimeExceptionPayloadDict
)
PluginManagementOperationResponse: TypeAlias = (
    PluginCheckResponse
    | PluginPrecheckResponse
    | PluginHealthResponse
    | PluginDiagnoseResponse
    | PluginDocumentationResponse
    | PluginLifecycleResponse
    | PluginConfigStateResponse
    | PluginConfigExportResponse
    | PluginConfigImportResponse
    | PluginDependencyCheckResponse
    | PluginPlanResponse
    | PluginBatchResponse
    | PluginDependencyInstallResponse
)
