import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, update

from plugins.core.artifacts import ArtifactStore, verify_artifact
from plugins.core.artifacts.schema import DIGEST_PATTERN, safe_artifact_path, strict_json
from plugins.core.deployment.service import PluginDeploymentService
from plugins.core.management.entity.do.release_models import SysPluginArtifact
from utils.time_util import TimezoneUtil

MAX_INVENTORY_OBJECTS = 10000
MAX_JOURNAL_BYTES = 64 * 1024
OBJECT_PATH_PARTS = 3


class PluginArtifactMaintenanceService(PluginDeploymentService):
    """
    停机维护制品存储，使用可恢复日志连接文件变更与数据库事务。
    """

    def _object_path(self, relative: str) -> Path:
        """
        解析规范的制品目录，拒绝越界、链接和非摘要目录。

        :param relative: 存储内的插件、版本和摘要路径
        :return: 已检查的绝对目录
        """
        parts = safe_artifact_path(relative).parts
        if len(parts) != OBJECT_PATH_PARTS or not DIGEST_PATTERN.fullmatch(parts[-1]):
            raise ValueError('制品维护目录必须是 plugin/version/digest')
        path = self.catalog.store.root.joinpath(*parts)
        ArtifactStore._assert_real_path(path)
        return path

    def _pending(self) -> list[Path]:
        """
        列出本服务创建的维护日志，不递归扫描外部路径。

        :return: 按摘要排序的维护日志路径
        """
        root = self.catalog.store.root / '.maintenance'
        ArtifactStore._assert_real_path(root)
        return sorted(root.glob('*.json')) if root.exists() else []

    def _paths(self) -> list[Path]:
        """
        有界枚举普通制品目录，在进入每级目录前排除链接。

        :return: 已检查边界的摘要目录列表
        """
        root = self.catalog.store.root
        result = []
        if not root.exists():
            return result
        for plugin in root.iterdir():
            if plugin.name.startswith('.'):
                continue
            ArtifactStore._assert_real_path(plugin)
            if not plugin.is_dir():
                continue
            for version in plugin.iterdir():
                ArtifactStore._assert_real_path(version)
                if not version.is_dir():
                    continue
                for path in version.iterdir():
                    ArtifactStore._assert_real_path(path)
                    if DIGEST_PATTERN.fullmatch(path.name) and path.is_dir():
                        result.append(path)
                        if len(result) > MAX_INVENTORY_OBJECTS:
                            raise ValueError('制品数量超过单次维护检查上限')
        return result

    async def inspect(self, *, keep_last: int = 2, min_age_days: int = 7) -> dict[str, Any]:
        """
        核对文件、索引和发布引用，生成无写入的保留与清理计划。

        :param keep_last: 每个插件至少保留的最近导入制品数量
        :param min_age_days: 制品最短保留天数
        :return: 完整检查结果、候选摘要与计划摘要
        """
        self.config.require_enabled()
        if keep_last < 0 or min_age_days < 0:
            raise ValueError('保留数量和天数不能为负数')
        async with self.session_factory() as db:
            records = {row.digest: row for row in await self.dao.list_artifacts(db)}
            releases = await self.dao.list_releases(db)
            workers = await self.dao.list_worker_reports(db)
        protected: dict[str, set[str]] = {}
        for release in releases:
            for field in ('target_digest', 'previous_digest', 'prepared_digest'):
                digest = getattr(release, field)
                if digest:
                    protected.setdefault(digest, set()).add(field)
        for worker in workers:
            if worker.artifact_digest and worker.state != 'stopped':
                protected.setdefault(worker.artifact_digest, set()).add('worker_reference')
        recent: dict[str, int] = {}
        for record in sorted(records.values(), key=lambda item: (item.create_time, item.digest), reverse=True):
            count = recent.get(record.plugin_id, 0)
            if count < keep_last:
                protected.setdefault(record.digest, set()).add('keep_last')
            recent[record.plugin_id] = count + 1
        paths = {path.relative_to(self.catalog.store.root).as_posix(): path for path in self._paths()}
        for record in records.values():
            # 索引只能定位规范目录，不能授予任意文件系统路径权限。
            paths.setdefault(record.relative_path, self._object_path(record.relative_path))
        keys = self.config.trusted_keys()
        cutoff = (TimezoneUtil.utc_now() - timedelta(days=min_age_days)).timestamp()
        rows = []
        for relative, path in sorted(paths.items()):
            digest = path.name
            record = records.get(digest)
            reasons = set(protected.get(digest, set()))
            row = {'digest': digest, 'relativePath': relative, 'registered': record is not None}
            await asyncio.to_thread(self._inspect_object, row, path, record, reasons, cutoff, keys)
            rows.append(row)
        pending = [path.stem for path in self._pending()]
        basis = {'keepLast': keep_last, 'minAgeDays': min_age_days, 'objects': rows, 'pending': pending}
        plan_id = hashlib.sha256(json.dumps(basis, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        return {
            'ok': True,
            'dryRun': True,
            **basis,
            'planId': plan_id,
            'candidates': [row['digest'] for row in rows if row['candidate']],
        }

    def _inspect_object(
        self, row: dict[str, Any], path: Path, record: Any, reasons: set[str], cutoff: float, keys: dict[str, Any]
    ) -> None:
        """
        校验单个对象并附加不可清理原因。

        :param row: 待补充的对象结果
        :param path: 规范制品路径
        :param record: 可选数据库索引
        :param reasons: 当前保护原因
        :param cutoff: 最短保留时间边界
        :param keys: 当前可信公钥
        :return: None
        """
        relative = row['relativePath']
        try:
            stored = self.catalog.store.verify_stored(path, keys)
            self.catalog.validate_candidate(stored)
            if record is not None and (
                record.relative_path != relative
                or (record.plugin_id, record.version, record.key_id)
                != (stored.plugin_id, stored.version, stored.key_id)
            ):
                raise ValueError('制品索引与实际身份不一致')
            created = record.create_time.timestamp() if record is not None else path.stat().st_mtime
            if created > cutoff:
                reasons.add('min_age')
            row.update(pluginId=stored.plugin_id, version=stored.version, keyId=stored.key_id)
            row['status'] = 'registered' if record is not None else 'orphan'
            row['bytes'] = sum(item.size for item in stored.files)
        except (ValueError, OSError) as exc:
            row['status'] = 'invalid' if path.exists() else 'missing'
            row['error'] = str(exc)
            reasons.add('verification_failed')
        row['protectedBy'] = sorted(reasons)
        row['candidate'] = not reasons

    def _write_journal(self, journal: dict[str, Any]) -> Path:
        """
        在任何文件变更前独占写入并刷盘维护日志。

        :param journal: 仅包含制品身份与恢复材料的日志
        :return: 已持久化日志路径
        """
        root = self.catalog.store.root / '.maintenance'
        self.catalog.store._mkdir(root)
        path = root / f'{journal["digest"]}.json'
        ArtifactStore._assert_real_path(path)
        with path.open('xb') as stream:
            stream.write(json.dumps(journal, ensure_ascii=False, sort_keys=True).encode())
            stream.flush()
            os.fsync(stream.fileno())
        return path

    def _quarantine(self, digest: str) -> Path:
        """
        获取维护日志所属摘要的隔离目录。

        :param digest: 已校验的制品摘要
        :return: 存储内部的隔离路径
        """
        if not DIGEST_PATTERN.fullmatch(digest):
            raise ValueError('维护日志摘要无效')
        root = self.catalog.store.root / '.maintenance' / 'objects'
        self.catalog.store._mkdir(root)
        path = root / digest
        ArtifactStore._assert_real_path(path)
        return path

    def _remove_quarantine(self, path: Path, digest: str) -> None:
        """
        再次验证隔离对象及其删除边界，只移除已确认摘要的完整对象。

        :param path: 本次维护隔离目录
        :param digest: 授权清理的摘要
        :return: None
        """
        root = (self.catalog.store.root / '.maintenance' / 'objects').resolve()
        ArtifactStore._assert_real_path(path)
        if path.parent.resolve() != root or path.name != digest:
            raise ValueError('制品清理目录越界')
        stored = self.catalog.store._verify_directory(path, self.config.trusted_keys())
        if stored.digest != digest:
            raise ValueError('隔离制品摘要不一致')
        shutil.rmtree(path)

    async def prune(
        self,
        *,
        keep_last: int = 2,
        min_age_days: int = 7,
        expected_plan: str | None = None,
        dry_run: bool = True,
        maintenance: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """
        按复核后的计划清理未引用制品，默认只预演。

        :param keep_last: 每个插件至少保留的最近导入数量
        :param min_age_days: 最短保留天数
        :param expected_plan: 操作者已核对的计划摘要
        :param dry_run: 是否仅返回计划
        :param maintenance: 是否确认全部宿主进程已停止
        :param actor: 操作者
        :return: 计划或实际清理摘要
        """
        if dry_run:
            return await self.inspect(keep_last=keep_last, min_age_days=min_age_days)
        self._require_maintenance(maintenance)
        async with self.lifecycle_lock.lock('__artifacts__', 'artifact_prune') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            self.catalog.require_no_pending_maintenance()
            plan = await self.inspect(keep_last=keep_last, min_age_days=min_age_days)
            if not expected_plan or plan['planId'] != expected_plan:
                raise ValueError('制品清理计划已变化，请重新预演并核对 --expected-plan')
            removed = []
            for row in plan['objects']:
                if not row['candidate']:
                    continue
                path = self._object_path(row['relativePath'])
                journal = self._write_journal({**row, 'action': 'prune'})
                quarantine = self._quarantine(row['digest'])
                if quarantine.exists():
                    raise ValueError('隔离目录已存在，须先恢复维护日志')
                path.rename(quarantine)
                async with self.session_factory() as db:
                    await db.execute(delete(SysPluginArtifact).where(SysPluginArtifact.digest == row['digest']))
                    await self._audit(db, {**row, 'ok': True, 'operation': 'artifact_prune'}, actor)
                    await db.commit()
                self._remove_quarantine(quarantine, row['digest'])
                journal.unlink()
                removed.append(row['digest'])
            return {'ok': True, 'dryRun': False, 'removed': removed, 'planId': plan['planId']}

    def _replace_signature(self, path: Path, signature: str) -> None:
        """
        在存储内部写入临时签名后原子替换，不改变插件内容和制品摘要。

        :param path: 已验证的制品根目录
        :param signature: 待写入的签名 JSON
        :return: None
        """
        temporary_root = self.catalog.store.root / '.maintenance'
        ArtifactStore._assert_real_path(temporary_root)
        ArtifactStore._assert_real_path(path / 'signature.json')
        descriptor, temporary_name = tempfile.mkstemp(prefix=f'{path.name}-', suffix='.signature', dir=temporary_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(signature.encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path / 'signature.json')
        finally:
            temporary.unlink(missing_ok=True)

    async def rotate_signature(
        self,
        archive: Path,
        *,
        expected_key_id: str,
        maintenance: bool = False,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """
        用新可信签名验证同一摘要的现有字节，再更新签名和索引。

        :param archive: 由新密钥签名且内容完全一致的 rpk
        :param expected_key_id: 最近读取的原签名密钥标识
        :param maintenance: 是否确认全部宿主进程已停止
        :param actor: 操作者
        :return: 保持摘要与版本不变的轮换结果
        """
        self._require_maintenance(maintenance)
        async with self.lifecycle_lock.lock('__artifacts__', 'artifact_rotate_signature') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            self.catalog.require_no_pending_maintenance()
            verified = await asyncio.to_thread(verify_artifact, archive, self.config.trusted_keys())
            self.config.authorize_publisher(verified.key_id, verified.plugin_id)
            async with self.session_factory() as db:
                record = await self.dao.get_artifact(db, verified.digest)
                if record is None or record.key_id != expected_key_id:
                    raise ValueError('制品未登记或签名密钥已变化')
                if verified.key_id == record.key_id:
                    raise ValueError('新旧签名密钥标识必须不同')
                path = self._object_path(record.relative_path)
                new_signature = verified.signature.model_dump_json(by_alias=True)
                stored = self.catalog.store._verify_directory(
                    path, self.config.trusted_keys(), signature_override=new_signature.encode()
                )
                if (stored.plugin_id, stored.version, stored.digest) != (
                    record.plugin_id,
                    record.version,
                    record.digest,
                ) or path.relative_to(self.catalog.store.root).parts != (
                    stored.plugin_id,
                    stored.version,
                    stored.digest,
                ):
                    raise ValueError('轮换制品内容与原索引不一致')
                self.catalog.validate_candidate(stored)
                old_signature = (path / 'signature.json').read_text(encoding='utf-8')
                journal = self._write_journal(
                    {
                        'action': 'rotate',
                        'digest': stored.digest,
                        'relativePath': record.relative_path,
                        'oldKeyId': record.key_id,
                        'newKeyId': stored.key_id,
                        'oldSignature': old_signature,
                        'newSignature': new_signature,
                    }
                )
                self._replace_signature(path, new_signature)
                result = await db.execute(
                    update(SysPluginArtifact)
                    .where(
                        SysPluginArtifact.digest == stored.digest,
                        SysPluginArtifact.key_id == expected_key_id,
                    )
                    .values(key_id=stored.key_id)
                )
                if result.rowcount != 1:
                    raise ValueError('制品签名索引发生并发变化')
                payload = {
                    'ok': True,
                    'operation': 'artifact_rotate_signature',
                    'pluginId': stored.plugin_id,
                    'digest': stored.digest,
                    'version': stored.version,
                    'oldKeyId': expected_key_id,
                    'keyId': stored.key_id,
                }
                await self._audit(db, payload, actor)
                await db.commit()
                journal.unlink()
                return payload

    async def reconcile(self, *, maintenance: bool = False, actor: str | None = None) -> dict[str, Any]:
        """
        依据已提交的数据库状态恢复中断操作，不重新执行发布或迁移。

        :param maintenance: 是否确认全部宿主进程已停止
        :param actor: 操作者
        :return: 已恢复的制品摘要列表
        """
        self._require_maintenance(maintenance)
        restored = []
        async with self.lifecycle_lock.lock('__artifacts__', 'artifact_reconcile') as lock:
            if not lock.acquired:
                raise ValueError(lock.message)
            await self._require_quiescent()
            for journal_path in self._pending():
                ArtifactStore._assert_real_path(journal_path)
                if journal_path.stat().st_size > MAX_JOURNAL_BYTES:
                    raise ValueError('制品维护日志过大')
                journal = strict_json(journal_path.read_bytes())
                digest = journal['digest']
                if not DIGEST_PATTERN.fullmatch(digest) or journal_path.stem != digest:
                    raise ValueError('制品维护日志身份无效')
                path = self._object_path(journal['relativePath'])
                if path.name != digest:
                    raise ValueError('维护日志目录与摘要不一致')
                async with self.session_factory() as db:
                    record = await self.dao.get_artifact(db, digest)
                    if journal['action'] == 'prune':
                        self._recover_prune(journal, path, record)
                    elif journal['action'] == 'rotate':
                        self._recover_rotation(journal, path, record)
                    else:
                        raise ValueError('未知制品维护日志操作')
                    await self._audit(
                        db,
                        {
                            'ok': True,
                            'operation': 'artifact_reconcile',
                            'pluginId': path.parts[-OBJECT_PATH_PARTS],
                            'digest': digest,
                            'recoveredAction': journal['action'],
                        },
                        actor,
                    )
                    await db.commit()
                journal_path.unlink()
                restored.append(digest)
        return {'ok': True, 'restored': restored}

    def _recover_prune(self, journal: dict[str, Any], path: Path, record: Any) -> None:
        """
        根据索引提交结果恢复或清理隔离对象。

        :param journal: 已检查的维护日志
        :param path: 规范制品目录
        :param record: 当前已提交的索引
        :return: None
        """
        digest = journal['digest']
        quarantine = self._quarantine(digest)
        if quarantine.exists():
            if path.exists():
                raise ValueError('原目录和隔离目录同时存在，拒绝自动覆盖')
            stored = self.catalog.store._verify_directory(quarantine, self.config.trusted_keys())
            if stored.digest != digest:
                raise ValueError('隔离对象与日志摘要不一致')
            if record is not None:
                if record.relative_path != journal['relativePath']:
                    raise ValueError('恢复目标与制品索引不一致')
                quarantine.rename(path)
            else:
                self._remove_quarantine(quarantine, digest)
        elif not path.exists() and record is not None:
            raise ValueError('索引仍存在但原目录和隔离目录均已丢失')

    def _recover_rotation(self, journal: dict[str, Any], path: Path, record: Any) -> None:
        """
        根据索引中的密钥恢复签名文件。

        :param journal: 已检查的维护日志
        :param path: 规范制品目录
        :param record: 当前已提交的索引
        :return: None
        """
        digest = journal['digest']
        if record is None or record.relative_path != journal['relativePath']:
            raise ValueError('轮换恢复缺少匹配的制品索引')
        if record.key_id not in {journal['oldKeyId'], journal['newKeyId']}:
            raise ValueError('签名索引已被其他操作更新')
        stored = self.catalog.store._verify_directory(
            path, self.config.trusted_keys(), signature_override=journal['newSignature'].encode()
        )
        if stored.digest != digest or stored.key_id != journal['newKeyId']:
            raise ValueError('轮换恢复签名与日志身份不一致')
        self.catalog.validate_candidate(stored)
        signature = journal['newSignature'] if record.key_id == journal['newKeyId'] else journal['oldSignature']
        self._replace_signature(path, signature)
