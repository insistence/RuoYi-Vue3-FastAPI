from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch


def test_browser_screen_builds_sections_from_selected_record(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='Jobs',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='Job A',
                status='ok',
                summary='summary a',
                metadata_lines=[],
                detail_sections=[
                    tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                        title='Job Detail',
                        status='ok',
                        lines=['detail a'],
                    )
                ],
            )
        ],
        shared_sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='Recent Logs', status='warn', lines=['log a'])
        ],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    sections = screen._get_sections_for_record(0)

    assert [section.title for section in sections] == ['Job Detail', 'Recent Logs']


def test_browser_screen_resolves_job_actions(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='Jobs',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='Job A',
                status='ok',
                summary='正常 · Cron 0/30 * * * * ?',
                metadata_lines=[],
                detail_sections=[],
            )
        ],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    primary_action = screen._resolve_action('primary')
    secondary_action = screen._resolve_action('secondary')
    global_action = screen._resolve_action('global')

    assert primary_action is not None
    assert primary_action.command_args == ('job', 'run-once', '1')
    assert secondary_action is not None
    assert secondary_action.command_args == ('job', 'pause', '1')
    assert global_action is not None
    assert global_action.command_args == ('job', 'sync')


def test_browser_screen_builds_action_panel_with_feedback(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='Jobs',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='Job A',
                status='ok',
                summary='正常 · Cron 0/30 * * * * ?',
                metadata_lines=[],
                detail_sections=[],
            )
        ],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )
    screen._action_feedback_lines = ['动作名称: 执行一次任务', '结果: 成功']

    lines = screen._build_record_action_lines(snapshot.records[0])

    assert any('动作键 [X] · 执行一次任务' in line for line in lines)
    assert any('浏览操作' in line for line in lines)
    assert any('最近动作反馈' in line for line in lines)
    assert any('结果: 成功' in line for line in lines)


@pytest.mark.asyncio
async def test_browser_screen_execute_external_action_suspends_app(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='代码生成',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='gen:201',
                title='sys_user',
                status='ok',
                summary='生成类 SysUser · 模块 system',
                metadata_lines=[],
                detail_sections=[],
            )
        ],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='gen',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )
    action = tui_modules.cli_tui_browser.TUI_ACTION_REGISTRY.resolve_browser_action(
        view_key='gen',
        slot='primary',
        record=snapshot.records[0],
        env='dev',
    )
    assert action is not None

    recorded_suspend: list[str] = []

    class DummySuspend:
        def __enter__(self) -> None:
            recorded_suspend.append('enter')

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> None:
            del exc_type, exc, tb
            recorded_suspend.append('exit')

    def build_suspend() -> DummySuspend:
        return DummySuspend()

    def refresh_current_view() -> None:
        pass

    fake_app = SimpleNamespace(
        suspend=build_suspend,
        action_refresh_current_view=refresh_current_view,
    )
    monkeypatch.setattr(tui_modules.cli_tui_browser.BrowserScreen, 'app', property(lambda self: fake_app))
    monkeypatch.setattr(
        tui_modules.cli_tui_interactions,
        'TUI_ACTION_EXECUTION_SERVICE',
        SimpleNamespace(
            execute_external=lambda spec: tui_modules.cli_tui_browser.TuiActionResult(
                spec=spec,
                external_exit_code=0,
                external_message='外部交互命令已执行完成',
            ),
            build_result_lines=lambda result: [],
        ),
    )
    monkeypatch.setattr(screen, 'notify', lambda *args, **kwargs: None)

    async def fake_render_record_detail(*, eager: bool = False) -> None:
        del eager

    monkeypatch.setattr(screen, '_render_record_detail', fake_render_record_detail)

    await screen._execute_action(action)

    assert recorded_suspend == ['enter', 'exit']


def test_browser_screen_filter_shortcut_remembers_and_refreshes(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='Job A',
                status='ok',
                summary='正常 · Cron 0/30 * * * * ?',
                metadata_lines=[],
                detail_sections=[],
            )
        ],
        shared_sections=[],
        filters=list(tui_modules.cli_tui_search.JOB_FILTER_OPTIONS),
        active_filter_key='all',
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_filters: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    fake_app = SimpleNamespace(
        remember_browser_filter=lambda view_key, filter_key: recorded_filters.append((view_key, filter_key)),
        action_refresh_current_view=lambda: refresh_calls.append('refresh'),
    )
    monkeypatch.setattr(tui_modules.cli_tui_browser.BrowserScreen, 'app', property(lambda self: fake_app))

    screen.action_apply_filter_2()

    assert recorded_filters == [('jobs', 'failed')]
    assert refresh_calls == ['refresh']


