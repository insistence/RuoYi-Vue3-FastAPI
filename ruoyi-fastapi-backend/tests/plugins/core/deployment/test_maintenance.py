import base64
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import delete, select

from plugins.core.artifacts import build_artifact
from plugins.core.deployment.maintenance import PluginArtifactMaintenanceService
from plugins.core.management.dao.release_dao import PluginReleaseDao
from plugins.core.management.entity.do.models import SysPluginOperationLog
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker
from plugins.core.runtime.service.lifecycle_lock import NoopPluginLifecycleLock, PluginLifecycleLockResult
from utils.time_util import TimezoneUtil


@pytest_asyncio.fixture
async def maintenance(deployment_config: Any, deployment_sessions: Any, deployment_archive: Path) -> Any:
    """
    创建只使用临时文件和 SQLite 的维护服务。

    :param deployment_config: 隔离部署配置
    :param deployment_sessions: 临时数据库会话
    :param deployment_archive: 测试制品
    :return: 服务与已导入制品
    """
    service = PluginArtifactMaintenanceService(
        deployment_config, session_factory=deployment_sessions, lifecycle_lock=NoopPluginLifecycleLock()
    )
    imported = await service.catalog.import_artifact(deployment_archive)
    stored = await service.catalog.get(imported['digest'])
    return service, stored


@pytest.fixture
def rotated_archive(deployment_config: Any, deployment_source: Path, tmp_path: Path) -> Path:
    """
    生成内容相同、密钥不同的可信制品。

    :param deployment_config: 隔离信任配置
    :param deployment_source: 插件源目录
    :param tmp_path: 临时目录
    :return: 新签名制品路径
    """
    key = Ed25519PrivateKey.generate()
    trust = json.loads(deployment_config.trust_file.read_text())
    trust['keys'].append(
        {
            'keyId': 'publisher-next',
            'pluginIds': ['artifact_demo'],
            'publicKey': base64.b64encode(
                key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            ).decode(),
        }
    )
    deployment_config.trust_file.write_text(json.dumps(trust), encoding='utf-8')
    path = tmp_path / 'rotated.rpk'
    build_artifact(deployment_source, path, key, 'publisher-next')
    return path


@pytest.mark.asyncio
async def test_prune_defaults_are_readonly_and_keep_recent(maintenance: Any) -> None:
    """
    验证默认预演保留最近导入对象。

    :param maintenance: 维护服务与制品
    :return: None
    """
    service, stored = maintenance
    plan = await service.prune()
    assert plan['dryRun'] and not plan['candidates']
    assert set(plan['objects'][0]['protectedBy']) == {'keep_last', 'min_age'}
    assert stored.root_path.exists() and not service._pending()


@pytest.mark.asyncio
@pytest.mark.parametrize('reference', ['target_digest', 'previous_digest', 'prepared_digest', 'worker'])
async def test_prune_protects_release_and_stale_worker_references(maintenance: Any, reference: str) -> None:
    """
    验证发布、回滚和过期但未停止的进程引用均阻止清理。

    :param maintenance: 维护服务与制品
    :param reference: 受保护引用类型
    :return: None
    """
    service, stored = maintenance
    async with service.session_factory() as db:
        if reference == 'worker':
            db.add(
                SysPluginWorker(
                    worker_id=uuid4().hex,
                    plugin_id=stored.plugin_id,
                    artifact_digest=stored.digest,
                    state='ready',
                    heartbeat_time=TimezoneUtil.utc_now() - timedelta(days=30),
                )
            )
        else:
            db.add(SysPluginRelease(plugin_id=stored.plugin_id, generation=uuid4().hex, **{reference: stored.digest}))
        await db.commit()
    plan = await service.prune(keep_last=0, min_age_days=0)
    assert plan['candidates'] == []
    assert plan['objects'][0]['protectedBy'] == ['worker_reference' if reference == 'worker' else reference]


@pytest.mark.asyncio
@pytest.mark.parametrize('orphan', [False, True])
async def test_prune_removes_only_reviewed_objects_and_audits(maintenance: Any, orphan: bool) -> None:
    """
    验证已登记和孤儿对象均须按计划清理，并写入审计。

    :param maintenance: 维护服务与制品
    :param orphan: 是否模拟索引未提交的孤儿对象
    :return: None
    """
    service, stored = maintenance
    if orphan:
        async with service.session_factory() as db:
            await db.execute(delete(SysPluginArtifact))
            await db.commit()
    plan = await service.prune(keep_last=0, min_age_days=0)
    assert plan['candidates'] == [stored.digest]
    result = await service.prune(
        keep_last=0, min_age_days=0, expected_plan=plan['planId'], dry_run=False, maintenance=True, actor='test'
    )
    assert result['removed'] == [stored.digest]
    assert not stored.root_path.exists() and not service._pending()
    async with service.session_factory() as db:
        assert await db.get(SysPluginArtifact, stored.digest) is None
        assert len((await db.scalars(select(SysPluginOperationLog))).all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['changed-plan', 'missing-maintenance', 'live-worker'])
