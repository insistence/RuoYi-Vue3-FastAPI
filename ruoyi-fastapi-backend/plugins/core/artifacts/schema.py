import base64
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from plugins.core.manifest.schema import PluginManifest
from plugins.core.utils import validate_plugin_id_value

DIGEST_PATTERN = re.compile(r'^[a-f0-9]{64}$')
KEY_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
ED25519_KEY_BYTES = 32
ED25519_SIGNATURE_BYTES = 64
FIRST_PRINTABLE_CHARACTER = 32
DELETE_CHARACTER = 127
MAX_PATH_COMPONENTS = 32
MAX_PATH_LENGTH = 1024
MAX_COMPONENT_LENGTH = 255

PublicKeyInput = Ed25519PublicKey | bytes | str
PrivateKeyInput = Ed25519PrivateKey | bytes | str


@dataclass(frozen=True)
class ArtifactLimits:
    """
    制品压缩容器、元数据和实际展开内容的独立资源上限。
    """

    max_files: int = 10000
    max_file_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_archive_bytes: int = 600 * 1024 * 1024
    max_central_directory_bytes: int = 16 * 1024 * 1024
    max_metadata_bytes: int = 4 * 1024 * 1024
    max_signature_bytes: int = 16 * 1024
    max_manifest_bytes: int = 1024 * 1024
    max_compression_ratio: int = 200


DEFAULT_LIMITS = ArtifactLimits()


def safe_artifact_path(value: str) -> PurePosixPath:
    """
    校验跨平台相对路径，拒绝设备名、目录穿越和不可移植字符。

    :param value: 待校验的制品相对路径
    :return: 通过校验的 POSIX 相对路径
    :raises ValueError: 路径不符合跨平台安全约束
    """
    parts = value.split('/')
    if (
        not value
        or len(value) > MAX_PATH_LENGTH
        or len(parts) > MAX_PATH_COMPONENTS
        or unicodedata.normalize('NFC', value) != value
        or any(
            part in {'', '.', '..'}
            or len(part) > MAX_COMPONENT_LENGTH
            or part.endswith((' ', '.'))
            or PureWindowsPath(part).is_reserved()
            or any(
                char in '<>:"\\|?*' or ord(char) < FIRST_PRINTABLE_CHARACTER or ord(char) == DELETE_CHARACTER
                for char in part
            )
            for part in parts
        )
    ):
        raise ValueError(f'制品包含不安全路径：{value!r}')
    return PurePosixPath(value)


def validate_path_inventory(files: list[str] | tuple[str, ...], directories: set[str] | None = None) -> None:
    """
    按路径组件检查重复文件、大小写歧义及文件与目录冲突。

    :param files: 全部文件的相对路径列表
    :param directories: 压缩容器显式声明的目录集合，可不提供
    :return: None
    :raises ValueError: 文件或目录存在重复、大小写歧义或层级冲突
    """
    all_spellings: dict[str, str] = {}
    file_keys: set[str] = set()
    directory_keys: set[str] = set()
    for name in files:
        parts = safe_artifact_path(name).parts
        key = name.casefold()
        if key in file_keys:
            raise ValueError(f'制品包含重复文件或大小写冲突：{name}')
        file_keys.add(key)
        for index in range(1, len(parts) + 1):
            part_path = '/'.join(parts[:index])
            previous = all_spellings.setdefault(part_path.casefold(), part_path)
            if previous != part_path:
                raise ValueError(f'制品包含目录大小写冲突：{name}')
            if index < len(parts):
                directory_keys.add(part_path.casefold())
    if file_keys & directory_keys:
        raise ValueError('制品存在文件与父目录冲突')
    for directory in directories or set():
        safe_artifact_path(directory)
        if directory.casefold() not in directory_keys or all_spellings.get(directory.casefold()) != directory:
            raise ValueError(f'制品包含多余或冲突目录：{directory}')