@pytest.mark.asyncio
async def test_browser_screen_detail_loader_failure_falls_back_to_failure_section(
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='任务一',
                status='warn',
                summary='摘要',
                metadata_lines=[],
                detail_sections=[],
                detail_loader=lambda: (_ for _ in ()).throw(RuntimeError('boom')),
            )
        ],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    rendered_calls: list[bool] = []

    async def fake_render_record_detail(*, eager: bool = False) -> None:
        del eager
        rendered_calls.append(True)

    screen._render_record_detail = fake_render_record_detail  # type: ignore[method-assign]
    screen._record_detail_request_id = 1

    await screen._load_record_detail_async(0, 1)

    cached_sections = snapshot.records[0]._cached_detail_sections

    assert rendered_calls == [True]
    assert cached_sections is not None
    assert len(cached_sections) == 1
    assert cached_sections[0].status == 'fail'
    assert cached_sections[0].title == '任务详情加载失败'
    assert any('boom' in line for line in cached_sections[0].lines)


def test_browser_screen_search_submit_remembers_and_refreshes(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='subtitle',
        records=[],
        shared_sections=[],
        filters=list(tui_modules.cli_tui_search.JOB_FILTER_OPTIONS),
        active_filter_key='all',
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按任务名搜索',
            query='',
            suggestions=['sync-user'],
        ),
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_queries: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    fake_app = SimpleNamespace(
        remember_browser_query=lambda view_key, query: recorded_queries.append((view_key, query)),
        action_refresh_current_view=lambda: refresh_calls.append('refresh'),
    )
    monkeypatch.setattr(tui_modules.cli_tui_browser.BrowserScreen, 'app', property(lambda self: fake_app))

    screen._handle_search_submitted('sync')

    assert recorded_queries == [('jobs', 'sync')]
    assert refresh_calls == ['refresh']


def test_browser_screen_support_builds_summary_actions_and_fallbacks(
    tui_modules: SimpleNamespace,
) -> None:
    support = tui_modules.cli_tui_browser.BrowserScreenSupport()
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='subtitle',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='Job A',
                status='ok',
                summary='正常 · Cron 0/30 * * * * ?',
                metadata_lines=[],
                detail_sections=[],
            )
        ],
        shared_sections=[],
        filters=list(tui_modules.cli_tui_search.JOB_FILTER_OPTIONS),
        active_filter_key='all',
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按任务名搜索',
            query='sync',
            suggestions=['sync-user'],
        ),
    )

    summary = support.build_summary_text(snapshot, 'jobs')
    filter_bar = support.build_filter_bar_text(snapshot)
    action = support.resolve_action(active_view='jobs', slot='primary', record=snapshot.records[0], env='dev')
    action_lines = support.build_record_action_lines(
        active_view='jobs',
        record=snapshot.records[0],
        env='dev',
        feedback_lines=['结果: 成功'],
    )
    empty_record = support.build_empty_record()
    loading_section = support.build_loading_section()
    failure_sections = support.build_detail_load_failure_sections(RuntimeError('boom'), '任务详情')
    empty_section = support.build_empty_section()

    assert '当前页共 1 条记录' in summary
    assert '当前搜索 · sync' in filter_bar
    assert action is not None
    assert action.command_args == ('job', 'run-once', '1')
    assert any('结果: 成功' in line for line in action_lines)
    assert empty_record.title == tui_modules.cli_tui_copy.TUI_COPY.build_browser_empty_record_copy('title')
    assert loading_section.title == tui_modules.cli_tui_copy.TUI_COPY.build_browser_loading_copy('title')
    assert failure_sections[0].status == 'fail'
    assert failure_sections[0].title == '任务详情加载失败'
    assert empty_section.title == tui_modules.cli_tui_copy.TUI_COPY.build_detail_empty_section_copy('title')


def test_browser_screen_focus_service_moves_and_scrolls_between_focus_targets(
    tui_modules: SimpleNamespace,
) -> None:
    focus_service = tui_modules.cli_tui_browser.BrowserScreenFocusService()
    focused: list[str] = []
    sidebar = SimpleNamespace(focus=lambda: focused.append('sidebar'))
    navigator = SimpleNamespace(focus=lambda: focused.append('records'))
    sections = SimpleNamespace(focus=lambda: focused.append('sections'))
    summary = SimpleNamespace(focus=lambda: focused.append('summary'))
    detail = SimpleNamespace(focus=lambda: focused.append('detail'))
    workspace_main = object()
    fake_app = SimpleNamespace(focused=None)
    fake_screen = SimpleNamespace(
        app=fake_app,
        query_one=lambda selector, widget_type=None: {
            tui_modules.cli_tui_widgets.WorkspaceSidebar: sidebar,
            tui_modules.cli_tui_widgets.RecordNavigator: navigator,
            tui_modules.cli_tui_widgets.SectionNavigator: sections,
            tui_modules.cli_tui_widgets.RecordSummaryView: summary,
            tui_modules.cli_tui_widgets.SectionDetailView: detail,
            '#workspace-main': workspace_main,
        }[selector],
    )

    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = navigator
    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = object()
    scroll_target = focus_service.get_scroll_target(fake_screen)

    assert focused == ['sidebar', 'sections']
    assert scroll_target is workspace_main


