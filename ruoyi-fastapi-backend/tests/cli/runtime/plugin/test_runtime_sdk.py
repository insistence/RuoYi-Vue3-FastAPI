import hashlib
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from cli.runtime.plugin.sdk import HASH_ALGORITHM, SDK_FILES, SDK_METADATA, SDK_SOURCE, VENDOR_FILES, PluginBridgeSdk


def write_source(
    frontend: Path, *, version: str = '1.0.0', wire: int = 1, capabilities: dict[str, int] | None = None
) -> PluginBridgeSdk:
    """
    写入不执行 JavaScript 的最小宿主 SDK 测试源。

    :param frontend: 临时宿主前端目录
    :param version: SDK 版本
    :param wire: 通信协议版本
    :param capabilities: 声明的可选能力版本
    :return: 指向测试源的 SDK 管理器
    """
    directory = frontend / 'src' / 'utils'
    directory.mkdir(parents=True, exist_ok=True)
    (frontend / 'package.json').write_text('{"dependencies":{"vue":"^3.5.26"}}', encoding='utf-8')
    (directory / SDK_FILES[0]).write_text(
        f"export const PLUGIN_BRIDGE_SDK_VERSION = '{version}'\nexport const PLUGIN_BRIDGE_VERSION = {wire}\n",
        encoding='utf-8',
    )
    (directory / SDK_FILES[1]).write_text(
        f"export const PLUGIN_BRIDGE_SDK_VERSION: '{version}'\nexport const PLUGIN_BRIDGE_VERSION: {wire}\n",
        encoding='utf-8',
    )
    metadata = {
        'schemaVersion': 1,
        'sdkVersion': version,
        'bridgeVersion': wire,
        'capabilities': capabilities if capabilities is not None else {'files': 1, 'streams': 1},
    }
    (directory / SDK_METADATA).write_text(json.dumps(metadata), encoding='utf-8')
    return PluginBridgeSdk(frontend)


def write_project(project: Path, sdk: PluginBridgeSdk) -> Path:
    """
    创建含业务文件和 SDK 副本的独立 bundle 工程。

    :param project: 临时工程目录
    :param sdk: 用于生成初始副本的宿主 SDK
    :return: 创建后的工程目录
    """
    vendor = project / 'web' / 'vendor'
    vendor.mkdir(parents=True)
    manifest = {
        'manifestVersion': 2,
        'id': 'sdk_demo',
        'name': 'SDK Demo',
        'version': '1.0.0',
        'backend': {
            'module': 'plugins.sdk_demo',
            'entrypoint': 'plugins.sdk_demo:create_plugin',
            'integration': 'asgi',
        },
        'frontend': {'delivery': {'type': 'bundle'}, 'bundle': {'directory': 'web/dist', 'entry': 'index.html'}},
    }
    (project / 'plugin.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    (project / 'web' / 'business.js').write_text('user-business-code\n', encoding='utf-8')
    for name, content in sdk.build_vendor_files().items():
        (vendor / name).write_bytes(content.encode('utf-8'))
    return project


def snapshot(project: Path) -> dict[str, bytes]:
    """
    收集测试工程全部文件以确认预演和拒绝操作没有副作用。

    :param project: 临时工程目录
    :return: 相对文件名与原始字节的映射
    """
    return {str(path.relative_to(project)): path.read_bytes() for path in project.rglob('*') if path.is_file()}


@pytest.fixture
def outdated(tmp_path: Path) -> tuple[PluginBridgeSdk, Path]:
    """
    创建完整且版本较旧的 SDK 副本。

    :param tmp_path: pytest 的独立临时目录
    :return: 当前宿主 SDK 及包含旧副本的工程
    """
    frontend = tmp_path / 'frontend'
    old = write_source(frontend, version='0.9.0', capabilities={'files': 1})
    project = write_project(tmp_path / 'project', old)
    return write_source(frontend), project


def test_build_vendor_records_normalized_hashes_and_versions(tmp_path: Path) -> None:
    """SDK 来源记录固定且可复现，CRLF 与 BOM 不改变内容摘要。"""
    frontend = tmp_path / 'frontend'
    sdk = write_source(frontend)
    expected = sdk.build_vendor_files()
    for name in VENDOR_FILES:
        path = frontend / 'src' / 'utils' / name
        text = path.read_text(encoding='utf-8')
        path.write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode('utf-8'))
    actual = sdk.build_vendor_files()
    assert actual == expected
    assert set(actual) == set(VENDOR_FILES)
    metadata = json.loads(actual[SDK_METADATA])
    assert metadata['hashAlgorithm'] == HASH_ALGORITHM
    assert metadata['source'] == SDK_SOURCE
    assert metadata['sdkVersion'] == '1.0.0'
    assert metadata['files'] == {name: hashlib.sha256(actual[name].encode('utf-8')).hexdigest() for name in SDK_FILES}
    project = write_project(tmp_path / 'project', sdk)
    for name in VENDOR_FILES:
        path = project / 'web' / 'vendor' / name
        path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    assert sdk.check(project)['status'] == 'current'


