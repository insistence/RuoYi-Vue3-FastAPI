from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypedDict, cast

from plugins.core.types import PluginConfigValue, SupportsModelDump


class PluginConfigStatePayloadDict(TypedDict, total=False):
    """
    插件配置读取/更新 payload。
    """

    ok: bool
    message: str
    pluginId: str
    configs: list[dict[str, object]]
    operation: str


class PluginConfigExportFailurePayloadDict(TypedDict, total=False):
    """
    插件配置导出失败 payload。
    """

    ok: object
    message: object
    pluginId: str
    revealSecret: bool
    values: dict[str, PluginConfigValue]
    metadata: list[dict[str, object]]


class PluginConfigExportPayloadDict(TypedDict):
    """
    插件配置导出 payload。
    """

    ok: bool
    message: str
    pluginId: str
    revealSecret: bool
    configs: list[dict[str, object]]
    values: dict[str, PluginConfigValue]
    metadata: list[dict[str, object]]


class PluginConfigDiagnosticSummaryPayloadDict(TypedDict):
    """
    插件配置诊断摘要 payload。
    """

    total: int
    secretCount: int
    requiredCount: int
    configuredCount: int
    missingRequiredCount: int
    missingRequiredKeys: list[str]
    masked: bool


class PluginConfigImportPayloadDict(TypedDict, total=False):
    """
    插件配置导入 payload。
    """

    ok: object
    message: object
    pluginId: object
    importedKeys: list[str]


class PluginConfigAuditChangePayload(TypedDict):
    """
    插件配置审计变更项 payload。
    """

    key: str
    label: PluginConfigValue
    secret: bool
    before: PluginConfigValue
    after: PluginConfigValue


class PluginConfigAuditSummaryPayload(TypedDict):
    """
    插件配置审计摘要 payload。
    """

    changedCount: int
    changedKeys: list[str]
    changes: list[PluginConfigAuditChangePayload]


class PluginConfigAuditPayloadDict(TypedDict):
    """
    插件配置审计 payload。
    """

    ok: bool
    operation: str
    pluginId: str
    message: str
    summary: PluginConfigAuditSummaryPayload


@dataclass(frozen=True)
class PluginConfigStatePayload:
    """
    插件配置状态结构化负载。
    """

    plugin_id: str
    message: str
    configs: list[SupportsModelDump]
    operation: str | None = None

    def to_payload(self) -> PluginConfigStatePayloadDict:
        """
        序列化为现有插件配置读取/更新 payload 契约。

        :return: 插件配置读取/更新 payload
        """
        payload: PluginConfigStatePayloadDict = {
            'ok': True,
            'message': self.message,
            'pluginId': self.plugin_id,
            'configs': [cast('dict[str, object]', config.model_dump(by_alias=True)) for config in self.configs],
        }
        if self.operation is not None:
            payload['operation'] = self.operation
        return payload


@dataclass(frozen=True)
class PluginConfigExportFailurePayload:
    """
    插件配置导出失败结构化负载。
    """

    plugin_id: str
    payload: Mapping[str, object]
    reveal_secret: bool

    def to_payload(self) -> PluginConfigExportFailurePayloadDict:
        """
        序列化为现有插件配置导出失败 payload 契约。

        :return: 插件配置导出失败 payload
        """
        return {
            **self.payload,
            'pluginId': self.plugin_id,
            'revealSecret': self.reveal_secret,
            'values': {},
            'metadata': [],
        }


@dataclass(frozen=True)
class PluginConfigExportPayload:
    """
    插件配置导出结构化负载。
    """

    plugin_id: str
    configs: list[object]
    reveal_secret: bool = False

    def to_payload(self) -> PluginConfigExportPayloadDict:
        """
        序列化为现有插件配置导出 payload 契约。

        :return: 插件配置导出 payload
        """
        config_items = [cast('dict[str, object]', config) for config in self.configs if isinstance(config, dict)]
        return {
            'ok': True,
            'message': '插件配置导出完成',
            'pluginId': self.plugin_id,
            'revealSecret': self.reveal_secret,
            'configs': config_items,
            'values': {
                config.get('key'): cast('PluginConfigValue', config.get('value'))
                for config in config_items
                if isinstance(config.get('key'), str)
            },
            'metadata': [self._build_metadata(config) for config in config_items],
        }

    @staticmethod
    def _build_metadata(config: Mapping[str, object]) -> dict[str, object]:
        """
        构建不包含配置值的导出元数据。

        :param config: 配置项
        :return: 配置导出元数据
        """
        return {
            key: config.get(key)
            for key in (
                'key',
                'label',
                'type',
                'default',
                'required',
                'secret',
                'group',
                'order',
                'placeholder',
                'min',
                'max',
                'pattern',
                'options',
                'description',
            )
        }


