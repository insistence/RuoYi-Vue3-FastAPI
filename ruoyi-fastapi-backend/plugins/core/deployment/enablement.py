from typing import Any
from uuid import uuid4

from sqlalchemy import select, update

from plugins.core.deployment.service import PluginDeploymentService
from plugins.core.management.dao.release_dao import PluginReleaseConflictError
from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.do.release_models import SysPluginRelease
from plugins.core.management.service.service import PluginService
from plugins.core.utils import validate_plugin_id_value


class PluginArtifactEnablementService(PluginDeploymentService):
    """
    在停机维护窗口原子更新制品启停状态与声明资源的服务。
    """

    async def set_enabled(
        self,
        plugin_id: str,
        *,
        enabled: bool,
        expected_generation: str,
        maintenance: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """
        在停机维护窗口原子更新制品启停状态、声明资源和发布代际。

        :param plugin_id: 插件ID
        :param enabled: 插件目标是否启用
        :param expected_generation: 调用方读取并确认的发布代际，用于并发状态校验
        :param maintenance: 是否已显式确认在停止全部宿主进程后执行维护
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: 新启停状态、发布代际及重启要求
        :raises ValueError: 维护条件、准备证据、依赖或资源更新不满足启停要求
        :raises PluginReleaseConflictError: 预检后发布代际或维护准备证据发生变化
        """
        self._require_maintenance(maintenance)
        validate_plugin_id_value(plugin_id)
        operation = 'release_enable' if enabled else 'release_disable'
        async with self.lifecycle_lock.lock(plugin_id, operation) as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            release, plugin = await self._read_state(plugin_id)
            if release is None or release.generation != expected_generation:
                raise PluginReleaseConflictError('发布代际已变化，请重新读取目标')
            if (
                not release.target_digest
                or release.prepare_status != 'prepared'
                or release.prepared_digest != release.target_digest
                or plugin is None
                or not plugin.installed_version
                or release.prepared_version != plugin.installed_version
            ):
                raise ValueError('当前发布目标未完成维护准备，不能更改启停状态')
            artifact = await self.catalog.get(release.target_digest)
            discovered = self.catalog.discovered(artifact)
            runtime = self.runtime_factory(self.config, await self._snapshot(artifact))
            precheck = await runtime.set_plugin_enabled(plugin_id, enabled=enabled, dry_run=True)
            if not precheck.get('ok'):
                raise ValueError(str(precheck.get('message') or '插件启停依赖预检失败'))
            async with self.session_factory() as db:
                generation = uuid4().hex
                installed_matches = (
                    select(SysPlugin.plugin_id)
                    .where(
                        SysPlugin.plugin_id == plugin_id,
                        SysPlugin.installed_version == SysPluginRelease.prepared_version,
                    )
                    .exists()
                )
                changed = await db.execute(
                    update(SysPluginRelease)
                    .where(
                        SysPluginRelease.plugin_id == plugin_id,
                        SysPluginRelease.generation == expected_generation,
                        SysPluginRelease.target_digest == artifact.digest,
                        SysPluginRelease.prepared_digest == artifact.digest,
                        SysPluginRelease.prepare_status == 'prepared',
                        SysPluginRelease.prepared_version == plugin.installed_version,
                        installed_matches,
                    )
                    .values(generation=generation, update_by=actor)
                    .execution_options(synchronize_session=False)
                )
                if changed.rowcount != 1:
                    raise PluginReleaseConflictError('发布状态已变化，启停操作未执行')
                result = await PluginService.update_plugin_enabled_services(db, plugin_id, enabled, discovered)
                if not result.is_success:
                    raise ValueError(result.message)
                payload = {
                    'ok': True,
                    'operation': operation,
                    'pluginId': plugin_id,
                    'enabled': enabled,
                    'digest': artifact.digest,
                    'generation': generation,
                    'restartRequired': True,
                    'message': '维护启停状态已保存，请启动全部 worker',
                }
                await self._audit(db, payload, actor)
                await db.commit()
            return payload
