from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_cache_clear_wizard_cancels_when_confirmation_rejected(
    monkeypatch: MonkeyPatch,
    cache_clear_flow: ModuleType,
    exit_codes: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    answers = iter(['dev', 'cache-name', 'sys_config', True, False])
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': next(answers),
            prompt_choice=lambda prompt_text, choices, default_value: next(answers),
            prompt_required_text=lambda prompt_text, default_value='': next(answers),
            prompt_optional_text=lambda prompt_text, default_value='': '',
            prompt_confirm=lambda prompt_text, default_value=False: next(answers),
        ),
    )
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow.context_factory,
        'build_regular',
        lambda env, output, allow_prod, yes, dry_run: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow.execution_service,
        'complete_result',
        lambda ctx, result: captured.update({'ctx': ctx, 'result': result}),
    )

    cache_clear_flow.run_cache_clear_wizard('text')

    assert captured['ctx'].env == 'dev'
    assert captured['result'].exit_code == exit_codes.GUARD_REJECTED
    assert captured['result'].data['message'] == '已取消向导执行：wizard cache-clear'


def test_cache_clear_wizard_accepts_default_context_values(
    monkeypatch: MonkeyPatch,
    cache_clear_flow: ModuleType,
) -> None:
    captured_defaults: dict[str, object] = {}
    captured_confirm_defaults: list[tuple[str, bool]] = []
    answers = iter(['dev', 'cache-name', 'sys_config', True, False])
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': captured_defaults.update({'env': default_env}) or next(answers),
            prompt_choice=lambda prompt_text, choices, default_value: (
                captured_defaults.update({'mode': default_value}) or next(answers)
            ),
            prompt_required_text=lambda prompt_text, default_value='': (
                captured_defaults.update({'cache_name': default_value}) or next(answers)
            ),
            prompt_optional_text=lambda prompt_text, default_value='': '',
            prompt_confirm=lambda prompt_text, default_value=False: (
                captured_confirm_defaults.append((prompt_text, default_value)) or next(answers)
            ),
        ),
    )
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow.context_factory,
        'build_regular',
        lambda env, output, allow_prod, yes, dry_run: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        cache_clear_flow.CacheClearWizardFlow.execution_service,
        'complete_result',
        lambda ctx, result: None,
    )

    cache_clear_flow.run_cache_clear_wizard(
        'text',
        default_env='dev',
        default_mode='cache-name',
        default_cache_name='sys_config',
        default_dry_run=True,
    )

    assert captured_defaults['env'] == 'dev'
    assert captured_defaults['mode'] == 'cache-name'
    assert captured_defaults['cache_name'] == 'sys_config'
    assert captured_confirm_defaults[0][1] is True
