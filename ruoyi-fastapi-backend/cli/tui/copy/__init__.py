from cli.tui.copy.actions import TuiActionCopyMixin
from cli.tui.copy.navigation import TuiNavigationCopyMixin
from cli.tui.copy.workspace import TuiWorkspaceCopyMixin


class TuiCopyService(TuiNavigationCopyMixin, TuiActionCopyMixin, TuiWorkspaceCopyMixin):
    """
    TUI 文案构造服务。

    该服务通过组合导航、动作和工作区文案混入对象，统一对外提供
    TUI 所需的文案构造能力，避免入口模块继续堆积实现细节。
    """


TUI_COPY = TuiCopyService()

__all__ = [
    'TUI_COPY',
    'TuiActionCopyMixin',
    'TuiCopyService',
    'TuiNavigationCopyMixin',
    'TuiWorkspaceCopyMixin',
]
