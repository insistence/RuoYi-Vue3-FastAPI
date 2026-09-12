import click.shell_completion as click_completion
import pytest
import typer

from cli.core.completion_dispatcher import CompletionDispatcher


@pytest.mark.parametrize(('comp_words', 'comp_cword'), [('ruoyi comp', 'comp'), ('ruoyi ', '')])
def test_powershell_completion_preserves_script_protocol_with_existing_registration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], comp_words: str, comp_cword: str
) -> None:
    """已有同名补全类时，仍按项目脚本的文本参数和制表符输出协议补全。"""
    # Click 8.5 的内置 PowerShell 补全复用 Bash 的数字 COMP_CWORD 协议。
    monkeypatch.setitem(click_completion._available_shells, 'powershell', click_completion.BashComplete)
    monkeypatch.setenv('_RUOYI_COMPLETE', 'powershell_complete')
    monkeypatch.setenv('COMP_WORDS', comp_words)
    monkeypatch.setenv('COMP_CWORD', comp_cword)
    app = typer.Typer(add_completion=False, callback=lambda: None)

    @app.command()
    def completion() -> None:
        """管理命令补全。"""

    with pytest.raises(SystemExit) as result:
        CompletionDispatcher().dispatch(app)

    assert result.value.code == 0
    captured = capsys.readouterr()
    assert captured.err == ''
    assert any(line.split('\t', 2)[:2] == ['plain', 'completion'] for line in captured.out.splitlines())
