import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from plugins.core.discovery.scanner import PluginScanner
from plugins.core.manifest.schema import EXPLICIT_MANIFEST_VERSION
from plugins.core.validation.structure import PluginStructureChecker

from .conftest import build_runtime

BACKEND_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = BACKEND_ROOT.parent / 'ruoyi-fastapi-frontend'
PLUGIN_ID = 'invoice_ops_27'
TEMPLATES = ('python-asgi', 'python-bundle', 'rust-asgi', 'rust-bundle')


def generate(tmp_path: Path, template: str, **kwargs: object) -> tuple[dict, Path]:
    """
    在临时宿主目录中生成指定 v2 模板。
    """
    backend = tmp_path / 'backend'
    payload = build_runtime(backend, frontend_root=FRONTEND_ROOT).create_plugin(PLUGIN_ID, template=template, **kwargs)
    assert payload['ok'], payload
    return payload, backend / 'plugin-projects' / PLUGIN_ID


def run_builder(source: Path, output: Path) -> subprocess.CompletedProcess[str]:
    """
    通过独立 Python 进程执行生成的交付构建脚本。
    """
    return subprocess.run(
        [sys.executable, '-X', 'utf8', str(source / 'build_release.py'), '--output', str(output)],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False,
    )


def write_bundle(source: Path) -> None:
    """
    写入最小已构建前端资源，供离线交付测试使用。
    """
    dist = source / 'web' / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<!doctype html><html><body>built</body></html>', encoding='utf-8')
    (dist / 'assets' / 'app.js').write_text('export const built = true\n', encoding='utf-8')


@pytest.mark.parametrize('template', TEMPLATES)
def test_v2_templates_create_independent_projects_without_importing_or_installing(
    tmp_path: Path, template: str
) -> None:
    """
    验证四类模板生成独立工程且不安装或导入插件。
    """
    payload, source = generate(tmp_path, template)
    plugin = PluginScanner(source.parent).load_manifest(source / 'plugin.yaml')
    native = template.startswith('rust-')
    bundle = template.endswith('-bundle')
    assert plugin.manifest.manifest_version == EXPLICIT_MANIFEST_VERSION
    assert plugin.manifest.runtime_kind == ('native' if native else 'python')
    assert plugin.manifest.integration_kind == 'asgi'
    assert plugin.manifest.frontend.delivery.type == ('bundle' if bundle else 'none')
    assert plugin.manifest.id == PLUGIN_ID
    assert plugin.manifest.backend.asgi.mount_path == f'/apps/{PLUGIN_ID}'
    assert payload['sourceDir'] == source.as_posix()
    assert payload['frontendVersion'] is None
    assert not (tmp_path / 'backend' / 'plugins').exists()
    assert f'plugins.{PLUGIN_ID}' not in sys.modules
    assert f'ruoyi_plugin_{PLUGIN_ID}' not in sys.modules
    for path in source.rglob('*'):
        if not path.is_file():
            continue
        content = path.read_text(encoding='utf-8')
        assert '__PLUGIN_ID__' not in content
        assert 'rust_demo' not in content
        assert 'bundle_demo' not in content
        if path.suffix == '.py':
            ast.parse(content)
    if native:
        distribution = 'ruoyi-plugin-invoice-ops-27'
        assert plugin.manifest.backend.module == f'ruoyi_plugin_{PLUGIN_ID}'
        for name in ('Cargo.toml', 'Cargo.lock', 'pyproject.toml'):
            assert f'name = "{distribution}"' in (source / name).read_text(encoding='utf-8')
        assert f'permission", "{PLUGIN_ID}:view"' in (source / 'src' / 'lib.rs').read_text(encoding='utf-8')
    else:
        assert plugin.manifest.backend.entrypoint == f'plugins.{PLUGIN_ID}:create_plugin'
    if bundle:
        for name in ('pluginBridge.js', 'pluginBridge.d.ts'):
            assert (source / 'web' / 'vendor' / name).read_text(encoding='utf-8') == (
                FRONTEND_ROOT / 'src' / 'utils' / name
            ).read_text(encoding='utf-8')
        package = json.loads((source / 'web' / 'package.json').read_text(encoding='utf-8'))
        assert package['scripts']['build'] == 'vite build'
        assert package['scripts']['dev'] == 'vite --host 127.0.0.1 --open /dev.html'
        assert (source / 'web' / 'dev.html').is_file()
        assert f'/apps/{PLUGIN_ID}/api/info' in (source / 'web' / 'dev.js').read_text(encoding='utf-8')
        assert "apply: 'serve'" in (source / 'web' / 'vite.config.js').read_text(encoding='utf-8')
        assert plugin.manifest.frontend.menus[0].component == 'PluginFrame'
        assert plugin.manifest.frontend.menus[0].perms == f'{PLUGIN_ID}:view'


