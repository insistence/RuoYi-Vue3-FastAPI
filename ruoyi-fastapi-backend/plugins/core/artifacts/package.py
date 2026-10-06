import base64
import hashlib
import json
import os
import stat
import struct
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

import yaml
from cryptography.exceptions import InvalidSignature

from plugins.core.artifacts.schema import (
    DEFAULT_LIMITS,
    ArtifactFile,
    ArtifactLimits,
    ArtifactMetadata,
    ArtifactSignature,
    PrivateKeyInput,
    PublicKeyInput,
    VerifiedArtifact,
    public_key,
    safe_artifact_path,
    strict_json,
    validate_path_inventory,
)
from plugins.core.artifacts.schema import (
    private_key as load_private_key,
)
from plugins.core.manifest.schema import EXPLICIT_MANIFEST_VERSION, PluginManifest, PluginManifestFactory

CHUNK_BYTES = 1024 * 1024
ZIP_END = struct.Struct('<4s4H2LH')
ZIP_CENTRAL = struct.Struct('<4s6H3L5H2L')
ZIP_MAX_COMMENT_BYTES = 65535
ZIP64_COUNT_SENTINEL = 0xFFFF
ZIP64_SIZE_SENTINEL = 0xFFFFFFFF
ROOT_DOCUMENTS = frozenset({'artifacts.json', 'signature.json'})
CACHE_DIRECTORIES = frozenset({'__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache'})
FORBIDDEN_DIRECTORIES = CACHE_DIRECTORIES | {
    'node_modules',
    '.git',
    '.hg',
    '.svn',
    '.venv',
    'venv',
    'target',
    '.idea',
    '.vscode',
}
FORBIDDEN_FILES = frozenset(
    {
        'cargo.toml',
        'cargo.lock',
        'rust-toolchain.toml',
        'package.json',
        'package-lock.json',
        'pnpm-lock.yaml',
        'yarn.lock',
        'pyproject.toml',
        'setup.py',
        'setup.cfg',
    }
)
FORBIDDEN_SUFFIXES = frozenset({'.rs', '.vue', '.tsx', '.jsx', '.ts', '.pyc', '.pyo'})


def is_link_or_reparse(info: os.stat_result) -> bool:
    """
    判断文件状态是否表示符号链接或 Windows 重解析点。

    :param info: 通过 lstat 获取的文件状态信息
    :return: 是否为符号链接、目录联接或其他重解析点
    """
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    )