def strict_json(data: bytes) -> dict[str, Any]:
    """
    解析 UTF-8 JSON 对象，在所有层级拒绝重复键和非有限数值。

    :param data: 待解析的原始字节内容
    :return: 通过严格解析的 JSON 对象
    :raises ValueError: 内容不是有效的 UTF-8 JSON 对象，或包含重复键及非法常量
    """

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        """
        将 JSON 键值对转换为字典，并拒绝重复字段。

        :param pairs: 按原始顺序提供的 JSON 对象键值对
        :return: 字段名唯一的字典
        :raises ValueError: 同一 JSON 对象中存在重复字段
        """
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'制品 JSON 包含重复键：{key}')
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        """
        拒绝 JSON 中不属于标准数值范围的常量。

        :param value: JSON 解析器识别到的非法常量文本
        :return: None
        :raises ValueError: 遇到 NaN、Infinity 等非标准 JSON 常量
        """
        raise ValueError(f'制品 JSON 包含非法常量：{value}')

    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=object_pairs, parse_constant=invalid_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('制品 JSON 不是有效的 UTF-8 对象') from exc
    if not isinstance(value, dict):
        raise ValueError('制品 JSON 必须为对象')
    return value


class ArtifactFile(BaseModel):
    """
    签名文件记录，路径相对于 rpk 根目录并位于自身 payload 目录中。
    """

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @field_validator('path')
    @classmethod
    def validate_path(cls, value: str) -> str:
        """
        校验签名文件记录中的相对路径。

        :param value: 待校验的制品相对路径
        :return: 通过校验的原始路径字符串
        :raises ValueError: 路径不符合跨平台安全约束
        """
        safe_artifact_path(value)
        return value


class ArtifactMetadata(BaseModel):
    """
    签名覆盖的制品元数据，字段及文件列表顺序共同确定签名内容。
    """

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    schema_version: Literal[1] = Field(alias='schemaVersion')
    plugin_id: str = Field(alias='pluginId')
    version: str = Field(min_length=1, max_length=32, pattern=r'^[0-9][a-z0-9._+\-]*$')
    files: tuple[ArtifactFile, ...]

    @field_validator('schema_version', mode='before')
    @classmethod
    def validate_schema_version(cls, value: Any) -> int:
        """
        要求协议版本为整数1，拒绝布尔值和数值类型转换。

        :param value: 模型收到的原始协议版本值
        :return: 已确认的协议版本1
        :raises ValueError: 协议版本不是整数1
        """
        if type(value) is not int or value != 1:
            raise ValueError('schemaVersion 必须为整数 1')
        return value

    @field_validator('plugin_id')
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        """
        校验制品所属插件的标识格式。

        :param value: 待校验的插件ID
        :return: 通过校验的插件ID
        """
        return validate_plugin_id_value(value)

    @field_validator('version')
    @classmethod
    def validate_version(cls, value: str) -> str:
        """
        校验制品版本能安全用作跨平台目录名。

        :param value: 待校验的插件版本
        :return: 通过校验的版本字符串
        """
        safe_artifact_path(value)
        return value

    @field_validator('files', mode='before')
    @classmethod
    def parse_files(cls, value: Any) -> Any:
        """
        将 JSON 文件列表转换为不可变元组供后续模型校验。

        :param value: 模型收到的原始文件列表字段
        :return: 列表转换后的元组，其他输入保持原值
        """
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode='after')
    def validate_files(self) -> 'ArtifactMetadata':
        """
        检查文件均属于当前插件，包含清单且不存在路径冲突。

        :return: 完成文件清单校验的当前元数据对象
        :raises ValueError: 文件归属、必要清单或路径清单不符合制品约束
        """
        paths = tuple(file.path for file in self.files)
        prefix = f'payload/{self.plugin_id}/'
        if not paths or any(not path.startswith(prefix) for path in paths):
            raise ValueError('制品文件必须全部位于自身 payload/<plugin_id>/ 目录')
        if f'{prefix}plugin.yaml' not in paths:
            raise ValueError('制品缺少 plugin.yaml')
        validate_path_inventory(paths)
        return self

    def canonical_bytes(self) -> bytes:
        """
        序列化规范 JSON，供签名验证和制品摘要计算共同使用。

        :return: 字段排序且不包含额外空白的 UTF-8 JSON 字节
        """
        return json.dumps(
            self.model_dump(mode='json', by_alias=True),
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
            allow_nan=False,
        ).encode('utf-8')