async def test_prune_guards_before_mutating(maintenance: Any, failure: str) -> None:
    """
    验证计划、维护确认和存活进程检查均早于文件变更。

    :param maintenance: 维护服务与制品
    :param failure: 待验证的拒绝原因
    :return: None
    """
    service, stored = maintenance
    plan = await service.prune(keep_last=0, min_age_days=0)
    if failure == 'live-worker':
        async with service.session_factory() as db:
            db.add(
                SysPluginWorker(
                    worker_id=uuid4().hex, plugin_id='__runtime__', state='ready', heartbeat_time=TimezoneUtil.utc_now()
                )
            )
            await db.commit()
    with pytest.raises(ValueError):
        await service.prune(
            keep_last=0,
            min_age_days=0,
            expected_plan='changed' if failure == 'changed-plan' else plan['planId'],
            dry_run=False,
            maintenance=failure != 'missing-maintenance',
        )
    assert stored.root_path.exists() and not service._pending()


@pytest.mark.asyncio
async def test_tampered_objects_are_reported_and_never_pruned(maintenance: Any) -> None:
    """
    验证损坏内容不会自动获得删除资格。

    :param maintenance: 维护服务与制品
    :return: None
    """
    service, stored = maintenance
    (stored.plugin_path / '__init__.py').write_text('tampered')
    plan = await service.prune(keep_last=0, min_age_days=0)
    assert plan['objects'][0]['status'] == 'invalid'
    assert plan['candidates'] == []


