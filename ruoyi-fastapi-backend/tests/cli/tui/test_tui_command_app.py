import importlib
from types import SimpleNamespace
from typing import Any

import pytest
import typer
from pytest import MonkeyPatch
from typer.testing import CliRunner


def test_tui_command_returns_dependency_error_when_textual_missing(
    monkeypatch: MonkeyPatch,
    tui_base_modules: SimpleNamespace,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tui_base_modules.BACKEND_DIR)

    def raise_missing_textual(module_name: str) -> Any:
        if module_name == 'cli.tui.app':
            raise ModuleNotFoundError("No module named 'textual'", name='textual')
        return importlib.import_module(module_name)

    monkeypatch.setattr(tui_base_modules.cli_tui_commands, 'import_module', raise_missing_textual)
    isolated_cli = typer.Typer()
    tui_base_modules.cli_tui_commands.TUI_COMMAND_REGISTRATION.register(isolated_cli)

    result = runner.invoke(isolated_cli, ['tui', '--env=dev'])

    assert result.exit_code == tui_base_modules.DEPENDENCY_ERROR
    assert '当前环境未安装 TUI 可选依赖' in result.stdout
    assert 'pip install -r requirements.txt' in result.stdout


def test_tui_app_mount_pushes_first_workspace_screen(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    recorded_calls: list[tuple[str, object]] = []

    class FakeDashboardScreen:
        def __init__(
            self,
            snapshot: object,
            env: str,
            active_view: str,
            navigation_items: list[object],
            refreshed_at: str,
        ) -> None:
            self.snapshot = snapshot
            self.env = env
            self.active_view = active_view
            self.navigation_items = navigation_items
            self.refreshed_at = refreshed_at

    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'dashboard',
        lambda env: tui_modules.cli_tui_app.DashboardSnapshot(env=env, panels=[]),
    )
    monkeypatch.setattr(tui_modules.cli_tui_app, 'DashboardScreen', FakeDashboardScreen)

    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    monkeypatch.setattr(app, 'push_screen', lambda screen: recorded_calls.append(('push', screen)))
    monkeypatch.setattr(app, 'switch_screen', lambda screen: recorded_calls.append(('switch', screen)))

    app.on_mount()

    assert recorded_calls
    assert recorded_calls[0][0] == 'push'
    assert isinstance(recorded_calls[0][1], FakeDashboardScreen)
    assert recorded_calls[0][1].env == 'dev'
    assert recorded_calls[0][1].active_view == 'dashboard'
    assert recorded_calls[0][1].navigation_items
    assert recorded_calls[0][1].refreshed_at
    assert app.current_view == 'dashboard'
    assert app.screen_navigator.initialized is True


def test_open_view_switches_to_expected_action(tui_modules: SimpleNamespace) -> None:
    calls: list[str] = []
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')

    def fake_show_view(view_key: str) -> None:
        calls.append(tui_modules.cli_tui_app.TUI_VIEW_REGISTRY.resolve_view_key(view_key))

    app.show_view = fake_show_view  # type: ignore[method-assign]

    app.open_view('jobs')
    app.open_view('app')
    app.open_view('ops')
    app.open_view('crypto')
    app.open_view('unknown')

    assert calls == ['jobs', 'app', 'ops', 'crypto', 'dashboard']


def test_workspace_header_render_includes_particle_line(tui_modules: SimpleNamespace) -> None:
    header = tui_modules.cli_tui_widgets.WorkspaceHeader('dev', 'dashboard')

    rendered = header.render()
    rendered_text = rendered.plain

    assert rendered.__class__.__name__ == 'Text'
    assert 'RuoYi 控制台' in rendered_text
    assert '环境 DEV · 页面 总览' in rendered_text
    assert any(symbol in rendered_text for symbol in ('█', '▓', '▒', '░', '·', '─'))


def test_workspace_header_centers_title_using_runtime_width(tui_modules: SimpleNamespace) -> None:
    header = tui_modules.cli_tui_widgets.WorkspaceHeader('dev', 'dashboard')
    header.styles.width = 140

    first_line = header.render().plain.splitlines()[0]

    assert first_line.startswith(' ')
    assert 'RuoYi 控制台' in first_line