def _regular_file(path: Path) -> os.stat_result:
    """
    检查路径是否为未建立额外硬链接的普通文件。

    :param path: 待处理的文件路径
    :return: 普通文件的状态信息
    :raises ValueError: 路径为链接、特殊文件或具有额外硬链接
    """
    info = path.lstat()
    if is_link_or_reparse(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        raise ValueError(f'制品不接受链接或特殊文件：{path}')
    return info


def _payload_path(name: str) -> None:
    """
    校验部署文件路径，拒绝源码工程、环境文件和构建缓存。

    :param name: 制品内文件的规范相对路径
    :return: None
    :raises ValueError: 路径不安全或包含禁止交付的文件
    """
    path = safe_artifact_path(name)
    if (
        any(part.casefold() in FORBIDDEN_DIRECTORIES for part in path.parts)
        or path.name.casefold() in FORBIDDEN_FILES
        or path.suffix.casefold() in FORBIDDEN_SUFFIXES
        or any(part.casefold() == '.env' or part.casefold().startswith('.env.') for part in path.parts)
    ):
        raise ValueError(f'制品必须使用预构建部署目录，不能包含源码工程或缓存：{name}')


def _scan_directory(
    root: Path, limits: ArtifactLimits, *, skip_caches: bool = False
) -> tuple[dict[str, Path], set[str]]:
    """
    在不跟随链接的前提下枚举目录，并检查文件类型和资源上限。

    :param root: 待扫描的普通目录
    :param limits: 文件数量、大小及压缩容器的资源上限
    :param skip_caches: 是否在构建阶段跳过 Python 和测试缓存
    :return: 相对路径到文件路径的映射，以及扫描到的相对目录集合
    :raises ValueError: 目录、文件类型、路径或资源用量不符合制品约束
    """
    root_info = root.lstat()
    if is_link_or_reparse(root_info) or not stat.S_ISDIR(root_info.st_mode):
        raise ValueError('制品目录必须是普通目录，不能是链接或重解析点')
    files: dict[str, Path] = {}
    directories: set[str] = set()
    pending = [root]
    total_bytes = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if skip_caches and (
                    entry.name.casefold() in CACHE_DIRECTORIES or Path(entry.name).suffix.casefold() in {'.pyc', '.pyo'}
                ):
                    continue
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                safe_artifact_path(relative)
                # Windows DirEntry.stat 的 st_nlink 可为 0；lstat 才提供硬链接计数。
                info = path.lstat()
                if is_link_or_reparse(info):
                    raise ValueError(f'制品目录包含链接或重解析点：{relative}')
                if stat.S_ISDIR(info.st_mode):
                    directories.add(relative)
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    files[relative] = path
                    total_bytes += info.st_size
                    if info.st_size > limits.max_file_bytes:
                        raise ValueError('制品单文件大小超过限制')
                else:
                    raise ValueError(f'制品目录包含特殊文件或硬链接：{relative}')
                if len(files) > limits.max_files or total_bytes > limits.max_total_bytes:
                    raise ValueError('制品文件数量或总大小超过限制')
                if len(directories) > limits.max_files * 32:
                    raise ValueError('制品目录数量超过限制')
    validate_path_inventory(tuple(files))
    return files, directories


def _read_limited(stream: BinaryIO, maximum: int) -> bytes:
    """
    在指定字节上限内读取完整文档。

    :param stream: 当前位置开始读取的二进制输入流
    :param maximum: 允许读取的最大字节数
    :return: 已读取的文档字节
    :raises ValueError: 文档实际大小超过读取上限
    """
    data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('制品文档大小超过限制')
    return data


def _hash_stream(stream: BinaryIO, maximum: int, output: BinaryIO | None = None) -> tuple[int, str]:
    """
    分块读取内容并计算大小和 SHA256，可同时复制到输出流。

    :param stream: 当前位置开始读取的二进制输入流
    :param maximum: 允许读取的最大字节数
    :param output: 可选的二进制输出流，为 None 时只计算摘要
    :return: 实际读取的字节数与小写 SHA256 摘要
    :raises ValueError: 文件实际大小超过读取上限
    """
    hasher = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(CHUNK_BYTES), b''):
        size += len(chunk)
        if size > maximum:
            raise ValueError('制品文件实际大小超过限制')
        hasher.update(chunk)
        if output is not None:
            output.write(chunk)
    return size, hasher.hexdigest()


def _preflight_zip(path: Path, limits: ArtifactLimits) -> None:
    """
    在创建 ZipFile 对象前流式检查中央目录，限制一次性元数据分配。

    :param path: 待处理的文件路径
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: None
    :raises ValueError: ZIP 结束记录、中央目录或容器类型不受支持
    """
    with path.open('rb') as stream:
        size = stream.seek(0, os.SEEK_END)
        tail_size = min(size, ZIP_END.size + ZIP_MAX_COMMENT_BYTES)
        stream.seek(size - tail_size)
        tail = stream.read(tail_size)
        marker = tail.rfind(b'PK\x05\x06')
        if marker < 0 or len(tail) - marker < ZIP_END.size:
            raise ValueError('制品 ZIP 缺少有效结束记录')
        _, disk, central_disk, disk_count, count, central_size, offset, comment_size = ZIP_END.unpack_from(tail, marker)
        if marker + ZIP_END.size + comment_size != len(tail):
            raise ValueError('制品 ZIP 结束记录或注释长度无效')
        if disk or central_disk or disk_count != count:
            raise ValueError('制品 ZIP 不支持分卷容器')
        if count == ZIP64_COUNT_SENTINEL or ZIP64_SIZE_SENTINEL in {central_size, offset}:
            raise ValueError('制品 ZIP 不支持 ZIP64 容器')
        central_end = size - tail_size + marker
        if offset + central_size != central_end or central_size > limits.max_central_directory_bytes:
            raise ValueError('制品 ZIP 中央目录位置或大小无效')
        if count > limits.max_files:
            raise ValueError('制品 ZIP 文件数量超过限制')
        stream.seek(offset)
        _preflight_entries(stream, central_end, count, limits)


