from types import SimpleNamespace

import pytest


def test_build_filter_bar_text_includes_search_context(tui_modules: SimpleNamespace) -> None:
    text = tui_modules.cli_tui_search.TUI_SEARCH_SERVICE.build_filter_bar_text(
        tui_modules.cli_tui_search.JOB_FILTER_OPTIONS,
        'failed',
        search_query='sync',
        search_placeholder='按任务名搜索',
        search_suggestions=['sync-job', 'sync-user'],
    )

    assert '当前筛选 · 失败' in text
    assert '搜索器 · [/] 按任务名搜索' in text
    assert '当前搜索 · sync  |  [Backspace] 清空' in text
    assert '候选建议 · sync-job  sync-user' in text


def test_tui_search_service_builds_filter_context_and_section_filtering(
    tui_modules: SimpleNamespace,
) -> None:
    service = tui_modules.cli_tui_search.TuiSearchService(
        tui_modules.cli_tui_search.TuiSearchSuggestionProviderRegistry(
            providers={
                'jobs': tui_modules.cli_tui_search.SearchSuggestionProviderSpec(
                    '按任务名搜索',
                    lambda incomplete: ['sync-user', 'sync-role', 'cleanup'],
                ),
                'app': tui_modules.cli_tui_search.SearchSuggestionProviderSpec('按分区或内容搜索'),
            }
        )
    )

    option = service.resolve_filter_option(tui_modules.cli_tui_search.JOB_FILTER_OPTIONS, 'failed')
    filter_bar = service.build_filter_bar_text(
        tui_modules.cli_tui_search.JOB_FILTER_OPTIONS,
        'failed',
        search_query='sync',
        search_placeholder='按任务名搜索',
        search_suggestions=['sync-user', 'sync-role'],
    )
    search_context = service.resolve_search_context('jobs', 'sync')
    default_context = service.resolve_search_context('app', '总览', default_suggestions=['总览判断', '应用配置'])
    sections = service.filter_detail_sections(
        [
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='总览判断', status='ok', lines=['应用正常']),
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='路由摘要', status='warn', lines=['同步任务接口']),
        ],
        '同步',
    )

    assert option is not None
    assert option.key == 'failed'
    assert '当前筛选 · 失败' in filter_bar
    assert search_context is not None
    assert search_context.placeholder == '按任务名搜索'
    assert search_context.suggestions[:2] == ['sync-user', 'sync-role']
    assert default_context is not None
    assert default_context.suggestions == ['总览判断']
    assert [section.title for section in sections] == ['路由摘要']


def test_tui_search_service_skips_provider_when_query_is_empty(
    tui_modules: SimpleNamespace,
) -> None:
    provider_calls: list[str] = []

    def record_provider(incomplete: str) -> list[str]:
        provider_calls.append(incomplete)
        return ['site_name']

    service = tui_modules.cli_tui_search.TuiSearchService(
        tui_modules.cli_tui_search.TuiSearchSuggestionProviderRegistry(
            providers={
                'configs': tui_modules.cli_tui_search.SearchSuggestionProviderSpec(
                    '按配置键搜索',
                    record_provider,
                )
            }
        )
    )

    search_context = service.resolve_search_context('configs', '')

    assert search_context is not None
    assert search_context.placeholder == '按配置键搜索'
    assert search_context.suggestions == []
    assert provider_calls == []


def test_search_highlight_helper_wraps_matches(tui_modules: SimpleNamespace) -> None:
    highlighted = tui_modules.cli_tui_search.TUI_SEARCH_HIGHLIGHTER.highlight('sync-user job', 'sync')

    assert highlighted == '【sync】-user job'


def test_dashboard_screen_support_builds_summary_signal_and_status_track(
    tui_modules: SimpleNamespace,
) -> None:
    support = tui_modules.cli_tui_dashboard.DashboardScreenSupport()
    snapshot = tui_modules.cli_tui_app.DashboardSnapshot(
        env='dev',
        metrics=[],
        panels=[
            tui_modules.cli_tui_adapters.DashboardPanelSnapshot(title='应用', status='ok', lines=['ok']),
            tui_modules.cli_tui_adapters.DashboardPanelSnapshot(title='任务', status='warn', lines=['warn']),
            tui_modules.cli_tui_adapters.DashboardPanelSnapshot(title='数据库', status='fail', lines=['fail']),
        ],
    )

    summary = support.build_summary_text(snapshot)
    status_track = support.build_status_track(snapshot)
    signal_lines = support.build_signal_lines(snapshot)

    assert '共 3 个面板' in summary
    assert status_track == 'o!x'
    assert any('失败 01' in line for line in signal_lines)


def test_dashboard_screen_focus_service_moves_and_scrolls_between_focus_targets(
    tui_modules: SimpleNamespace,
) -> None:
    focus_service = tui_modules.cli_tui_dashboard.DashboardScreenFocusService()
    focused: list[str] = []
    sidebar = SimpleNamespace(focus=lambda: focused.append('sidebar'))
    workspace_main = SimpleNamespace(focus=lambda: focused.append('main'))
    fake_app = SimpleNamespace(focused=None)
    fake_screen = SimpleNamespace(
        app=fake_app,
        query_one=lambda selector, widget_type=None: {
            tui_modules.cli_tui_widgets.WorkspaceSidebar: sidebar,
            '#workspace-main': workspace_main,
        }[selector],
    )

    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = sidebar
    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = object()
    scroll_target = focus_service.get_scroll_target(fake_screen)

    assert focused == ['sidebar', 'main']
    assert scroll_target is workspace_main


@pytest.mark.asyncio
async def test_dashboard_grid_expands_to_fit_status_panels(
    monkeypatch: pytest.MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    expected_dashboard_panel_count = 8
    min_expanded_dashboard_grid_height = 20
    snapshot = tui_modules.cli_tui_app.DashboardSnapshot(
        env='dev',
        metrics=[],
        panels=[
            tui_modules.cli_tui_adapters.DashboardPanelSnapshot(
                title=f'面板 {index + 1}',
                status='ok' if index % 2 == 0 else 'warn',
                lines=[
                    '## 巡检摘要',
                    f'当前面板: {index + 1}',
                    '状态说明: 这里需要展示多行内容',
                    '',
                    '## 建议动作',
                    '进入对应分区继续查看详情',
                ],
            )
            for index in range(8)
        ],
    )

    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors, 'dashboard', lambda env: snapshot
    )

    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    async with app.run_test(size=(160, 60)) as pilot:
        await pilot.pause()
        await pilot.pause()

        grid = app.screen.query_one('#dashboard-grid')
        panels = list(
            app.screen.query(tui_modules.cli_tui_widgets.StatusPanel).results(tui_modules.cli_tui_widgets.StatusPanel)
        )

        assert len(panels) == expected_dashboard_panel_count
        assert grid.virtual_size.height > min_expanded_dashboard_grid_height
        assert all(panel.content_size.height > 0 for panel in panels)
        assert len({panel.region.height for panel in panels}) == 1
