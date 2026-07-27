from __future__ import annotations

from typing import TypeAlias

from pydantic import Field

from plugins.core.runtime.support import (
    BatchOperationResultPayload,
    PluginAuditSnapshotFailurePayloadDict,
    PluginAuditSnapshotPayloadDict,
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
from plugins.core.runtime.support.payload.base import PluginPayloadModel


class PluginCatalogListResponsePayload(PluginPayloadModel):
    """
    插件列表响应 payload。
    """

    ok: bool
    count: int
    plugins: list[dict[str, object]]
    database_available: bool | None = Field(default=None, alias='databaseAvailable')
    database_error: str | None = Field(default=None, alias='databaseError')


class PluginCatalogInfoResponsePayload(PluginPayloadModel):
    """
    插件详情响应 payload。
    """

    ok: bool
    plugin: dict[str, object]


class PluginBatchRunResponsePayload(PluginPayloadModel):
    """
    插件批量执行响应 payload。
    """

    ok: bool | None = None
    message: str | None = None
    dry_run: bool | None = Field(default=None, alias='dryRun')
    continue_on_error: bool | None = Field(default=None, alias='continueOnError')
    executed: list[dict[str, object]] | None = None
    failed: dict[str, object] | None = None
    summary: dict[str, object] | None = None
    exit_code: int | None = None


class PluginRuntimeBlockedPayload(PluginPayloadModel):
    """
    插件运行模式阻断响应 payload。
    """

    ok: bool
    status: str
    operation: str
    plugin_id: str = Field(alias='pluginId')
    message: str
    suggestion: str
    capability: dict[str, object]
    dry_run: bool | None = Field(default=None, alias='dryRun')
    exit_code: int


PluginCatalogListResponseDict: TypeAlias = dict[str, object]
PluginCatalogInfoResponseDict: TypeAlias = dict[str, object]
PluginBatchRunResponseDict: TypeAlias = dict[str, object]
PluginRuntimeBlockedPayloadDict: TypeAlias = dict[str, object]


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