def _preflight_entries(stream: BinaryIO, central_end: int, count: int, limits: ArtifactLimits) -> None:
    """
    逐条检查 ZIP 中央目录记录，并核对实际数量与结束位置。

    :param stream: 当前位置开始读取的二进制输入流
    :param central_end: 中央目录结束位置的绝对字节偏移
    :param count: ZIP 结束记录声明的条目数量
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: None
    :raises ValueError: 中央目录记录不完整、越界或实际数量不匹配
    """
    actual_count = 0
    while stream.tell() < central_end:
        if central_end - stream.tell() < ZIP_CENTRAL.size:
            raise ValueError('制品 ZIP 中央目录记录不完整')
        header = ZIP_CENTRAL.unpack(stream.read(ZIP_CENTRAL.size))
        if header[0] != b'PK\x01\x02' or header[13]:
            raise ValueError('制品 ZIP 中央目录记录无效')
        if ZIP64_SIZE_SENTINEL in {header[8], header[9], header[16]}:
            raise ValueError('制品 ZIP 不支持 ZIP64 文件')
        actual_count += 1
        if actual_count > limits.max_files:
            raise ValueError('制品 ZIP 实际文件数量超过限制')
        next_position = stream.tell() + sum(header[10:13])
        if next_position > central_end:
            raise ValueError('制品 ZIP 中央目录字段越界')
        stream.seek(next_position)
    if actual_count != count:
        raise ValueError('制品 ZIP 中央目录文件数量不一致')


def _zip_inventory(archive: ZipFile, limits: ArtifactLimits) -> dict[str, ZipInfo]:
    """
    校验 ZIP 文件类型、路径和资源上限，并建立文件清单。

    :param archive: 已打开的 ZIP 压缩容器
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 安全相对文件路径与 ZIP 条目的映射
    :raises ValueError: ZIP 条目不安全、超过限制或缺少必要文档
    """
    entries = archive.infolist()
    if len(entries) > limits.max_files or sum(entry.file_size for entry in entries) > limits.max_total_bytes:
        raise ValueError('制品 ZIP 文件数量或展开大小超过限制')
    files: dict[str, ZipInfo] = {}
    directories: set[str] = set()
    names: set[str] = set()
    for entry in entries:
        if entry.orig_filename != entry.filename:
            raise ValueError('制品 ZIP 文件名包含截断字符')
        name = entry.filename[:-1] if entry.is_dir() else entry.filename
        safe_artifact_path(name)
        if name.casefold() in names:
            raise ValueError(f'制品 ZIP 包含重复或大小写冲突路径：{name}')
        names.add(name.casefold())
        mode = entry.external_attr >> 16
        kind = stat.S_IFMT(mode)
        if (
            kind not in {0, stat.S_IFREG, stat.S_IFDIR}
            or bool(entry.external_attr & 0x400)
            or (kind == stat.S_IFDIR and not entry.is_dir())
            or (kind == stat.S_IFREG and entry.is_dir())
        ):
            raise ValueError('制品 ZIP 不能包含链接、重解析点或特殊文件')
        if entry.flag_bits & 1 or entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            raise ValueError('制品 ZIP 不支持加密或该压缩算法')
        if (
            entry.file_size > limits.max_file_bytes
            or entry.file_size > max(1, entry.compress_size) * limits.max_compression_ratio
        ):
            raise ValueError('制品 ZIP 单文件大小或压缩比超过限制')
        if entry.is_dir():
            if entry.file_size:
                raise ValueError('制品 ZIP 目录不能携带数据')
            directories.add(name)
        else:
            files[name] = entry
    validate_path_inventory(tuple(files), directories)
    if not ROOT_DOCUMENTS.issubset(files):
        raise ValueError('制品缺少 artifacts.json 或 signature.json')
    return files