@pytest.mark.parametrize('template', TEMPLATES)
def test_v2_template_dry_run_and_conflict_never_overwrite(tmp_path: Path, template: str) -> None:
    """
    验证预演不写文件，目录冲突时不覆盖已有内容。
    """
    payload, source = generate(tmp_path, template, dry_run=True)
    assert payload['dryRun'] is True
    assert not source.exists()
    source.mkdir(parents=True)
    marker = source / 'do-not-overwrite.txt'
    marker.write_text('keep', encoding='utf-8')
    payload = build_runtime(tmp_path / 'backend', frontend_root=FRONTEND_ROOT).create_plugin(
        PLUGIN_ID, template=template
    )
    assert payload['ok'] is False
    assert marker.read_text(encoding='utf-8') == 'keep'
    assert not (source / 'plugin.yaml').exists()


@pytest.mark.parametrize(
    ('template', 'options', 'error'),
    [
        ('python-asgi', {'backend': False}, '--frontend-only'),
        ('rust-bundle', {'frontend': False}, '--backend-only'),
        ('python-bundle', {'frontend_version': 'vue2'}, '--frontend-version'),
    ],
)
def test_v2_templates_reject_incompatible_legacy_options(
    tmp_path: Path, template: str, options: dict, error: str
) -> None:
    """
    验证 v2 模板拒绝不兼容的旧版选项。
    """
    payload = build_runtime(tmp_path / 'backend', frontend_root=FRONTEND_ROOT).create_plugin(
        PLUGIN_ID, template=template, **options
    )
    assert payload['ok'] is False
    assert error in payload['error']
    assert not (tmp_path / 'backend' / 'plugin-projects').exists()


def test_bundle_template_requires_verified_host_sdk_and_no_test_is_honored(tmp_path: Path) -> None:
    """
    验证 bundle 需要宿主桥接 SDK，且遵守不生成测试的选项。
    """
    missing = build_runtime(tmp_path / 'backend').create_plugin(PLUGIN_ID, template='python-bundle')
    assert missing['ok'] is False
    assert '桥接 SDK' in missing['error']
    assert not (tmp_path / 'backend' / 'plugin-projects').exists()
    payload, source = generate(tmp_path, 'python-bundle', test=False)
    assert payload['test'] is False
    assert not (source / 'tests').exists()


@pytest.mark.parametrize('template', ['python-asgi', 'python-bundle'])
def test_generated_python_release_passes_structure_and_generated_contract_tests(tmp_path: Path, template: str) -> None:
    """
    验证生成的 Python 交付通过结构检查与其自身合约测试。
    """
    _, source = generate(tmp_path, template)
    if template.endswith('-bundle'):
        write_bundle(source)
    (source / 'private.pem').write_text('never copy this', encoding='utf-8')
    output = tmp_path / 'release'
    built = run_builder(source, output)
    assert built.returncode == 0, built.stderr
    delivered = output / PLUGIN_ID
    plugin = PluginScanner(output).load_manifest(delivered / 'plugin.yaml')
    check = PluginStructureChecker(BACKEND_ROOT).check(plugin)
    assert check.ok, check.failed_items
    assert not (delivered / 'tests').exists()
    assert not (delivered / 'build_release.py').exists()
    assert not (delivered / 'web' / 'src').exists()
    assert not (delivered / 'private.pem').exists()
    environment = {**os.environ, 'RUOYI_PLUGIN_DIRECTORY': str(delivered)}
    tested = subprocess.run(
        [
            sys.executable,
            '-X',
            'utf8',
            '-m',
            'pytest',
            '-c',
            str(BACKEND_ROOT / 'pyproject.toml'),
            str(source / 'tests'),
            '-q',
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=False,
    )
    assert tested.returncode == 0, tested.stdout + tested.stderr
    again = run_builder(source, output)
    assert again.returncode != 0
    assert (delivered / '__init__.py').read_bytes() == (source / '__init__.py').read_bytes()


@pytest.mark.parametrize('invalid_file', ['assets/app.js.map', 'assets/private.pem', '.env', 'assets/entry.ts'])
def test_python_bundle_packaging_rejects_nonrelease_content(tmp_path: Path, invalid_file: str) -> None:
    """
    验证 Python 交付拒绝源码、密钥和其他非交付资源。
    """
    _, source = generate(tmp_path, 'python-bundle')
    write_bundle(source)
    (source / 'web' / 'dist' / invalid_file).write_text('must not package', encoding='utf-8')
    output = tmp_path / 'unsafe'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()


def test_python_bundle_packaging_rejects_missing_build_and_overlapping_output(tmp_path: Path) -> None:
    """
    验证 Python 交付拒绝缺失前端构建及输出目录重叠。
    """
    _, source = generate(tmp_path, 'python-bundle')
    output = tmp_path / 'missing-build'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()
    write_bundle(source)
    assert run_builder(source, source / 'release').returncode != 0
    assert not (source / 'release').exists()


def test_python_release_rejects_hardlinked_resources(tmp_path: Path) -> None:
    """
    验证 Python 交付拒绝硬链接资源。
    """
    _, source = generate(tmp_path, 'python-asgi')
    os.link(source / '__init__.py', tmp_path / 'entry-copy.py')
    output = tmp_path / 'hardlink-release'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()
