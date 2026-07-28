from dataclasses import dataclass
from typing import Literal

from plugins.core.validation.versioning import PluginVersionComparator

PluginStatus = Literal['discovered', 'installed', 'pending_upgrade', 'error']
PluginStateOperation = Literal[
    'discover',
    'install',
    'disable',
    'enable',
    'upgrade_available',
    'upgrade',
    'mark_error',
]


@dataclass(frozen=True)
class PluginStateTransition:
    """
    插件状态流转规则。

    :param source: 来源状态，None 表示数据库中尚无插件状态
    :param operation: 状态流转操作
    :param target: 目标状态
    :param description: 流转说明
    """

    source: PluginStatus | None
    operation: PluginStateOperation
    target: PluginStatus
    description: str


@dataclass(frozen=True)
class PluginStateSnapshot:
    """
    插件状态输入快照。

    :param source_version: 当前源码版本
    :param installed_version: 已安装版本
    :param enabled: 是否启用
    :param current_status: 当前持久化状态
    """

    source_version: str | None
    installed_version: str | None
    enabled: bool
    current_status: str | None = None


class PluginStateResolver:
    """
    插件状态解析器。

    使用 State Resolver 模式集中维护插件管理和运行时注册表共享的状态流转规则。
    """

    @classmethod
    def resolve(cls, snapshot: PluginStateSnapshot) -> PluginStatus:
        """
        根据源码版本、安装版本、启停状态和当前状态解析插件状态。

        :param snapshot: 插件状态输入快照
        :return: 插件状态
        """
        if snapshot.current_status == 'error':
            return 'error'
        if not snapshot.installed_version and snapshot.current_status in {None, 'discovered'}:
            return 'discovered'
        if cls._needs_upgrade(snapshot.installed_version, snapshot.source_version):
            return 'pending_upgrade'
        return 'installed' if snapshot.installed_version else 'discovered'

    @staticmethod
    def is_enabled(database_plugin: object | None) -> bool:
        """
        解析插件启用状态。

        :param database_plugin: 数据库插件状态对象
        :return: 是否启用
        """
        if not database_plugin:
            return False
        if getattr(database_plugin, 'status', None) == 'error':
            return False
        if not getattr(database_plugin, 'installed_version', None):
            return False
        database_enabled = getattr(database_plugin, 'enabled', None) if database_plugin else None
        if database_enabled is not None:
            return database_enabled == '0'
        return False

    @staticmethod
    def enabled_to_db_value(enabled: bool) -> str:
        """
        将布尔启停状态转换为数据库枚举值。

        :param enabled: 是否启用
        :return: 数据库启停枚举值，`0` 表示启用，`1` 表示停用
        """
        return '0' if enabled else '1'

    @staticmethod
    def db_value_to_enabled(enabled: str | None, fallback: bool) -> bool:
        """
        将数据库启停枚举值转换为布尔值。

        :param enabled: 数据库启停枚举值
        :param fallback: 数据库值为空时使用的默认值
        :return: 是否启用
        """
        if enabled is None:
            return fallback
        return enabled == '0'

    @classmethod
    def is_database_plugin_enabled(cls, database_plugin: object | None, fallback: bool = False) -> bool:
        """
        判断数据库插件状态是否表示可用启用态。

        :param database_plugin: 数据库插件状态对象
        :param fallback: 数据库对象或启停值为空时使用的默认值
        :return: 是否为可用启用态
        """
        if not database_plugin:
            return fallback
        if getattr(database_plugin, 'status', None) == 'error':
            return False
        return cls.db_value_to_enabled(getattr(database_plugin, 'enabled', None), fallback=fallback)

    @staticmethod
    def _needs_upgrade(installed_version: str | None, source_version: str | None) -> bool:
        """
        判断源码版本是否高于已安装版本。

        :param installed_version: 已安装版本
        :param source_version: 当前源码版本
        :return: 是否需要升级
        """
        return bool(
            installed_version
            and source_version
            and PluginVersionComparator.is_upgrade_available(installed_version, source_version)
        )


class PluginStateTransitionTable:
    """
    插件状态流转表。

    使用 Table Driven 模式集中维护可观察的插件状态流转，供文档、测试和后续预检复用。
    """

    _TRANSITIONS = (
        PluginStateTransition(None, 'discover', 'discovered', '首次扫描到本地插件'),
        PluginStateTransition('discovered', 'install', 'installed', '插件安装完成'),
        PluginStateTransition('discovered', 'disable', 'discovered', '未安装插件被显式停用'),
        PluginStateTransition('discovered', 'mark_error', 'error', '插件安装或启动失败'),
        PluginStateTransition('installed', 'disable', 'installed', '插件被停用'),
        PluginStateTransition('installed', 'enable', 'installed', '插件被启用'),
        PluginStateTransition('installed', 'upgrade_available', 'pending_upgrade', '发现源码版本高于已安装版本'),
        PluginStateTransition('installed', 'mark_error', 'error', '插件运行或操作失败'),
        PluginStateTransition('pending_upgrade', 'upgrade', 'installed', '插件升级完成'),
        PluginStateTransition('pending_upgrade', 'disable', 'pending_upgrade', '待升级插件被停用'),
        PluginStateTransition('pending_upgrade', 'enable', 'pending_upgrade', '待升级插件被启用'),
        PluginStateTransition('pending_upgrade', 'mark_error', 'error', '插件升级或运行失败'),
        PluginStateTransition('error', 'disable', 'error', '异常插件被显式停用'),
        PluginStateTransition('error', 'install', 'installed', '异常插件重新安装成功'),
        PluginStateTransition('error', 'upgrade', 'installed', '异常插件升级修复完成'),
        PluginStateTransition('error', 'mark_error', 'error', '异常插件再次记录失败信息'),
    )

    @classmethod
    def list_transitions(cls) -> list[PluginStateTransition]:
        """
        获取全部插件状态流转规则。

        :return: 插件状态流转规则列表
        """
        return list(cls._TRANSITIONS)

    @classmethod
    def can_transition(cls, source: PluginStatus | None, operation: PluginStateOperation) -> bool:
        """
        判断状态操作是否允许执行。

        :param source: 来源状态，None 表示数据库中尚无插件状态
        :param operation: 状态流转操作
        :return: 是否允许流转
        """
        return cls.resolve_target(source, operation) is not None

    @classmethod
    def resolve_target(
        cls,
        source: PluginStatus | None,
        operation: PluginStateOperation,
    ) -> PluginStatus | None:
        """
        解析状态操作的目标状态。

        :param source: 来源状态，None 表示数据库中尚无插件状态
        :param operation: 状态流转操作
        :return: 目标状态，不允许流转时返回 None
        """
        for transition in cls._TRANSITIONS:
            if transition.source == source and transition.operation == operation:
                return transition.target

        return None
