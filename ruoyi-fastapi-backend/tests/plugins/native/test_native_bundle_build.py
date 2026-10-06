import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from plugins.core.artifacts import package
from plugins.core.manifest.schema import PluginManifest, PluginManifestFactory
from scripts import build_native_plugin


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / 'native_bundle'
    (root / 'web' / 'dist' / 'assets').mkdir(parents=True)
    (root / 'web' / 'dist' / 'index.html').write_text('<html></html>', encoding='utf-8')
    (root / 'web' / 'dist' / 'assets' / 'app.js').write_text('export const value = 1;', encoding='utf-8')
    (root / 'web' / 'src').mkdir()
    (root / 'web' / 'src' / 'app.ts').write_text('development', encoding='utf-8')
    (root / 'web' / 'package.json').write_text('{}', encoding='utf-8')
    (root / 'Cargo.lock').write_text('version = 4\n', encoding='utf-8')
    return root


def manifest(**overrides: object) -> PluginManifest:
    data = {
        'manifestVersion': 2,
        'id': 'native_bundle',
        'name': 'Native bundle',
        'version': '1.0.0',
        'backend': {
            'runtime': 'native',
            'integration': 'asgi',
            'module': 'ruoyi_plugin_native_bundle',
            'entrypoint': 'ruoyi_plugin_native_bundle._native:create_plugin',
            'native': {'distribution': 'ruoyi-plugin-native-bundle'},
        },
        'frontend': {'delivery': {'type': 'bundle'}, 'bundle': {'directory': 'web/dist'}},
    }
    data.update(overrides)
    return PluginManifestFactory.create(data)


def test_collects_only_built_bundle_and_declared_resource_directories(source: Path, tmp_path: Path) -> None:
    migrations = source / 'migrations' / 'mysql'
    migrations.mkdir(parents=True)
    (migrations / '001_init.sql').write_text('SELECT 1;', encoding='utf-8')
    (source / 'plugin.lock.yaml').write_text('schemaVersion: 1\n', encoding='utf-8')
    plugin = manifest()
    plugin.backend.migrations = ['migrations/mysql']
    resources = build_native_plugin.collect_deployment_resources(source, plugin, tmp_path / 'output')
    assert set(resources) == {
        'web/dist/index.html',
        'web/dist/assets/app.js',
        'migrations/mysql/001_init.sql',
        'plugin.lock.yaml',
    }


def test_missing_bundle_entry_fails_before_compilation(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (source / 'web' / 'dist' / 'index.html').unlink()
    (source / 'plugin.yaml').write_text(yaml.safe_dump(manifest().model_dump(by_alias=True)), encoding='utf-8')
    output = tmp_path / 'output'
    compile_process = Mock()
    monkeypatch.setattr(build_native_plugin.subprocess, 'run', compile_process)
    monkeypatch.setattr(sys, 'argv', ['build_native_plugin.py', '--source', str(source), '--output', str(output)])
    with pytest.raises(ValueError, match='HTML'):
        build_native_plugin.main()
    compile_process.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize('name', ['.env.production', 'package.json', 'secret.rs', 'src/private.ts'])
def test_rejects_development_or_secret_files_in_dist(source: Path, tmp_path: Path, name: str) -> None:
    path = source / 'web' / 'dist' / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('not a deployment asset', encoding='utf-8')
    with pytest.raises(ValueError, match='开发工程或敏感配置'):
        build_native_plugin.collect_deployment_resources(source, manifest(), tmp_path / 'output')


def test_rejects_output_inside_bundle(source: Path) -> None:
    with pytest.raises(ValueError, match='输出目录'):
        build_native_plugin.collect_deployment_resources(source, manifest(), source / 'web' / 'dist' / 'package')


def test_rejects_hardlinked_assets(source: Path, tmp_path: Path) -> None:
    external = tmp_path / 'private.txt'
    external.write_text('private', encoding='utf-8')
    os.link(external, source / 'web' / 'dist' / 'private.txt')
    with pytest.raises(ValueError, match='硬链接'):
        build_native_plugin.collect_deployment_resources(source, manifest(), tmp_path / 'output')


def test_rejects_reparse_points_before_descending(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = package.is_link_or_reparse
    resource = source / 'web' / 'dist' / 'assets'
    inode = resource.lstat().st_ino
    monkeypatch.setattr(package, 'is_link_or_reparse', lambda info: info.st_ino == inode or original(info))
    with pytest.raises(ValueError, match='链接'):
        build_native_plugin.collect_deployment_resources(source, manifest(), tmp_path / 'output')


@pytest.mark.parametrize('relative', ['plugin.yaml', 'native/data.json'])
def test_resources_cannot_overwrite_manifest_or_native_package(source: Path, tmp_path: Path, relative: str) -> None:
    path = source / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('reserved', encoding='utf-8')
    plugin = manifest()
    plugin.backend.seeds = [relative]
    with pytest.raises(ValueError, match='覆盖'):
        build_native_plugin.collect_deployment_resources(source, plugin, tmp_path / 'output')
