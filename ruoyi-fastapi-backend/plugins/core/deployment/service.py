import sys
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from config.database import DataSourceRegistry
from plugins.core.artifacts import StoredArtifact
from plugins.core.deployment.catalog import PluginArtifactCatalog, artifact_payload
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.state import RUNTIME_PLUGIN_ID, aggregate_release
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.dao.release_dao import PluginReleaseConflictError, PluginReleaseDao
from plugins.core.management.service.service import PluginService
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock, RedisPluginLifecycleLock
from plugins.core.utils import validate_plugin_id_value
from plugins.core.validation.versioning import PluginVersionComparator
from utils.time_util import TimezoneUtil


def build_maintenance_runtime(config: PluginDeploymentConfig, plugins: list[DiscoveredPlugin]) -> Any:
    """
    复用现有生命周期用例，为独立维护实例注入制品发现快照。

    :param config: 制品发布配置快照
    :param plugins: 候选制品及其依赖使用的插件发现快照
    :return: 已配置维护模式和管理网关的插件运行时
    """
    from plugins.core.management.service.gateway import PluginManagementRuntimeGateway  # noqa: PLC0415
    from plugins.core.runtime.service import PluginRuntimeService  # noqa: PLC0415
    from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides  # noqa: PLC0415

    environment = PluginRuntimeEnvironmentService(backend_root=config.backend_root, python_executable=sys.executable)
    environment.backend_runtime_mode = 'maintenance'
    gateway = PluginManagementRuntimeGateway()
    runtime = PluginRuntimeService(
        runtime_environment=environment,
        gateways=PluginRuntimeGatewayOverrides(
            config_gateway=gateway,
            audit_gateway=gateway,
            state_query_gateway=gateway,
            migration_history_gateway=gateway,
            purge_plan_gateway=gateway,
            lifecycle_state_gateway=gateway,
            lifecycle_uow_gateway=gateway,
            migration_execution_gateway=gateway,
        ),
        model_gateway=gateway,
        command_gateway=gateway,
        # 外层发布服务已经持有同一个全局生命周期锁，不能在此二次竞争。
        lifecycle_lock=NoopPluginLifecycleLock(),
    )
    runtime.context.set_discovery_snapshot(plugins)
    return runtime


