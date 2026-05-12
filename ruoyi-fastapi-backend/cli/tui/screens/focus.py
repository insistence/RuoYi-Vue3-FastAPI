from abc import ABC, abstractmethod
from typing import Any

from textual.containers import ScrollableContainer


class BaseScreenFocusService(ABC):
    """
    TUI 屏幕焦点服务基类。

    该基类统一处理焦点顺序中的左右移动和滚动目标回退逻辑，具体页面
    只需声明自身的焦点顺序和默认滚动容器。
    """

    @abstractmethod
    def get_focus_order(self, screen: Any) -> list[Any]:
        """
        返回当前页面的焦点顺序。

        :param screen: 当前屏幕对象
        :return: 焦点组件列表
        """

    @abstractmethod
    def get_default_scroll_target(self, screen: Any) -> ScrollableContainer:
        """
        返回当前页面的默认滚动容器。

        :param screen: 当前屏幕对象
        :return: 默认滚动容器
        """

    def move_focus(self, screen: Any, step: int) -> None:
        """
        按给定方向移动当前焦点。

        :param screen: 当前屏幕对象
        :param step: 焦点移动步长
        :return: None
        """
        order = self.get_focus_order(screen)
        focused = screen.app.focused
        if focused not in order:
            order[0].focus()
            return
        target_index = max(0, min(order.index(focused) + step, len(order) - 1))
        order[target_index].focus()

    def get_scroll_target(self, screen: Any) -> Any:
        """
        获取当前应响应滚动动作的焦点区域。

        :param screen: 当前屏幕对象
        :return: 当前焦点组件或默认滚动容器
        """
        focused = screen.app.focused
        order = self.get_focus_order(screen)
        if focused in order:
            return focused
        return self.get_default_scroll_target(screen)


class ScreenFocusActionsMixin:
    """
    TUI 屏幕焦点动作混入。

    该混入负责将焦点服务暴露为屏幕上的左右移动与滚动 action，避免
    各个 Screen 类重复编写同形转发方法。
    """

    focus_service: BaseScreenFocusService

    def _move_focus(self, step: int) -> None:
        """
        按给定方向移动当前焦点。

        :param step: 焦点移动步长
        :return: None
        """
        self.focus_service.move_focus(self, step)

    def _get_scroll_target(self) -> Any:
        """
        获取当前应响应滚动动作的焦点区域。

        :return: 当前焦点组件或主工作区
        """
        return self.focus_service.get_scroll_target(self)

    def action_scroll_focus_down(self) -> None:
        """
        向下滚动当前焦点区域。

        :return: None
        """
        self._get_scroll_target().scroll_down(animate=False)

    def action_scroll_focus_up(self) -> None:
        """
        向上滚动当前焦点区域。

        :return: None
        """
        self._get_scroll_target().scroll_up(animate=False)

    def action_scroll_focus_page_down(self) -> None:
        """
        向下翻动当前焦点区域。

        :return: None
        """
        self._get_scroll_target().scroll_page_down(animate=False)

    def action_scroll_focus_page_up(self) -> None:
        """
        向上翻动当前焦点区域。

        :return: None
        """
        self._get_scroll_target().scroll_page_up(animate=False)

    def action_scroll_focus_home(self) -> None:
        """
        将当前焦点区域滚动到起始位置。

        :return: None
        """
        self._get_scroll_target().scroll_home(animate=False)

    def action_scroll_focus_end(self) -> None:
        """
        将当前焦点区域滚动到末尾位置。

        :return: None
        """
        self._get_scroll_target().scroll_end(animate=False)

    def action_focus_left(self) -> None:
        """
        将焦点向左移动一列。

        :return: None
        """
        self._move_focus(-1)

    def action_focus_right(self) -> None:
        """
        将焦点向右移动一列。

        :return: None
        """
        self._move_focus(1)
