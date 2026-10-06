import base64
import hashlib
import json
import os
import stat
import struct
import sys
from dataclasses import replace
from pathlib import Path
from zipfile import ZIP_BZIP2, ZIP_STORED, ZipFile, ZipInfo

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from plugins.core.artifacts import ArtifactLimits, build_artifact, verify_artifact
from plugins.core.artifacts import package as artifact_package
from plugins.core.artifacts.schema import ArtifactMetadata, safe_artifact_path, strict_json

EXPECTED_ARTIFACT_FILE_COUNT = 4


def archive_files(path: Path) -> dict[str, bytes]:
    """读取测试容器中的全部文件，供定向篡改用例使用。"""
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def write_archive(path: Path, files: dict[str, bytes], compression: int = ZIP_STORED) -> Path:
    """按测试给定内容重建 ZIP 容器。"""
    with ZipFile(path, 'w', compression=compression) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def signed_files(artifact_path: Path, signing_key: Ed25519PrivateKey, *, manifest: bytes) -> dict[str, bytes]:
    """生成测试所需的规范元数据及有效签名文档。"""
    files = archive_files(artifact_path)
    name = 'payload/artifact_demo/plugin.yaml'
    files[name] = manifest
    metadata = json.loads(files['artifacts.json'])
    for item in metadata['files']:
        if item['path'] == name:
            item.update(size=len(manifest), sha256=hashlib.sha256(manifest).hexdigest())
    canonical = ArtifactMetadata.model_validate(metadata).canonical_bytes()
    files['artifacts.json'] = canonical
    signature = json.loads(files['signature.json'])
    signature['signature'] = base64.b64encode(signing_key.sign(canonical)).decode()
    files['signature.json'] = json.dumps(signature).encode()
    return files


def test_roundtrip_is_static_and_canonical(
    artifact_source: Path,
    artifact_path: Path,
    tmp_path: Path,
    signing_key: Ed25519PrivateKey,
    trusted_keys: dict[str, Ed25519PublicKey],
) -> None:
    """验证构建和校验保持规范摘要且不导入插件代码。"""
    first = verify_artifact(artifact_path, trusted_keys)
    second = build_artifact(artifact_source, tmp_path / 'second.rpk', signing_key, 'publisher')
    assert first.digest == second.digest == hashlib.sha256(first.metadata.canonical_bytes()).hexdigest()
    assert first.plugin_id == 'artifact_demo'
    assert first.version == '1.0.0'
    assert first.key_id == 'publisher'
    assert len(first.files) == EXPECTED_ARTIFACT_FILE_COUNT
    assert 'plugins.artifact_demo' not in sys.modules
    files = archive_files(artifact_path)
    metadata = json.loads(files['artifacts.json'])
    files['artifacts.json'] = json.dumps(dict(reversed(list(metadata.items()))), indent=4).encode()
    reformatted = write_archive(tmp_path / 'reformatted.rpk', files)
    assert verify_artifact(reformatted, trusted_keys).digest == first.digest


