from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_app_run_wizard_execs_nested_cli_after_confirmation(
    monkeypatch: MonkeyPatch,
    app_run_flow: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    answers = iter(['dev', False, True])
    monkeypatch.setattr(
        app_run_flow.AppRunWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': next(answers),
            prompt_confirm=lambda prompt_text, default_value=False: next(answers),
        ),
    )
    monkeypatch.setattr(
        app_run_flow.AppRunWizardFlow.context_factory,
        'build_readonly',
        lambda env, output: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        app_run_flow.AppRunWizardFlow,
        'nested_live_command_runner',
        lambda *arguments: captured.update({'arguments': arguments}),
    )

    app_run_flow.run_app_run_wizard()

    assert captured['arguments'] == ('app', 'run', '--env=dev')
