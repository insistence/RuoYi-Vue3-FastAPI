import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.env import PluginArtifactConfig

MAX_TRUST_FILE_BYTES = 1024 * 1024


class TrustedPublisher(BaseModel):
    """
    将公钥与可发布插件ID显式绑定的发布者配置。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True, strict=True)
    key_id: str = Field(alias='keyId', pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
    public_key: str = Field(alias='publicKey', min_length=1, max_length=8192)
    plugin_ids: list[str] = Field(alias='pluginIds', min_length=1, max_length=256)
    enabled: bool = True

    @field_validator('plugin_ids')
    @classmethod
    def validate_plugin_ids(cls, values: list[str]) -> list[str]:
        """
        校验发布者授权范围，通配授权必须明确使用星号。

        :param values: 发布者允许发布的插件ID或显式通配符列表
        :return: 无重复且格式正确的插件ID授权列表
        :raises ValueError: 授权范围存在重复或非法插件ID
        """
        import re  # noqa: PLC0415

        if len(set(values)) != len(values):
            raise ValueError('发布者插件授权不能重复')
        if any(value != '*' and not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', value) for value in values):
            raise ValueError('发布者插件授权包含非法插件 ID')
        return values


class PluginTrustDocument(BaseModel):
    """
    由宿主管理的发布者公钥及授权范围配置文档。
    """

    model_config = ConfigDict(extra='forbid', populate_by_name=True, strict=True)
    schema_version: int = Field(alias='schemaVersion', ge=1, le=1)
    keys: list[TrustedPublisher] = Field(max_length=256)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """
    构造信任配置对象，拒绝同一对象中的重复字段。

    :param pairs: 按原始顺序提供的 JSON 对象键值对
    :return: 字段名唯一的配置字典
    :raises ValueError: 公钥配置对象包含重复字段
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'公钥配置存在重复字段：{key}')
        result[key] = value
    return result


@dataclass(frozen=True)
class PluginDeploymentConfig:
    """
    制品发布配置快照，支持为测试和维护实例注入独立目录。
    """

    backend_root: Path
    store_root: Path
    trust_file: Path
    enabled: bool = True
    heartbeat_seconds: int = 15
    worker_ttl_seconds: int = 60

    @classmethod
    def from_settings(cls, backend_root: Path | str) -> 'PluginDeploymentConfig':
        """
        读取宿主制品配置，并将相对存储路径转换为绝对路径。

        :param backend_root: 宿主后端项目根目录
        :return: 制品发布配置快照
        """
        root = Path(backend_root).resolve()
        settings = PluginArtifactConfig
        store = Path(settings.plugin_artifact_store)
        trust = Path(settings.plugin_artifact_trust_file)
        return cls(
            backend_root=root,
            store_root=(store if store.is_absolute() else root / store).resolve(),
            trust_file=(trust if trust.is_absolute() else root / trust).resolve(),
            enabled=settings.plugin_artifact_enabled,
            heartbeat_seconds=settings.plugin_artifact_heartbeat_seconds,
            worker_ttl_seconds=settings.plugin_artifact_worker_ttl_seconds,
        )

    def require_enabled(self) -> None:
        """
        检查发布功能已启用且制品存储与源码目录相互隔离。

        :return: None
        :raises ValueError: 功能未启用或制品存储与宿主源码路径重叠
        """
        if not self.enabled:
            raise ValueError('签名插件制品未启用，请配置 PLUGIN_ARTIFACT_ENABLED 和外部信任公钥文件')
        if self.store_root == self.backend_root or self.store_root in self.backend_root.parents:
            raise ValueError('插件制品目录不能是宿主目录或其上级目录')
        plugins_root = (self.backend_root / 'plugins').resolve()
        if self.store_root == plugins_root or self.store_root.is_relative_to(plugins_root):
            raise ValueError('不可变插件制品必须保存在源码 plugins 目录之外')

    def read_publishers(self) -> dict[str, TrustedPublisher]:
        """
        读取并校验宿主管理的发布者公钥配置。

        :return: 签名密钥标识到发布者配置的映射
        :raises ValueError: 公钥配置缺失、超过大小限制或内容不合法
        """
        self.require_enabled()
        if not self.trust_file.is_file() or self.trust_file.stat().st_size > MAX_TRUST_FILE_BYTES:
            raise ValueError('宿主插件信任公钥文件不存在或过大')
        data = json.loads(self.trust_file.read_text(encoding='utf-8'), object_pairs_hook=_unique_json_object)
        document = PluginTrustDocument.model_validate(data)
        result: dict[str, TrustedPublisher] = {}
        for publisher in document.keys:
            if publisher.key_id in result:
                raise ValueError(f'重复的发布者 keyId：{publisher.key_id}')
            result[publisher.key_id] = publisher
        return result

    def trusted_keys(self) -> dict[str, str]:
        """
        从当前发布者配置中提取启用的可信公钥。

        :return: 启用的签名密钥标识与公钥文本映射
        """
        return {key: item.public_key for key, item in self.read_publishers().items() if item.enabled}

    def authorize_publisher(self, key_id: str, plugin_id: str) -> None:
        """
        检查发布者是否启用并获准发布指定插件。

        :param key_id: 签名公钥在宿主信任配置中的标识
        :param plugin_id: 插件ID
        :return: None
        :raises ValueError: 发布者不受信任、已停用或未获准发布指定插件
        """
        publisher = self.read_publishers().get(key_id)
        if publisher is None or not publisher.enabled:
            raise ValueError('插件发布者不在当前信任列表中')
        if '*' not in publisher.plugin_ids and plugin_id not in publisher.plugin_ids:
            raise ValueError(f'发布者 {key_id} 未获准发布插件 {plugin_id}')