@pytest.mark.parametrize('encoding', ['raw', 'base64', 'pem', 'object'])
def test_external_public_key_encodings(
    artifact_path: Path,
    signing_key: Ed25519PrivateKey,
    encoding: str,
) -> None:
    """验证宿主可信公钥支持规定的输入编码。"""
    key = signing_key.public_key()
    encodings = {
        'raw': key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
        'base64': base64.b64encode(
            key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode(),
        'pem': key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
        'object': key,
    }
    assert verify_artifact(artifact_path, {'publisher': encodings[encoding]}).key_id == 'publisher'


@pytest.mark.parametrize('encoding', ['raw', 'base64', 'pem'])
def test_private_key_encodings_are_only_used_for_signing(
    artifact_source: Path,
    tmp_path: Path,
    signing_key: Ed25519PrivateKey,
    encoding: str,
) -> None:
    """验证不同私钥编码可用于签名且不会泄露到制品。"""
    raw = signing_key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    encodings = {
        'raw': raw,
        'base64': base64.b64encode(raw).decode(),
        'pem': signing_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
    }
    result = build_artifact(artifact_source, tmp_path / 'encoded.rpk', encodings[encoding], 'publisher')
    assert set(archive_files(result.artifact_path)) == {'artifacts.json', 'signature.json'} | {
        item.path for item in result.files
    }


@pytest.mark.parametrize('keys', ['missing', 'wrong'])
def test_untrusted_or_wrong_key_rejected(artifact_path: Path, keys: str) -> None:
    """验证未信任或错误的签名密钥无法通过校验。"""
    trust = {} if keys == 'missing' else {'publisher': Ed25519PrivateKey.generate().public_key()}
    with pytest.raises(ValueError, match=r'密钥|签名验证失败'):
        verify_artifact(artifact_path, trust)


@pytest.mark.parametrize(
    'mutation', ['payload', 'metadata', 'missing', 'extra', 'signature', 'algorithm', 'self-trust']
)
def test_tampered_archives_rejected(
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证元数据、签名及文件内容的篡改均被拒绝。"""
    files = archive_files(artifact_path)
    if mutation == 'payload':
        files['payload/artifact_demo/LICENSE'] = b'Forgery of equal size.\n'
    elif mutation == 'metadata':
        metadata = json.loads(files['artifacts.json'])
        metadata['version'] = '1.0.1'
        files['artifacts.json'] = json.dumps(metadata).encode()
    elif mutation == 'missing':
        del files['payload/artifact_demo/LICENSE']
    elif mutation == 'extra':
        files['payload/artifact_demo/extra.txt'] = b'not signed'
    else:
        signature = json.loads(files['signature.json'])
        if mutation == 'signature':
            signature['signature'] = base64.b64encode(b'x' * 64).decode()
        elif mutation == 'algorithm':
            signature['algorithm'] = 'RSA'
        else:
            signature['publicKey'] = base64.b64encode(b'x' * 32).decode()
        files['signature.json'] = json.dumps(signature).encode()
    with pytest.raises(ValueError):
        verify_artifact(write_archive(tmp_path / 'tampered.rpk', files), trusted_keys)


@pytest.mark.parametrize(
    'raw', [b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}', b'{"a":Infinity}', b'[]', b'\xff']
)
def test_strict_json_rejects_ambiguous_documents(raw: bytes) -> None:
    """验证 JSON 重复键和非法常量不能进入签名文档。"""
    with pytest.raises(ValueError):
        strict_json(raw)


@pytest.mark.parametrize('value', [True, 1.0, '1', 2])
def test_metadata_version_is_exact_integer_one(artifact_path: Path, value: object) -> None:
    """验证协议版本只接受整数1。"""
    metadata = json.loads(archive_files(artifact_path)['artifacts.json'])
    metadata['schemaVersion'] = value
    with pytest.raises(ValueError):
        ArtifactMetadata.model_validate(metadata)


@pytest.mark.parametrize('field,value', [('size', True), ('size', -1), ('sha256', 'F' * 64), ('unexpected', 1)])
def test_file_records_reject_coercion_and_unknown_fields(artifact_path: Path, field: str, value: object) -> None:
    """验证文件记录不接受隐式类型转换或未知字段。"""
    metadata = json.loads(archive_files(artifact_path)['artifacts.json'])
    metadata['files'][0][field] = value
    with pytest.raises(ValueError):
        ArtifactMetadata.model_validate(metadata)


@pytest.mark.parametrize('value', ['1.0.RC1', '1.0.0.', 'a' * 33, '../1', '1/2', 'con'])
def test_versions_are_portable_and_database_bounded(artifact_path: Path, value: str) -> None:
    """验证版本字符串满足路径可移植性与数据库长度限制。"""
    metadata = json.loads(archive_files(artifact_path)['artifacts.json'])
    metadata['version'] = value
    with pytest.raises(ValueError):
        ArtifactMetadata.model_validate(metadata)


@pytest.mark.parametrize(
    'path',
    [
        '/absolute',
        '../escape',
        'a/../../b',
        'a\\b',
        'C:/escape',
        'a/CON',
        'a/nul.txt',
        'a:stream',
        'a//b',
        'a/./b',
        'a/end.',
        'a/end ',
        'a/\x00b',
        'a/\x1fb',
        'a/\x7fb',
        'a/e\u0301',
        'a/' + 'b' * 256,
    ],
)
def test_paths_reject_cross_platform_ambiguity(path: str) -> None:
    """验证路径校验拒绝跨平台歧义和目录穿越。"""
    with pytest.raises(ValueError, match='不安全路径'):
        safe_artifact_path(path)


@pytest.mark.parametrize(
    'names',
    [
        ('../escape',),
        ('/absolute',),
        ('a\\b',),
        ('a:stream',),
        ('a/CON',),
        ('Foo/x', 'foo/y'),
        ('a', 'a/b'),
        ('a/',),
        ('payload//',),
    ],
)
def test_zip_inventory_rejects_unsafe_extra_paths(
    artifact_path: Path,
    tmp_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    names: tuple[str, ...],
) -> None:
    """验证 ZIP 中额外的不安全路径不能绕过清单检查。"""
    files = archive_files(artifact_path)
    files.update(dict.fromkeys(names, b''))
    with pytest.raises(ValueError):
        verify_artifact(write_archive(tmp_path / 'unsafe.rpk', files), trusted_keys)


@pytest.mark.parametrize(
    'mode,windows_attributes', [(stat.S_IFLNK | 0o777, 0), (stat.S_IFIFO | 0o600, 0), (stat.S_IFREG | 0o600, 0x400)]
)
def test_zip_special_files_rejected(
    artifact_path: Path,
    tmp_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    mode: int,
    windows_attributes: int,
) -> None:
    """验证 ZIP 不接受链接、重解析点或特殊文件。"""
    target = tmp_path / 'special.rpk'
    files = archive_files(artifact_path)
    with ZipFile(target, 'w') as archive:
        for name, data in files.items():
            item = ZipInfo(name)
            item.create_system = 3
            item.external_attr = (mode << 16) | windows_attributes
            archive.writestr(item, data)
    with pytest.raises(ValueError, match='特殊文件'):
        verify_artifact(target, trusted_keys)


def test_duplicate_zip_member_rejected(artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]) -> None:
    """验证重复的压缩条目被拒绝。"""
    with ZipFile(artifact_path, 'a') as archive, pytest.warns(UserWarning, match='Duplicate'):
        archive.writestr('payload/artifact_demo/LICENSE', b'duplicate')
    with pytest.raises(ValueError, match='重复'):
        verify_artifact(artifact_path, trusted_keys)


def test_zip_null_name_rejected(artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]) -> None:
    """验证包含空字符导致截断的文件名被拒绝。"""
    artifact_path.write_bytes(artifact_path.read_bytes().replace(b'/LICENSE', b'/LI\x00ENSE'))
    with pytest.raises(ValueError, match='截断'):
        verify_artifact(artifact_path, trusted_keys)


def test_zip_unsupported_compression_rejected(
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    tmp_path: Path,
) -> None:
    """验证不支持的压缩算法被拒绝。"""
    target = write_archive(tmp_path / 'bzip2.rpk', archive_files(artifact_path), ZIP_BZIP2)
    with pytest.raises(ValueError, match='压缩算法'):
        verify_artifact(target, trusted_keys)


def test_zip_encryption_flag_rejected(artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey]) -> None:
    """验证设置加密标记的压缩条目被拒绝。"""
    data = bytearray(artifact_path.read_bytes())
    central = data.index(b'PK\x01\x02')
    struct.pack_into('<H', data, central + 8, 1)
    artifact_path.write_bytes(data)
    with pytest.raises(ValueError, match='加密'):
        verify_artifact(artifact_path, trusted_keys)


def test_crc_failure_rejected(artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey], tmp_path: Path) -> None:
    """验证 CRC 错误会使制品校验失败。"""
    target = write_archive(tmp_path / 'crc.rpk', archive_files(artifact_path))
    with ZipFile(target) as archive:
        entry = archive.getinfo('payload/artifact_demo/LICENSE')
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    data = bytearray(target.read_bytes())
    data[offset] ^= 1
    target.write_bytes(data)
    with pytest.raises(ValueError, match='CRC'):
        verify_artifact(target, trusted_keys)


@pytest.mark.parametrize(
    'limit',
    [
        'max_files',
        'max_file_bytes',
        'max_total_bytes',
        'max_archive_bytes',
        'max_metadata_bytes',
        'max_signature_bytes',
        'max_manifest_bytes',
        'max_central_directory_bytes',
        'max_compression_ratio',
    ],
)
def test_all_resource_limits_apply(artifact_path: Path, trusted_keys: dict[str, Ed25519PublicKey], limit: str) -> None:
    """验证容器、元数据及展开文件的各项资源上限生效。"""
    with pytest.raises(ValueError):
        verify_artifact(artifact_path, trusted_keys, limits=replace(ArtifactLimits(), **{limit: 1}))


@pytest.mark.parametrize('mutation', ['underreported', 'directory-size', 'zip64', 'multidisk', 'truncated'])
def test_central_directory_is_bounded_before_zipfile_allocates(
    artifact_path: Path,
    trusted_keys: dict[str, Ed25519PublicKey],
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证在 ZipFile 分配条目对象前限制中央目录和实际文件数量。"""
    data = bytearray(artifact_path.read_bytes())
    end = len(data) - 22
    limits = ArtifactLimits()
    if mutation == 'underreported':
        struct.pack_into('<HH', data, end + 8, 0, 0)
        limits = replace(limits, max_files=2)
    elif mutation == 'directory-size':
        limits = replace(limits, max_central_directory_bytes=1)
    elif mutation == 'zip64':
        struct.pack_into('<HH', data, end + 8, 65535, 65535)
    elif mutation == 'multidisk':
        struct.pack_into('<H', data, end + 4, 1)
    else:
        del data[-4:]
    artifact_path.write_bytes(data)

    def allocation_forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('ZipFile must not allocate an unbounded inventory before preflight')

    monkeypatch.setattr(artifact_package, 'ZipFile', allocation_forbidden)
    with pytest.raises(ValueError):
        verify_artifact(artifact_path, trusted_keys, limits=limits)


@pytest.mark.parametrize('mutation', ['v1', 'source', 'identity', 'version'])
def test_signed_manifest_must_match_supported_deployment_protocol(
    artifact_path: Path,
    signing_key: Ed25519PrivateKey,
    trusted_keys: dict[str, Ed25519PublicKey],
    tmp_path: Path,
    mutation: str,
) -> None:
    """验证签名清单的身份与版本匹配且采用受支持的交付协议。"""
    manifest = yaml.safe_load(archive_files(artifact_path)['payload/artifact_demo/plugin.yaml'])
    if mutation == 'v1':
        manifest['manifestVersion'] = 1
    elif mutation == 'source':
        manifest['frontend'] = {'delivery': {'type': 'source'}}
    elif mutation == 'identity':
        manifest['id'] = 'another_plugin'
        manifest['backend']['module'] = 'plugins.another_plugin'
        manifest['backend']['entrypoint'] = 'plugins.another_plugin:create_plugin'
    else:
        manifest['version'] = '2.0.0'
    files = signed_files(artifact_path, signing_key, manifest=yaml.safe_dump(manifest).encode())
    with pytest.raises(ValueError):
        verify_artifact(write_archive(tmp_path / 'protocol.rpk', files), trusted_keys)


@pytest.mark.parametrize(
    'filename',
    [
        'Cargo.toml',
        'web/package.json',
        'native/src/lib.rs',
        'web/src/App.vue',
        '.env',
        'node_modules/a.js',
        '.git/config',
    ],
)
def test_builder_rejects_source_projects(
    artifact_source: Path, tmp_path: Path, signing_key: Ed25519PrivateKey, filename: str
) -> None:
    """验证构建器拒绝将源码工程文件打入部署制品。"""
    extra = artifact_source / filename
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b'source')
    with pytest.raises(ValueError, match='预构建'):
        build_artifact(artifact_source, tmp_path / 'invalid.rpk', signing_key, 'publisher')
    assert not (tmp_path / 'invalid.rpk').exists()


def test_builder_ignores_python_caches(artifact_source: Path, tmp_path: Path, signing_key: Ed25519PrivateKey) -> None:
    """验证构建器只忽略允许的 Python 与测试缓存。"""
    (artifact_source / '__pycache__').mkdir()
    (artifact_source / '__pycache__' / 'old.pyc').write_bytes(b'cache')
    result = build_artifact(artifact_source, tmp_path / 'no-cache.rpk', signing_key, 'publisher')
    assert all('__pycache__' not in item.path and not item.path.endswith('.pyc') for item in result.files)


def test_builder_never_overwrites_or_writes_inside_source(
    artifact_source: Path,
    artifact_path: Path,
    signing_key: Ed25519PrivateKey,
) -> None:
    """验证构建器不覆盖输出且不向源目录内写入制品。"""
    before = artifact_path.read_bytes()
    with pytest.raises(FileExistsError):
        build_artifact(artifact_source, artifact_path, signing_key, 'publisher')
    assert artifact_path.read_bytes() == before
    with pytest.raises(ValueError, match='源插件目录'):
        build_artifact(artifact_source, artifact_source / 'self.rpk', signing_key, 'publisher')


def test_builder_rejects_hardlinks(artifact_source: Path, tmp_path: Path, signing_key: Ed25519PrivateKey) -> None:
    """验证构建器拒绝已建立额外硬链接的部署文件。"""
    os.link(artifact_source / 'LICENSE', tmp_path / 'linked-license')
    with pytest.raises(ValueError, match='硬链接'):
        build_artifact(artifact_source, tmp_path / 'hardlink.rpk', signing_key, 'publisher')
