import base64
import csv
import hashlib
import io
import stat
import sys
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.tags import sys_tags

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.manifest.schema import PluginManifest, PluginManifestFactory
from plugins.core.native import wheel as wheel_tools
from plugins.core.native.wheel import install_native_wheel, select_native_wheel
from plugins.core.runtime.entrypoint import PluginEntrypointLoader

MODULE = 'ruoyi_plugin_wheel_test'
METADATA = f'{MODULE}-1.0.0.dist-info'


@pytest.fixture
def manifest() -> PluginManifest:
    """创建原生 wheel 测试使用的插件清单。"""
    return PluginManifestFactory.create(
        {
            'manifestVersion': 2,
            'id': 'wheel_test',
            'name': 'Wheel test',
            'version': '1.0.0',
            'backend': {
                'runtime': 'native',
                'module': MODULE,
                'entrypoint': f'{MODULE}._native:create_plugin',
                'native': {'distribution': 'ruoyi-plugin-wheel-test'},
            },
        }
    )


def make_wheel(root: Path, *, extra: dict[str, bytes] | None = None, tag: str | None = None) -> Path:
    """构造包含可控元数据、文件内容和 RECORD 的原生测试 wheel。"""
    selected_tag = tag or str(next(sys_tags()))
    path = root / f'{MODULE}-1.0.0-{selected_tag}.whl'
    files = {
        f'{MODULE}/__init__.py': b'raise RuntimeError("static validation must not import")',
        f'{MODULE}/_native{EXTENSION_SUFFIXES[0]}': b'not-an-executable-test-fixture',
        f'{METADATA}/METADATA': b'Name: ruoyi-plugin-wheel-test\nVersion: 1.0.0\nRequires-Python: >=3.10\n',
        f'{METADATA}/WHEEL': f'Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: {selected_tag}\n'.encode(),
        **(extra or {}),
    }
    record = io.StringIO()
    writer = csv.writer(record)
    for name, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode('ascii')
        writer.writerow([name, f'sha256={digest}', len(data)])
    writer.writerow([f'{METADATA}/RECORD', '', ''])
    files[f'{METADATA}/RECORD'] = record.getvalue().encode()
    with ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_install_yields_runtime_loadable_metadata_without_import(tmp_path: Path, manifest: PluginManifest) -> None:
    """验证安装生成可加载的元数据布局且不导入插件。"""
    wheel = make_wheel(tmp_path)
    make_wheel(tmp_path, tag='cp20-cp20-unsupported_platform')
    assert select_native_wheel(tmp_path, manifest) == wheel
    plugin_root = tmp_path / 'wheel_test'
    install_native_wheel(wheel, plugin_root / 'native', manifest)
    discovered = DiscoveredPlugin(manifest, plugin_root, plugin_root / 'plugin.yaml')
    location = PluginEntrypointLoader(discovered).check_entrypoint()
    assert location.path.is_file()
    assert MODULE not in sys.modules


@pytest.mark.parametrize(
    'name',
    [
        '../escaped',
        '/absolute',
        f'{MODULE}/../escape',
        f'{MODULE}/sub\\escape',
        f'{MODULE}/CON',
        'other_module/file.py',
    ],
)
def test_unsafe_archive_rejected_before_creating_destination(
    tmp_path: Path, manifest: PluginManifest, name: str
) -> None:
    """验证不安全容器在创建安装目录前被拒绝。"""
    wheel = make_wheel(tmp_path, extra={name: b'bad'})
    destination = tmp_path / 'native'
    with pytest.raises(ValueError):
        install_native_wheel(wheel, destination, manifest)
    assert not destination.exists()
    assert not (tmp_path.parent / 'escaped').exists()


@pytest.mark.parametrize('mutation', ['tamper', 'unlisted', 'symlink', 'case_collision'])
def test_record_and_file_types_are_enforced(tmp_path: Path, manifest: PluginManifest, mutation: str) -> None:
    """验证 RECORD 完整性与文件类型限制生效。"""
    wheel = make_wheel(tmp_path)
    with ZipFile(wheel) as archive:
        entries = [(item, archive.read(item)) for item in archive.infolist()]
    with ZipFile(wheel, 'w') as archive:
        for item, content in entries:
            payload = content
            if mutation == 'tamper' and item.filename.endswith('__init__.py'):
                payload = b'changed'
            if mutation == 'symlink' and item.filename.endswith('__init__.py'):
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, payload)
        if mutation == 'unlisted':
            archive.writestr(f'{MODULE}/hidden.py', b'pass')
        if mutation == 'case_collision':
            archive.writestr(f'{MODULE}/__INIT__.py', b'pass')
    with pytest.raises(ValueError):
        install_native_wheel(wheel, tmp_path / 'native', manifest)
    assert not (tmp_path / 'native').exists()


def test_install_never_overwrites_existing_directory(tmp_path: Path, manifest: PluginManifest) -> None:
    """验证 wheel 安装不会覆盖已存在的目录。"""
    wheel = make_wheel(tmp_path)
    destination = tmp_path / 'native'
    destination.mkdir()
    sentinel = destination / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')
    with pytest.raises(FileExistsError):
        install_native_wheel(wheel, destination, manifest)
    assert sentinel.read_text(encoding='utf-8') == 'keep'


def test_archive_size_limit(tmp_path: Path, manifest: PluginManifest, monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 wheel 文件数量和大小限制生效。"""
    wheel = make_wheel(tmp_path)
    monkeypatch.setattr(wheel_tools, 'MAX_WHEEL_BYTES', 1)
    with pytest.raises(ValueError, match='超过限制'):
        install_native_wheel(wheel, tmp_path / 'native', manifest)


def test_missing_dependency_is_not_installed(tmp_path: Path, manifest: PluginManifest) -> None:
    """验证缺失依赖只会导致失败而不会触发安装。"""
    wheel = make_wheel(
        tmp_path,
        extra={
            f'{METADATA}/METADATA': b'Name: ruoyi-plugin-wheel-test\nVersion: 1.0.0\n'
            b'Requires-Dist: ruoyi-wheel-test-nonexistent-dependency==1.0\n'
        },
    )
    with pytest.raises(ValueError, match='缺少 wheel 依赖'):
        install_native_wheel(wheel, tmp_path / 'native', manifest)


def test_incompatible_wheel_has_no_selection(tmp_path: Path, manifest: PluginManifest) -> None:
    """验证不兼容 wheel 不能被选择为安装候选。"""
    make_wheel(tmp_path, tag='cp20-cp20-unsupported_platform')
    with pytest.raises(ValueError, match='未找到'):
        select_native_wheel(tmp_path, manifest)


def test_extract_failure_cleans_only_new_directory(
    tmp_path: Path, manifest: PluginManifest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证展开失败仅清理本次创建的新目录。"""
    wheel = make_wheel(tmp_path)
    sentinel = tmp_path / 'keep.txt'
    sentinel.touch()

    def fail_copy(*args: object, **kwargs: object) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(wheel_tools.shutil, 'copyfileobj', fail_copy)
    with pytest.raises(OSError, match='disk full'):
        install_native_wheel(wheel, tmp_path / 'native', manifest)
    assert not (tmp_path / 'native').exists()
    assert sentinel.exists()
