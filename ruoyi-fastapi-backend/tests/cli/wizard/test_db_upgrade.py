from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_db_upgrade_wizard_executes_nested_cli_with_confirmed_inputs(
    monkeypatch: MonkeyPatch,
    db_upgrade_flow: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': 'dev',
            prompt_required_text=lambda prompt_text, default_value='': 'head',
            prompt_confirm=lambda prompt_text, default_value=False: True,
        ),
    )
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow.context_factory,
        'build_regular',
        lambda env, output, allow_prod, yes, dry_run: SimpleNamespace(
            env=env,
            output=output,
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
        ),
    )
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow,
        'nested_command_runner',
        lambda *arguments, parse_json=False: SimpleNamespace(
            returncode=0,
            payload={'ok': True, 'message': '数据库已升级到 head', 'dryRun': True},
        ),
    )
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow.execution_service,
        'complete_payload',
        lambda ctx, payload, default_exit_code=0: captured.update(
            {
                'ctx': ctx,
                'payload': payload,
                'default_exit_code': default_exit_code,
            }
        ),
    )

    db_upgrade_flow.run_db_upgrade_wizard('json')

    assert captured['ctx'].env == 'dev'
    assert captured['ctx'].output == 'json'
    assert captured['ctx'].dry_run is True
    assert captured['payload'] == {'ok': True, 'message': '数据库已升级到 head', 'dryRun': True}


def test_db_upgrade_wizard_accepts_default_context_values(
    monkeypatch: MonkeyPatch,
    db_upgrade_flow: ModuleType,
) -> None:
    captured_defaults: dict[str, object] = {}
    captured_confirm_defaults: list[tuple[str, bool]] = []
    confirm_answers = iter([True, False])
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': captured_defaults.update({'env': default_env}) or 'dev',
            prompt_required_text=lambda prompt_text, default_value='': (
                captured_defaults.update({'revision': default_value}) or 'head'
            ),
            prompt_confirm=lambda prompt_text, default_value=False: (
                captured_confirm_defaults.append((prompt_text, default_value)) or next(confirm_answers)
            ),
        ),
    )
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow.context_factory,
        'build_regular',
        lambda env, output, allow_prod, yes, dry_run: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        db_upgrade_flow.DbUpgradeWizardFlow.execution_service,
        'complete_result',
        lambda ctx, result: None,
    )

    db_upgrade_flow.run_db_upgrade_wizard(
        'text',
        default_env='dev',
        default_revision='head',
        default_dry_run=True,
    )

    assert captured_defaults['env'] == 'dev'
    assert captured_defaults['revision'] == 'head'
    assert captured_confirm_defaults[0][1] is True
