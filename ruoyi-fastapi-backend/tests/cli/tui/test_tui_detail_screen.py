from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch


def test_detail_screen_updates_section_detail_view(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='Jobs',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='Section A', status='ok', lines=['line a']),
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='Section B', status='warn', lines=['line b']),
        ],
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='jobs',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_sections: list[object] = []

    class FakeSectionDetailView:
        def show_section(self, section: object, query: str = '') -> None:
            del query
            recorded_sections.append(section)

    screen.query_one = lambda widget_type: FakeSectionDetailView()  # type: ignore[method-assign]

    screen._update_selected_section(1)

    assert screen.selected_section_index == 1
    assert recorded_sections
    assert recorded_sections[0].title == 'Section B'


def test_detail_screen_search_submit_remembers_and_refreshes(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='数据库',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='历史版本', status='ok', lines=['line a']),
        ],
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按 revision 搜索',
            query='',
            suggestions=['head', 'base'],
        ),
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='database',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_queries: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    fake_app = SimpleNamespace(
        remember_browser_query=lambda view_key, query: recorded_queries.append((view_key, query)),
        action_refresh_current_view=lambda: refresh_calls.append('refresh'),
    )
    monkeypatch.setattr(tui_modules.cli_tui_detail.DetailScreen, 'app', property(lambda self: fake_app))

    screen._handle_search_submitted('head')

    assert recorded_queries == [('database', 'head')]
    assert refresh_calls == ['refresh']


def test_detail_screen_clear_search_remembers_empty_and_refreshes(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='数据库',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='历史版本', status='ok', lines=['line a']),
        ],
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按 revision 搜索',
            query='head',
            suggestions=['head', 'base'],
        ),
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='database',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    recorded_queries: list[tuple[str, str]] = []
    refresh_calls: list[str] = []
    fake_app = SimpleNamespace(
        remember_browser_query=lambda view_key, query: recorded_queries.append((view_key, query)),
        action_refresh_current_view=lambda: refresh_calls.append('refresh'),
    )
    monkeypatch.setattr(tui_modules.cli_tui_detail.DetailScreen, 'app', property(lambda self: fake_app))

    screen.action_clear_search()

    assert recorded_queries == [('database', '')]
    assert refresh_calls == ['refresh']


@pytest.mark.asyncio
async def test_detail_screen_execute_external_action_suspends_app(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='数据库',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='迁移版本', status='ok', lines=['line a']),
        ],
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='database',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )
    action = tui_modules.cli_tui_detail.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='database',
        slot='global',
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
    monkeypatch.setattr(tui_modules.cli_tui_detail.DetailScreen, 'app', property(lambda self: fake_app))
    monkeypatch.setattr(
        tui_modules.cli_tui_interactions,
        'TUI_ACTION_EXECUTION_SERVICE',
        SimpleNamespace(
            execute_external=lambda spec: tui_modules.cli_tui_detail.TuiActionResult(
                spec=spec,
                external_exit_code=0,
                external_message='外部交互命令已执行完成',
            ),
            build_result_lines=lambda result: [],
        ),
    )
    monkeypatch.setattr(screen, 'notify', lambda *args, **kwargs: None)

    await screen._execute_action(action)

    assert recorded_suspend == ['enter', 'exit']


@pytest.mark.asyncio
async def test_detail_screen_execute_nested_json_action_without_suspend(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='传输加密',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='运行校验', status='ok', lines=['line a']),
        ],
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='crypto',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )
    action = tui_modules.cli_tui_detail.TUI_ACTION_REGISTRY.resolve_detail_action(
        view_key='crypto',
        slot='global',
        env='dev',
    )
    assert action is not None
    assert action.execution_mode == 'nested_json'

    suspend_calls: list[str] = []
    execute_calls: list[tuple[object, str]] = []

    class DummySuspend:
        def __enter__(self) -> None:
            suspend_calls.append('enter')

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> None:
            del exc_type, exc, tb
            suspend_calls.append('exit')

    def build_suspend() -> DummySuspend:
        return DummySuspend()

    def refresh_current_view() -> None:
        pass

    fake_app = SimpleNamespace(
        suspend=build_suspend,
        action_refresh_current_view=refresh_current_view,
    )
    monkeypatch.setattr(tui_modules.cli_tui_detail.DetailScreen, 'app', property(lambda self: fake_app))
    monkeypatch.setattr(
        tui_modules.cli_tui_interactions,
        'TUI_ACTION_EXECUTION_SERVICE',
        SimpleNamespace(
            execute=lambda spec, env: (
                execute_calls.append((spec, env))
                or tui_modules.cli_tui_detail.TuiActionResult(
                    spec=spec,
                    payload={'ok': True, 'message': '轮换预演完成'},
                )
            ),
            build_result_lines=lambda result: [],
        ),
    )
    monkeypatch.setattr(screen, 'notify', lambda *args, **kwargs: None)

    await screen._execute_action(action)

    assert suspend_calls == []
    assert execute_calls == [(action, 'dev')]