def _verify_documents(
    metadata_bytes: bytes, signature_bytes: bytes, trusted_keys: Mapping[str, PublicKeyInput], limits: ArtifactLimits
) -> tuple[ArtifactMetadata, ArtifactSignature, str]:
    """
    解析制品元数据和签名文档，并使用宿主可信公钥验签。

    :param metadata_bytes: artifacts.json 的原始内容
    :param signature_bytes: signature.json 的原始内容
    :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 制品元数据、签名信息和规范元数据摘要
    :raises ValueError: 元数据、签名、信任关系或资源声明校验失败
    """
    if len(metadata_bytes) > limits.max_metadata_bytes or len(signature_bytes) > limits.max_signature_bytes:
        raise ValueError('制品元数据或签名文档超过大小限制')
    metadata = ArtifactMetadata.model_validate(strict_json(metadata_bytes))
    signature = ArtifactSignature.model_validate(strict_json(signature_bytes))
    if len(metadata.files) > limits.max_files or sum(item.size for item in metadata.files) > limits.max_total_bytes:
        raise ValueError('制品清单文件数量或总大小超过限制')
    for item in metadata.files:
        _payload_path(item.path)
        if item.size > limits.max_file_bytes:
            raise ValueError('制品清单单文件大小超过限制')
    if signature.key_id not in trusted_keys:
        raise ValueError(f'未受信任或已撤销的制品签名密钥：{signature.key_id}')
    canonical = metadata.canonical_bytes()
    try:
        public_key(trusted_keys[signature.key_id]).verify(signature.signature_bytes(), canonical)
    except InvalidSignature as exc:
        raise ValueError('制品签名验证失败') from exc
    return metadata, signature, hashlib.sha256(canonical).hexdigest()


def _verify_manifest(data: bytes, metadata: ArtifactMetadata, limits: ArtifactLimits) -> PluginManifest:
    """
    静态解析插件清单，检查协议、身份、版本及前端交付类型。

    :param data: plugin.yaml 的原始 UTF-8 内容
    :param metadata: 签名覆盖的制品元数据
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 通过校验的插件清单对象
    :raises ValueError: 插件清单无效、身份不匹配或使用不支持的交付协议
    """
    if len(data) > limits.max_manifest_bytes:
        raise ValueError('plugin.yaml 大小超过限制')
    try:
        raw = yaml.safe_load(data.decode('utf-8'))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ValueError('制品 plugin.yaml 无效') from exc
    if not isinstance(raw, dict) or raw.get('manifestVersion') != EXPLICIT_MANIFEST_VERSION:
        raise ValueError('签名制品仅支持 manifestVersion 2')
    manifest = PluginManifestFactory.create(raw)
    if manifest.id != metadata.plugin_id or manifest.version != metadata.version:
        raise ValueError('制品身份或版本与 plugin.yaml 不一致')
    if manifest.frontend.delivery.type not in {'none', 'bundle'}:
        raise ValueError('签名制品仅支持 none/bundle，不能交付 source 前端')
    return manifest


def _verify_archive(
    archive: ZipFile, artifact_path: Path, trusted_keys: Mapping[str, PublicKeyInput], limits: ArtifactLimits
) -> VerifiedArtifact:
    """
    校验签名、完整文件清单及逐文件摘要，生成只读验证结果。

    :param archive: 已打开的 ZIP 压缩容器
    :param artifact_path: 当前受验证制品容器的绝对路径
    :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 完成全部静态校验的制品信息
    :raises ValueError: 文件清单、签名或实际文件内容不一致
    """
    files = _zip_inventory(archive, limits)
    with archive.open(files['artifacts.json']) as source:
        metadata_bytes = _read_limited(source, limits.max_metadata_bytes)
    with archive.open(files['signature.json']) as source:
        signature_bytes = _read_limited(source, limits.max_signature_bytes)
    metadata, signature, digest = _verify_documents(metadata_bytes, signature_bytes, trusted_keys, limits)
    if set(files) != ROOT_DOCUMENTS | {item.path for item in metadata.files}:
        raise ValueError('制品文件库存与签名清单不一致，存在额外或缺失文件')
    for item in metadata.files:
        if files[item.path].file_size != item.size:
            raise ValueError(f'制品文件大小不匹配：{item.path}')
        with archive.open(files[item.path]) as source:
            size, actual = _hash_stream(source, item.size)
        if size != item.size or actual != item.sha256:
            raise ValueError(f'制品文件 SHA256 或大小不匹配：{item.path}')
    with archive.open(files[f'payload/{metadata.plugin_id}/plugin.yaml']) as source:
        manifest = _verify_manifest(_read_limited(source, limits.max_manifest_bytes), metadata, limits)
    return VerifiedArtifact(
        metadata.plugin_id,
        metadata.version,
        digest,
        signature.key_id,
        metadata.files,
        metadata,
        signature,
        manifest,
        artifact_path,
    )