class PluginDeploymentService:
    """
    签名制品维护准备、发布目标选择及集群状态查询服务。
    """

    def __init__(
        self,
        config: PluginDeploymentConfig,
        *,
        session_factory: Any = None,
        dao: Any = PluginReleaseDao,
        lifecycle_lock: Any = None,
        runtime_factory: Callable[..., Any] = build_maintenance_runtime,
    ) -> None:
        """
        初始化签名制品维护发布服务。

        :param config: 制品发布配置快照
        :param session_factory: 异步数据库会话工厂，未提供时使用宿主数据源
        :param dao: 制品、发布目标及进程报告的数据访问接口
        :param lifecycle_lock: 与插件维护发布共用的生命周期锁
        :param runtime_factory: 用于创建独立维护运行时的工厂
        :return: None
        """
        self.config = config
        self.session_factory = session_factory or DataSourceRegistry.session
        self.dao = dao
        self.catalog = PluginArtifactCatalog(config, session_factory=self.session_factory, dao=dao)
        self.lifecycle_lock = lifecycle_lock or RedisPluginLifecycleLock()
        self.runtime_factory = runtime_factory

    async def status(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        汇总发布目标、维护准备证据及宿主进程实际加载状态。

        :param plugin_id: 可选的插件ID过滤条件，为 None 时汇总全部发布记录
        :return: 发布摘要列表和进程报告列表
        """
        self.config.require_enabled()
        if plugin_id is not None:
            validate_plugin_id_value(plugin_id)
        async with self.session_factory() as db:
            releases = await self.dao.list_releases(db)
            reports = await self.dao.list_worker_reports(db, plugin_id)
            rows = []
            for release in releases:
                if plugin_id is not None and release.plugin_id != plugin_id:
                    continue
                plugin = await PluginDao.get_plugin_by_id(db, release.plugin_id)
                summary = aggregate_release(
                    release,
                    reports,
                    now=TimezoneUtil.utc_now(),
                    ttl_seconds=self.config.worker_ttl_seconds,
                    enabled=getattr(plugin, 'enabled', '1') == '0',
                ).to_payload()
                summary.update(
                    installedVersion=getattr(plugin, 'installed_version', None),
                    enabled=getattr(plugin, 'enabled', '1') == '0',
                    preparedDigest=release.prepared_digest,
                    preparedVersion=release.prepared_version,
                    previousDigest=release.previous_digest,
                )
                rows.append(summary)
            workers = [
                {
                    'workerId': item.worker_id,
                    'pluginId': item.plugin_id,
                    'digest': item.artifact_digest,
                    'version': item.version,
                    'generation': item.generation,
                    'state': item.state,
                    'heartbeatTime': item.heartbeat_time.isoformat(),
                    'error': item.error,
                }
                for item in reports
            ]
        return {'ok': True, 'releases': rows, 'workers': workers}

    async def _require_quiescent(self) -> None:
        """
        在全局锁内检查存活宿主报告，确认当前没有进程阻挡维护。

        该检查依赖已上报的进程状态，调用方仍须先实际停止全部宿主进程。

        :return: None
        :raises ValueError: 仍存在有效期内且尚未停止的宿主进程报告
        """
        cutoff = TimezoneUtil.utc_now() - timedelta(seconds=self.config.worker_ttl_seconds)
        async with self.session_factory() as db:
            reports = await self.dao.list_worker_reports(db)
            if any(
                item.plugin_id == RUNTIME_PLUGIN_ID and item.state != 'stopped' and item.heartbeat_time >= cutoff
                for item in reports
            ):
                raise ValueError('仍有存活的宿主 worker，请停止全部 worker 后执行维护发布')

    @staticmethod
    def _require_maintenance(maintenance: bool) -> None:
        """
        要求调用方显式确认已进入停机维护窗口。

        :param maintenance: 是否已显式确认在停止全部宿主进程后执行维护
        :return: None
        :raises ValueError: 调用方未显式确认停机维护
        """
        if not maintenance:
            raise ValueError('该操作必须在独立维护进程执行，并显式传入 --maintenance')

    @staticmethod
    def _require_clean_process(plugin: DiscoveredPlugin) -> None:
        """
        拒绝已加载目标插件模块的进程继续执行制品维护准备。

        :param plugin: 本次拟执行维护准备的插件发现对象
        :return: None
        :raises ValueError: 当前进程已经导入该插件的模块命名空间
        """
        namespace = plugin.manifest.backend.module
        if any(name == namespace or name.startswith(f'{namespace}.') for name in sys.modules):
            raise ValueError('该维护进程已加载插件模块，请启动新进程执行，不能复用旧版本模块')

    async def _snapshot(self, candidate: StoredArtifact) -> list[DiscoveredPlugin]:
        """
        收集源码插件、候选制品和其他发布目标供静态依赖预检使用。

        :param candidate: 本次拟预检的制品对象
        :return: 未导入插件代码的发现结果列表
        """
        sources = PluginScanner(self.config.backend_root / 'plugins').discover_with_errors().plugins
        async with self.session_factory() as db:
            selected = [(row.plugin_id, row.target_digest) for row in await self.dao.list_releases(db)]
        result = {plugin.manifest.id: plugin for plugin in sources}
        for plugin_id, digest in selected:
            if digest and plugin_id != candidate.plugin_id:
                artifact = await self.catalog.get(digest)
                result[plugin_id] = self.catalog.discovered(artifact)
        result[candidate.plugin_id] = self.catalog.discovered(candidate)
        return list(result.values())

    async def _read_state(self, plugin_id: str) -> tuple[Any, Any]:
        """
        读取指定插件的发布记录和数据结构安装状态。

        :param plugin_id: 插件ID
        :return: 发布记录与插件记录，缺失记录分别为 None
        """
        async with self.session_factory() as db:
            release = await self.dao.get_release(db, plugin_id)
            plugin = await PluginDao.get_plugin_by_id(db, plugin_id)
            return release, plugin

    @staticmethod
    def _has_prepared_evidence(release: Any, digest: str, installed: str | None) -> bool:
        """
        检查制品摘要与已安装数据结构版本是否具有一致的维护准备证据。

        :param release: 插件发布目标及维护准备记录
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :param installed: 当前已安装的数据结构版本，未安装时为 None
        :return: 是否存在完全匹配的维护准备证据
        """
        return bool(
            release is not None
            and release.prepare_status == 'prepared'
            and release.prepared_digest == digest
            and release.prepared_version == installed
        )

    async def plan(self, plugin_id: str, digest: str) -> dict[str, Any]:
        """
        静态预检制品及维护操作，区分数据结构准备与代码目标切换。

        :param plugin_id: 插件ID
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :return: 可执行性、所需维护操作及准备证据说明
        :raises ValueError: 请求的制品不属于指定插件或当前制品校验失败
        """
        validate_plugin_id_value(plugin_id)
        artifact = await self.catalog.get(digest)
        if artifact.plugin_id != plugin_id:
            raise ValueError('制品不属于请求的插件')
        release, plugin = await self._read_state(plugin_id)
        installed = getattr(plugin, 'installed_version', None)
        operation = 'install' if not installed else 'upgrade'
        comparison = PluginVersionComparator.compare(artifact.version, installed) if installed else 1
        if installed and comparison != 1:
            operation = 'reuse_prepared' if comparison == 0 else 'rollback_required'
        runtime = self.runtime_factory(self.config, await self._snapshot(artifact))
        if operation in {'install', 'upgrade'}:
            precheck = await getattr(runtime, f'{operation}_plugin')(plugin_id, dry_run=True)
        else:
            precheck = await runtime.check_plugin_async(plugin_id)
        preparation_matches = self._has_prepared_evidence(release, digest, installed)
        same_version_ready = operation != 'reuse_prepared' or (installed == artifact.version and preparation_matches)
        return {
            'ok': bool(precheck.get('ok')) and operation != 'rollback_required' and same_version_ready,
            'operation': operation,
            **artifact_payload(artifact),
            'installedVersion': installed,
            'targetDigest': getattr(release, 'target_digest', None),
            'generation': getattr(release, 'generation', None),
            'restartRequired': True,
            'maintenanceRequired': True,
            'preparationMatches': preparation_matches,
            'message': (
                '同版本制品缺少匹配的维护准备证据；请提升版本后发布，不能猜测已安装内容'
                if not same_version_ready
                else str(precheck.get('message') or '')
            ),
            'precheck': precheck,
        }

    async def prepare(
        self,
        plugin_id: str,
        digest: str,
        *,
        maintenance: bool = False,
        actor: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        在停机维护窗口执行安装或升级，并保存与制品绑定的准备证据。

        准备成功不会自动选择发布目标；目标选择须通过单独的显式操作完成。

        :param plugin_id: 插件ID
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :param maintenance: 是否已显式确认在停止全部宿主进程后执行维护
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :param dry_run: 是否只执行预检而不写入文件或数据库
        :return: 维护准备结果或只读预检计划
        :raises ValueError: 维护条件、版本顺序或生命周期准备结果不符合发布要求
        """
        if dry_run:
            return await self.plan(plugin_id, digest)
        self._require_maintenance(maintenance)
        async with self.lifecycle_lock.lock(plugin_id, 'release_prepare') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            artifact = await self.catalog.get(digest)
            if artifact.plugin_id != validate_plugin_id_value(plugin_id):
                raise ValueError('制品不属于请求的插件')
            candidate = self.catalog.discovered(artifact)
            self._require_clean_process(candidate)
            release, plugin = await self._read_state(plugin_id)
            installed = getattr(plugin, 'installed_version', None)
            if installed == artifact.version:
                if self._has_prepared_evidence(release, digest, installed):
                    return {'ok': True, 'message': '该制品已完成维护准备', **artifact_payload(artifact)}
                raise ValueError('同版本制品缺少匹配的维护准备证据；请提升版本后发布，不能猜测已安装内容')
            if installed and PluginVersionComparator.compare(artifact.version, installed) != 1:
                raise ValueError('维护准备只允许升级；代码回滚请使用显式 rollback 命令')
            async with self.session_factory() as db:
                release = await self.dao.set_preparation_status(db, plugin_id, status='preparing', actor=actor)
                generation = release.generation
                await db.commit()
            operation = 'install' if not installed else 'upgrade'
            try:
                # 插件可能在 Hook 内延迟 import；整个维护进程禁写字节码以保持制品完整性。
                sys.dont_write_bytecode = True
                runtime = self.runtime_factory(self.config, await self._snapshot(artifact))
                result = await getattr(runtime, f'{operation}_plugin')(plugin_id, operated_by=actor)
                if not result.get('ok'):
                    raise ValueError(str(result.get('message') or '插件生命周期准备失败'))
                # Hook 不得修改自身发布目录；准备完成前重新检查全部字节。
                await self.catalog.get(digest)
                async with self.session_factory() as db:
                    current = await PluginDao.get_plugin_by_id(db, plugin_id)
                    if current is None or current.installed_version != artifact.version:
                        raise ValueError('维护准备后安装版本没有到达目标版本')
                    await self.dao.set_preparation_status(
                        db,
                        plugin_id,
                        status='prepared',
                        prepared_digest=digest,
                        prepared_version=current.installed_version,
                        actor=actor,
                        expected_generation=generation,
                    )
                    await db.commit()
                return {
                    'ok': True,
                    'message': '维护准备完成；选择目标制品后再启动 worker',
                    'generation': generation,
                    'restartRequired': True,
                    **artifact_payload(artifact),
                }
            except BaseException as exc:
                async with self.session_factory() as db:
                    await self.dao.set_preparation_status(
                        db,
                        plugin_id,
                        status='failed',
                        last_error=str(exc)[:2000] or type(exc).__name__,
                        actor=actor,
                        expected_generation=generation,
                    )
                    await db.commit()
                raise

    async def select(
        self,
        plugin_id: str,
        digest: str,
        *,
        expected_generation: str,
        expected_workers: int = 1,
        maintenance: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """
        在匹配准备证据和发布代际的前提下选择目标制品。

        :param plugin_id: 插件ID
        :param digest: 制品规范元数据的小写 SHA256 摘要
        :param expected_generation: 调用方读取并确认的发布代际，用于并发状态校验
        :param expected_workers: 预期启动并报告当前目标的宿主进程数量
        :param maintenance: 是否已显式确认在停止全部宿主进程后执行维护
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: 新发布代际、目标制品身份和重启要求
        :raises ValueError: 维护条件、制品归属或准备证据不符合要求
        :raises PluginReleaseConflictError: 发布代际在操作期间发生变化
        """
        self._require_maintenance(maintenance)
        async with self.lifecycle_lock.lock(plugin_id, 'release_select') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            artifact = await self.catalog.get(digest)
            if artifact.plugin_id != validate_plugin_id_value(plugin_id):
                raise ValueError('目标制品不属于请求的插件')
            async with self.session_factory() as db:
                release = await self.dao.select_target(
                    db,
                    plugin_id,
                    target_digest=digest,
                    expected_generation=expected_generation,
                    expected_workers=expected_workers,
                    actor=actor,
                )
                payload = {
                    'ok': True,
                    'operation': 'release_select',
                    'message': '发布目标已更新，等待全部 worker 重启并报告实际版本',
                    'generation': release.generation,
                    'restartRequired': True,
                    'expectedWorkers': expected_workers,
                    **artifact_payload(artifact),
                }
                await self._audit(db, payload, actor)
                await db.commit()
            return payload

    async def rollback(
        self,
        plugin_id: str,
        *,
        expected_generation: str,
        schema_compatible: bool = False,
        maintenance: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """
        切回上一代码制品并重建声明资源，保留当前数据结构安装版本。

        :param plugin_id: 插件ID
        :param expected_generation: 调用方读取并确认的发布代际，用于并发状态校验
        :param schema_compatible: 是否明确确认旧代码兼容当前数据结构，回滚不会撤销数据库迁移
        :param maintenance: 是否已显式确认在停止全部宿主进程后执行维护
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: 回滚后的发布代际、代码制品身份及保留的安装版本
        :raises ValueError: 未确认结构兼容性、没有上一制品或回滚预检失败
        :raises PluginReleaseConflictError: 发布代际在操作期间发生变化
        """
        self._require_maintenance(maintenance)
        if not schema_compatible:
            raise ValueError('代码回滚不会撤销数据库迁移，须确认旧代码兼容当前数据结构并传入 --schema-compatible')
        async with self.lifecycle_lock.lock(plugin_id, 'release_rollback') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            release, plugin = await self._read_state(validate_plugin_id_value(plugin_id))
            if release is None or release.generation != expected_generation:
                raise PluginReleaseConflictError('发布代际已变化，请重新读取目标')
            if not release.previous_digest or plugin is None or not plugin.installed_version:
                raise ValueError('没有可回滚的上一制品或数据结构安装状态')
            artifact = await self.catalog.get(release.previous_digest)
            candidate = self.catalog.discovered(artifact)
            runtime = self.runtime_factory(self.config, await self._snapshot(artifact))
            check = await runtime.check_plugin_async(plugin_id)
            if not check.get('ok'):
                raise ValueError(str(check.get('message') or '回滚制品预检失败'))
            async with self.session_factory() as db:
                # 重建菜单/配置/任务声明，绝不执行旧版迁移、seed或Hook。
                await PluginService.upsert_discovered_plugin_services(
                    db, candidate, self.config.backend_root / 'plugins'
                )
                await PluginService.install_plugin_menu_services(db, candidate, enabled=plugin.enabled == '0')
                await PluginService.install_plugin_default_config_services(db, candidate)
                await PluginService.install_plugin_job_services(db, candidate, enabled=plugin.enabled == '0')
                await self.dao.set_preparation_status(
                    db,
                    plugin_id,
                    status='prepared',
                    prepared_digest=artifact.digest,
                    prepared_version=plugin.installed_version,
                    actor=actor,
                    expected_generation=expected_generation,
                )
                selected = await self.dao.select_target(
                    db,
                    plugin_id,
                    target_digest=artifact.digest,
                    expected_generation=expected_generation,
                    expected_workers=release.expected_workers,
                    actor=actor,
                )
                payload = {
                    'ok': True,
                    'operation': 'release_rollback',
                    'message': '已选择上一代码制品，数据库版本保持不变；请重启全部 worker',
                    'installedVersion': plugin.installed_version,
                    'generation': selected.generation,
                    'restartRequired': True,
                    **artifact_payload(artifact),
                }
                await self._audit(db, payload, actor)
                await db.commit()
            return payload

    @staticmethod
    async def _audit(db: Any, payload: dict[str, Any], actor: str | None) -> None:
        """
        在调用方事务中记录发布操作审计，审计失败时向上传播异常。

        :param db: 当前操作使用的数据库会话
        :param payload: 需要写入审计的操作结果数据
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :return: None
        """
        await PluginService.add_plugin_operation_log_services(
            db, {**payload, 'operatedBy': actor}, dry_run=False, continue_on_error=False
        )
