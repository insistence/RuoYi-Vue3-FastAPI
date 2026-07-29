from pytest import MonkeyPatch

from cli.tui import platform as platform_module


def test_windows_enables_reduced_motion_by_default(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv('RUOYI_TUI_REDUCED_MOTION', raising=False)
    monkeypatch.setattr(platform_module.sys, 'platform', 'win32')

    policy = platform_module.TuiPlatformPolicy.detect()

    assert policy.reduced_motion is True


def test_reduced_motion_environment_override_wins(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(platform_module.sys, 'platform', 'win32')
    monkeypatch.setenv('RUOYI_TUI_REDUCED_MOTION', 'off')

    policy = platform_module.TuiPlatformPolicy.detect()

    assert policy.reduced_motion is False
