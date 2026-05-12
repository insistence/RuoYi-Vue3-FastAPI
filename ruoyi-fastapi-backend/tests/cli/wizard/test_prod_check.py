from types import ModuleType, SimpleNamespace

from pytest import MonkeyPatch


def test_prod_check_wizard_aggregates_nested_cli_payloads(
    monkeypatch: MonkeyPatch,
    prod_check_flow: ModuleType,
) -> None:
    captured: dict[str, object] = {}
    answers = iter(['prod', True, True])
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='prod': next(answers),
            prompt_confirm=lambda prompt_text, default_value=False: next(answers),
        ),
    )
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow.context_factory,
        'build_readonly',
        lambda env, output: SimpleNamespace(env=env, output=output),
    )

    def fake_run_nested_cli_command(*arguments: str, parse_json: bool = False) -> SimpleNamespace:
        del parse_json
        if arguments[0:2] == ('app', 'env'):
            return SimpleNamespace(
                payload={
                    'ok': True,
                    'runtime': {
                        'cliEnv': 'prod',
                        'configEnv': 'prod',
                        'envFile': '.env.prod',
                        'envFileExists': True,
                    },
                }
            )
        if arguments[0:2] == ('app', 'doctor'):
            return SimpleNamespace(payload={'ok': True, 'message': '应用启动前检查通过'})
        return SimpleNamespace(
            payload={
                'ok': True,
                'config': {
                    'name': 'demo',
                    'host': '0.0.0.0',
                    'port': 9099,
                    'dbType': 'mysql',
                    'redisHost': '127.0.0.1',
                    'redisPort': 6379,
                },
            }
        )

    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow,
        'nested_command_runner',
        fake_run_nested_cli_command,
    )
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow.execution_service,
        'complete_payload',
        lambda ctx, payload, default_exit_code=0: captured.update({'ctx': ctx, 'payload': payload}),
    )

    prod_check_flow.run_prod_check_wizard('json')

    assert captured['ctx'].env == 'prod'
    assert captured['payload']['ok'] is True
    assert captured['payload']['doctor']['message'] == '应用启动前检查通过'
    assert captured['payload']['runtime']['cliEnv'] == 'prod'
    assert captured['payload']['config']['name'] == 'demo'


def test_prod_check_wizard_accepts_default_context_values(
    monkeypatch: MonkeyPatch,
    prod_check_flow: ModuleType,
) -> None:
    captured_defaults: dict[str, object] = {}
    confirm_answers = iter([True, False])
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow,
        'prompt_service',
        SimpleNamespace(
            prompt_env=lambda default_env='prod': captured_defaults.update({'env': default_env}) or 'prod',
            prompt_confirm=lambda prompt_text, default_value=False: (
                captured_defaults.update({'include_config': default_value}) or next(confirm_answers)
            ),
        ),
    )
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow.context_factory,
        'build_readonly',
        lambda env, output: SimpleNamespace(env=env, output=output),
    )
    monkeypatch.setattr(
        prod_check_flow.ProdCheckWizardFlow.execution_service,
        'complete_result',
        lambda ctx, result: None,
    )

    prod_check_flow.run_prod_check_wizard(
        'text',
        default_env='prod',
        default_include_config=True,
    )

    assert captured_defaults['env'] == 'prod'
    assert captured_defaults['include_config'] is True