def verify_artifact(
    path: Path | str, trusted_keys: Mapping[str, PublicKeyInput], *, limits: ArtifactLimits = DEFAULT_LIMITS
) -> VerifiedArtifact:
    """
    只读校验制品签名、清单和全部文件摘要，不安装依赖或导入插件代码。

    :param path: 待处理的文件路径
    :param trusted_keys: 由宿主提供的签名密钥标识与可信公钥映射
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 完成全部静态校验的制品信息
    :raises ValueError: 制品容器、签名、清单或文件内容校验失败
    """
    path = Path(path).absolute()
    if _regular_file(path).st_size > limits.max_archive_bytes:
        raise ValueError('制品容器大小超过限制')
    try:
        _preflight_zip(path, limits)
        with ZipFile(path) as archive:
            return _verify_archive(archive, path, trusted_keys, limits)
    except (BadZipFile, struct.error) as exc:
        raise ValueError('制品 ZIP 无效或 CRC 校验失败') from exc


def build_artifact(
    source_plugin_dir: Path | str,
    output_file: Path | str,
    private_key: PrivateKeyInput,
    key_id: str,
    *,
    limits: ArtifactLimits = DEFAULT_LIMITS,
) -> VerifiedArtifact:
    """
    从预构建部署目录签名打包，不覆盖已有输出，仅忽略 Python 和测试缓存。

    :param source_plugin_dir: 目录名与插件ID一致的预构建部署目录
    :param output_file: 待创建的 rpk 文件路径，必须位于源目录之外
    :param private_key: 仅在当前构建进程内使用的 Ed25519 签名私钥
    :param key_id: 签名公钥在宿主信任配置中的标识
    :param limits: 文件数量、大小及压缩容器的资源上限
    :return: 构建完成并重新校验的制品信息
    :raises ValueError: 部署内容不合法、超过限制或在构建期间发生变化
    :raises FileExistsError: 输出路径已经存在，无法安全创建新制品
    """
    source = Path(source_plugin_dir).absolute()
    files, _ = _scan_directory(source, limits, skip_caches=True)
    if 'plugin.yaml' not in files:
        raise ValueError('预构建插件目录缺少 plugin.yaml')
    with files['plugin.yaml'].open('rb') as stream:
        raw_manifest = _read_limited(stream, limits.max_manifest_bytes)
    raw = yaml.safe_load(raw_manifest.decode('utf-8'))
    if not isinstance(raw, dict):
        raise ValueError('plugin.yaml 必须是对象')
    records = []
    for relative, path in sorted(files.items()):
        _payload_path(relative)
        with path.open('rb') as stream:
            size, digest = _hash_stream(stream, limits.max_file_bytes)
        records.append(ArtifactFile(path=f'payload/{source.name}/{relative}', size=size, sha256=digest))
    metadata = ArtifactMetadata(schemaVersion=1, pluginId=source.name, version=raw.get('version'), files=tuple(records))
    _verify_manifest(raw_manifest, metadata, limits)
    key = load_private_key(private_key)
    signature = ArtifactSignature(
        algorithm='Ed25519',
        keyId=key_id,
        signature=base64.b64encode(key.sign(metadata.canonical_bytes())).decode(),
    )
    output = Path(output_file).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('制品输出已经存在，拒绝覆盖')
    if output.is_relative_to(source):
        raise ValueError('制品输出不能位于源插件目录内')
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix='.rpk-build-', dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(temporary, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('artifacts.json', metadata.canonical_bytes())
            archive.writestr('signature.json', json.dumps(signature.model_dump(by_alias=True), separators=(',', ':')))
            for item in records:
                relative = item.path.removeprefix(f'payload/{source.name}/')
                path = files[relative]
                _regular_file(path)
                if path.resolve() != path or not path.resolve().is_relative_to(source.resolve()):
                    raise ValueError('构建期间插件资源路径发生变化')
                with path.open('rb') as stream, archive.open(item.path, 'w') as target:
                    size, digest = _hash_stream(stream, item.size, target)
                if (size, digest) != (item.size, item.sha256):
                    raise ValueError('构建期间插件资源内容发生变化')
        verify_artifact(temporary, {key_id: key.public_key()}, limits=limits)
        # 硬链接创建具备跨平台的 O_EXCL 语义，避免 POSIX rename 覆盖已有文件。
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return verify_artifact(output, {key_id: key.public_key()}, limits=limits)