@pytest.mark.asyncio
async def test_interrupted_prune_restores_before_commit_and_finishes_after_commit(
    maintenance: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    验证事务失败后恢复原目录，提交成功后恢复继续清理。

    :param maintenance: 维护服务与制品
    :param monkeypatch: 故障注入工具
    :return: None
    """
    service, stored = maintenance
    plan = await service.prune(keep_last=0, min_age_days=0)
    with monkeypatch.context() as patcher:
        patcher.setattr(service, '_audit', AsyncMock(side_effect=RuntimeError('audit failed')))
        with pytest.raises(RuntimeError):
            await service.prune(
                keep_last=0, min_age_days=0, expected_plan=plan['planId'], dry_run=False, maintenance=True
            )
    with pytest.raises(ValueError, match='reconcile'):
        await service.catalog.get(stored.digest)
    with pytest.raises(ValueError, match='reconcile'):
        service.catalog.require_no_pending_maintenance()
    assert (await service.reconcile(maintenance=True))['restored'] == [stored.digest]
    assert (await service.catalog.get(stored.digest)).digest == stored.digest
    plan = await service.prune(keep_last=0, min_age_days=0)
    with monkeypatch.context() as patcher:
        patcher.setattr(service, '_remove_quarantine', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError):
            await service.prune(
                keep_last=0, min_age_days=0, expected_plan=plan['planId'], dry_run=False, maintenance=True
            )
    await service.reconcile(maintenance=True)
    assert not service._pending() and not service._quarantine(stored.digest).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke_old', [False, True])
async def test_rotation_preserves_content_digest_and_accepts_revoked_old_key(
    maintenance: Any,
    rotated_archive: Path,
    revoke_old: bool,
) -> None:
    """
    验证新签名可独立证明现有内容，旧密钥撤销不阻止恢复可信签名。

    :param maintenance: 维护服务与制品
    :param rotated_archive: 新密钥签名制品
    :param revoke_old: 是否撤销旧密钥
    :return: None
    """
    service, stored = maintenance
    original = (stored.plugin_path / '__init__.py').read_bytes()
    if revoke_old:
        trust = json.loads(service.config.trust_file.read_text())
        trust['keys'][0]['enabled'] = False
        service.config.trust_file.write_text(json.dumps(trust), encoding='utf-8')
    result = await service.rotate_signature(rotated_archive, expected_key_id='publisher', maintenance=True)
    assert result['digest'] == stored.digest and result['keyId'] == 'publisher-next'
    assert (await service.catalog.get(stored.digest)).key_id == 'publisher-next'
    assert (stored.plugin_path / '__init__.py').read_bytes() == original
    assert not service._pending()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['tampered', 'wrong-key', 'publisher-scope'])
async def test_rotation_refuses_invalid_content_or_identity(
    maintenance: Any, rotated_archive: Path, failure: str
) -> None:
    """
    验证内容、索引 CAS 和发布者授权均在签名替换前检查。

    :param maintenance: 维护服务与制品
    :param rotated_archive: 新签名制品
    :param failure: 故障类型
    :return: None
    """
    service, stored = maintenance
    signature = (stored.root_path / 'signature.json').read_bytes()
    if failure == 'tampered':
        (stored.plugin_path / '__init__.py').write_text('tampered')
    if failure == 'publisher-scope':
        trust = json.loads(service.config.trust_file.read_text())
        trust['keys'][1]['pluginIds'] = ['other_plugin']
        service.config.trust_file.write_text(json.dumps(trust), encoding='utf-8')
    with pytest.raises(ValueError):
        await service.rotate_signature(
            rotated_archive, expected_key_id='wrong' if failure == 'wrong-key' else 'publisher', maintenance=True
        )
    assert (stored.root_path / 'signature.json').read_bytes() == signature
    assert not service._pending()


@pytest.mark.asyncio
async def test_failed_rotation_reconciles_to_committed_key(
    maintenance: Any,
    rotated_archive: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    验证签名替换后事务失败可恢复旧签名并再次成功轮换。

    :param maintenance: 维护服务与制品
    :param rotated_archive: 新签名制品
    :param monkeypatch: 故障注入工具
    :return: None
    """
    service, stored = maintenance
    with monkeypatch.context() as patcher:
        patcher.setattr(service, '_audit', AsyncMock(side_effect=RuntimeError('audit failed')))
        with pytest.raises(RuntimeError):
            await service.rotate_signature(rotated_archive, expected_key_id='publisher', maintenance=True)
    assert json.loads((stored.root_path / 'signature.json').read_text())['keyId'] == 'publisher-next'
    await service.reconcile(maintenance=True)
    assert (await service.catalog.get(stored.digest)).key_id == 'publisher'
    await service.rotate_signature(rotated_archive, expected_key_id='publisher', maintenance=True)
    assert (await service.catalog.get(stored.digest)).key_id == 'publisher-next'


@pytest.mark.asyncio
async def test_reconcile_rejects_path_escape(maintenance: Any) -> None:
    """
    验证篡改维护日志不能指向存储外路径。

    :param maintenance: 维护服务与制品
    :return: None
    """
    service, stored = maintenance
    service._write_journal({'digest': stored.digest, 'relativePath': '../outside', 'action': 'prune'})
    with pytest.raises(ValueError, match='路径'):
        await service.reconcile(maintenance=True)
    assert stored.root_path.exists()


@pytest.mark.asyncio
async def test_import_holds_lifecycle_lock_until_index_commit(maintenance: Any, deployment_archive: Path) -> None:
    """
    验证导入在写索引和提交完成前不会释放与清理共用的生命周期锁。

    :param maintenance: 维护服务与制品
    :param deployment_archive: 已验证测试制品
    :return: None
    """
    service, stored = maintenance
    events = []

    class TrackingLock:
        """
        记录文件发布和索引写入是否在同一锁范围内。
        """

        @asynccontextmanager
        async def lock(self, plugin_id: str, operation: str) -> AsyncIterator[PluginLifecycleLockResult]:
            """
            记录导入锁进入与退出顺序。

            :param plugin_id: 生命周期操作命名空间
            :param operation: 操作类型
            :return: 已获取锁的上下文
            """
            assert (plugin_id, operation) == ('__artifacts__', 'artifact_import')
            events.append('locked')
            yield PluginLifecycleLockResult(acquired=True)
            async with service.session_factory() as db:
                assert await db.get(SysPluginArtifact, stored.digest) is not None
            events.append('released')

    class TrackingDao(PluginReleaseDao):
        """
        记录索引登记时锁仍有效。
        """

        @classmethod
        async def register_artifact(cls, db: Any, **values: Any) -> SysPluginArtifact:
            """
            保留真实数据库写入，仅添加锁范围断言。

            :param db: 测试数据库会话
            :param values: 制品身份和索引数据
            :return: 已登记的制品记录
            """
            assert events == ['locked']
            events.append('registered')
            return await super().register_artifact(db, **values)

    async with service.session_factory() as db:
        await db.execute(delete(SysPluginArtifact))
        await db.commit()
    service.catalog.lifecycle_lock = TrackingLock()
    service.catalog.dao = TrackingDao
    await service.catalog.import_artifact(deployment_archive)
    assert events == ['locked', 'registered', 'released']
