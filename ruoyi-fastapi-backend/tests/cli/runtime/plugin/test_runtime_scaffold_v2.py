import ast
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

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


def write_release_files(source: Path, names: list[object]) -> None:
    """
    为隔离工程写入受控交付清单，允许传入非法项供拒绝路径测试。

    :param source: 隔离插件工程根目录
    :param names: 清单中的完整文件列表
    :return: None
    """
    (source / 'release-files.json').write_text(
        json.dumps({'schemaVersion': 1, 'files': names}, ensure_ascii=False), encoding='utf-8'
    )


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
    else:
        assert not (source / 'web').exists()
        assert not list(source.rglob('pluginBridge.sdk.json'))


@pytest.mark.parametrize('template', ['python-bundle', 'rust-bundle'])
def test_bundle_templates_record_sdk_identity_and_source_hashes(tmp_path: Path, template: str) -> None:
    """
    验证 bundle 工程包含独立 SDK 版本、协议能力及与实际副本一致的来源摘要。
    """
    _, source = generate(tmp_path, template)
    vendor = source / 'web' / 'vendor'
    sdk = json.loads((vendor / 'pluginBridge.sdk.json').read_text(encoding='utf-8'))
    assert sdk['schemaVersion'] == 1
    assert sdk['sdkVersion'] == '1.0.0'
    assert sdk['bridgeVersion'] == 1
    assert sdk['capabilities'] == {'files': 1, 'streams': 1}
    assert sdk['hashAlgorithm'] == 'sha256-utf8-lf'
    assert sdk['source'] == {'project': 'RuoYi-Vue3-FastAPI', 'directory': 'ruoyi-fastapi-frontend/src/utils'}
    assert set(sdk['files']) == {'pluginBridge.js', 'pluginBridge.d.ts'}
    for name in ('pluginBridge.js', 'pluginBridge.d.ts'):
        content = (vendor / name).read_text(encoding='utf-8')
        assert sdk['files'][name] == hashlib.sha256(content.encode('utf-8')).hexdigest()


def test_bundle_sdk_source_hashes_are_stable_across_crlf_checkout(tmp_path: Path) -> None:
    """
    验证使用 CRLF 的宿主源码副本生成工程后，SDK 溯源摘要仍与规范化内容一致。
    """
    frontend = tmp_path / 'frontend'
    sdk_source = frontend / 'src' / 'utils'
    sdk_source.mkdir(parents=True)
    for name in ('pluginBridge.js', 'pluginBridge.d.ts', 'pluginBridge.sdk.json'):
        content = (FRONTEND_ROOT / 'src' / 'utils' / name).read_text(encoding='utf-8')
        (sdk_source / name).write_bytes(content.replace('\n', '\r\n').encode('utf-8'))
    backend = tmp_path / 'backend'
    payload = build_runtime(backend, frontend_root=frontend).create_plugin(PLUGIN_ID, template='python-bundle')
    assert payload['ok'], payload
    vendor = backend / 'plugin-projects' / PLUGIN_ID / 'web' / 'vendor'
    sdk = json.loads((vendor / 'pluginBridge.sdk.json').read_text(encoding='utf-8'))
    for name in ('pluginBridge.js', 'pluginBridge.d.ts'):
        expected = (FRONTEND_ROOT / 'src' / 'utils' / name).read_text(encoding='utf-8')
        assert (vendor / name).read_text(encoding='utf-8') == expected
        assert sdk['files'][name] == hashlib.sha256(expected.encode('utf-8')).hexdigest()


