import json
import re
from typing import cast

from plugins.core.management.entity.vo.schemas import PluginConfigModel, PluginConfigValueModel
from plugins.core.manifest.schema import PluginConfigItemManifest
from plugins.core.types import PluginConfigValue
from utils.crypto_util import CryptoUtil
from utils.log_util import logger


class PluginConfigManager:
    """
    插件配置管理器。

    使用 Manager 模式集中处理配置声明、配置值序列化、默认值安装和脱敏输出。
    """

    MASK_VALUE = '******'
    ENCRYPTED_PREFIX = 'enc:v1:'

    @classmethod
    def build_config_model(cls, plugin_id: str, item: PluginConfigItemManifest) -> PluginConfigModel:
        """
        根据 manifest 配置项构建数据库配置模型。

        :param plugin_id: 插件ID
        :param item: 插件配置项声明
        :return: 插件配置数据库模型
        """
        serialized_default = cls.serialize_config_value(item.default, secret=item.secret)

        return PluginConfigModel(
            pluginId=plugin_id,
            configKey=item.key,
            configLabel=item.label,
            configType=item.type,
            configValue=serialized_default,
            defaultValue=serialized_default,
            required='0' if item.required else '1',
            secret='0' if item.secret else '1',
            options=cls.serialize_value([option.model_dump() for option in item.options]),
            description=item.description,
        )

    @classmethod
    def build_config_value(
        cls,
        config: object,
        manifest_item: PluginConfigItemManifest | None = None,
        *,
        reveal_secret: bool = False,
    ) -> PluginConfigValueModel:
        """
        构建面向插件管理接口和运行时负载的插件配置值。

        :param config: 数据库配置对象
        :param manifest_item: manifest 配置项声明
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置值模型
        """
        secret = getattr(config, 'secret', '1') == '0'
        raw_value = getattr(config, 'config_value', None)
        config_type = getattr(config, 'config_type', 'string')
        value = cls.deserialize_config_value(raw_value, config_type, secret=secret)
        if secret and not reveal_secret and value not in (None, ''):
            value = cls.MASK_VALUE
        default = cls.deserialize_config_value(getattr(config, 'default_value', None), config_type, secret=secret)
        if secret and not reveal_secret and default not in (None, ''):
            default = cls.MASK_VALUE
        config_key = config.config_key

        return PluginConfigValueModel(
            key=config_key,
            label=getattr(config, 'config_label', None) or getattr(manifest_item, 'label', None),
            type=getattr(config, 'config_type', None) or getattr(manifest_item, 'type', 'string'),
            value=value,
            default=default,
            required=getattr(config, 'required', '1') == '0',
            secret=secret,
            group=getattr(manifest_item, 'group', 'default'),
            order=getattr(manifest_item, 'order', 0),
            placeholder=getattr(manifest_item, 'placeholder', ''),
            min=getattr(manifest_item, 'min_value', None),
            max=getattr(manifest_item, 'max_value', None),
            pattern=getattr(manifest_item, 'pattern', None),
            options=cls.deserialize_options(getattr(config, 'options', None)),
            description=getattr(config, 'description', None) or getattr(manifest_item, 'description', None),
        )

    @classmethod
    def migrate_config_secret_storage(
        cls,
        config: object,
        item: PluginConfigItemManifest,
    ) -> str | None:
        """
        在 manifest 修改 secret 属性时迁移已有配置值的存储格式。

        :param config: 已有数据库配置对象
        :param item: 当前 manifest 配置声明
        :return: 使用新 secret 策略序列化后的配置值
        """
        old_secret = getattr(config, 'secret', '1') == '0'
        if old_secret == item.secret:
            return getattr(config, 'config_value', None)

        current_value = cls.deserialize_config_value(
            getattr(config, 'config_value', None),
            getattr(config, 'config_type', 'string'),
            secret=old_secret,
        )
        return cls.serialize_config_value(current_value, secret=item.secret)

    @classmethod
    def serialize_value(cls, value: PluginConfigValue) -> str | None:
        """
        序列化插件配置值。

        :param value: 原始配置值
        :return: 字符串配置值
        """
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @classmethod
    def serialize_config_value(cls, value: PluginConfigValue, *, secret: bool = False) -> str | None:
        """
        序列化插件配置值，敏感值加密落库。

        :param value: 原始配置值
        :param secret: 是否敏感配置
        :return: 可落库字符串
        """
        serialized_value = cls.serialize_value(value)
        if not secret or serialized_value in (None, ''):
            return serialized_value

        return f'{cls.ENCRYPTED_PREFIX}{CryptoUtil.encrypt(serialized_value)}'

    @classmethod
    def deserialize_value(cls, value: str | None, config_type: str = 'string') -> PluginConfigValue:
        """
        反序列化插件配置值。

        :param value: 字符串配置值
        :param config_type: 配置值类型
        :return: 反序列化后的配置值
        """
        if value is None:
            return None
        if config_type == 'boolean':
            return str(value).lower() in {'1', 'true', 'yes', 'on'}
        if config_type == 'number':
            try:
                return int(value) if float(value).is_integer() else float(value)
            except ValueError:
                return value
        if config_type == 'json':
            try:
                return cast('PluginConfigValue', json.loads(value))
            except json.JSONDecodeError:
                return value
        return value

    @classmethod
    def deserialize_config_value(
        cls,
        value: str | None,
        config_type: str = 'string',
        *,
        secret: bool = False,
    ) -> PluginConfigValue:
        """
        反序列化插件配置值，敏感配置必须是平台加密格式。

        :param value: 数据库存储值
        :param config_type: 配置类型
        :param secret: 是否敏感配置
        :return: 反序列化后的配置值
        """
        raw_value = value
        if secret and raw_value not in (None, ''):
            if not isinstance(raw_value, str) or not raw_value.startswith(cls.ENCRYPTED_PREFIX):
                raise ValueError('敏感插件配置不是加密存储格式')
            raw_value = CryptoUtil.decrypt(raw_value.removeprefix(cls.ENCRYPTED_PREFIX))

        return cls.deserialize_value(raw_value, config_type)

    @classmethod
    def deserialize_options(cls, value: str | None) -> list[dict[str, PluginConfigValue]]:
        """
        反序列化配置选项。

        :param value: 配置选项 JSON 字符串
        :return: 配置选项列表
        """
        if not value:
            return []
        try:
            options = json.loads(value)
        except json.JSONDecodeError as exc:
            logger.warning(f'⚠️ 插件配置选项 JSON 解析失败：{exc}')
            return [{'parseError': '配置选项 JSON 解析失败'}]
        if not isinstance(options, list):
            logger.warning('⚠️ 插件配置选项 JSON 内容不是数组')
            return [{'parseError': '配置选项 JSON 内容不是数组'}]
        return cast('list[dict[str, PluginConfigValue]]', options)

    @classmethod
    def validate_update_value(cls, item: PluginConfigItemManifest, value: PluginConfigValue) -> None:
        """
        校验配置更新值。

        :param item: 插件配置项声明
        :param value: 待更新配置值
        :return: None
        """
        if item.required and value in (None, ''):
            raise ValueError(f'配置 {item.key} 不能为空')
        if item.type == 'boolean' and not isinstance(value, bool):
            raise ValueError(f'配置 {item.key} 必须是布尔值')
        if item.type == 'number' and (not isinstance(value, int | float) or isinstance(value, bool)):
            raise ValueError(f'配置 {item.key} 必须是数字')
        if item.type == 'select' and item.options:
            allowed_values = [option.value for option in item.options]
            if value not in allowed_values:
                raise ValueError(f'配置 {item.key} 不在允许的选项范围内')
        if item.type == 'number':
            cls._validate_number_range(item, value)
        if (
            item.pattern
            and item.type in {'string', 'textarea', 'password'}
            and value not in (None, '')
            and not re.fullmatch(item.pattern, str(value))
        ):
            raise ValueError(f'配置 {item.key} 不匹配正则约束')

    @classmethod
    def _validate_number_range(cls, item: PluginConfigItemManifest, value: int | float) -> None:
        """
        校验数字配置值范围。

        :param item: 插件配置项声明
        :param value: 待更新配置值
        :return: None
        """
        if item.min_value is not None and value < item.min_value:
            raise ValueError(f'配置 {item.key} 不能小于 {item.min_value}')
        if item.max_value is not None and value > item.max_value:
            raise ValueError(f'配置 {item.key} 不能大于 {item.max_value}')