def test_detail_screen_support_builds_summary_actions_and_fallbacks(
    tui_modules: SimpleNamespace,
) -> None:
    support = tui_modules.cli_tui_detail.DetailScreenSupport()
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='数据库',
        subtitle='subtitle',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='迁移版本', status='ok', lines=['line a']),
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(title='Heads 状态', status='warn', lines=['line b']),
        ],
        search=tui_modules.cli_tui_search.PageSearchContext(
            placeholder='按 revision 搜索',
            query='head',
            suggestions=['head'],
        ),
    )

    summary = support.build_summary_text(snapshot, 'database')
    query = support.current_search_query(snapshot)
    action = support.resolve_action(active_view='database', slot='global', env='dev')
    empty_section = support.build_empty_section()

    assert '2 个分区' in summary
    assert query == 'head'
    assert action is not None
    assert action.command_args[:2] == ('wizard', 'db-upgrade')
    assert empty_section.title == tui_modules.cli_tui_copy.TUI_COPY.build_detail_empty_section_copy('title')


def test_detail_screen_focus_service_moves_and_scrolls_between_focus_targets(
    tui_modules: SimpleNamespace,
) -> None:
    focus_service = tui_modules.cli_tui_detail.DetailScreenFocusService()
    focused: list[str] = []
    sidebar = SimpleNamespace(focus=lambda: focused.append('sidebar'))
    sections = SimpleNamespace(focus=lambda: focused.append('sections'))
    detail = SimpleNamespace(focus=lambda: focused.append('detail'))
    workspace_main = object()
    fake_app = SimpleNamespace(focused=None)
    fake_screen = SimpleNamespace(
        app=fake_app,
        query_one=lambda selector, widget_type=None: {
            tui_modules.cli_tui_widgets.WorkspaceSidebar: sidebar,
            tui_modules.cli_tui_widgets.SectionNavigator: sections,
            tui_modules.cli_tui_widgets.SectionDetailView: detail,
            '#workspace-main': workspace_main,
        }[selector],
    )

    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = sections
    focus_service.move_focus(fake_screen, 1)
    fake_app.focused = object()
    scroll_target = focus_service.get_scroll_target(fake_screen)

    assert focused == ['sidebar', 'detail']
    assert scroll_target is workspace_main


def test_detail_screen_unmount_cancels_action_task(tui_modules: SimpleNamespace) -> None:
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='数据库',
        subtitle='subtitle',
        sections=[],
    )
    screen = tui_modules.cli_tui_detail.DetailScreen(
        snapshot,
        env='dev',
        active_view='database',
        navigation_items=tui_modules.cli_tui_app.NAVIGATION_ITEMS,
        refreshed_at='2026-04-30 10:00:00',
    )

    cancelled: list[str] = []

    class DummyTask:
        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            cancelled.append('action')

    screen._action_task = DummyTask()  # type: ignore[assignment]

    screen.on_unmount()

    assert cancelled == ['action']


@pytest.mark.asyncio
async def test_detail_screen_scrolls_in_small_viewport(tui_modules: SimpleNamespace) -> None:
    thin_scrollbar_size = 1
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.action_show_dashboard = lambda: None  # type: ignore[method-assign]
    app.current_view = 'app'
    snapshot = tui_modules.cli_tui_app.DetailPageSnapshot(
        title='应用',
        subtitle='超长详情',
        sections=[
            tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                title='配置总览',
                status='warn',
                lines=[f'第{i:02d}行 内容很长 内容很长 内容很长 内容很长' for i in range(1, 40)],
            )
        ],
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
        detail_body = app.screen.query_one('#detail-body')
        detail_view = app.screen.query_one(tui_modules.cli_tui_widgets.SectionDetailView)

        assert main.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert main.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert main.virtual_size.height > main.size.height
        assert detail_body.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert detail_body.styles.scrollbar_size_horizontal == thin_scrollbar_size
        assert detail_view.styles.scrollbar_size_vertical == thin_scrollbar_size
        assert detail_view.styles.scrollbar_size_horizontal == thin_scrollbar_size