@pytest.mark.parametrize('template', TEMPLATES)
def test_v2_template_readme_matches_browser_capabilities(tmp_path: Path, template: str) -> None:
    """
    验证生成说明区分浏览器 SDK 能力与模板自带接口，并保留协商和传输限制。
    """
    _, source = generate(tmp_path, template)
    readme = (source / 'README.md').read_text(encoding='utf-8')
    if template.endswith('-bundle'):
        assert 'JSON 请求和响应每条最多 64 KiB' in readme
        assert '`upload` / `download`' in readme
        assert '`capabilities.files.version=1`' in readme
        assert '单次最多 10 MiB' in readme
        assert '`stream`' in readme
        assert '`capabilities.streams.version=1`' in readme
        assert '每个页面最多 2 条连接' in readme
        assert '不自动重连' in readme
        assert '本模板仅生成 `/api/info`，文件和事件接口需自行实现并校验权限' in readme
        assert '`TRANSPORT_CRYPTO_EXCLUDE_PATHS`' in readme
        assert '不支持上传、流式响应' not in readme
        assert '`web/vendor/pluginBridge.sdk.json`' in readme
        assert f'ruoyi plugin sdk check plugin-projects/{PLUGIN_ID} --output json' in readme
        assert f'ruoyi plugin sdk update plugin-projects/{PLUGIN_ID} --dry-run' in readme
        assert f'ruoyi plugin sdk update plugin-projects/{PLUGIN_ID}\n' in readme
        assert '只有 `current` 状态返回成功退出码' in readme
        assert '修改过或没有溯源记录的旧副本默认拒绝覆盖' in readme
        assert '`--force`' in readme and '`.plugin-sdk-backups/`' in readme
        assert '协议兼容不等于业务兼容' in readme
        assert '不联网、不安装依赖、不更新业务源码或运行中的插件' in readme
        assert f'更新后必须重新运行 `npm --prefix plugin-projects/{PLUGIN_ID}/web run build`' in readme
    else:
        assert '子应用不提供独立登录' in readme
        assert 'capabilities.files' not in readme
        assert 'capabilities.streams' not in readme
        assert 'pluginBridge.sdk.json' not in readme
        assert 'ruoyi plugin sdk' not in readme


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


@pytest.mark.parametrize('template', TEMPLATES)
def test_v2_python_templates_describe_explicit_release_files(tmp_path: Path, template: str) -> None:
    """
    验证仅 Python 模板生成受控交付清单，并说明模块和迁移的扩展方法。

    :param tmp_path: 隔离宿主目录
    :param template: 待检查的 v2 模板
    :return: None
    """
    _, source = generate(tmp_path, template)
    config = source / 'release-files.json'
    readme = (source / 'README.md').read_text(encoding='utf-8')
    if template.startswith('python-'):
        assert json.loads(config.read_text(encoding='utf-8')) == {'schemaVersion': 1, 'files': ['__init__.py']}
        assert '`release-files.json`' in readme
        assert '`models.py`、`migrations/mysql/001_init.sql`' in readme
        assert '`plugin.yaml` 固定纳入' in readme
        assert '未列出的私有文件不会自动复制' in readme
    else:
        assert not config.exists()
        assert 'release-files.json' not in readme


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
            '--confcutdir',
            str(source),
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


@pytest.mark.parametrize(
    'invalid_file', ['assets/app.js.map', 'assets/private.pem', '.env', 'assets/entry.ts', 'assets/.private.js']
)
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


@pytest.mark.parametrize('template', ['python-asgi', 'python-bundle'])
def test_python_release_copies_declared_modules_and_sql_without_importing(tmp_path: Path, template: str) -> None:
    """
    验证新增模块和 SQL 按清单交付，未声明的私有文件不会混入且业务入口不会执行。

    :param tmp_path: 隔离构建目录
    :param template: Python API 或 bundle 模板
    :return: None
    """
    _, source = generate(tmp_path, template)
    names = ['__init__.py', 'models.py', 'api/__init__.py', 'api/reports.py', 'migrations/mysql/001_init.sql']
    for name in names:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = 'select 1;\n' if path.suffix == '.sql' else 'raise RuntimeError("must never import delivery files")\n'
        path.write_text(content, encoding='utf-8')
    for name in ('private.py', 'credentials.sql', 'keys/secret.py', 'tests/test_private.py', '.env', 'vendor/debug.py'):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('do not deliver\n', encoding='utf-8')
    write_release_files(source, names)
    expected = {'plugin.yaml', *names}
    if template.endswith('-bundle'):
        write_bundle(source)
        expected.update({'web/dist/index.html', 'web/dist/assets/app.js'})
    output = tmp_path / 'controlled-release'
    result = run_builder(source, output)
    assert result.returncode == 0, result.stderr
    delivered = output / PLUGIN_ID
    assert {path.relative_to(delivered).as_posix() for path in delivered.rglob('*') if path.is_file()} == expected
    for name in expected:
        assert (delivered / name).read_bytes() == (source / name).read_bytes()


