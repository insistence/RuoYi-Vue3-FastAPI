import os

from click.shell_completion import (
    CompletionItem,
    ShellComplete,
    add_completion_class,
    get_completion_class,
    split_arg_string,
)

_SOURCE_POWERSHELL = """\
$%(complete_func)s = {
    param($wordToComplete, $commandAst, $cursorPosition)

    $previousCompWords = $env:COMP_WORDS
    $previousCompCword = $env:COMP_CWORD
    $previousCompleteInstruction = $env:%(complete_var)s

    $commandLine = $commandAst.ToString()
    if ($cursorPosition -lt $commandLine.Length) {
        $commandLine = $commandLine.Substring(0, $cursorPosition)
    }

    $env:COMP_WORDS = $commandLine
    $env:COMP_CWORD = $wordToComplete
    $env:%(complete_var)s = "powershell_complete"

    try {
        %(prog_name)s | ForEach-Object {
            $line = $_.ToString()
            if ([string]::IsNullOrWhiteSpace($line)) {
                return
            }
            $parts = $line -split "`t", 3
            $completionValue = if ($parts.Length -ge 2) { $parts[1] } else { "" }
            $completionHelp = if ($parts.Length -ge 3 -and $parts[2]) { $parts[2] } else { $completionValue }
            [System.Management.Automation.CompletionResult]::new(
                $completionValue,
                $completionValue,
                [System.Management.Automation.CompletionResultType]::ParameterValue,
                $completionHelp
            )
        }
    } finally {
        if ($null -ne $previousCompWords) {
            $env:COMP_WORDS = $previousCompWords
        } else {
            Remove-Item Env:\\COMP_WORDS -ErrorAction SilentlyContinue
        }
        if ($null -ne $previousCompCword) {
            $env:COMP_CWORD = $previousCompCword
        } else {
            Remove-Item Env:\\COMP_CWORD -ErrorAction SilentlyContinue
        }
        if ($null -ne $previousCompleteInstruction) {
            $env:%(complete_var)s = $previousCompleteInstruction
        } else {
            Remove-Item Env:\\%(complete_var)s -ErrorAction SilentlyContinue
        }
    }
}

Register-ArgumentCompleter -Native -CommandName %(prog_name)s -ScriptBlock $%(complete_func)s
"""


class PowerShellComplete(ShellComplete):
    """
    PowerShell shell completion 支持。

    基于 PowerShell `Register-ArgumentCompleter -Native` 协议，将当前
    命令行和光标位置传回 Click completion 分发器，再把返回的候选项转换为
    `CompletionResult` 对象。
    """

    name = 'powershell'
    source_template = _SOURCE_POWERSHELL

    def get_completion_args(self) -> tuple[list[str], str]:
        """
        从 PowerShell 注入的环境变量中恢复 CLI 上下文。

        :return: 已解析的完整参数与当前不完整输入
        """
        cwords = split_arg_string(os.environ.get('COMP_WORDS', ''))
        incomplete = os.environ.get('COMP_CWORD', '')
        if incomplete:
            incomplete_parts = split_arg_string(incomplete)
            incomplete = incomplete_parts[0] if incomplete_parts else incomplete
        args = cwords[1:]
        if incomplete and args and args[-1] == incomplete:
            args.pop()
        return args, incomplete

    def format_completion(self, item: CompletionItem) -> str:
        """
        将候选项格式化为 PowerShell 脚本可解析的文本行。

        :param item: Click completion 候选项
        :return: 格式化后的文本
        """
        help_text = item.help or item.value
        return f'{item.type}\t{item.value}\t{help_text}'


def ensure_custom_completion_classes_registered() -> None:
    """
    确保自定义 shell completion 类已注册到 Click。

    :return: None
    """
    if get_completion_class(PowerShellComplete.name) is None:
        add_completion_class(PowerShellComplete)
