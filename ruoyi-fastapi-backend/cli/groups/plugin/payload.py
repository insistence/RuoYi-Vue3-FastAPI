from copy import deepcopy
from typing import Any


class PluginCommandPayloadAdapter:
    """
    插件 CLI 输出负载适配器。

    核心运行时 payload 同时服务管理接口和 CLI。CLI 在输出前通过本适配器消除
    `enabled` 的多重语义，不改变管理接口既有契约。
    """

    _LIFECYCLE_OPERATIONS = {'enable', 'disable', 'uninstall'}

    @classmethod
    def adapt(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """
        生成语义明确的 CLI 输出负载。

        :param payload: 核心运行时负载
        :return: CLI 输出负载
        """
        adapted_payload = deepcopy(payload)
        cls._adapt_node(adapted_payload)
        return adapted_payload

    @classmethod
    def _adapt_node(cls, node: object, *, parent_key: str | None = None) -> None:
        """
        递归适配负载节点。

        :param node: 当前负载节点
        :param parent_key: 当前节点在父对象中的字段名
        :return: None
        """
        if isinstance(node, list):
            for item in node:
                cls._adapt_node(item, parent_key=parent_key)
            return
        if not isinstance(node, dict):
            return

        cls._adapt_database_state(node, parent_key)
        cls._adapt_lifecycle_target(node)
        cls._adapt_action_state(node, parent_key)
        cls._adapt_plan_plugin_state(node, parent_key)
        cls._adapt_plugin_runtime_state(node)
        cls._adapt_manifest_job_state(node, parent_key)
        for key, value in list(node.items()):
            cls._adapt_node(value, parent_key=key)

    @staticmethod
    def _adapt_database_state(node: dict[str, Any], parent_key: str | None) -> None:
        """
        将数据库启停枚举转换为语义明确的布尔字段。

        :param node: 当前负载节点
        :param parent_key: 当前节点在父对象中的字段名
        :return: None
        """
        if parent_key != 'database' or 'enabled' not in node:
            return
        database_enabled = node.pop('enabled')
        node['configuredEnabled'] = PluginCommandPayloadAdapter._normalize_enabled_value(database_enabled)

    @classmethod
    def _adapt_lifecycle_target(cls, node: dict[str, Any]) -> None:
        """
        将生命周期结果中的目标启停值改为 targetEnabled。

        :param node: 当前负载节点
        :return: None
        """
        if node.get('operation') == 'purge' and 'enabled' in node:
            node.pop('enabled')
            return
        if (
            node.get('operation') in cls._LIFECYCLE_OPERATIONS
            and 'pluginId' in node
            and 'dryRun' in node
            and 'enabled' in node
        ):
            node['targetEnabled'] = node.pop('enabled')

    @staticmethod
    def _adapt_action_state(node: dict[str, Any], parent_key: str | None) -> None:
        """
        将动作和清理计划项中的 enabled 改为 willRun。

        :param node: 当前负载节点
        :param parent_key: 当前节点在父对象中的字段名
        :return: None
        """
        is_action = parent_key == 'actions' and 'name' in node
        is_purge_plan_item = parent_key == 'items' and 'destructive' in node and 'label' in node
        if (is_action or is_purge_plan_item) and isinstance(node.get('enabled'), bool):
            node['willRun'] = node.pop('enabled')

    @staticmethod
    def _adapt_plan_plugin_state(node: dict[str, Any], parent_key: str | None) -> None:
        """
        将批量计划项中的数据库启停枚举改为 configuredEnabled。

        :param node: 当前负载节点
        :param parent_key: 当前节点在父对象中的字段名
        :return: None
        """
        if parent_key != 'items' or 'pluginId' not in node or 'ready' not in node or 'enabled' not in node:
            return
        configured_enabled = node.pop('enabled')
        node['configuredEnabled'] = PluginCommandPayloadAdapter._normalize_enabled_value(configured_enabled)

    @staticmethod
    def _adapt_plugin_runtime_state(node: dict[str, Any]) -> None:
        """
        将插件有效启用态改为 runtimeEnabled。

        :param node: 当前负载节点
        :return: None
        """
        if 'pluginId' not in node or 'status' not in node or 'enabled' not in node or 'dryRun' in node:
            return
        enabled = node.pop('enabled')
        if isinstance(enabled, bool):
            node['runtimeEnabled'] = enabled
            return
        node['configuredEnabled'] = PluginCommandPayloadAdapter._normalize_enabled_value(enabled)

    @staticmethod
    def _adapt_manifest_job_state(node: dict[str, Any], parent_key: str | None) -> None:
        """
        将 manifest 任务默认启用配置改为 defaultEnabled。

        :param node: 当前负载节点
        :param parent_key: 当前节点在父对象中的字段名
        :return: None
        """
        if parent_key == 'jobs' and 'id' in node and isinstance(node.get('enabled'), bool):
            node['defaultEnabled'] = node.pop('enabled')

    @staticmethod
    def _normalize_enabled_value(value: object) -> object:
        """
        将数据库 0/1 枚举转换为布尔值，其余值原样保留。

        :param value: 原始启停值
        :return: 规范化启停值
        """
        if isinstance(value, str) and value in {'0', '1'}:
            return value == '0'
        return value


__all__ = ['PluginCommandPayloadAdapter']
