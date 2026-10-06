from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.vo.schemas import PluginPageQueryModel
from plugins.core.management.service import release_view
from plugins.core.management.service.service import PluginService
from plugins.core.manifest.schema import PluginManifestFactory

DIGEST = 'a' * 64
PREVIOUS_DIGEST = 'b' * 64
GENERATION = 'c' * 32


def artifact_record() -> SysPlugin:
    """构造管理视图使用的制品来源插件记录。"""
    return SysPlugin(
        plugin_id='demo',
        plugin_name='Demo',
        version='2.0.0',
        installed_version='2.0.0',
        source='artifact',
        enabled='0',
        status='installed',
        backend_path=f'artifact:{DIGEST}',
    )


@pytest.mark.asyncio
async def test_disabled_feature_preserves_artifact_identity_and_never_queries_release_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证功能关闭时保留制品身份且不查询发布表。"""
    plugin = artifact_record()
    monkeypatch.setattr(PluginDao, 'get_plugin_by_id', AsyncMock(return_value=plugin))
    monkeypatch.setattr(PluginDao, 'get_plugin_list', AsyncMock(return_value=[plugin]))
    monkeypatch.setattr(release_view.PluginDeploymentConfig, 'from_settings', lambda _: SimpleNamespace(enabled=False))
    get_release = AsyncMock(side_effect=AssertionError('feature disabled must not query release tables'))
    monkeypatch.setattr(release_view.PluginReleaseDao, 'get_release', get_release)
    backend_plugins = tmp_path / 'backend' / 'plugins'
    model = await PluginService.plugin_detail_services(object(), 'demo', backend_root=backend_plugins)
    assert model.source == 'artifact'
    assert model.installed_version == '2.0.0'
    assert model.release['status'] == 'unavailable'
    assert model.capability['runtimeManageable'] is False
    assert 'purge' in model.capability['blockedOperations']
    items = await PluginService.get_plugin_page_list_services(
        object(), PluginPageQueryModel(), is_page=False, backend_root=backend_plugins
    )
    assert len(items) == 1
    assert items[0]['source'] == 'artifact'
    get_release.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('verified', [True, False])
async def test_release_view_separates_selected_code_schema_and_worker_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verified: bool
) -> None:
    """验证视图区分目标代码版本、安装版本和进程激活状态。"""
    release = SimpleNamespace(
        plugin_id='demo',
        target_digest=DIGEST,
        previous_digest=PREVIOUS_DIGEST,
        prepared_digest=DIGEST,
        prepared_version='2.0.0',
        generation=GENERATION,
        expected_workers=2,
        prepare_status='prepared',
        last_error=None,
    )
    monkeypatch.setattr(
        release_view.PluginDeploymentConfig,
        'from_settings',
        lambda _: SimpleNamespace(enabled=True, worker_ttl_seconds=60),
    )
    monkeypatch.setattr(release_view.PluginReleaseDao, 'get_release', AsyncMock(return_value=release))
    monkeypatch.setattr(release_view.PluginReleaseDao, 'list_worker_reports', AsyncMock(return_value=[]))
    manifest = PluginManifestFactory.create(
        {
            'manifestVersion': 2,
            'id': 'demo',
            'name': 'Demo',
            'version': '1.0.0',
            'backend': {'module': 'plugins.demo', 'entrypoint': 'plugins.demo:create_plugin'},
        }
    )
    discovered = DiscoveredPlugin(
        manifest=manifest,
        backend_path=tmp_path / 'immutable' / DIGEST,
        manifest_path=tmp_path / 'immutable' / DIGEST / 'plugin.yaml',
        artifact_digest=DIGEST,
        artifact_generation=GENERATION,
    )

    class Catalog:
        def __init__(self, config: object) -> None:
            pass

        @staticmethod
        def reject_source_conflict(plugin_id: str) -> None:
            assert plugin_id == 'demo'

        @staticmethod
        async def get(digest: str) -> object:
            assert digest == DIGEST
            if not verified:
                raise ValueError('制品摘要校验失败')
            return SimpleNamespace(plugin_id='demo', version='1.0.0')

        @staticmethod
        def discovered(artifact: object, generation: str) -> DiscoveredPlugin:
            assert generation == GENERATION
            return discovered

    monkeypatch.setattr(release_view, 'PluginArtifactCatalog', Catalog)
    model = await release_view.build_artifact_plugin_view(
        object(), artifact_record(), tmp_path / 'backend' / 'plugins', None, PluginService._build_plugin_model
    )
    assert model.source == 'artifact'
    assert model.installed_version == '2.0.0'
    assert model.status == 'installed'
    assert model.capability['runtimeManageable'] is False
    assert model.release['targetDigest'] == DIGEST
    assert model.release['preparedDigest'] == DIGEST
    assert model.release['previousDigest'] == PREVIOUS_DIGEST
    assert model.release['preparedVersion'] == '2.0.0'
    assert model.release['generation'] == GENERATION
    assert model.release['status'] == 'pending_restart'
    assert model.release['healthyWorkers'] == 0
    assert model.release['restartRequired'] is True
    if verified:
        assert model.version == '1.0.0'
        assert model.release['targetVersion'] == '1.0.0'
        assert model.backend_path == f'artifact:{DIGEST}'
    else:
        assert '摘要校验失败' in model.release['verificationError']


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['build_plugin_purge_plan_by_id_services', '_purge_plugin_metadata_by_id'])
async def test_artifact_metadata_cannot_be_purged_as_orphan(monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    """验证制品插件不会被当作孤儿记录允许清理。"""
    monkeypatch.setattr(PluginDao, 'get_plugin_by_id', AsyncMock(return_value=artifact_record()))
    with pytest.raises(ValueError, match='制品插件不能'):
        await getattr(PluginService, method)(object(), 'demo')