@pytest.mark.parametrize(
    ('name', 'reason'),
    [
        ('../outside.py', '不安全路径'),
        ('/absolute.py', '不安全路径'),
        ('C:/drive.py', '不安全路径'),
        (r'package\module.py', '不安全路径'),
        ('package//module.py', '不安全路径'),
        ('./module.py', '不安全路径'),
        ('.private/module.py', '不安全路径'),
        ('module.py ', '不安全路径'),
        ('CON.py', '不安全路径'),
        ('*.py', '不安全路径'),
        ('[ab].py', '不安全路径'),
        ('tests/helper.py', '仅允许业务'),
        ('Tests/helper.sql', '仅允许业务'),
        ('keys/secret.py', '仅允许业务'),
        ('vendor/helper.py', '仅允许业务'),
        ('web/vendor/helper.py', '仅允许业务'),
        ('node_modules/helper.py', '仅允许业务'),
        ('build_release.py', '仅允许业务'),
        ('test_business.py', '仅允许业务'),
        ('private.pem', '仅允许业务'),
        ('plugin.yaml', '仅允许业务'),
        ('package', '仅允许业务'),
        (None, '必须为字符串'),
    ],
)
def test_python_release_rejects_unsafe_declared_paths_before_output(tmp_path: Path, name: object, reason: str) -> None:
    """
    验证显式声明仍不能绕过路径、资源类型和开发目录限制。

    :param tmp_path: 隔离源码及输出目录
    :param name: 清单中的非法资源路径
    :param reason: 预期的拒绝原因片段
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    write_release_files(source, ['__init__.py', name])
    output = tmp_path / 'unsafe-release'
    result = run_builder(source, output)
    assert result.returncode != 0
    assert reason in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    'names',
    [
        ['__init__.py', '__init__.py'],
        ['models.py', 'Models.py'],
        ['Package/one.py', 'package/two.py'],
        ['module.py', 'module.py/child.py'],
    ],
)
def test_python_release_rejects_duplicate_and_conflicting_inventory(tmp_path: Path, names: list[str]) -> None:
    """
    验证重复文件、大小写目录歧义及文件目录冲突在访问资源前被拒绝。

    :param tmp_path: 隔离源码及输出目录
    :param names: 存在重复或冲突的完整清单
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    write_release_files(source, names)
    output = tmp_path / 'collision-release'
    result = run_builder(source, output)
    assert result.returncode != 0
    assert '冲突' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    'content',
    [
        'not json',
        '[]',
        '{"schemaVersion": true, "files": ["__init__.py"]}',
        '{"schemaVersion": 2, "files": ["__init__.py"]}',
        '{"schemaVersion": 1, "files": [], "extra": true}',
        '{"schemaVersion": 1, "files": []}',
        '{"schemaVersion": 1, "files": "__init__.py"}',
        '{"schemaVersion": 1, "files": [], "files": ["__init__.py"]}',
        json.dumps({'schemaVersion': 1, 'files': ['__init__.py'] * 1025}),
        ' ' * (64 * 1024 + 1),
    ],
    ids=[
        'invalid-json',
        'not-object',
        'bool-version',
        'wrong-version',
        'extra-field',
        'empty-list',
        'not-list',
        'duplicate-json-key',
        'too-many-files',
        'oversized-config',
    ],
)
def test_python_release_rejects_invalid_or_oversized_config(tmp_path: Path, content: str) -> None:
    """
    验证清单结构、重复字段和资源上限，拒绝时不创建输出目录。

    :param tmp_path: 隔离源码及输出目录
    :param content: 非法交付清单文本
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    (source / 'release-files.json').write_text(content, encoding='utf-8')
    output = tmp_path / 'invalid-config-release'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()


@pytest.mark.parametrize('missing', ['release-files.json', 'module.py', 'directory.py'])
def test_python_release_requires_existing_config_and_regular_declared_files(tmp_path: Path, missing: str) -> None:
    """
    验证缺失清单、缺失资源及伪装为 .py 的目录均不会留下半成品输出。

    :param tmp_path: 隔离源码及输出目录
    :param missing: 缺失清单或不可用的声明资源
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    if missing == 'release-files.json':
        (source / missing).unlink()
    else:
        write_release_files(source, ['__init__.py', missing])
        if missing == 'directory.py':
            (source / missing).mkdir()
    output = tmp_path / 'missing-release'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()


