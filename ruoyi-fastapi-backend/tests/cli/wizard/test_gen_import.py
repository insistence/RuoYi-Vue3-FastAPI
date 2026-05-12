from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_gen_import_wizard_executes_nested_cli_with_selected_tables(
    monkeypatch: MonkeyPatch,
    gen_import_flow: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    answers = iter(['dev', 'sys_user,sys_role', True, True])
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': next(answers),
            prompt_required_text=lambda prompt_text, default_value='': next(answers),
            prompt_confirm=lambda prompt_text, default_value=False: next(answers),
        ),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.context_factory,
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
        gen_import_flow.GenImportWizardFlow,
        'nested_command_runner',
        lambda *arguments, parse_json=False: SimpleNamespace(
            returncode=0,
            payload={
                'ok': True,
                'message': '物理表导入预演完成，未执行实际导入',
                'dryRun': True,
                'tableNames': ['sys_user', 'sys_role'],
            },
        ),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.execution_service,
        'complete_payload',
        lambda ctx, payload, default_exit_code=0: captured.update(
            {
                'ctx': ctx,
                'payload': payload,
                'default_exit_code': default_exit_code,
            }
        ),
    )

    gen_import_flow.run_gen_import_wizard('json')

    assert captured['ctx'].env == 'dev'
    assert captured['ctx'].output == 'json'
    assert captured['ctx'].dry_run is True
    assert captured['payload']['tableNames'] == ['sys_user', 'sys_role']


def test_gen_import_wizard_accepts_default_context_values(
    monkeypatch: MonkeyPatch,
    gen_import_flow: ModuleType,
) -> None:
    captured_defaults: dict[str, object] = {}
    captured_confirm_defaults: list[tuple[str, bool]] = []
    answers = iter(['dev', 'sys_user', True, False])
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': captured_defaults.update({'env': default_env}) or next(answers),
            prompt_required_text=lambda prompt_text, default_value='': (
                captured_defaults.update({'table_names': default_value}) or next(answers)
            ),
            prompt_confirm=lambda prompt_text, default_value=False: (
                captured_confirm_defaults.append((prompt_text, default_value)) or next(answers)
            ),
        ),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.context_factory,
        'build_regular',
        lambda env, output, allow_prod, yes, dry_run: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.execution_service,
        'complete_result',
        lambda ctx, result: None,
    )

    gen_import_flow.run_gen_import_wizard(
        'text',
        default_env='dev',
        default_table_names='sys_user',
        default_dry_run=True,
    )

    assert captured_defaults['env'] == 'dev'
    assert captured_defaults['table_names'] == 'sys_user'
    assert captured_confirm_defaults[0][1] is True


def test_gen_import_wizard_falls_back_to_failure_payload_when_nested_result_has_no_dict_payload(
    monkeypatch: MonkeyPatch,
    gen_import_flow: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    answers = iter(['dev', 'sys_notice', True, True])
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='dev': next(answers),
            prompt_required_text=lambda prompt_text, default_value='': next(answers),
            prompt_confirm=lambda prompt_text, default_value=False: next(answers),
        ),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.context_factory,
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
        gen_import_flow.GenImportWizardFlow,
        'nested_command_runner',
        lambda *arguments, parse_json=False: SimpleNamespace(
            returncode=0,
            stdout='OK SUCCESS\nmessage: 导入表结构演练完成，未执行实际写入',
            stderr='',
            payload=[],
        ),
    )
    monkeypatch.setattr(
        gen_import_flow.GenImportWizardFlow.execution_service,
        'complete_payload',
        lambda ctx, payload, default_exit_code=0: captured.update(
            {
                'ctx': ctx,
                'payload': payload,
                'default_exit_code': default_exit_code,
            }
        ),
    )

    gen_import_flow.run_gen_import_wizard('text')

    assert captured['ctx'].env == 'dev'
    assert captured['payload'] == {
        'ok': False,
        'message': '代码生成导入向导执行失败',
        'error': 'OK SUCCESS\nmessage: 导入表结构演练完成，未执行实际写入',
        'exit_code': 0,
    }
