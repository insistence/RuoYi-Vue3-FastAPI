from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli.tui.actions.builders import TuiActionSpecFactory, TuiActionTemplate
    from cli.tui.actions.models import ActionSlot, TuiActionSpec
    from cli.tui.adapters.models import BrowserRecordSnapshot


@dataclass(frozen=True)
class TuiActionRegistry:
    """
    TUI 动作注册表。

    该注册表负责集中维护浏览页和详情页的动作解析器，从而将
    原本散落的条件分发收敛为可声明的映射关系。

    :param browser_resolvers: 浏览页动作槽位解析器映射
    :param detail_resolvers: 详情页动作槽位解析器映射
    """

    browser_resolvers: dict[str, TuiActionSlotResolver]
    detail_resolvers: dict[str, TuiActionSlotResolver]

    def resolve_browser_action(
        self,
        *,
        view_key: str,
        slot: ActionSlot,
        record: BrowserRecordSnapshot | None,
        env: str,
    ) -> TuiActionSpec | None:
        """
        解析浏览页动作。

        :param view_key: 当前页面视图标识
        :param slot: 动作槽位
        :param record: 当前选中记录
        :param env: 当前运行环境
        :return: 动作定义
        """
        resolver = self.browser_resolvers.get(view_key)
        if resolver is None:
            return None
        return resolver.resolve(slot=slot, record=record, env=env)

    def resolve_detail_action(
        self,
        *,
        view_key: str,
        slot: ActionSlot,
        env: str,
    ) -> TuiActionSpec | None:
        """
        解析详情页动作。

        :param view_key: 当前页面视图标识
        :param slot: 动作槽位
        :param env: 当前运行环境
        :return: 动作定义
        """
        resolver = self.detail_resolvers.get(view_key)
        if resolver is None:
            return None
        return resolver.resolve(slot=slot, record=None, env=env)


@dataclass(frozen=True)
class TuiActionSlotResolver:
    """
    TUI 动作槽位解析器。

    该对象将一个页面支持的槽位动作集中定义为映射关系，避免继续在
    `resolve_*_action` 中堆叠条件分支。

    :param slot_templates: 槽位到动作模板的映射
    :param spec_factory: 动作规格构建器
    """

    slot_templates: dict[ActionSlot, TuiActionTemplate]
    spec_factory: TuiActionSpecFactory

    def resolve(
        self,
        *,
        slot: ActionSlot,
        record: BrowserRecordSnapshot | None,
        env: str,
    ) -> TuiActionSpec | None:
        """
        解析指定槽位的动作定义。

        :param slot: 动作槽位
        :param record: 当前选中记录
        :param env: 当前运行环境
        :return: 动作定义
        """
        template = self.slot_templates.get(slot)
        if template is None:
            return None
        return template.build(record=record, env=env, spec_factory=self.spec_factory)
