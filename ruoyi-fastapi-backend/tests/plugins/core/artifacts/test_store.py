import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from plugins.core.artifacts.package import verify_artifact
from plugins.core.artifacts.schema import StoredArtifact, VerifiedArtifact
from plugins.core.artifacts.store import ArtifactStore


def _parallel_import(root: str, artifact_path: str, public_key: bytes, gate: Any) -> tuple[str, str]:
    """在独立进程中同步校验起点，使并发导入争用同一制品目标。"""
    checked = False

    def check_candidate(candidate: StoredArtifact) -> None:
        nonlocal checked
        assert (candidate.plugin_path / 'plugin.yaml').is_file()
        if not checked:
            checked = True
            gate.wait(timeout=30)

    stored = ArtifactStore(root).import_artifact(
        artifact_path, {'publisher': public_key}, validate_candidate=check_candidate
    )
    return str(stored.root_path), stored.digest


def _assert_staging_empty(root: Path) -> None:
    """检查本次导入没有遗留暂存目录。"""
    staging = root / '.staging'
    assert staging.is_dir()
    assert list(staging.iterdir()) == []


def _file_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """记录存储文件内容和修改时间以比较幂等导入结果。"""
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in root.rglob('*')
        if path.is_file()
    }


def test_roundtrip_verifies_root_plugin_path_and_digest_without_importing_code(
    tmp_path: Path,
    artifact_path: Path,
    artifact_source: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
) -> None:
    """验证不同定位方式均重新校验制品且不导入插件代码。"""
    store = ArtifactStore(tmp_path / 'store')
    expected = verify_artifact(artifact_path, trusted_keys)
    stored = store.import_artifact(artifact_path, trusted_keys)

    assert stored.root_path == store.root / expected.plugin_id / expected.version / expected.digest
    assert stored.plugin_path == stored.root_path / 'payload' / expected.plugin_id
    assert (stored.plugin_path / '__init__.py').read_bytes() == (artifact_source / '__init__.py').read_bytes()
    assert f'plugins.{expected.plugin_id}' not in sys.modules
    for reference in (
        stored.root_path,
        stored.plugin_path,
        stored.digest,
        stored.root_path.relative_to(store.root),
        stored.plugin_path.relative_to(store.root),
    ):
        verified = store.verify_stored(reference, trusted_keys)
        assert verified.root_path == stored.root_path
        assert verified.plugin_path == stored.plugin_path
        assert verified.digest == expected.digest
    _assert_staging_empty(store.root)


