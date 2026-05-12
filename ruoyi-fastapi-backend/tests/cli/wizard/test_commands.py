from pathlib import Path
from types import ModuleType

from pytest import MonkeyPatch
from typer.testing import CliRunner


def test_wizard_help_lists_supported_subcommands(
    monkeypatch: MonkeyPatch,
    backend_dir: Path,
    cli_main: ModuleType,
) -> None:
    runner = CliRunner()
    monkeypatch.chdir(backend_dir)

    result = runner.invoke(cli_main.CLI_APPLICATION_BUILDER.build(), ['wizard', '--help'])

    assert result.exit_code == 0
    assert 'app-run' in result.stdout
    assert 'db-upgrade' in result.stdout
    assert 'cache-clear' in result.stdout
    assert 'gen-export' in result.stdout
    assert 'gen-import' in result.stdout
    assert 'prod-check' in result.stdout
