import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from plugins.core.deployment.catalog import PluginArtifactCatalog
from plugins.core.deployment.config import PluginDeploymentConfig
from plugins.core.management.dao.release_dao import PluginReleaseDao
from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease


@pytest.mark.asyncio
async def test_import_indexes_immutable_object_without_installing_or_selecting(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
) -> None:
    """验证制品导入仅登记不可变对象，不安装插件或选择目标。"""
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    imported = await catalog.import_artifact(deployment_archive, actor='publisher-test')
    stored = await catalog.get(imported['digest'])
    stat = (stored.plugin_path / 'plugin.yaml').stat()
    repeated = await catalog.import_artifact(deployment_archive, actor='another-actor')
    assert imported['digest'] == repeated['digest'] == stored.digest
    assert (stored.plugin_path / 'plugin.yaml').stat().st_mtime_ns == stat.st_mtime_ns
    assert 'plugins.artifact_demo' not in sys.modules
    assert (await catalog.list_artifacts('artifact_demo'))['artifacts'][0]['digest'] == stored.digest
    async with deployment_sessions() as db:
        record = await db.get(SysPluginArtifact, stored.digest)
        assert record.created_by == 'publisher-test'
        assert record.relative_path == f'artifact_demo/1.0.0/{stored.digest}'
        assert (await db.scalars(select(SysPlugin))).all() == []
        assert (await db.scalars(select(SysPluginRelease))).all() == []


@pytest.mark.asyncio
async def test_dry_run_writes_neither_store_nor_database(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
) -> None:
    """验证只读预检不写入制品存储或数据库。"""
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    result = await catalog.import_artifact(deployment_archive, dry_run=True)
    assert result['ok'] and result['dryRun']
    assert not deployment_config.store_root.exists()
    assert (await catalog.list_artifacts())['artifacts'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disabled-key', 'removed-key', 'scope', 'source-conflict', 'payload'])
async def test_every_catalog_read_rechecks_current_trust_scope_source_conflicts_and_content(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
    change: str,
) -> None:
    """验证每次目录读取均检查当前信任、授权、源码冲突及文件内容。"""
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    result = await catalog.import_artifact(deployment_archive)
    stored = await catalog.get(result['digest'])
    trust = json.loads(deployment_config.trust_file.read_text())
    if change == 'disabled-key':
        trust['keys'][0]['enabled'] = False
    elif change == 'removed-key':
        trust['keys'] = []
    elif change == 'scope':
        trust['keys'][0]['pluginIds'] = ['other_plugin']
    elif change == 'source-conflict':
        (deployment_config.backend_root / 'plugins' / 'artifact_demo').mkdir()
    else:
        (stored.plugin_path / '__init__.py').write_text('raise RuntimeError("tampered")\n')
    deployment_config.trust_file.write_text(json.dumps(trust), encoding='utf-8')
    with pytest.raises(ValueError):
        await catalog.get(result['digest'])


@pytest.mark.asyncio
async def test_import_rejects_source_conflict_before_publishing(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
) -> None:
    """验证发布不可变对象前拒绝同名源码目录冲突。"""
    (deployment_config.backend_root / 'plugins' / 'artifact_demo').mkdir()
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    with pytest.raises(ValueError, match='源码目录'):
        await catalog.import_artifact(deployment_archive)
    assert not (deployment_config.store_root / 'artifact_demo').exists()
    assert (await catalog.list_artifacts())['artifacts'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'field,value', [('plugin_id', 'wrong_plugin'), ('relative_path', '../outside'), ('key_id', 'other-key')]
)
async def test_database_metadata_never_authorizes_an_unverified_path(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
    field: str,
    value: str,
) -> None:
    """验证数据库索引字段不能授予未经验证路径的访问权限。"""
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    result = await catalog.import_artifact(deployment_archive)
    async with deployment_sessions() as db:
        record = await db.get(SysPluginArtifact, result['digest'])
        setattr(record, field, value)
        await db.commit()
    with pytest.raises(ValueError):
        await catalog.get(result['digest'])


@pytest.mark.asyncio
async def test_database_failure_leaves_valid_object_for_idempotent_retry(
    deployment_sessions: async_sessionmaker[AsyncSession],
    deployment_config: PluginDeploymentConfig,
    deployment_archive: Path,
) -> None:
    """验证索引写入失败后保留完整对象以支持幂等重试。"""

    class FailingDao(PluginReleaseDao):
        @classmethod
        async def register_artifact(cls, db: AsyncSession, **kwargs: Any) -> SysPluginArtifact:
            await super().register_artifact(db, **kwargs)
            raise RuntimeError('index transaction failed')

    failing = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions, dao=FailingDao)
    with pytest.raises(RuntimeError, match='index transaction failed'):
        await failing.import_artifact(deployment_archive)
    catalog = PluginArtifactCatalog(deployment_config, session_factory=deployment_sessions)
    assert (await catalog.list_artifacts())['artifacts'] == []
    objects = list(deployment_config.store_root.glob('artifact_demo/1.0.0/*'))
    assert len(objects) == 1
    initial = (objects[0] / 'artifacts.json').stat().st_mtime_ns
    result = await catalog.import_artifact(deployment_archive)
    assert result['digest'] == objects[0].name
    assert (objects[0] / 'artifacts.json').stat().st_mtime_ns == initial