def test_workspace_header_keeps_title_alignment_stable_across_frames(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    header = tui_modules.cli_tui_widgets.WorkspaceHeader('dev', 'dashboard')
    monotonic_values = iter([10.0, 10.0, 11.0, 11.0])
    workspace_module = importlib.import_module('cli.tui.widgets.workspace')
    monkeypatch.setattr(workspace_module, 'monotonic', lambda: next(monotonic_values))

    first_line_a = header.render().plain.splitlines()[0]
    first_line_b = header.render().plain.splitlines()[0]

    assert first_line_a.index('RuoYi 控制台') == first_line_b.index('RuoYi 控制台')


def test_workspace_hero_pulses_border_with_expected_palette(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    hero = tui_modules.cli_tui_widgets.WorkspaceHero(
        title='标题',
        subtitle='副标题',
        env='dev',
        active_view='dashboard',
        summary='摘要',
        refreshed_at='2026-05-12 12:00:00',
    )
    workspace_module = importlib.import_module('cli.tui.widgets.workspace')
    monkeypatch.setattr(workspace_module, 'monotonic', lambda: 10.0)
    original_border_text = str(hero.styles.border)

    hero._pulse_border()

    border_text = str(hero.styles.border)

    assert 'double' in border_text
    assert border_text != original_border_text


def test_workspace_hero_render_uses_rich_text_for_title_glow(tui_modules: SimpleNamespace) -> None:
    hero = tui_modules.cli_tui_widgets.WorkspaceHero(
        title='标题',
        subtitle='副标题',
        env='dev',
        active_view='dashboard',
        summary='摘要',
        refreshed_at='2026-05-12 12:00:00',
    )

    rendered = hero._build_render_text()

    assert rendered.__class__.__name__ == 'Text'
    assert '标题' in rendered.plain
    assert '副标题' in rendered.plain
    assert '运行摘要 · 摘要' in rendered.plain


def test_tui_app_runner_runs_created_application(tui_modules: SimpleNamespace) -> None:
    recorded_envs: list[str] = []
    recorded_runs: list[str] = []

    class FakeApp:
        def __init__(self, env: str) -> None:
            recorded_envs.append(env)

        def run(self) -> None:
            recorded_runs.append('run')

    runner = tui_modules.cli_tui_app.TuiAppRunner(FakeApp)

    runner.run('dev')

    assert recorded_envs == ['dev']
    assert recorded_runs == ['run']


def test_tui_app_show_jobs_uses_remembered_filter(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    recorded_filter_keys: list[tuple[str, str]] = []
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.remember_browser_filter('jobs', 'failed')
    app.remember_browser_query('jobs', 'sync')
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'jobs',
        lambda env, filter_key='all', query='': (
            recorded_filter_keys.append((filter_key, query))
            or tui_modules.cli_tui_app.BrowserPageSnapshot(
                title='任务',
                subtitle='subtitle',
                records=[],
                shared_sections=[],
                filters=[],
                active_filter_key=filter_key,
                search=None,
            )
        ),
    )
    monkeypatch.setattr(app.screen_navigator, 'show', lambda screen: None)
    app.action_show_jobs()

    assert recorded_filter_keys == [('failed', 'sync')]


def test_tui_app_show_configs_uses_remembered_filter(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    recorded_filter_keys: list[tuple[str, str]] = []
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.remember_browser_filter('configs', 'cache-drift')
    app.remember_browser_query('configs', 'site')
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'configs',
        lambda env, filter_key='all', query='': (
            recorded_filter_keys.append((filter_key, query))
            or tui_modules.cli_tui_app.BrowserPageSnapshot(
                title='参数配置',
                subtitle='subtitle',
                records=[],
                shared_sections=[],
                filters=[],
                active_filter_key=filter_key,
                search=None,
            )
        ),
    )
    monkeypatch.setattr(app.screen_navigator, 'show', lambda screen: None)
    app.action_show_configs()

    assert recorded_filter_keys == [('cache-drift', 'site')]


def test_tui_app_show_cache_and_gen_use_remembered_query(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    cache_queries: list[str] = []
    gen_queries: list[str] = []
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.remember_browser_query('cache', 'sys')
    app.remember_browser_query('gen', 'user')
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'cache',
        lambda env, query='': (
            cache_queries.append(query)
            or tui_modules.cli_tui_app.BrowserPageSnapshot(
                title='缓存',
                subtitle='subtitle',
                records=[],
                shared_sections=[],
                filters=[],
                active_filter_key=None,
                search=None,
            )
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'gen',
        lambda env, query='': (
            gen_queries.append(query)
            or tui_modules.cli_tui_app.BrowserPageSnapshot(
                title='代码生成',
                subtitle='subtitle',
                records=[],
                shared_sections=[],
                filters=[],
                active_filter_key=None,
                search=None,
            )
        ),
    )
    monkeypatch.setattr(app.screen_navigator, 'show', lambda screen: None)
    app.action_show_cache()
    app.action_show_gen()

    assert cache_queries == ['sys']
    assert gen_queries == ['user']


def test_tui_app_detail_views_use_remembered_query(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    database_queries: list[str] = []
    app_queries: list[str] = []
    ops_queries: list[str] = []
    crypto_queries: list[str] = []
    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    app.remember_browser_query('database', 'head')
    app.remember_browser_query('app', 'route')
    app.remember_browser_query('ops', 'disk')
    app.remember_browser_query('crypto', 'kid')
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'database',
        lambda env, query='': (
            database_queries.append(query)
            or tui_modules.cli_tui_app.DetailPageSnapshot(title='数据库', subtitle='subtitle', sections=[])
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'app',
        lambda env, query='': (
            app_queries.append(query)
            or tui_modules.cli_tui_app.DetailPageSnapshot(title='应用', subtitle='subtitle', sections=[])
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'ops',
        lambda env, query='': (
            ops_queries.append(query)
            or tui_modules.cli_tui_app.DetailPageSnapshot(title='运维', subtitle='subtitle', sections=[])
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'crypto',
        lambda env, query='': (
            crypto_queries.append(query)
            or tui_modules.cli_tui_app.DetailPageSnapshot(title='传输加密', subtitle='subtitle', sections=[])
        ),
    )
    monkeypatch.setattr(app.screen_navigator, 'show', lambda screen: None)
    app.action_show_database()
    app.action_show_app()
    app.action_show_ops()
    app.action_show_crypto()

    assert database_queries == ['head']
    assert app_queries == ['route']
    assert ops_queries == ['disk']
    assert crypto_queries == ['kid']


@pytest.mark.asyncio
async def test_tui_app_open_view_updates_screen_across_multiple_switches(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'dashboard',
        lambda env: tui_modules.cli_tui_app.DashboardSnapshot(env=env, panels=[]),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'app',
        lambda env, query='': tui_modules.cli_tui_app.DetailPageSnapshot(
            title='应用详情',
            subtitle=query or 'app-subtitle',
            sections=[
                tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                    title='应用分区',
                    status='ok',
                    lines=['app-line'],
                )
            ],
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'ops',
        lambda env, query='': tui_modules.cli_tui_app.DetailPageSnapshot(
            title='运维详情',
            subtitle=query or 'ops-subtitle',
            sections=[
                tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                    title='运维分区',
                    status='warn',
                    lines=['ops-line'],
                )
            ],
        ),
    )

    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DashboardScreen'
        assert app.current_view == 'dashboard'

        app.open_view('app')
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DetailScreen'
        assert app.current_view == 'app'
        assert app.screen.snapshot.title == '应用详情'

        app.open_view('ops')
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DetailScreen'
        assert app.current_view == 'ops'
        assert app.screen.snapshot.title == '运维详情'


@pytest.mark.asyncio
async def test_tui_sidebar_highlight_updates_screen_across_multiple_switches(
    monkeypatch: MonkeyPatch,
    tui_modules: SimpleNamespace,
) -> None:
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'dashboard',
        lambda env: tui_modules.cli_tui_app.DashboardSnapshot(env=env, panels=[]),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'app',
        lambda env, query='': tui_modules.cli_tui_app.DetailPageSnapshot(
            title='应用详情',
            subtitle='app-subtitle',
            sections=[
                tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                    title='应用分区',
                    status='ok',
                    lines=['app-line'],
                )
            ],
        ),
    )
    monkeypatch.setitem(
        tui_modules.cli_tui_app.TUI_SNAPSHOT_COLLECTOR_REGISTRY.collectors,
        'ops',
        lambda env, query='': tui_modules.cli_tui_app.DetailPageSnapshot(
            title='运维详情',
            subtitle='ops-subtitle',
            sections=[
                tui_modules.cli_tui_adapters.DetailSectionSnapshot(
                    title='运维分区',
                    status='warn',
                    lines=['ops-line'],
                )
            ],
        ),
    )

    app = tui_modules.cli_tui_app.RuoyiTuiApp('dev')
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DashboardScreen'
        assert app.current_view == 'dashboard'

        await pilot.press('down')
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DetailScreen'
        assert app.current_view == 'app'
        assert app.screen.snapshot.title == '应用详情'

        await pilot.press('down')
        await pilot.pause()
        await pilot.pause()

        assert type(app.screen).__name__ == 'DetailScreen'
        assert app.current_view == 'ops'
        assert app.screen.snapshot.title == '运维详情'
