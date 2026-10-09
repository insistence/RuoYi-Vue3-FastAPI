import asyncio
import hashlib
import json
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from config.database import DataSourceRegistry
from plugins.core.deployment.catalog import PluginArtifactCatalog
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.deployment.state import RUNTIME_PLUGIN_ID
from plugins.core.discovery.scanner import PluginDiscoveryError
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.dao.release_dao import PluginReleaseDao
from utils.log_util import logger
from utils.time_util import TimezoneUtil


@dataclass(frozen=True)
class WorkerTarget:
    """
    当前宿主进程固定的插件目标、发布代际和维护准备状态快照。
    """

    plugin_id: str
    digest: str
    generation: str
    enabled: bool
    prepared: bool


class PluginReleaseWorker:
    """
    宿主发布快照与心跳上报器，注册时与维护服务共用全局锁。
    """

    def __init__(
        self,
        config: PluginDeploymentConfig,
        *,
        session_factory: Any = None,
        dao: Any = PluginReleaseDao,
    ) -> None:
        """
        初始化当前宿主进程的发布快照与心跳上报器。

        :param config: 制品发布配置快照
        :param session_factory: 异步数据库会话工厂，未提供时使用宿主数据源
        :param dao: 制品、发布目标及进程报告的数据访问接口
        :return: None
        """
        self.config = config
        self.session_factory = session_factory or DataSourceRegistry.session
        self.dao = dao
        self.catalog = PluginArtifactCatalog(config, session_factory=self.session_factory, dao=dao)
        self.worker_id = uuid4().hex
        self.targets: tuple[WorkerTarget, ...] = ()
        self.reserved_ids: set[str] = set()
        self.versions: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self.state = 'starting'
        self.task: asyncio.Task | None = None
        self.app: Any = None
        self.registered = False

    async def start(self, app: Any, builder: Any, lifecycle_lock: Any, *, timeout: float = 60) -> None:
        """
        在生命周期锁内登记宿主快照，验证目标制品并启动心跳上报。

        :param app: 当前宿主应用对象
        :param builder: 接收制品发现快照的插件运行时构建器
        :param lifecycle_lock: 与插件维护发布共用的生命周期锁
        :param timeout: 等待生命周期锁的最长时间，单位为秒
        :return: None
        :raises TimeoutError: 在等待时限内未能取得维护发布锁
        """
        self.config.require_enabled()
        self.app = app
        deadline = time.monotonic() + timeout
        while True:
            async with lifecycle_lock.lock(RUNTIME_PLUGIN_ID, 'release_snapshot') as lock:
                if lock.acquired:
                    await self._register_snapshot()
                    break
            if time.monotonic() >= deadline:
                raise TimeoutError('等待插件维护发布锁超时')
            await asyncio.sleep(min(1, self.config.heartbeat_seconds))
        # 验签和大文件散列期间也维持宿主存活，维护命令不能越过启动中的进程。
        self.task = asyncio.create_task(self._heartbeat(), name=f'plugin-release-{self.worker_id}')
        plugins = []
        for target in self.targets:
            try:
                if not target.prepared:
                    raise ValueError('目标制品缺少匹配的数据结构维护准备证据')
                artifact = await self.catalog.get(target.digest)
                if artifact.plugin_id != target.plugin_id:
                    raise ValueError('发布目标与制品插件 ID 不一致')
                self.versions[target.plugin_id] = artifact.version
                plugins.append(self.catalog.discovered(artifact, target.generation))
            except Exception as exc:  # noqa: PERF203 - 单个制品损坏不能阻断其他插件。
                self.errors[target.plugin_id] = str(exc)[:2000]
                logger.error(f'插件发布目标验证失败：{target.plugin_id}，{exc}')
        errors = [
            PluginDiscoveryError(None, self.config.store_root / plugin_id, message)
            for plugin_id, message in self.errors.items()
        ]
        builder.set_artifact_plugins(plugins, reserved_ids=self.reserved_ids, errors=errors)
        if self.targets:
            # 延迟导入也不能在已签名的目录内产生未登记字节码。
            sys.dont_write_bytecode = True
        await self.report()

    async def _register_snapshot(self) -> None:
        """
        固定当前发布目标和保留插件ID，并登记正在启动的宿主进程。

        :return: None
        """
        async with self.session_factory() as db:
            targets = []
            # 即使尚未选择目标，已导入制品的 ID 也不能回退为同名源码插件。
            self.reserved_ids = {item.plugin_id for item in await self.dao.list_artifacts(db)}
            for release in await self.dao.list_releases(db):
                self.reserved_ids.add(release.plugin_id)
                if not release.target_digest:
                    continue
                plugin = await PluginDao.get_plugin_by_id(db, release.plugin_id)
                prepared = bool(
                    plugin
                    and plugin.installed_version
                    and release.prepare_status == 'prepared'
                    and release.prepared_digest == release.target_digest
                    and release.prepared_version == plugin.installed_version
                )
                targets.append(
                    WorkerTarget(
                        release.plugin_id,
                        release.target_digest,
                        release.generation,
                        bool(plugin and plugin.enabled == '0'),
                        prepared,
                    )
                )
            self.targets = tuple(sorted(targets, key=lambda item: item.plugin_id))
            await self.dao.upsert_worker_report(
                db,
                worker_id=self.worker_id,
                plugin_id=RUNTIME_PLUGIN_ID,
                state='starting',
                heartbeat_time=TimezoneUtil.utc_now(),
            )
            await db.commit()
            self.registered = True

    def generation(self, base: str) -> str:
        """
        将基础启动代际与目标快照及保留插件ID合成为就绪屏障代际。

        :param base: 宿主提供的基础启动代际标识
        :return: 当前启动快照对应的小写 SHA256 代际摘要
        """
        payload = [(item.plugin_id, item.digest, item.generation, item.enabled) for item in self.targets]
        return hashlib.sha256(
            json.dumps([base, payload, sorted(self.reserved_ids)], separators=(',', ':')).encode()
        ).hexdigest()

    async def assert_snapshot_current(self) -> None:
        """
        在导入或就绪前确认数据库发布目标仍与当前进程快照一致。

        :return: None
        :raises RuntimeError: 当前发布目标或代际与进程启动快照不一致
        """
        async with self.session_factory() as db:
            current = [
                (item.plugin_id, item.target_digest, item.generation)
                for item in await self.dao.list_releases(db)
                if item.target_digest
            ]
        expected = [(item.plugin_id, item.digest, item.generation) for item in self.targets]
        if sorted(current) != expected:
            raise RuntimeError('插件发布目标在当前 worker 启动过程中变化，请重新启动')

    async def ready(self) -> None:
        """
        确认发布快照未变后上报宿主就绪及各插件的实际状态。

        :return: None
        :raises RuntimeError: 当前发布目标或代际在启动过程中发生变化
        """
        await self.assert_snapshot_current()
        self.state = 'ready'
        await self.report()

    def _plugin_state(self, target: WorkerTarget) -> tuple[str, str | None]:
        """
        根据实际激活结果生成单个目标的进程报告状态。

        :param target: 当前进程固定的单个插件发布目标快照
        :return: 报告状态与可选错误说明
        """
        if self.state in {'failed', 'stopped'}:
            return self.state, self.errors.get(target.plugin_id)
        if target.plugin_id in self.errors:
            return 'failed', self.errors[target.plugin_id]
        if not target.enabled:
            return 'stopped', None
        if self.state == 'starting':
            return 'starting', None
        runtime = getattr(self.app.state, 'plugin_explicit_runtime', None)
        loaded = getattr(runtime, 'loaded', {}).get(target.plugin_id)
        if loaded is not None and loaded.active and (loaded.lifespan is None or loaded.lifespan.ready):
            discovered = loaded.plugin.discovered_plugin
            if discovered.artifact_digest == target.digest and discovered.artifact_generation == target.generation:
                return 'ready', None
        return 'failed', '当前 worker 未完成目标制品激活或健康检查'

    async def report(self) -> None:
        """
        以同一心跳时间写入宿主状态及全部目标插件的实际加载状态。

        :return: None
        """
        if not self.registered:
            return
        now = TimezoneUtil.utc_now()
        async with self.session_factory() as db:
            await self.dao.upsert_worker_report(
                db, worker_id=self.worker_id, plugin_id=RUNTIME_PLUGIN_ID, state=self.state, heartbeat_time=now
            )
            for target in self.targets:
                state, error = self._plugin_state(target)
                await self.dao.upsert_worker_report(
                    db,
                    worker_id=self.worker_id,
                    plugin_id=target.plugin_id,
                    state=state,
                    heartbeat_time=now,
                    artifact_digest=target.digest,
                    version=self.versions.get(target.plugin_id),
                    generation=target.generation,
                    error=error,
                )
            await db.commit()

    async def _heartbeat(self) -> None:
        """
        周期性刷新进程报告，数据库暂不可用时保留旧报告等待自然过期。

        :return: None
        """
        while True:
            await asyncio.sleep(self.config.heartbeat_seconds)
            try:
                await self.report()
            except Exception:
                # 数据库暂不可用时不伪造就绪时间；旧报告会按 TTL 过期。
                logger.exception('插件 worker 心跳上报失败')

    async def stop(self, *, failed: bool = False) -> None:
        """
        停止心跳任务，并上报正常停止或宿主失败状态。

        :param failed: 是否以失败状态结束宿主报告，为 False 时报告正常停止
        :return: None
        """
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None
        self.state = 'failed' if failed else 'stopped'
        await self.report()