@pytest.mark.parametrize('scope', [['*'], ['artifact_demo']])
def test_external_publisher_authorization_accepts_explicit_scope(
    deployment_config: PluginDeploymentConfig, scope: list[str]
) -> None:
    """验证发布者授权仅接受明确配置的插件范围。"""
    data = json.loads(deployment_config.trust_file.read_text())
    data['keys'][0]['pluginIds'] = scope
    deployment_config.trust_file.write_text(json.dumps(data), encoding='utf-8')
    deployment_config.authorize_publisher('publisher', 'artifact_demo')
    assert list(deployment_config.trusted_keys()) == ['publisher']


@pytest.mark.parametrize(
    'mutation',
    [
        'duplicate-json',
        'duplicate-id',
        'duplicate-scope',
        'invalid-scope',
        'schema-bool',
        'enabled-string',
        'self-trust',
    ],
)
def test_trust_document_rejects_ambiguous_or_invalid_configuration(
    deployment_config: PluginDeploymentConfig, mutation: str
) -> None:
    """验证外部信任文档拒绝歧义字段与非法配置。"""
    data = json.loads(deployment_config.trust_file.read_text())
    if mutation == 'duplicate-id':
        data['keys'].append(data['keys'][0])
    elif mutation == 'duplicate-scope':
        data['keys'][0]['pluginIds'] = ['artifact_demo', 'artifact_demo']
    elif mutation == 'invalid-scope':
        data['keys'][0]['pluginIds'] = ['../artifact_demo']
    elif mutation == 'schema-bool':
        data['schemaVersion'] = True
    elif mutation == 'enabled-string':
        data['keys'][0]['enabled'] = 'true'
    elif mutation == 'self-trust':
        data['trustEmbeddedKeys'] = True
    raw = json.dumps(data)
    if mutation == 'duplicate-json':
        raw = raw.replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1')
    deployment_config.trust_file.write_text(raw, encoding='utf-8')
    with pytest.raises(ValueError):
        deployment_config.read_publishers()


@pytest.mark.parametrize('location', ['backend', 'ancestor', 'plugins', 'plugin-child'])
def test_store_cannot_overlap_host_source_tree(deployment_config: PluginDeploymentConfig, location: str) -> None:
    """验证制品存储不能与宿主源码目录重叠。"""
    paths = {
        'backend': deployment_config.backend_root,
        'ancestor': deployment_config.backend_root.parent,
        'plugins': deployment_config.backend_root / 'plugins',
        'plugin-child': deployment_config.backend_root / 'plugins' / 'artifact_store',
    }
    with pytest.raises(ValueError):
        replace(deployment_config, store_root=paths[location]).require_enabled()


def test_disabled_deployment_rejects_usage(deployment_config: PluginDeploymentConfig) -> None:
    """验证未启用发布功能时拒绝使用目录服务。"""
    with pytest.raises(ValueError, match='未启用'):
        replace(deployment_config, enabled=False).trusted_keys()