def test_browser_screen_clear_search_remembers_empty_and_refreshes(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='subtitle',
        records=[],
        shared_sections=[],
        filters=list(tui_modules.cli_tui_search.JOB_FILTER_OPTIONS),
        active_filter_key='all',
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按任务名搜索',
            query='sync',
            suggestions=['sync-user'],
        ),
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_queries: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    fake_app = SimpleNamespace(
        remember_browser_query=lambda view_key, query: recorded_queries.append((view_key, query)),
        action_refresh_current_view=lambda: refresh_calls.append('refresh'),
    )
    monkeypatch.setattr(tui_modules.cli_tui_browser.BrowserScreen, 'app', property(lambda self: fake_app))

    screen.action_clear_search()

    assert recorded_queries == [('jobs', '')]
    assert refresh_calls == ['refresh']


def test_browser_screen_unmount_cancels_background_tasks(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='缓存',
        subtitle='subtitle',
        records=[],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='cache',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    cancelled: list[str] = []

    class DummyTask:
        def __init__(self, name: str) -> None:
            self.name = name

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            cancelled.append(self.name)

    screen._record_detail_task = DummyTask('detail')  # type: ignore[assignment]
    screen._action_task = DummyTask('action')  # type: ignore[assignment]
    request_id = screen._record_detail_request_id

    screen.on_unmount()

    assert cancelled == ['detail', 'action']
    assert screen._record_detail_request_id == request_id + 1


def test_browser_screen_failure_sections_use_current_snapshot_title(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='缓存',
        subtitle='subtitle',
        records=[],
        shared_sections=[],
    )
    screen = tui_modules.cli_tui_browser.BrowserScreen(
        snapshot,
        env='dev',
        active_view='cache',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    sections = screen._build_detail_load_failure_sections(RuntimeError('boom'))

    assert sections[0].title == '缓存详情加载失败'


@pytest.mark.asyncio
async def test_browser_screen_scrolls_in_small_viewport(tui_modules: SimpleNamespace) -> None:
    thin_scrollbar_size = 1
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.action_show_dashboard = lambda: None  # type: ignore[method-assign]
    app.current_view = 'jobs'
    snapshot = tui_modules.cli_tui_adapters.BrowserPageSnapshot(
        title='任务',
        subtitle='超长浏览',
        records=[
            tui_modules.cli_tui_adapters.BrowserRecordSnapshot(
                key='job:1',
                title='任务一',
                status='warn',
                summary='摘要很长 摘要很长 摘要很长',
                metadata_lines=[f'字段{i}: 值很长 值很长 值很长' for i in range(1, 18)],
                detail_sections=[
                    tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                        title='明细分区',
                        status='warn',
                        lines=[f'明细{i}: 说明很长 说明很长 说明很长' for i in range(1, 30)],
                    )
                ],
            )
            for _ in range(6)
        ],
        shared_sections=[],
    )
    screen = app.screen_factory.build(
        snapshot=snapshot,
        env=app.env,
        active_view=app.current_view,
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        action_feedback_lines=app.get_action_feedback_lines(app.current_view),
    )

    async with app.run_test(size=(80, 24)) as pilot:
        app.screen_navigator.show(screen)
        await pilot.pause()
        await pilot.pause()

        main = app.screen.query_one('#workspace-main')
        browser_body = app.screen.query_one('#browser-body')
        browser_detail_pane = app.screen.query_one('#browser-detail-pane')
        record_navigator = app.screen.query_one(tui_modules.cli_tui_widgets.RecordNavigator)
        record_summary = app.screen.query_one(tui_modules.cli_tui_widgets.RecordSummaryView)
        section_detail = app.screen.query_one(tui_modules.cli_tui_widgets.SectionDetailView)

        assert main.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert main.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert main.virtual_size.height > main.size.height
        assert browser_body.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert browser_body.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert browser_body.virtual_size.width > browser_body.size.width
        assert browser_detail_pane.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert browser_detail_pane.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert browser_detail_pane.virtual_size.height > browser_detail_pane.size.height
        assert record_navigator.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert record_navigator.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert record_summary.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert record_summary.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert section_detail.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert section_detail.styles.scrollbar_size_horizontal == thin_scrollbar_size
