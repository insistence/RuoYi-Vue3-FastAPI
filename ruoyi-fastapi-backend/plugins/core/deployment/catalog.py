import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from config.database import DataSourceRegistry
from plugins.core.artifacts import ArtifactStore, StoredArtifact, verify_artifact
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.discovery.scanner import DiscoveredPlugin, PluginScanner
from plugins.core.management.dao.release_dao import PluginReleaseDao
from plugins.core.manifest.schema import EXPLICIT_MANIFEST_VERSION
from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock
from plugins.core.validation.manifest import PluginManifestChecker
from plugins.core.validation.structure import PluginStructureChecker


def artifact_payload(artifact: Any) -> dict[str, Any]:
    """
    构建只包含制品身份的返回数据，避免以文件路径授予发布权限。

    :param artifact: 已完成签名和文件校验的制品对象
    :return: 插件ID、版本、摘要和签名密钥标识组成的字典
    """
    return {
        'pluginId': artifact.plugin_id,
        'version': artifact.version,
        'digest': artifact.digest,
        'keyId': artifact.key_id,
    }


class PluginArtifactCatalog:
    """
    已验证制品文件与数据库索引之间的访问服务。
    """

    def __init__(
        self,
        config: PluginDeploymentConfig,
        *,
        session_factory: Any = None,
        dao: Any = PluginReleaseDao,
        lifecycle_lock: Any = None,
    ) -> None:
        """
        初始化不可变制品目录与数据库索引的访问服务。

        :param config: 制品发布配置快照
        :param session_factory: 异步数据库会话工厂，未提供时使用宿主数据源
        :param dao: 制品、发布目标及进程报告的数据访问接口
        :param lifecycle_lock: 与维护、清理和轮换共用的全局生命周期锁
        :return: None
        """
        self.config = config
        self.session_factory = session_factory or DataSourceRegistry.session
        self.dao = dao
        self.lifecycle_lock = lifecycle_lock or RedisPluginLifecycleLock()

    def require_no_pending_maintenance(self) -> None:
        """
        拒绝在文件与索引尚未完成恢复时导入或加载制品。

        :return: None
        """
        pending = self.config.store_root / '.maintenance'
        ArtifactStore._assert_real_path(pending)
        if pending.exists() and any(pending.glob('*.json')):
            raise ValueError('存在未完成的制品维护，请先执行 artifact reconcile')

    @property
    def store(self) -> ArtifactStore:
        """
        根据当前配置创建受限的不可变制品存储。

        :return: 制品存储实例
        """
        self.config.require_enabled()
        return ArtifactStore(self.config.store_root)

    def reject_source_conflict(self, plugin_id: str) -> None:
        """
        检查目标插件ID是否与已有源码目录冲突。

        :param plugin_id: 插件ID
        :return: None
        :raises ValueError: 源码插件目录与制品插件ID冲突
        """
        if (self.config.backend_root / 'plugins' / plugin_id).exists():
            raise ValueError(f'插件 {plugin_id} 已存在源码目录，不能与制品发布同时使用')

    def discovered(self, artifact: StoredArtifact, generation: str | None = None) -> DiscoveredPlugin:
        """
        将验证后的制品转换为带发布身份的插件发现结果。

        :param artifact: 已完成签名和文件校验的制品对象
        :param generation: 附加到发现结果的发布代际，静态维护检查时可不提供
        :return: 指向不可变部署目录的插件发现对象
        """
        plugin = PluginScanner(artifact.plugin_path.parent).load_manifest(artifact.plugin_path / 'plugin.yaml')
        return replace(plugin, artifact_digest=artifact.digest, artifact_generation=generation)

    def validate_candidate(self, artifact: StoredArtifact) -> None:
        """
        校验候选制品的交付协议、发布者授权及静态平台兼容性。

        :param artifact: 已完成签名和文件校验的制品对象
        :return: None
        :raises ValueError: 协议、信任授权、源码目录或运行平台校验失败
        """
        if (
            artifact.manifest.manifest_version != EXPLICIT_MANIFEST_VERSION
            or artifact.manifest.frontend.delivery.type not in {'none', 'bundle'}
        ):
            raise ValueError('制品发布只接受 manifest v2 和 none/bundle 前端')
        self.config.authorize_publisher(artifact.key_id, artifact.plugin_id)
        self.reject_source_conflict(artifact.plugin_id)
        plugin = self.discovered(artifact)
        compatibility = PluginManifestChecker(backend_root=self.config.backend_root).check(plugin.manifest)
        structure = PluginStructureChecker(self.config.backend_root).check(plugin)
        errors = [item.message for item in compatibility.error_issues]
        errors.extend(item.message for item in structure.failed_items)
        if errors:
            raise ValueError('制品静态检查失败：' + '；'.join(errors))

    async def import_artifact(
        self, path: Path | str, *, actor: str | None = None, dry_run: bool = False
    ) -> dict[str, Any]:
        """
        验证并登记制品，不选择发布目标、不安装依赖或运行插件代码。

        :param path: 待导入的签名 rpk 文件路径
        :param actor: 本次操作的执行者，未提供时不记录执行者名称
        :param dry_run: 是否只执行预检而不写入文件或数据库
        :return: 制品身份及导入或预检结果
        :raises ValueError: 制品完整性、发布者授权或部署兼容性校验失败
        """
        self.config.require_enabled()
        keys = self.config.trusted_keys()
        if dry_run:
            verified = await asyncio.to_thread(verify_artifact, path, keys)
            self.config.authorize_publisher(verified.key_id, verified.plugin_id)
            self.reject_source_conflict(verified.plugin_id)
            return {
                'ok': True,
                'dryRun': True,
                'message': '容器验签和摘要检查通过；平台及目录结构将在正式导入的临时目录中检查',
                **artifact_payload(verified),
            }
        async with self.lifecycle_lock.lock('__artifacts__', 'artifact_import') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            self.require_no_pending_maintenance()
            return await self._import_locked(path, keys, actor)

    async def _import_locked(self, path: Path | str, keys: dict[str, Any], actor: str | None) -> dict[str, Any]:
        """
        持有全局维护锁时完成文件发布和索引事务，取消时先等待文件操作结束。

        :param path: 已签名制品路径
        :param keys: 当前可信公钥
        :param actor: 操作者
        :return: 导入后的制品身份
        """
        work = asyncio.create_task(
            asyncio.to_thread(self.store.import_artifact, path, keys, validate_candidate=self.validate_candidate)
        )
        try:
            stored = await asyncio.shield(work)
        except asyncio.CancelledError:
            await work
            raise
        # 文件与数据库不能共享事务。数据库失败时保留已验签不可变对象，重试可幂等登记。
        async with self.session_factory() as db:
            await self.dao.register_artifact(
                db,
                digest=stored.digest,
                plugin_id=stored.plugin_id,
                version=stored.version,
                key_id=stored.key_id,
                relative_path=stored.root_path.relative_to(self.config.store_root).as_posix(),
                manifest_json=json.dumps(stored.manifest.model_dump(mode='json', by_alias=True), ensure_ascii=False),
                created_by=actor,
            )
            await db.commit()
        return {'ok': True, 'message': '已导入并验证制品，尚未选择发布目标', **artifact_payload(stored)}

    async def get(self, digest: str) -> StoredArtifact:
        """
        根据数据库索引定位制品，并在返回前重新验证签名和全部文件。

        :param digest: 制品规范元数据的小写 SHA256 摘要
        :return: 当前信任配置下通过验证的制品存储对象
        :raises ValueError: 制品不存在、索引不一致或当前信任及文件校验失败
        """
        self.require_no_pending_maintenance()
        async with self.session_factory() as db:
            record = await self.dao.get_artifact(db, digest)
            if record is None:
                raise ValueError('制品尚未导入')
            identity = (record.plugin_id, record.version, record.digest, record.key_id)
            relative_path = record.relative_path
        stored = await asyncio.to_thread(
            self.store.verify_stored, self.config.store_root / relative_path, self.config.trusted_keys()
        )
        if (stored.plugin_id, stored.version, stored.digest, stored.key_id) != identity:
            raise ValueError('制品索引与实际验证内容不一致')
        self.validate_candidate(stored)
        return stored

    async def list_artifacts(self, plugin_id: str | None = None) -> dict[str, Any]:
        """
        查询数据库中已登记制品的身份信息。

        :param plugin_id: 可选的插件ID过滤条件，为 None 时查询全部制品
        :return: 已登记制品的插件ID、版本、摘要和签名密钥标识列表
        """
        self.config.require_enabled()
        async with self.session_factory() as db:
            artifacts = await self.dao.list_artifacts(db, plugin_id)
            return {'ok': True, 'artifacts': [artifact_payload(item) for item in artifacts]}
