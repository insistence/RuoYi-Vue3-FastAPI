import re

PLUGIN_ID_PATTERN_TEXT = r'[a-z][a-z0-9_]{1,63}'
PLUGIN_ID_PATTERN = re.compile(rf'^{PLUGIN_ID_PATTERN_TEXT}$')


def validate_plugin_id_value(plugin_id: str, *, field_name: str = '插件ID') -> str:
    """
    校验插件 ID。

    :param plugin_id: 插件 ID
    :param field_name: 错误提示中的字段名称
    :return: 校验后的插件 ID
    """
    if not PLUGIN_ID_PATTERN.match(plugin_id):
        raise ValueError(f'{field_name}必须以小写字母开头，且只能包含小写字母、数字和下划线，长度为2-64')
    return plugin_id


def escape_sql_like(value: str) -> str:
    """
    转义 SQL LIKE 模式中的通配符。

    :param value: 原始字面量
    :return: 可安全拼接到 LIKE 模式中的字面量
    """
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
