from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from plugins.core.capability import STATE_CHANGE_OPERATIONS
from plugins.core.deployment.catalog import PluginArtifactCatalog
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.state import aggregate_release
from plugins.core.environment import PLUGIN_RUNTIME_ENVIRONMENT
from plugins.core.management.dao.release_dao import PluginReleaseDao
from plugins.core.management.entity.vo.schemas import PluginModel
from utils.common_util import CamelCaseUtil
from utils.time_util import TimezoneUtil

ARTIFACT_MAINTENANCE_REASON = '签名制品插件仅允许通过维护发布命令变更，完成后重启全部worker。'


def artifact_capability(plugin_id: str) -> dict[str, Any]:
    """
    构建制品插件的维护能力说明，目录不可用时仍保留制品身份限制。

    :param plugin_id: 插件ID
    :return: 管理端使用的能力、受限操作和提示信息
    """
    return {
        'pluginId': plugin_id,
        'frontendMode': PLUGIN_RUNTIME_ENVIRONMENT.get_frontend_mode(),
        'backendRuntimeMode': PLUGIN_RUNTIME_ENVIRONMENT.get_backend_runtime_mode(),
        'hasFrontendResources': False,
        'frontendBuildRequired': False,
        'frontendRuntimeManageable': False,
        'backendRuntimeManageable': False,
        'runtimeManageable': False,
        'blockedOperations': sorted(STATE_CHANGE_OPERATIONS),
        'warnings': [ARTIFACT_MAINTENANCE_REASON],
        'primaryReason': ARTIFACT_MAINTENANCE_REASON,
    }


async def build_artifact_plugin_view(
    db: AsyncSession,
    plugin: object,
    backend_root: Path,
    frontend_root: Path | None,
    build_model: Callable[..., PluginModel],
) -> PluginModel:
    """
    展示目标制品及进程状态，读取清单前重新验签且不导入插件代码。

    :param db: 当前操作使用的数据库会话
    :param plugin: 数据库中的插件状态记录
    :param backend_root: 后端插件根目录
    :param frontend_root: 前端插件根目录，未配置时为 None
    :param build_model: 将发现结果、目录及已有状态转换为展示模型的回调
    :return: 合并制品清单、安装版本及发布摘要的插件展示模型
    """
    model = PluginModel(**CamelCaseUtil.transform_result(plugin))
    model.source = 'artifact'
    model.capability = artifact_capability(model.plugin_id)
    config = PluginDeploymentConfig.from_settings(backend_root.parent)
    if not config.enabled:
        model.release = {
            'status': 'unavailable',
            'lastError': '签名制品发布功能未启用，无法确认 worker 实际状态',
        }
        return model
    release = await PluginReleaseDao.get_release(db, model.plugin_id)
    if release is None:
        model.release = {'status': 'no_target', 'targetDigest': None, 'restartRequired': False}
        return model
    reports = await PluginReleaseDao.list_worker_reports(db, model.plugin_id)
    summary = aggregate_release(
        release,
        reports,
        now=TimezoneUtil.utc_now(),
        ttl_seconds=config.worker_ttl_seconds,
        enabled=getattr(plugin, 'enabled', '0') != '1',
    ).to_payload()
    summary.update(
        previousDigest=release.previous_digest,
        preparedDigest=release.prepared_digest,
        preparedVersion=release.prepared_version,
        installedVersion=model.installed_version,
        workers=[
            {
                'workerId': report.worker_id,
                'digest': report.artifact_digest,
                'version': report.version,
                'generation': report.generation,
                'state': report.state,
                'heartbeatTime': TimezoneUtil.format_rfc3339(report.heartbeat_time),
                'error': report.error,
            }
            for report in reports
            if report.plugin_id == model.plugin_id
        ],
    )
    digest = release.target_digest or release.prepared_digest
    catalog = PluginArtifactCatalog(config)
    try:
        catalog.reject_source_conflict(model.plugin_id)
        if digest:
            artifact = await catalog.get(digest)
            if artifact.plugin_id != model.plugin_id:
                raise ValueError('发布目标制品与插件ID不一致')
            model = build_model(catalog.discovered(artifact, release.generation), backend_root, frontend_root, plugin)
            summary['targetVersion'] = artifact.version if release.target_digest else None
    except (ValueError, OSError) as exc:
        summary['verificationError'] = str(exc)
    model.release = summary
    return model
