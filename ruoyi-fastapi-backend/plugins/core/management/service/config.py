import json
import re
from typing import Any

from plugins.core.management.entity.vo.schemas import PluginConfigModel, PluginConfigValueModel
from plugins.core.manifest.schema import PluginConfigItemManifest


class PluginConfigManager:
    """
    插件配置管理器。

    使用 Manager 模式集中处理配置声明、配置值序列化、默认值安装和脱敏输出。
    """

    MASK_VALUE = '******'

    @classmethod
    def build_config_model(cls, plugin_id: str, item: PluginConfigItemManifest) -> PluginConfigModel:
        """
        根据 manifest 配置项构建数据库配置模型。

        :param plugin_id: 插件ID
        :param item: 插件配置项声明
        :return: 插件配置数据库模型
        """
        serialized_default = cls.serialize_value(item.default)

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
        value = cls.deserialize_value(raw_value, getattr(config, 'config_type', 'string'))
        if secret and not reveal_secret and value not in (None, ''):
            value = cls.MASK_VALUE
        config_key = config.config_key

        return PluginConfigValueModel(
            key=config_key,
            label=getattr(config, 'config_label', None) or getattr(manifest_item, 'label', None),
            type=getattr(config, 'config_type', None) or getattr(manifest_item, 'type', 'string'),
            value=value,
            default=cls.deserialize_value(
                getattr(config, 'default_value', None), getattr(config, 'config_type', 'string')
            ),
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
    def serialize_value(cls, value: Any) -> str | None:
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
    def deserialize_value(cls, value: str | None, config_type: str = 'string') -> Any:
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
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    @classmethod
    def deserialize_options(cls, value: str | None) -> list[dict[str, Any]]:
        """
        反序列化配置选项。

        :param value: 配置选项 JSON 字符串
        :return: 配置选项列表
        """
        if not value:
            return []
        try:
            options = json.loads(value)
        except json.JSONDecodeError:
            return []
        return options if isinstance(options, list) else []

    @classmethod
    def validate_update_value(cls, item: PluginConfigItemManifest, value: Any) -> None:
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
        if item.type == 'number' and not isinstance(value, int | float):
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
    def _validate_number_range(cls, item: PluginConfigItemManifest, value: Any) -> None:
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