@pytest.mark.parametrize('frontend_framework', ['vue2', 'vue3', 'react', 'custom_ui-1'])
def test_sdk_workspace_records_selected_source(tmp_path: Path, frontend_framework: str) -> None:
    """校验 SDK 来源记录使用当前项目名及所选的 Web 工程。"""
    sdk = write_source(tmp_path / 'ruoyi-fastapi-frontend' / frontend_framework / 'web')
    metadata = json.loads(sdk.build_vendor_files()[SDK_METADATA])
    assert metadata['source'] == {
        'project': 'RuoYi-FastAPI',
        'directory': f'ruoyi-fastapi-frontend/{frontend_framework}/web/src/utils',
    }
    project = write_project(tmp_path / 'project', sdk)
    assert sdk.check(project)['status'] == 'current'


def test_sdk_preserves_independent_host_framework_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """校验离线 SDK 在独立工程中保留环境框架提示，标准目录保留自身身份。"""
    monkeypatch.setenv('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'custom_ui-1')
    sdk = write_source(tmp_path / 'independent-frontend')
    metadata = json.loads(sdk.build_vendor_files()[SDK_METADATA])
    assert metadata['source']['directory'] == 'ruoyi-fastapi-frontend/custom_ui-1/web/src/utils'
    standard_sdk = write_source(tmp_path / 'ruoyi-fastapi-frontend/react/web')
    standard_metadata = json.loads(standard_sdk.build_vendor_files()[SDK_METADATA])
    assert standard_metadata['source']['directory'] == 'ruoyi-fastapi-frontend/react/web/src/utils'


@pytest.mark.parametrize(
    'source',
    [
        {'project': 'RuoYi-Vue3-FastAPI', 'directory': 'ruoyi-fastapi-frontend/vue3/web/src/utils'},
        {'project': 'RuoYi-FastAPI', 'directory': 'ruoyi-fastapi-frontend/../web/src/utils'},
        {'project': 'RuoYi-FastAPI', 'directory': 'ruoyi-fastapi-frontend/auto/web/src/utils'},
        {'project': 'RuoYi-FastAPI', 'directory': 'ruoyi-fastapi-frontend/React/web/src/utils'},
        {'project': 'RuoYi-FastAPI', 'directory': 'ruoyi-fastapi-frontend/react\\outside/web/src/utils'},
        {'project': 'RuoYi-FastAPI', 'directory': 'ruoyi-fastapi-frontend/react/web/src/utils/extra'},
    ],
)
def test_sdk_rejects_invalid_vendor_source(tmp_path: Path, source: dict[str, str]) -> None:
    """校验旧项目名和非规范框架目录不能作为有效 SDK 来源。"""
    sdk = write_source(tmp_path / 'frontend')
    project = write_project(tmp_path / 'project', sdk)
    metadata_path = project / 'web/vendor' / SDK_METADATA
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    metadata['source'] = source
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')

    report = sdk.check(project)

    assert not report['ok']
    assert report['status'] == 'invalid'


@pytest.mark.parametrize('target', ['pluginBridge.js', 'pluginBridge.d.ts', 'pluginBridge.sdk.json'])
def test_invalid_source_version_cannot_be_used(tmp_path: Path, target: str) -> None:
    """宿主源三份版本声明必须一致，强制模式不能绕过源错误。"""
    frontend = tmp_path / 'frontend'
    sdk = write_source(frontend)
    project = write_project(tmp_path / 'project', sdk)
    before = snapshot(project)
    path = frontend / 'src' / 'utils' / target
    path.write_text(path.read_text(encoding='utf-8').replace('1.0.0', '9.0.0'), encoding='utf-8')
    with pytest.raises(ValueError, match='版本声明'):
        sdk.build_vendor_files()
    assert sdk.check(project)['status'] == 'invalid'
    assert not sdk.update(project, force=True)['ok']
    assert snapshot(project) == before


@pytest.mark.parametrize(
    ('field', 'value'),
    [('schemaVersion', True), ('bridgeVersion', True), ('sdkVersion', 'latest'), ('capabilities', {'files': True})],
)
def test_invalid_source_metadata_types_fail_closed(tmp_path: Path, field: str, value: Any) -> None:
    """布尔值不能代替版本整数，无效来源元数据不能生成副本。"""
    sdk = write_source(tmp_path)
    path = tmp_path / 'src' / 'utils' / SDK_METADATA
    metadata = json.loads(path.read_text(encoding='utf-8'))
    metadata[field] = value
    path.write_text(json.dumps(metadata), encoding='utf-8')
    with pytest.raises(ValueError):
        sdk.build_vendor_files()


def test_outdated_optional_capability_remains_protocol_compatible(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """旧版缺少 streams 时仍兼容通信协议，但 CI 检查不会误报为最新副本。"""
    sdk, project = outdated
    report = sdk.check(project)
    assert not report['ok']
    assert report['status'] == 'outdated'
    assert report['sdkVersion'] == '0.9.0'
    assert report['currentSdkVersion'] == '1.0.0'
    assert report['protocolCompatible'] is True
    assert report['updateAvailable'] is True


def test_update_previews_then_backs_up_exact_bytes_and_writes_metadata_last(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """预演零写入，实际更新先备份且最后替换来源记录，不改业务文件。"""
    sdk, project = outdated
    before = snapshot(project)
    preview = sdk.update(project, dry_run=True)
    assert preview['ok'] and preview['dryRun'] and not preview['updated']
    assert snapshot(project) == before
    assert not (project / '.plugin-sdk-backups').exists()
    calls = []
    replace = os.replace

    def record_replace(source: Path, target: Path) -> None:
        """记录原子替换顺序以验证元数据只在代码之后发布。"""
        calls.append(target.name)
        replace(source, target)

    monkeypatch.setattr(os, 'replace', record_replace)
    report = sdk.update(project)
    assert report['ok'] and report['updated'] and report['status'] == 'current'
    assert calls == list(VENDOR_FILES)
    backup = Path(report['backupDir'])
    for name in VENDOR_FILES:
        assert (backup / name).read_bytes() == before[str(Path('web/vendor') / name)]
    assert (project / 'web/business.js').read_bytes() == before[str(Path('web/business.js'))]
    assert not (project / '.plugin-sdk.lock').exists()
    no_op = sdk.update(project)
    assert no_op['ok'] and not no_op['updated'] and no_op['backupDir'] is None
    assert len(list((project / '.plugin-sdk-backups').iterdir())) == 1


@pytest.mark.parametrize('state', ['modified', 'untracked', 'invalid', 'missing_file'])
def test_local_changes_require_force_and_are_backed_up(outdated: tuple[PluginBridgeSdk, Path], state: str) -> None:
    """本地改动、缺文件及来源记录损坏只允许显式备份后覆盖。"""
    sdk, project = outdated
    vendor = project / 'web/vendor'
    if state == 'modified':
        (vendor / SDK_FILES[0]).write_bytes(b'local edits\r\n')
    elif state == 'untracked':
        (vendor / SDK_METADATA).unlink()
    elif state == 'invalid':
        (vendor / SDK_METADATA).write_bytes(b'{broken')
    else:
        (vendor / SDK_FILES[1]).unlink()
    before = snapshot(project)
    expected = 'modified' if state == 'missing_file' else state
    assert sdk.check(project)['status'] == expected
    assert not sdk.update(project)['ok']
    assert snapshot(project) == before
    assert sdk.update(project, force=True, dry_run=True)['ok']
    assert snapshot(project) == before
    report = sdk.update(project, force=True)
    assert report['ok'] and report['status'] == 'current'
    backup = Path(report['backupDir'])
    for name in VENDOR_FILES:
        relative = str(Path('web/vendor') / name)
        assert (backup / name).exists() == (relative in before)
        if relative in before:
            assert (backup / name).read_bytes() == before[relative]


def test_protocol_change_is_not_force_updatable(tmp_path: Path) -> None:
    """不同通信协议需要人工迁移，不能借 --force 越过该边界。"""
    frontend = tmp_path / 'frontend'
    sdk = write_source(frontend)
    project = write_project(tmp_path / 'project', sdk)
    write_source(frontend, wire=2)
    before = snapshot(project)
    report = sdk.check(project)
    assert report['status'] == 'incompatible' and report['protocolCompatible'] is False
    assert not sdk.update(project, force=True)['ok']
    assert snapshot(project) == before


@pytest.mark.parametrize('metadata_state', ['tracked', 'untracked', 'invalid'])
def test_actual_modified_wire_cannot_be_hidden_by_metadata(
    outdated: tuple[PluginBridgeSdk, Path], metadata_state: str
) -> None:
    """实际导出协议不同即拒绝强制更新，不依赖旧记录是否存在或完整。"""
    sdk, project = outdated
    vendor = project / 'web/vendor'
    path = vendor / SDK_FILES[0]
    path.write_text(
        path.read_text(encoding='utf-8').replace('PLUGIN_BRIDGE_VERSION = 1', 'PLUGIN_BRIDGE_VERSION = 2'),
        encoding='utf-8',
    )
    if metadata_state == 'untracked':
        (vendor / SDK_METADATA).unlink()
    elif metadata_state == 'invalid':
        (vendor / SDK_METADATA).write_bytes(b'{broken')
    before = snapshot(project)
    report = sdk.check(project)
    assert report['status'] == 'incompatible'
    assert report['protocolCompatible'] is False
    assert not sdk.update(project, force=True)['ok']
    assert snapshot(project) == before


def test_metadata_wire_conflict_cannot_be_force_ignored(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """元数据声明不同协议时，不能仅凭代码的当前协议导出宣布兼容。"""
    sdk, project = outdated
    path = project / 'web/vendor' / SDK_METADATA
    metadata = json.loads(path.read_text(encoding='utf-8'))
    metadata['bridgeVersion'] = 2
    path.write_text(json.dumps(metadata), encoding='utf-8')
    before = snapshot(project)
    assert sdk.check(project)['protocolCompatible'] is False
    assert not sdk.update(project, force=True)['ok']
    assert snapshot(project) == before


def test_unrecognizable_actual_wire_remains_unknown(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """实际声明无法静态识别时不再使用旧元数据伪报兼容。"""
    sdk, project = outdated
    path = project / 'web/vendor' / SDK_FILES[0]
    path.write_text('export const PLUGIN_BRIDGE_VERSION = getVersion()\n', encoding='utf-8')
    report = sdk.check(project)
    assert report['status'] == 'modified'
    assert report['protocolCompatible'] is None
    assert sdk.update(project, force=True)['ok']


def test_legacy_untracked_wire_one_without_sdk_version_can_be_adopted(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """早期没有独立 SDK 版本常量的协议 v1 副本仍能显式备份纳管。"""
    sdk, project = outdated
    vendor = project / 'web/vendor'
    (vendor / SDK_METADATA).unlink()
    for name in SDK_FILES:
        path = vendor / name
        text = path.read_text(encoding='utf-8')
        path.write_text(
            '\n'.join(line for line in text.splitlines() if 'PLUGIN_BRIDGE_SDK_VERSION' not in line), encoding='utf-8'
        )
    report = sdk.check(project)
    assert report['status'] == 'untracked' and report['protocolCompatible'] is True
    assert not sdk.update(project)['ok']
    assert sdk.update(project, force=True)['ok']


@pytest.mark.parametrize('manifest', [{}, {'manifestVersion': 1}, {'manifestVersion': True}, {'manifestVersion': 2}])
def test_invalid_project_is_never_force_updatable(
    outdated: tuple[PluginBridgeSdk, Path], manifest: dict[str, Any]
) -> None:
    """强制模式不允许更新非 v2 bundle 工程。"""
    sdk, project = outdated
    (project / 'plugin.yaml').write_text(yaml.safe_dump(manifest), encoding='utf-8')
    before = snapshot(project)
    assert sdk.check(project)['status'] == 'invalid'
    assert not sdk.update(project, force=True)['ok']
    assert snapshot(project) == before


def test_existing_lock_is_preserved_and_prevents_update(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """其他更新持有的锁不会被覆盖或自动清理。"""
    sdk, project = outdated
    (project / '.plugin-sdk.lock').write_text('other updater', encoding='utf-8')
    before = snapshot(project)
    report = sdk.update(project)
    assert not report['ok'] and '锁已存在' in report['message']
    assert snapshot(project) == before


@pytest.mark.parametrize('failure_file', list(VENDOR_FILES))
def test_failed_update_restores_originals_and_keeps_backup(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch, failure_file: str
) -> None:
    """任一替换失败均恢复原有三个文件，包括原始换行字节。"""
    sdk, project = outdated
    before = snapshot(project)
    replace = os.replace
    failed = False

    def fail_once(source: Path, target: Path) -> None:
        """模拟磁盘替换失败一次，使后续回滚仍可写回原内容。"""
        nonlocal failed
        if target.name == failure_file and not failed:
            failed = True
            raise OSError('simulated replacement failure')
        replace(source, target)

    monkeypatch.setattr(os, 'replace', fail_once)
    report = sdk.update(project)
    assert not report['ok'] and not report['updated']
    assert Path(report['backupDir']).is_dir()
    for name in VENDOR_FILES:
        assert (project / 'web/vendor' / name).read_bytes() == before[str(Path('web/vendor') / name)]
    assert sdk.check(project)['status'] == 'outdated'
    assert not (project / '.plugin-sdk.lock').exists()
    assert not list((project / 'web/vendor').glob('*.tmp'))


def test_final_content_verification_failure_rolls_back(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件系统未报错但最终内容不匹配时仍回滚，不能宣布更新成功。"""
    sdk, project = outdated
    before = snapshot(project)
    replace = os.replace
    corrupted = False

    def corrupt_once(source: Path, target: Path) -> None:
        """模拟元数据发布后发现实际文件字节不同。"""
        nonlocal corrupted
        replace(source, target)
        if target.name == SDK_METADATA and not corrupted:
            corrupted = True
            (target.parent / SDK_FILES[0]).write_bytes(b'simulated corrupted bytes')

    monkeypatch.setattr(os, 'replace', corrupt_once)
    report = sdk.update(project)
    assert not report['ok'] and not report['updated']
    assert '内容校验失败' in report['message']
    for name in VENDOR_FILES:
        assert (project / 'web/vendor' / name).read_bytes() == before[str(Path('web/vendor') / name)]
    assert sdk.check(project)['status'] == 'outdated'


def test_untracked_creation_failure_removes_new_files(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """纳管空 vendor 失败后删除本次新增 SDK 文件，不留下半套副本。"""
    sdk, project = outdated
    for name in VENDOR_FILES:
        (project / 'web/vendor' / name).unlink()
    replace = os.replace

    def fail_metadata(source: Path, target: Path) -> None:
        """模拟首次创建副本时发布元数据失败。"""
        if target.name == SDK_METADATA:
            raise OSError('metadata write failed')
        replace(source, target)

    monkeypatch.setattr(os, 'replace', fail_metadata)
    report = sdk.update(project, force=True)
    assert not report['ok']
    assert not list((project / 'web/vendor').iterdir())
    assert not (project / '.plugin-sdk.lock').exists()
    assert sdk.check(project)['status'] == 'untracked'


def test_rollback_failure_reports_backup_and_continues_other_files(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """恢复其中一个文件失败时继续处理其他文件，并明确提示使用备份。"""
    sdk, project = outdated
    before = snapshot(project)
    replace = os.replace

    def fail_types(source: Path, target: Path) -> None:
        """模拟类型声明文件持续无法替换。"""
        if target.name == SDK_FILES[1]:
            raise OSError('type file unavailable')
        replace(source, target)

    monkeypatch.setattr(os, 'replace', fail_types)
    report = sdk.update(project)
    assert not report['ok'] and '回滚未完成' in report['message']
    backup = Path(report['backupDir'])
    assert str(backup) in report['message']
    for name in VENDOR_FILES:
        assert (backup / name).read_bytes() == before[str(Path('web/vendor') / name)]
    assert (project / 'web/vendor' / SDK_FILES[0]).read_bytes() == before[str(Path('web/vendor') / SDK_FILES[0])]
    assert not (project / '.plugin-sdk.lock').exists()


@pytest.mark.parametrize('relative', ['web', 'web/vendor', 'web/vendor/pluginBridge.js', '.plugin-sdk-backups'])
def test_windows_reparse_components_are_rejected(
    outdated: tuple[PluginBridgeSdk, Path], monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    """无需创建链接权限也覆盖 Windows 重解析点及父路径拒绝逻辑。"""
    sdk, project = outdated
    before = snapshot(project)
    rejected = project / relative
    lstat = Path.lstat

    def reparse_lstat(path: Path) -> Any:
        """将指定路径模拟为 Windows 重解析点。"""
        if path == rejected:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return lstat(path)

    monkeypatch.setattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400, raising=False)
    monkeypatch.setattr(Path, 'lstat', reparse_lstat)
    report = sdk.update(project, force=True)
    assert not report['ok'] and '重解析点' in report['message']
    assert snapshot(project) == before


def test_metadata_cannot_choose_target_paths(outdated: tuple[PluginBridgeSdk, Path]) -> None:
    """篡改摘要键不能让更新读取或覆盖固定三文件以外的路径。"""
    sdk, project = outdated
    metadata_path = project / 'web/vendor' / SDK_METADATA
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    metadata['files']['../business.js'] = metadata['files'].pop(SDK_FILES[0])
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    before = (project / 'web/business.js').read_bytes()
    assert sdk.check(project)['status'] == 'invalid'
    assert not sdk.update(project)['ok']
    assert sdk.update(project, force=True)['ok']
    assert (project / 'web/business.js').read_bytes() == before


@pytest.mark.parametrize('target_name', ['pluginBridge.js', 'pluginBridge.sdk.json', '.plugin-sdk-backups'])
def test_symlinks_are_rejected_without_touching_target(
    outdated: tuple[PluginBridgeSdk, Path], tmp_path: Path, target_name: str
) -> None:
    """SDK 文件和备份路径中的符号链接不能作为可强制覆盖的普通副本。"""
    sdk, project = outdated
    directory = target_name == '.plugin-sdk-backups'
    target = tmp_path / 'outside'
    if directory:
        target.mkdir()
    else:
        target.write_bytes(b'outside unchanged')
    link = project / target_name if directory else project / 'web/vendor' / target_name
    if link.exists():
        link.unlink()
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f'当前平台不允许创建测试符号链接：{exc}')
    assert not sdk.update(project, force=True)['ok']
    if directory:
        assert not list(target.iterdir())
    else:
        assert target.read_bytes() == b'outside unchanged'
    assert link.is_symlink()