def test_repeated_import_keeps_existing_bytes_and_modification_times(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证重复导入保持已有文件内容和修改时间。"""
    store = ArtifactStore(tmp_path / 'store')
    first = store.import_artifact(artifact_path, trusted_keys)
    before = _file_snapshot(first.root_path)
    checked_paths: list[Path] = []

    def check_candidate(candidate: StoredArtifact) -> None:
        checked_paths.append(candidate.root_path)

    second = store.import_artifact(artifact_path, trusted_keys, validate_candidate=check_candidate)

    assert second.root_path == first.root_path
    assert _file_snapshot(first.root_path) == before
    staged_check, existing_check = checked_paths
    assert existing_check == first.root_path
    assert staged_check != first.root_path
    _assert_staging_empty(store.root)


def test_corrupted_existing_object_is_rejected_without_overwrite(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证损坏的已有对象被拒绝且不会被自动覆盖。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    payload = stored.plugin_path / '__init__.py'
    payload.write_bytes(b'corrupted existing object')
    before = _file_snapshot(stored.root_path)

    with pytest.raises(ValueError, match=r'SHA256|大小'):
        store.import_artifact(artifact_path, trusted_keys)

    assert _file_snapshot(stored.root_path) == before
    _assert_staging_empty(store.root)


def test_current_trust_is_required_for_existing_objects_and_reimports(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证已有对象读取和重复导入均遵循当前信任配置。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    before = _file_snapshot(stored.root_path)

    with pytest.raises(ValueError, match=r'未受信任|撤销'):
        store.verify_stored(stored.digest, {})
    with pytest.raises(ValueError, match=r'未受信任|撤销'):
        store.import_artifact(artifact_path, {})

    assert _file_snapshot(stored.root_path) == before
    _assert_staging_empty(store.root)


@pytest.mark.parametrize('failure', ['reject', 'raise', 'mutate'])
def test_candidate_failure_never_publishes_or_removes_unrelated_staging(
    tmp_path: Path,
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    failure: str,
) -> None:
    """验证候选检查失败不会发布制品或删除无关暂存目录。"""
    store = ArtifactStore(tmp_path / 'store')
    unrelated = store.root / '.staging' / 'unrelated-import'
    unrelated.mkdir(parents=True)
    sentinel = unrelated / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')
    expected = verify_artifact(artifact_path, trusted_keys)

    def check_candidate(candidate: StoredArtifact) -> bool:
        if failure == 'raise':
            raise RuntimeError('platform validation failed')
        if failure == 'mutate':
            (candidate.plugin_path / '__init__.py').write_bytes(b'mutated by validator')
            return True
        return False

    error = RuntimeError if failure == 'raise' else ValueError
    with pytest.raises(error):
        store.import_artifact(artifact_path, trusted_keys, validate_candidate=check_candidate)

    assert not (store.root / expected.plugin_id / expected.version / expected.digest).exists()
    assert list((store.root / '.staging').iterdir()) == [unrelated]
    assert sentinel.read_text(encoding='utf-8') == 'keep'


def test_async_candidate_validation_is_rejected_instead_of_being_skipped(
    tmp_path: Path,
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    recwarn: pytest.WarningsRecorder,
) -> None:
    """验证异步候选回调会被明确拒绝。"""
    store = ArtifactStore(tmp_path / 'store')
    executed = False

    async def check_candidate(candidate: StoredArtifact) -> bool:
        nonlocal executed
        executed = True
        return False

    with pytest.raises(TypeError, match='同步'):
        store.import_artifact(artifact_path, trusted_keys, validate_candidate=check_candidate)

    assert not executed
    assert not any(issubclass(warning.category, RuntimeWarning) for warning in recwarn)
    assert not list(store.root.glob('*/*/' + '?' * 64))
    _assert_staging_empty(store.root)


def test_extraction_failure_cleans_only_its_private_directory(
    tmp_path: Path,
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证展开失败仅清理本次导入独占的目录。"""
    store = ArtifactStore(tmp_path / 'store')
    sentinel = tmp_path / 'keep.txt'
    sentinel.write_text('keep', encoding='utf-8')

    def fail_extract(snapshot: Path, candidate: Path, verified: VerifiedArtifact) -> None:
        assert snapshot.is_file()
        assert verified.plugin_id
        candidate.mkdir()
        (candidate / 'partial.txt').write_bytes(b'partial')
        raise OSError('disk full')

    monkeypatch.setattr(store, '_extract', fail_extract)
    with pytest.raises(OSError, match='disk full'):
        store.import_artifact(artifact_path, trusted_keys)

    assert sentinel.read_text(encoding='utf-8') == 'keep'
    _assert_staging_empty(store.root)


@pytest.mark.parametrize('mutation', ['extra_file', 'empty_directory', 'cache_file', 'missing_file'])
def test_stored_inventory_rejects_untracked_and_missing_content(
    tmp_path: Path,
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    mutation: str,
) -> None:
    """验证已存储目录拒绝新增、缺失或未登记内容。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    if mutation == 'extra_file':
        (stored.plugin_path / 'untracked.py').write_bytes(b'pass')
    elif mutation == 'empty_directory':
        (stored.plugin_path / 'unexpected').mkdir()
    elif mutation == 'cache_file':
        cache = stored.plugin_path / '__pycache__'
        cache.mkdir()
        (cache / 'module.pyc').write_bytes(b'cache must not be ignored by stored verification')
    else:
        (stored.plugin_path / '__init__.py').unlink()

    with pytest.raises(ValueError, match=r'额外|缺失|多余'):
        store.verify_stored(stored.root_path, trusted_keys)


def test_stored_files_cannot_gain_external_hardlinks(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证存储文件增加外部硬链接后无法继续通过校验。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    payload = stored.plugin_path / '__init__.py'
    external = tmp_path / 'external-hardlink.py'
    try:
        os.link(payload, external)
    except OSError as exc:
        pytest.skip(f'当前文件系统不支持创建硬链接：{exc}')

    with pytest.raises(ValueError, match=r'硬链接|链接'):
        store.verify_stored(stored.root_path, trusted_keys)
    assert external.read_bytes() == payload.read_bytes()


def test_import_verifies_the_private_snapshot_after_source_is_replaced(
    tmp_path: Path,
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证源容器替换后导入仍只使用先前建立的私有快照。"""
    expected = verify_artifact(artifact_path, trusted_keys)
    store = ArtifactStore(tmp_path / 'store')
    snapshot = store._snapshot

    def snapshot_then_replace_source(source: Path, target: Path) -> None:
        snapshot(source, target)
        source.write_bytes(b'original upload was replaced after snapshot')

    monkeypatch.setattr(store, '_snapshot', snapshot_then_replace_source)
    stored = store.import_artifact(artifact_path, trusted_keys)

    assert stored.digest == expected.digest
    assert store.verify_stored(stored.root_path, trusted_keys).digest == expected.digest
    with pytest.raises(ValueError, match='ZIP'):
        verify_artifact(artifact_path, trusted_keys)
    _assert_staging_empty(store.root)


def test_store_rejects_outside_paths_and_wrong_digest_layout(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证存储拒绝外部路径及摘要目录布局错误。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    with pytest.raises(ValueError, match='不属于'):
        store.verify_stored(tmp_path / 'outside', trusted_keys)

    wrong_name = '0' * 64 if stored.digest != '0' * 64 else '1' * 64
    renamed = stored.root_path.with_name(wrong_name)
    stored.root_path.rename(renamed)
    with pytest.raises(ValueError, match=r'身份|digest'):
        store.verify_stored(renamed, trusted_keys)


def test_concurrent_processes_publish_one_complete_object(
    tmp_path: Path,
    artifact_path: Path,
    signing_key: Ed25519PrivateKey,
    trusted_keys: dict[str, Ed25519PublicKey],
) -> None:
    """验证多个进程并发导入只发布一个完整对象。"""
    root = tmp_path / 'store'
    key_bytes = signing_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    context = multiprocessing.get_context('spawn')
    with context.Manager() as manager:
        gate = manager.Barrier(2)
        with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
            futures = [
                executor.submit(_parallel_import, str(root), str(artifact_path), key_bytes, gate) for _ in range(2)
            ]
            results = [future.result(timeout=60) for future in futures]

    assert results[0] == results[1]
    stored = ArtifactStore(root).verify_stored(results[0][1], trusted_keys)
    assert str(stored.root_path) == results[0][0]
    assert list((root / stored.plugin_id / stored.version).iterdir()) == [stored.root_path]
    _assert_staging_empty(root)


def test_symlink_store_root_is_rejected(tmp_path: Path) -> None:
    """验证存储根目录不能是符号链接。"""
    real_root = tmp_path / 'real-store'
    real_root.mkdir()
    linked_root = tmp_path / 'linked-store'
    try:
        linked_root.symlink_to(real_root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f'当前环境无符号链接创建权限：{exc}')

    with pytest.raises(ValueError, match=r'链接|重解析'):
        ArtifactStore(linked_root)
    assert list(real_root.iterdir()) == []


def test_stored_symlink_is_rejected_without_touching_external_target(
    tmp_path: Path, artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]
) -> None:
    """验证制品内符号链接被拒绝且不会修改外部目标。"""
    store = ArtifactStore(tmp_path / 'store')
    stored = store.import_artifact(artifact_path, trusted_keys)
    external = tmp_path / 'external.py'
    external.write_bytes(b'external target')
    linked = stored.plugin_path / 'external.py'
    try:
        linked.symlink_to(external)
    except OSError as exc:
        pytest.skip(f'当前环境无符号链接创建权限：{exc}')

    with pytest.raises(ValueError, match=r'链接|重解析'):
        store.verify_stored(stored.root_path, trusted_keys)
    assert external.read_bytes() == b'external target'
