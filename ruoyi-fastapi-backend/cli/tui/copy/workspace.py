from cli.tui.copy.fragments import (
    ACTION_HINT_COPY,
    BROWSER_ACTION_PANEL_COPY,
    BROWSER_EMPTY_RECORD_COPY,
    BROWSER_LOADING_COPY,
    DASHBOARD_HERO_COPY,
    DETAIL_EMPTY_SECTION_COPY,
    GENERAL_COPY,
    METRIC_COPY,
    SIGNAL_RAIL_COPY,
    STATE_SECTION_TITLES,
    STATE_SUGGESTIONS,
    STATUS_PANEL_COPY,
    WORKSPACE_EMPTY_TEXTS,
    WORKSPACE_LABELS,
    WORKSPACE_TITLES,
)


class TuiWorkspaceCopyMixin:
    """
    TUI 工作区与状态文案混入。
    """

    @staticmethod
    def build_workspace_label(label_key: str) -> str:
        """
        根据工作台标签标识构建文案。

        :param label_key: 标签标识
        :return: 标签文案
        """
        normalized_key = str(label_key).strip().lower()
        return WORKSPACE_LABELS.get(normalized_key, normalized_key)

    @staticmethod
    def build_workspace_title(title_key: str) -> str:
        """
        根据工作台标题标识构建文案。

        :param title_key: 标题标识
        :return: 标题文案
        """
        normalized_key = str(title_key).strip().lower()
        return WORKSPACE_TITLES.get(normalized_key, normalized_key)

    @staticmethod
    def build_workspace_empty_text(text_key: str) -> str:
        """
        根据工作台空态标识构建文案。

        :param text_key: 空态标识
        :return: 空态文案
        """
        normalized_key = str(text_key).strip().lower()
        return WORKSPACE_EMPTY_TEXTS.get(normalized_key, normalized_key)

    @staticmethod
    def build_status_panel_empty_text() -> str:
        """
        构建状态面板空态提示文案。

        :return: 空态提示文案
        """
        return STATUS_PANEL_COPY['empty']

    @staticmethod
    def build_signal_rail_empty_text() -> str:
        """
        构建信号带空态提示文案。

        :return: 空态提示文案
        """
        return SIGNAL_RAIL_COPY['empty']

    @staticmethod
    def build_more_detail_hint() -> str:
        """
        构建查看更多提示文案。

        :return: 提示文案
        """
        return GENERAL_COPY['more_detail_hint']

    @staticmethod
    def build_empty_state_suggestion() -> str:
        """
        构建通用空态建议文案。

        :return: 建议文案
        """
        return STATE_SUGGESTIONS['empty']

    @staticmethod
    def build_loading_state_suggestion() -> str:
        """
        构建通用加载态建议文案。

        :return: 建议文案
        """
        return STATE_SUGGESTIONS['loading']

    @staticmethod
    def build_failure_state_suggestion() -> str:
        """
        构建通用失败态建议文案。

        :return: 建议文案
        """
        return STATE_SUGGESTIONS['failure']

    @staticmethod
    def build_dashboard_failure_suggestion() -> str:
        """
        构建首页失败态建议文案。

        :return: 建议文案
        """
        return STATE_SUGGESTIONS['dashboard_failure']

    @staticmethod
    def build_dashboard_empty_suggestion() -> str:
        """
        构建首页空态建议文案。

        :return: 建议文案
        """
        return STATE_SUGGESTIONS['dashboard_empty']

    @staticmethod
    def build_state_section_title(title_key: str) -> str:
        """
        根据状态区块标识构建标题文案。

        :param title_key: 区块标识
        :return: 标题文案
        """
        normalized_key = str(title_key).strip().lower()
        return STATE_SECTION_TITLES.get(normalized_key, normalized_key)

    @staticmethod
    def build_dashboard_hero_title() -> str:
        """
        构建首页 Hero 标题文案。

        :return: 标题文案
        """
        return DASHBOARD_HERO_COPY['title']

    @staticmethod
    def build_dashboard_hero_subtitle() -> str:
        """
        构建首页 Hero 副标题文案。

        :return: 副标题文案
        """
        return DASHBOARD_HERO_COPY['subtitle']

    @staticmethod
    def build_browser_empty_record_copy(field_key: str) -> str:
        """
        根据字段标识构建浏览页空记录文案。

        :param field_key: 字段标识
        :return: 文案
        """
        normalized_key = str(field_key).strip().lower()
        return BROWSER_EMPTY_RECORD_COPY.get(normalized_key, normalized_key)

    @staticmethod
    def build_browser_loading_copy(field_key: str) -> str:
        """
        根据字段标识构建浏览页加载占位文案。

        :param field_key: 字段标识
        :return: 文案
        """
        normalized_key = str(field_key).strip().lower()
        return BROWSER_LOADING_COPY.get(normalized_key, normalized_key)

    @staticmethod
    def build_detail_empty_section_copy(field_key: str) -> str:
        """
        根据字段标识构建详情页空态文案。

        :param field_key: 字段标识
        :return: 文案
        """
        normalized_key = str(field_key).strip().lower()
        return DETAIL_EMPTY_SECTION_COPY.get(normalized_key, normalized_key)

    @staticmethod
    def build_refresh_page_suggestion(page_name: str, detail: str) -> str:
        """
        构建详情页场景下的统一建议操作文案。

        :param page_name: 页面名称
        :param detail: 后续动作描述
        :return: 建议文案
        """
        return f'可按 [R] 刷新，或进入{page_name}页面{detail}'

    @staticmethod
    def build_dashboard_page_suggestion(page_name: str, detail: str) -> str:
        """
        构建首页总览面板场景下的统一建议操作文案。

        :param page_name: 页面名称
        :param detail: 后续动作描述
        :return: 建议文案
        """
        return f'按 [R] 刷新，或进入{page_name}页面{detail}'

    @staticmethod
    def build_unavailable_record_title(resource_name: str) -> str:
        """
        构建浏览页失败兜底记录标题。

        :param resource_name: 资源名称
        :return: 标题文本
        """
        return f'{resource_name}数据暂不可用'

    @staticmethod
    def build_load_failure_section_title(resource_name: str) -> str:
        """
        构建浏览页失败兜底分区标题。

        :param resource_name: 资源名称
        :return: 分区标题
        """
        return f'{resource_name}加载失败'

    @staticmethod
    def build_empty_record_title(resource_name: str) -> str:
        """
        构建浏览页空记录标题。

        :param resource_name: 资源名称
        :return: 标题文本
        """
        return f'暂无{resource_name}'

    @staticmethod
    def build_unavailable_subtitle(resource_name: str, message: str) -> str:
        """
        构建浏览页数据不可用副标题。

        :param resource_name: 资源名称
        :param message: 错误摘要
        :return: 副标题文本
        """
        return f'{resource_name}数据不可用：{message}'

    @staticmethod
    def build_empty_record_summary(detail: str) -> str:
        """
        构建浏览页空记录摘要。

        :param detail: 摘要说明
        :return: 摘要文本
        """
        return detail

    @staticmethod
    def build_loaded_collection_subtitle(count: int, unit: str, detail: str) -> str:
        """
        构建浏览页“已加载”副标题。

        :param count: 数量
        :param unit: 单位
        :param detail: 补充说明
        :return: 副标题文本
        """
        return f'已加载 {count} {unit}，{detail}'

    @staticmethod
    def build_summary_with_message(summary: str, message: str) -> str:
        """
        构建带结果摘要补充的副标题。

        :param summary: 主摘要
        :param message: 结果消息
        :return: 副标题文本
        """
        return f'{summary} | {message}'

    @staticmethod
    def build_count_detail_subtitle(prefix: str, count: int, unit: str, suffix: str) -> str:
        """
        构建带数量的详情页副标题。

        :param prefix: 前缀文本
        :param count: 数量
        :param unit: 数量单位
        :param suffix: 后缀文本
        :return: 副标题文本
        """
        return f'{prefix} {count} {unit}{suffix}'

    @staticmethod
    def build_value_detail_subtitle(prefix: str, value: str, suffix: str) -> str:
        """
        构建带单值信息的详情页副标题。

        :param prefix: 前缀文本
        :param value: 值文本
        :param suffix: 后缀文本
        :return: 副标题文本
        """
        return f'{prefix} {value}{suffix}'

    @staticmethod
    def build_workspace_hero_lines(
        *,
        view_label: str,
        title: str,
        subtitle: str,
        env: str,
        summary: str,
        refreshed_at: str,
        shortcut_hint: str,
    ) -> list[str]:
        """
        构建工作区顶部摘要文本行。

        :param view_label: 当前页面显示名称
        :param title: 页面标题
        :param subtitle: 页面副标题
        :param env: 当前环境
        :param summary: 页面摘要
        :param refreshed_at: 刷新时间
        :param shortcut_hint: 快捷键提示
        :return: 文本行列表
        """
        return [
            f'[{view_label} 控制台]',
            title,
            subtitle,
            '',
            f'运行环境 · {env}',
            f'当前页面 · {view_label}',
            f'运行摘要 · {summary}',
            f'操作提示 · {shortcut_hint}',
            f'最近刷新 · {refreshed_at}',
        ]

    @staticmethod
    def build_navigation_item_lines(index: int, label: str, shortcut: str, description: str) -> list[str]:
        """
        构建左侧导航项文案。

        :param index: 导航索引
        :param label: 导航标题
        :param shortcut: 快捷键
        :param description: 导航说明
        :return: 文本行列表
        """
        return [
            f'▌ {WORKSPACE_LABELS["menu"]} {index + 1:02d} · {label}',
            f'│ {WORKSPACE_LABELS["shortcut"]} [{shortcut.upper()}] · {description}',
        ]

    @staticmethod
    def build_section_item_lines(index: int, title: str, status_badge: str, preview: str) -> list[str]:
        """
        构建详情页分区导航项文案。

        :param index: 分区索引
        :param title: 分区标题
        :param status_badge: 状态徽标
        :param preview: 预览文本
        :return: 文本行列表
        """
        return [
            f'▌ {WORKSPACE_LABELS["section"]} {index + 1:02d} · {title}',
            f'│ {status_badge} {preview}',
        ]

    @staticmethod
    def build_record_item_lines(index: int, title: str, status_badge: str, summary: str) -> list[str]:
        """
        构建浏览页记录导航项文案。

        :param index: 记录索引
        :param title: 记录标题
        :param status_badge: 状态徽标
        :param summary: 记录摘要
        :return: 文本行列表
        """
        return [
            f'▌ {WORKSPACE_LABELS["record"]} {index + 1:02d} · {title}',
            f'│ {status_badge} {summary}',
        ]

    @staticmethod
    def build_section_detail_lines(title: str, status_label: str, status_badge: str, body: str) -> list[str]:
        """
        构建详情页右侧分区内容文案。

        :param title: 分区标题
        :param status_label: 分区状态
        :param status_badge: 状态徽标
        :param body: 主体文本
        :return: 文本行列表
        """
        return [
            f'{status_badge} {title}',
            f'{WORKSPACE_LABELS["status"]} · {status_label}',
            '',
            body,
        ]

    @staticmethod
    def build_browser_action_panel_lines(action_lines: list[str], feedback_lines: list[str]) -> list[str]:
        """
        构建浏览页动作面板文案。

        :param action_lines: 可执行动作文本
        :param feedback_lines: 最近动作反馈文本
        :return: 文本行列表
        """
        lines = [
            BROWSER_ACTION_PANEL_COPY['action_section_title'],
            *[f'> {line}' for line in action_lines],
            '',
            BROWSER_ACTION_PANEL_COPY['operation_section_title'],
        ]
        lines.extend(ACTION_HINT_COPY['operation_hint_lines'])
        if feedback_lines:
            lines.extend(
                [
                    '',
                    BROWSER_ACTION_PANEL_COPY['recent_action_section_title'],
                    *[f'> {line}' for line in feedback_lines],
                ]
            )
        return lines

    @staticmethod
    def build_status_panel_text(title: str, status_code: str, status_label: str, body: str) -> str:
        """
        构建状态面板渲染文本。

        :param title: 面板标题
        :param status_code: 状态码
        :param status_label: 状态标签
        :param body: 面板正文
        :return: 渲染文本
        """
        return f'{status_code} {title}\n{WORKSPACE_LABELS["status"]} · {status_label}\n\n{body}'

    @staticmethod
    def build_metric_panel_text(title: str, value: str, status_code: str, status_label: str, hint: str) -> str:
        """
        构建指标卡渲染文本。

        :param title: 指标标题
        :param value: 指标值
        :param status_code: 状态码
        :param status_label: 状态标签
        :param hint: 提示文本
        :return: 渲染文本
        """
        return (
            f'{METRIC_COPY["label"]} · {title}\n'
            f'────────────────────────\n'
            f'{METRIC_COPY["value_label"]} · {value}\n'
            f'{WORKSPACE_LABELS["status"]} · {status_code} / {status_label}\n'
            f'{METRIC_COPY["hint_label"]} · {hint}'
        )

    @staticmethod
    def build_signal_rail_text(pulse: str, body: str) -> str:
        """
        构建首页信号带渲染文本。

        :param pulse: 当前脉冲字符
        :param body: 主体文本
        :return: 渲染文本
        """
        return '\n'.join(
            [
                f'{SIGNAL_RAIL_COPY["title"]} {pulse}',
                '────────────────────────',
                body or SIGNAL_RAIL_COPY['empty'],
            ]
        )

    @staticmethod
    def build_workspace_header_lines(
        *,
        env: str,
        view_label: str,
        timestamp: str,
        shortcut_hint: str,
    ) -> list[str]:
        """
        构建工作区顶部状态栏文本行。

        :param env: 当前环境
        :param view_label: 当前页面显示名称
        :param timestamp: 当前时间
        :param shortcut_hint: 快捷键提示
        :return: 文本行列表
        """
        return [
            f'RuoYi 控制台 · 环境 {env.upper()} · 页面 {view_label}',
            f'快捷键 · {shortcut_hint}  时间 {timestamp}',
        ]

    @staticmethod
    def build_dashboard_signal_lines(
        *,
        status_track: str,
        fail_count: int,
        warn_count: int,
        ok_count: int,
        total_count: int,
        navigation_shortcut_hint: str,
    ) -> list[str]:
        """
        构建首页信号带文案。

        :param status_track: 面板状态轨迹
        :param fail_count: 失败数量
        :param warn_count: 警告数量
        :param ok_count: 正常数量
        :param total_count: 总数量
        :param navigation_shortcut_hint: 页面快捷键提示
        :return: 文本行列表
        """
        return [
            f'面板轨迹 · {status_track or "-"}',
            f'风险分布 · 失败 {fail_count:02d}  警告 {warn_count:02d}  正常 {ok_count:02d}  合计 {total_count:02d}',
            f'快捷入口 · 页面 {navigation_shortcut_hint}',
        ]

    @staticmethod
    def build_dashboard_summary_text(total_count: int, ok_count: int, warn_count: int, fail_count: int) -> str:
        """
        构建首页摘要文本。

        :param total_count: 面板总数
        :param ok_count: 正常数量
        :param warn_count: 警告数量
        :param fail_count: 失败数量
        :return: 摘要文本
        """
        posture = '存在风险' if fail_count else '需要关注' if warn_count else '运行稳定'
        return (
            f'当前态势：{posture}。共 {total_count} 个面板，正常 {ok_count} 个，'
            f'警告 {warn_count} 个，失败 {fail_count} 个。'
        )

    @staticmethod
    def build_detail_summary_text(total_count: int, ok_count: int, warn_count: int, fail_count: int) -> str:
        """
        构建详情页摘要文本。

        :param total_count: 分区总数
        :param ok_count: 正常数量
        :param warn_count: 警告数量
        :param fail_count: 失败数量
        :return: 摘要文本
        """
        return (
            f'当前页共 {total_count} 个分区，正常 {ok_count} 个，警告 {warn_count} 个，失败 {fail_count} 个。'
            '左侧上下切页，左右切换当前焦点区域。'
        )

    @staticmethod
    def build_browser_summary_text(
        total_count: int,
        ok_count: int,
        warn_count: int,
        fail_count: int,
        action_hint: str,
    ) -> str:
        """
        构建浏览页摘要文本。

        :param total_count: 记录总数
        :param ok_count: 正常数量
        :param warn_count: 警告数量
        :param fail_count: 失败数量
        :param action_hint: 动作提示文案
        :return: 摘要文本
        """
        return (
            f'当前页共 {total_count} 条记录，正常 {ok_count} 条，警告 {warn_count} 条，失败 {fail_count} 条。'
            f'切换记录后，右侧会联动展示概览与分区详情。{action_hint}'
        )