@pytest.mark.parametrize('kind', ['file', 'directory'])
def test_python_release_rejects_linked_declared_resources(tmp_path: Path, kind: str) -> None:
    """
    验证文件或父目录符号链接不能将工程外内容引入交付。

    :param tmp_path: 隔离源码、外部文件及输出目录
    :param kind: 文件链接或目录链接
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'module.py').write_text('private = True\n', encoding='utf-8')
    try:
        if kind == 'file':
            (source / 'module.py').symlink_to(outside / 'module.py')
            name = 'module.py'
        else:
            (source / 'package').symlink_to(outside, target_is_directory=True)
            name = 'package/module.py'
    except OSError as exc:
        pytest.skip(f'当前文件系统不允许创建符号链接：{exc}')
    write_release_files(source, ['__init__.py', name])
    output = tmp_path / 'linked-release'
    assert run_builder(source, output).returncode != 0
    assert not output.exists()


def test_python_release_rejects_reparse_resource_before_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    验证 Windows 重解析标志独立于符号链接权限，且校验失败发生在输出创建之前。

    :param tmp_path: 隔离源码及输出目录
    :param monkeypatch: 模拟文件系统重解析标志和命令参数
    :return: None
    """
    _, source = generate(tmp_path, 'python-asgi')
    namespace = runpy.run_path(str(source / 'build_release.py'))
    original_lstat = Path.lstat
    resource = source / '__init__.py'

    def reparse_lstat(path: Path) -> object:
        """
        仅向被检查资源注入重解析标志，其余文件沿用真实元数据。

        :param path: 待查询的文件系统路径
        :return: 原始 stat 或包含重解析标志的模拟对象
        """
        metadata = original_lstat(path)
        if path == resource:
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return metadata

    monkeypatch.setattr(Path, 'lstat', reparse_lstat)
    output = tmp_path / 'reparse-release'
    monkeypatch.setattr(sys, 'argv', ['build_release.py', '--output', str(output)])
    with pytest.raises(ValueError, match='重解析点'):
        namespace['main']()
    assert not output.exists()


def test_task_demo_release_builder_matches_scaffold_template() -> None:
    """
    验证任务示例和 Python 脚手架共用同一独立构建逻辑，防止安全约束漂移。

    :return: None
    """
    example = BACKEND_ROOT / 'plugins' / 'examples' / 'python' / 'task_demo'
    template = BACKEND_ROOT / 'cli' / 'runtime' / 'plugin' / 'scaffold' / 'assets' / 'python' / 'build_release.py.tmpl'
    expected = template.read_text(encoding='utf-8').replace('__PLUGIN_ID__', 'task_demo').replace('__BUNDLE__', 'True')
    assert (example / 'build_release.py').read_text(encoding='utf-8') == expected
    assert json.loads((example / 'release-files.json').read_text(encoding='utf-8')) == {
        'schemaVersion': 1,
        'files': [
            '__init__.py',
            'models.py',
            'service.py',
            'migrations/mysql/001_init.sql',
            'migrations/mysql/002_priority.sql',
            'migrations/postgresql/001_init.sql',
            'migrations/postgresql/002_priority.sql',
        ],
    }