@dataclass(frozen=True)
class PluginConfigDiagnosticSummaryPayload:
    """
    插件配置诊断摘要结构化负载。
    """

    configs: object

    def to_payload(self) -> PluginConfigDiagnosticSummaryPayloadDict:
        """
        序列化为现有插件配置诊断摘要 payload 契约。

        :return: 插件配置诊断摘要 payload
        """
        config_items = (
            [config for config in self.configs if isinstance(config, dict)] if isinstance(self.configs, list) else []
        )
        secret_count = sum(1 for config in config_items if bool(config.get('secret')))
        required_count = sum(1 for config in config_items if bool(config.get('required')))
        missing_required_keys = [
            str(config.get('key', '-'))
            for config in config_items
            if bool(config.get('required')) and not config.get('value')
        ]
        configured_count = sum(
            1
            for config in config_items
            if config.get('value') not in (None, '') and str(config.get('value')) != '******'
        )

        return {
            'total': len(config_items),
            'secretCount': secret_count,
            'requiredCount': required_count,
            'configuredCount': configured_count,
            'missingRequiredCount': len(missing_required_keys),
            'missingRequiredKeys': missing_required_keys,
            'masked': secret_count > 0,
        }


@dataclass(frozen=True)
class PluginConfigImportPayload:
    """
    插件配置导入结构化负载。
    """

    plugin_id: str
    payload: Mapping[str, object]
    values: dict[str, PluginConfigValue]

    def to_payload(self) -> PluginConfigImportPayloadDict:
        """
        序列化为现有插件配置导入 payload 契约。

        :return: 插件配置导入 payload
        """
        if self.payload.get('ok', False):
            return {**self.payload, 'importedKeys': sorted(self.values)}

        return {
            **self.payload,
            'pluginId': self.payload.get('pluginId', self.plugin_id),
            'importedKeys': [],
        }


@dataclass(frozen=True)
class PluginConfigAuditPayload:
    """
    插件配置审计结构化负载。
    """

    plugin_id: str
    operation: str
    values: dict[str, PluginConfigValue]
    before_configs: list[SupportsModelDump]
    after_configs: list[SupportsModelDump]
    message: str

    def to_payload(self) -> PluginConfigAuditPayloadDict:
        """
        序列化为现有插件配置审计 payload 契约。

        :return: 插件配置审计 payload
        """
        before_map = self._build_audit_map(self.before_configs)
        after_map = self._build_audit_map(self.after_configs)
        changed_keys = sorted(str(key) for key in self.values)
        changed_items = [
            self._build_audit_item(key, before_map.get(key, {}), after_map.get(key, {})) for key in changed_keys
        ]

        return {
            'ok': True,
            'operation': self.operation,
            'pluginId': self.plugin_id,
            'message': self.message,
            'summary': {
                'changedCount': len(changed_items),
                'changedKeys': changed_keys,
                'changes': changed_items,
            },
        }

    @staticmethod
    def _build_audit_map(configs: list[SupportsModelDump]) -> dict[str, dict[str, PluginConfigValue]]:
        """
        构建按配置键索引的审计配置映射。

        :param configs: 插件配置模型列表
        :return: 按配置键索引的配置审计映射
        """
        config_map: dict[str, dict[str, PluginConfigValue]] = {}
        for config in configs:
            payload = config.model_dump(by_alias=True) if hasattr(config, 'model_dump') else {}
            if not isinstance(payload, dict) or not isinstance(payload.get('key'), str):
                continue
            config_map[payload['key']] = cast('dict[str, PluginConfigValue]', payload)

        return config_map

    @classmethod
    def _build_audit_item(
        cls,
        key: str,
        before_config: dict[str, PluginConfigValue],
        after_config: dict[str, PluginConfigValue],
    ) -> PluginConfigAuditChangePayload:
        """
        构建单个配置项的脱敏变更摘要。

        :param key: 配置键
        :param before_config: 变更前配置负载
        :param after_config: 变更后配置负载
        :return: 单个配置项脱敏变更摘要
        """
        secret = bool(before_config.get('secret') or after_config.get('secret'))

        return {
            'key': key,
            'label': after_config.get('label') or before_config.get('label'),
            'secret': secret,
            'before': cls._mask_audit_value(before_config.get('value'), secret),
            'after': cls._mask_audit_value(after_config.get('value'), secret),
        }

    @staticmethod
    def _mask_audit_value(value: PluginConfigValue, secret: bool) -> PluginConfigValue:
        """
        对配置审计值执行敏感信息脱敏。

        :param value: 配置值
        :param secret: 是否敏感配置
        :return: 脱敏后的配置值
        """
        return '******' if secret and value is not None else value


