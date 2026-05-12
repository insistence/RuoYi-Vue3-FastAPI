from cli.tui.copy.fragments import (
    APP_BINDING_LABELS,
    GENERAL_COPY,
    INTERNAL_BINDING_LABELS,
    NAVIGATION_DESCRIPTIONS,
    STATUS_LABELS,
    VIEW_LABELS,
)


class TuiNavigationCopyMixin:
    """
    TUI 导航与基础标签文案混入。
    """

    @staticmethod
    def render_view_label(view_key: str) -> str:
        """
        将内部视图标识转换为中文显示名称。

        :param view_key: 视图标识
        :return: 中文视图名称
        """
        normalized_view = str(view_key).strip().lower()
        return VIEW_LABELS.get(normalized_view, view_key)

    @staticmethod
    def render_status_label(status: str, fallback: str = '信息') -> str:
        """
        将状态值转换为中文显示文本。

        :param status: 原始状态值
        :param fallback: 缺失时兜底文本
        :return: 中文状态文本
        """
        normalized_status = str(status).strip().lower()
        if not normalized_status:
            return fallback
        return STATUS_LABELS.get(normalized_status, str(status).strip().upper())

    @staticmethod
    def render_status_code(status: str) -> str:
        """
        将状态值转换为控制台风格状态码。

        :param status: 原始状态值
        :return: 状态码文本
        """
        normalized_status = str(status).strip().lower()
        status_code_mapping = {
            'ok': 'SYS.OK',
            'success': 'SYS.OK',
            'healthy': 'SYS.OK',
            'fail': 'SYS.FAIL',
            'error': 'SYS.FAIL',
            'down': 'SYS.FAIL',
            'warn': 'SYS.WARN',
            'warning': 'SYS.WARN',
            'degraded': 'SYS.WARN',
            'info': 'SYS.INFO',
        }
        return status_code_mapping.get(normalized_status, f'SYS.{normalized_status.upper() or "INFO"}')

    @staticmethod
    def render_navigation_description(view_key: str) -> str:
        """
        获取指定视图的导航说明。

        :param view_key: 视图标识
        :return: 导航说明
        """
        normalized_view = str(view_key).strip().lower()
        return NAVIGATION_DESCRIPTIONS.get(normalized_view, '')

    @staticmethod
    def build_tui_command_help() -> str:
        """
        构建 `ruoyi tui` 命令帮助文案。

        :return: 命令帮助文案
        """
        return GENERAL_COPY['tui_command_help']

    @staticmethod
    def build_missing_dependency_message() -> str:
        """
        构建 TUI 可选依赖缺失时的提示消息。

        :return: 缺依赖提示消息
        """
        return GENERAL_COPY['tui_missing_dependency_message']

    @staticmethod
    def build_missing_dependency_hint() -> str:
        """
        构建 TUI 可选依赖缺失时的恢复建议。

        :return: 恢复建议文案
        """
        return GENERAL_COPY['tui_missing_dependency_hint']

    @staticmethod
    def build_app_binding_label(binding_key: str) -> str:
        """
        根据绑定标识构建应用级快捷键标签文案。

        :param binding_key: 绑定标识
        :return: 快捷键标签文案
        """
        normalized_key = str(binding_key).strip().lower()
        return APP_BINDING_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_confirm_binding_label(binding_key: str) -> str:
        """
        根据确认弹窗绑定标识构建快捷键标签文案。

        :param binding_key: 绑定标识
        :return: 快捷键标签文案
        """
        normalized_key = str(binding_key).strip().lower()
        return INTERNAL_BINDING_LABELS.get(f'confirm_{normalized_key}', normalized_key)

    @staticmethod
    def build_internal_binding_label(binding_key: str) -> str:
        """
        根据内部交互绑定标识构建快捷键标签文案。

        :param binding_key: 绑定标识
        :return: 快捷键标签文案
        """
        normalized_key = str(binding_key).strip().lower()
        return INTERNAL_BINDING_LABELS.get(normalized_key, normalized_key)
