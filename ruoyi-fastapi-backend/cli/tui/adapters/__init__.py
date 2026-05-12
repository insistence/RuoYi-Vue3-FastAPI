from collections.abc import Callable
from dataclasses import dataclass

from cli.tui.adapters.app import APP_DETAIL_ADAPTER as _APP_DETAIL_ADAPTER
from cli.tui.adapters.cache import CACHE_BROWSER_ADAPTER as _CACHE_BROWSER_ADAPTER
from cli.tui.adapters.configs import CONFIGS_BROWSER_ADAPTER as _CONFIGS_BROWSER_ADAPTER
from cli.tui.adapters.crypto import CRYPTO_DETAIL_ADAPTER as _CRYPTO_DETAIL_ADAPTER
from cli.tui.adapters.database import DATABASE_DETAIL_ADAPTER as _DATABASE_DETAIL_ADAPTER
from cli.tui.adapters.gen import GEN_BROWSER_ADAPTER as _GEN_BROWSER_ADAPTER
from cli.tui.adapters.health import (
    DASHBOARD_ADAPTER as _DASHBOARD_ADAPTER,
)
from cli.tui.adapters.health import DashboardPanelSnapshot, DashboardSnapshot
from cli.tui.adapters.jobs import JOBS_BROWSER_ADAPTER as _JOBS_BROWSER_ADAPTER
from cli.tui.adapters.models import (
    BrowserPageSnapshot,
    BrowserRecordSnapshot,
    DetailPageSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.adapters.ops import OPS_DETAIL_ADAPTER as _OPS_DETAIL_ADAPTER

PageSnapshot = BrowserPageSnapshot | DashboardSnapshot | DetailPageSnapshot
SnapshotCollector = Callable[..., PageSnapshot]


@dataclass(frozen=True)
class TuiSnapshotCollectorRegistry:
    """
    TUI 页面快照采集注册表。

    该对象集中维护页面视图标识与其采集函数之间的映射，
    使应用层和测试层可以通过统一入口发现当前可用的采集器。

    :param collectors: 视图到采集函数的映射
    """

    collectors: dict[str, SnapshotCollector]

    @staticmethod
    def normalize_view_key(view_key: str) -> str:
        """
        规范化页面视图标识。

        :param view_key: 原始页面视图标识
        :return: 规范化后的视图标识
        """
        return str(view_key).strip().lower()

    def get_collector(self, view_key: str) -> SnapshotCollector | None:
        """
        读取指定视图的快照采集器。

        :param view_key: 页面视图标识
        :return: 采集函数
        """
        return self.collectors.get(self.normalize_view_key(view_key))

    def collect(self, view_key: str, *args, **kwargs) -> PageSnapshot:
        """
        调用指定视图的快照采集器。

        :param view_key: 页面视图标识
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 页面快照
        :raises KeyError: 当视图未注册时抛出
        """
        collector = self.get_collector(view_key)
        if collector is None:
            raise KeyError(self.normalize_view_key(view_key))
        return collector(*args, **kwargs)


TUI_SNAPSHOT_COLLECTOR_REGISTRY = TuiSnapshotCollectorRegistry(
    collectors={
        'dashboard': _DASHBOARD_ADAPTER.collect_snapshot,
        'app': _APP_DETAIL_ADAPTER.collect_snapshot,
        'ops': _OPS_DETAIL_ADAPTER.collect_snapshot,
        'database': _DATABASE_DETAIL_ADAPTER.collect_snapshot,
        'cache': _CACHE_BROWSER_ADAPTER.collect_snapshot,
        'jobs': _JOBS_BROWSER_ADAPTER.collect_snapshot,
        'gen': _GEN_BROWSER_ADAPTER.collect_snapshot,
        'configs': _CONFIGS_BROWSER_ADAPTER.collect_snapshot,
        'crypto': _CRYPTO_DETAIL_ADAPTER.collect_snapshot,
    }
)

__all__ = [
    'TUI_SNAPSHOT_COLLECTOR_REGISTRY',
    'BrowserPageSnapshot',
    'BrowserRecordSnapshot',
    'DashboardPanelSnapshot',
    'DashboardSnapshot',
    'DetailPageSnapshot',
    'DetailSectionSnapshot',
    'TuiSnapshotCollectorRegistry',
]