class PluginConfigPayloadBuilder:
    """
    插件配置负载构建器。

    使用 Builder 模式集中处理配置诊断摘要、配置导出和配置变更审计负载。
    """

    @staticmethod
    def build_read_payload(plugin_id: str, configs: list[SupportsModelDump]) -> PluginConfigStatePayloadDict:
        """
        构建插件配置读取负载。

        :param plugin_id: 插件ID
        :param configs: 插件配置模型列表
        :return: 插件配置读取负载
        """
        return PluginConfigStatePayload(
            plugin_id=plugin_id,
            message='插件配置读取完成',
            configs=configs,
        ).to_payload()

    @staticmethod
    def build_export_failure_payload(
        plugin_id: str,
        payload: Mapping[str, object],
        *,
        reveal_secret: bool,
    ) -> PluginConfigExportFailurePayloadDict:
        """
        构建插件配置导出失败负载。

        :param plugin_id: 插件ID
        :param payload: 配置读取失败负载
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出失败负载
        """
        return PluginConfigExportFailurePayload(
            plugin_id=plugin_id,
            payload=payload,
            reveal_secret=reveal_secret,
        ).to_payload()

    @staticmethod
    def build_diagnostic_summary(configs: object) -> PluginConfigDiagnosticSummaryPayloadDict:
        """
        构建插件配置诊断摘要。

        :param configs: 插件配置明细列表
        :return: 配置诊断摘要
        """
        return PluginConfigDiagnosticSummaryPayload(configs).to_payload()

    @staticmethod
    def build_export_payload(
        plugin_id: str,
        configs: list[object],
        *,
        reveal_secret: bool = False,
    ) -> PluginConfigExportPayloadDict:
        """
        构建插件配置导出负载。

        :param plugin_id: 插件ID
        :param configs: 插件配置列表
        :param reveal_secret: 是否导出敏感配置明文
        :return: 插件配置导出负载
        """
        return PluginConfigExportPayload(
            plugin_id=plugin_id,
            configs=configs,
            reveal_secret=reveal_secret,
        ).to_payload()

    @classmethod
    def build_update_payload(
        cls,
        plugin_id: str,
        *,
        operation: str,
        message: str,
        configs: list[SupportsModelDump],
    ) -> PluginConfigStatePayloadDict:
        """
        构建插件配置更新负载。

        :param plugin_id: 插件ID
        :param operation: 配置操作类型
        :param message: 成功提示
        :param configs: 更新后的配置模型列表
        :return: 插件配置更新负载
        """
        return PluginConfigStatePayload(
            plugin_id=plugin_id,
            message=message,
            configs=configs,
            operation=operation,
        ).to_payload()

    @staticmethod
    def build_import_payload(
        plugin_id: str,
        payload: Mapping[str, object],
        values: dict[str, PluginConfigValue],
    ) -> PluginConfigImportPayloadDict:
        """
        构建插件配置导入负载。

        :param plugin_id: 插件ID
        :param payload: 配置更新负载
        :param values: 待导入配置键值
        :return: 插件配置导入负载
        """
        return PluginConfigImportPayload(
            plugin_id=plugin_id,
            payload=payload,
            values=values,
        ).to_payload()

    @classmethod
    def build_audit_payload(
        cls,
        plugin_id: str,
        *,
        operation: str,
        values: dict[str, PluginConfigValue],
        before_configs: list[SupportsModelDump],
        after_configs: list[SupportsModelDump],
        message: str,
    ) -> PluginConfigAuditPayloadDict:
        """
        构建插件配置变更审计负载。

        :param plugin_id: 插件ID
        :param operation: 配置操作类型
        :param values: 本次请求更新的配置键值
        :param before_configs: 更新前配置列表
        :param after_configs: 更新后配置列表
        :param message: 审计备注信息
        :return: 插件配置变更审计负载
        """
        return PluginConfigAuditPayload(
            plugin_id=plugin_id,
            operation=operation,
            values=values,
            before_configs=before_configs,
            after_configs=after_configs,
            message=message,
        ).to_payload()