class ArtifactSignature(BaseModel):
    """
    Ed25519 签名记录，密钥标识仅用于查询宿主提供的信任配置。
    """

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    algorithm: Literal['Ed25519']
    key_id: str = Field(alias='keyId', pattern=KEY_ID_PATTERN.pattern)
    signature: str

    def signature_bytes(self) -> bytes:
        """
        严格解码标准 Base64 签名并检查 Ed25519 签名长度。

        :return: 64字节的 Ed25519 签名内容
        :raises ValueError: 签名编码或长度不合法
        """
        try:
            signature = base64.b64decode(self.signature, validate=True)
        except ValueError as exc:
            raise ValueError('制品签名必须为标准 Base64') from exc
        if len(signature) != ED25519_SIGNATURE_BYTES or base64.b64encode(signature).decode() != self.signature:
            raise ValueError('制品 Ed25519 签名长度或编码不合法')
        return signature


def public_key(value: PublicKeyInput) -> Ed25519PublicKey:
    """
    加载 Ed25519 公钥，支持密钥对象、原始字节、PEM 和 Base64。

    :param value: 公钥对象、32字节原始公钥、PEM 或原始公钥的 Base64 文本
    :return: 可用于验签的 Ed25519 公钥对象
    :raises ValueError: 公钥格式无法解析或不是 Ed25519 公钥
    """
    if isinstance(value, Ed25519PublicKey):
        return value
    data = _key_bytes(value)
    key = (
        Ed25519PublicKey.from_public_bytes(data)
        if len(data) == ED25519_KEY_BYTES
        else serialization.load_pem_public_key(data)
    )
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('制品可信公钥必须为 Ed25519')
    return key


def private_key(value: PrivateKeyInput) -> Ed25519PrivateKey:
    """
    在内存中加载 Ed25519 签名私钥，不写入制品或目标目录。

    :param value: 私钥对象、32字节原始私钥、未加密 PEM 或原始私钥的 Base64 文本
    :return: 可用于签名的 Ed25519 私钥对象
    :raises ValueError: 私钥格式无法解析或不是 Ed25519 私钥
    """
    if isinstance(value, Ed25519PrivateKey):
        return value
    data = _key_bytes(value)
    key = (
        Ed25519PrivateKey.from_private_bytes(data)
        if len(data) == ED25519_KEY_BYTES
        else serialization.load_pem_private_key(data, password=None)
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('制品签名私钥必须为 Ed25519')
    return key


def _key_bytes(value: bytes | str) -> bytes:
    """
    规范化密钥字节输入，解析 PEM 文本或严格 Base64 编码。

    :param value: 密钥原始字节、PEM 文本或 Base64 文本
    :return: 原始密钥字节或 PEM 文本对应的字节
    :raises ValueError: 密钥输入类型或 Base64 编码不合法
    """
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        raise ValueError('制品密钥类型无效')
    if value.startswith('-----BEGIN '):
        return value.encode('ascii')
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise ValueError('制品密钥必须为 PEM 或原始密钥的 Base64') from exc


@dataclass(frozen=True)
class VerifiedArtifact:
    """
    完成静态校验的容器信息，不替代文件变化后的重新验证。
    """

    plugin_id: str
    version: str
    digest: str
    key_id: str
    files: tuple[ArtifactFile, ...]
    metadata: ArtifactMetadata
    signature: ArtifactSignature
    manifest: PluginManifest
    artifact_path: Path


@dataclass(frozen=True)
class StoredArtifact:
    """
    完成验证的不可变存储信息，供平台预检与发布服务读取。
    """

    plugin_id: str
    version: str
    digest: str
    key_id: str
    files: tuple[ArtifactFile, ...]
    metadata: ArtifactMetadata
    signature: ArtifactSignature
    manifest: PluginManifest
    root_path: Path
    plugin_path: Path
