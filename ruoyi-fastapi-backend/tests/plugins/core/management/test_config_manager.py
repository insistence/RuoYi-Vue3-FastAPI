import pytest

from plugins.core.management.service.config import PluginConfigManager
from plugins.core.manifest.schema import PluginConfigItemManifest


def _build_item(**overrides: object) -> PluginConfigItemManifest:
    """构造指定类型和值的测试配置项。"""
    data: dict[str, object] = {'key': 'limit', 'type': 'number', 'default': 5}
    data.update(overrides)
    return PluginConfigItemManifest.model_validate(data)


def test_validate_update_value_rejects_bool_for_number_config() -> None:
    """校验数值配置拒绝布尔值。"""
    item = _build_item()

    with pytest.raises(ValueError, match='必须是数字'):
        PluginConfigManager.validate_update_value(item, True)

    with pytest.raises(ValueError, match='必须是数字'):
        PluginConfigManager.validate_update_value(item, False)


def test_validate_update_value_accepts_int_and_float_for_number_config() -> None:
    """校验数值配置接受整数和浮点数。"""
    item = _build_item()

    PluginConfigManager.validate_update_value(item, 10)
    PluginConfigManager.validate_update_value(item, 3.14)


def test_validate_update_value_accepts_bool_for_boolean_config() -> None:
    """校验布尔配置接受布尔值。"""
    item = _build_item(type='boolean', default=False)

    PluginConfigManager.validate_update_value(item, True)
    PluginConfigManager.validate_update_value(item, False)


def test_validate_update_value_rejects_int_for_boolean_config() -> None:
    """校验布尔配置拒绝整数值。"""
    item = _build_item(type='boolean', default=False)

    with pytest.raises(ValueError, match='必须是布尔值'):
        PluginConfigManager.validate_update_value(item, 1)
