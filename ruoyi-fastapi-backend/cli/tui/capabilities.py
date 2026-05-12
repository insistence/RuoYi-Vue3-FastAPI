from dataclasses import dataclass
from typing import Literal

from cli.tui.copy import TUI_COPY

CapabilityKind = Literal['read_only', 'preview', 'low_risk_action', 'wizard_entry', 'command_hint']
CapabilityScope = Literal['browser', 'detail']


@dataclass(frozen=True)
class TuiCapability:
    """
    TUI 页面能力定义。

    :param kind: 能力类型
    :param slot: 绑定的动作槽位
    :param key: 绑定的快捷键
    :param label: 展示标签
    :param hint_label: 用于顶部提示的简洁标签
    :param scope: 能力所在页面范围
    """

    kind: CapabilityKind
    slot: str
    key: str
    label: str
    hint_label: str
    scope: CapabilityScope


@dataclass(frozen=True)
class TuiCapabilitySpec:
    """
    TUI 页面能力规格定义。

    :param capability_key: 能力标识
    :param kind: 能力类型
    :param slot: 绑定动作槽位
    :param key: 绑定快捷键
    """

    capability_key: str
    kind: CapabilityKind
    slot: str
    key: str


_BROWSER_CAPABILITY_SPECS: dict[str, tuple[TuiCapabilitySpec, ...]] = {
    'jobs': (
        TuiCapabilitySpec('job_run_once', 'low_risk_action', 'primary', 'X'),
        TuiCapabilitySpec('job_toggle', 'low_risk_action', 'secondary', 'Z'),
        TuiCapabilitySpec('job_sync', 'preview', 'global', 'Y'),
    ),
    'configs': (TuiCapabilitySpec('config_sync', 'low_risk_action', 'global', 'Y'),),
    'cache': (
        TuiCapabilitySpec('cache_clear_wizard', 'wizard_entry', 'global', 'Y'),
        TuiCapabilitySpec('cache_warmup', 'low_risk_action', 'utility', 'W'),
    ),
    'gen': (
        TuiCapabilitySpec('gen_export_wizard', 'wizard_entry', 'primary', 'X'),
        TuiCapabilitySpec('gen_import_wizard', 'wizard_entry', 'secondary', 'Z'),
        TuiCapabilitySpec('gen_export_dry_run', 'preview', 'global', 'Y'),
        TuiCapabilitySpec('gen_sync_db', 'low_risk_action', 'utility', 'W'),
    ),
}

_DETAIL_CAPABILITY_SPECS: dict[str, tuple[TuiCapabilitySpec, ...]] = {
    'app': (
        TuiCapabilitySpec('app_run', 'wizard_entry', 'primary', 'X'),
        TuiCapabilitySpec('app_run_wizard', 'wizard_entry', 'global', 'Y'),
        TuiCapabilitySpec('completion_install', 'command_hint', 'utility', 'W'),
    ),
    'database': (
        TuiCapabilitySpec('db_upgrade_wizard', 'wizard_entry', 'global', 'Y'),
        TuiCapabilitySpec('db_init_dry_run', 'preview', 'utility', 'W'),
    ),
    'ops': (
        TuiCapabilitySpec('ops_ping_db', 'low_risk_action', 'primary', 'X'),
        TuiCapabilitySpec('ops_ping_redis', 'low_risk_action', 'secondary', 'Z'),
        TuiCapabilitySpec('prod_check_wizard', 'wizard_entry', 'global', 'Y'),
    ),
    'crypto': (
        TuiCapabilitySpec('crypto_keygen', 'wizard_entry', 'primary', 'X'),
        TuiCapabilitySpec('crypto_rotate_dry_run', 'preview', 'global', 'Y'),
    ),
}


@dataclass(frozen=True)
class TuiCapabilityRegistry:
    """
    TUI 页面能力注册表。

    该对象集中维护浏览页与详情页的能力描述，避免模块级散落
    的字典常量在后续扩展时继续增长。

    :param browser_capabilities: 浏览页能力映射
    :param detail_capabilities: 详情页能力映射
    """

    browser_capabilities: dict[str, tuple[TuiCapability, ...]]
    detail_capabilities: dict[str, tuple[TuiCapability, ...]]

    @staticmethod
    def normalize_view_key(view_key: str) -> str:
        """
        规范化页面标识。

        :param view_key: 原始页面标识
        :return: 规范化后的页面标识
        """
        return str(view_key).strip().lower()

    def get_browser_capabilities(self, view_key: str) -> tuple[TuiCapability, ...]:
        """
        获取浏览页支持的能力列表。

        :param view_key: 页面视图标识
        :return: 能力列表
        """
        return self.browser_capabilities.get(self.normalize_view_key(view_key), ())

    def get_detail_capabilities(self, view_key: str) -> tuple[TuiCapability, ...]:
        """
        获取详情页支持的能力列表。

        :param view_key: 页面视图标识
        :return: 能力列表
        """
        return self.detail_capabilities.get(self.normalize_view_key(view_key), ())


@dataclass(frozen=True)
class TuiCapabilityRegistryBuilder:
    """
    TUI 页面能力注册表构建器。

    该对象负责通过统一文案服务构建页面能力定义，避免模块内继续
    直接堆叠硬编码的标题和提示标签。
    """

    def build_capability(
        self,
        *,
        capability_key: str,
        kind: CapabilityKind,
        slot: str,
        key: str,
        scope: CapabilityScope,
    ) -> TuiCapability:
        """
        构建单条能力定义。

        :param capability_key: 能力标识
        :param kind: 能力类型
        :param slot: 绑定动作槽位
        :param key: 绑定快捷键
        :param scope: 页面范围
        :return: 能力定义
        """
        return TuiCapability(
            kind=kind,
            slot=slot,
            key=key,
            label=TUI_COPY.build_capability_label(capability_key),
            hint_label=TUI_COPY.build_capability_hint_label(capability_key),
            scope=scope,
        )

    def build_scope_capabilities(
        self,
        specs_by_view: dict[str, tuple[TuiCapabilitySpec, ...]],
        *,
        scope: CapabilityScope,
    ) -> dict[str, tuple[TuiCapability, ...]]:
        """
        根据规格映射构建指定页面范围的能力注册表。

        :param specs_by_view: 页面能力规格映射
        :param scope: 页面范围
        :return: 构建后的能力映射
        """
        return {
            view_key: tuple(
                self.build_capability(
                    capability_key=spec.capability_key,
                    kind=spec.kind,
                    slot=spec.slot,
                    key=spec.key,
                    scope=scope,
                )
                for spec in specs
            )
            for view_key, specs in specs_by_view.items()
        }

    def build(self) -> TuiCapabilityRegistry:
        """
        构建页面能力注册表。

        :return: 能力注册表
        """
        return TuiCapabilityRegistry(
            browser_capabilities=self.build_scope_capabilities(_BROWSER_CAPABILITY_SPECS, scope='browser'),
            detail_capabilities=self.build_scope_capabilities(_DETAIL_CAPABILITY_SPECS, scope='detail'),
        )


TUI_CAPABILITY_REGISTRY = TuiCapabilityRegistryBuilder().build()
