from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CompletionShellSpec:
    """
    Shell completion 元数据定义。

    name: shell 名称
    description: shell 描述文本
    generator: 脚本生成方式
    default_target: 默认脚本落盘路径，相对于用户 home 目录
    default_rc_file: 默认 rc 文件路径，相对于用户 home 目录
    auto_discovery: 是否会被 shell 自动发现
    supported: 当前版本是否已支持
    """

    name: str
    description: str
    generator: Literal['click', 'custom', 'unsupported']
    default_target: str
    default_rc_file: str | None
    auto_discovery: bool
    supported: bool


@dataclass(frozen=True)
class CompletionShellSpecRegistry:
    """
    completion shell 元数据注册表。

    该注册表集中维护 CLI 当前支持的 shell completion 元数据，
    供 installer、doctor 和 provider 等场景统一查询。

    :param specs: 按 shell 名称索引的元数据表
    """

    specs: dict[str, CompletionShellSpec]

    def get_spec(self, shell_name: str) -> CompletionShellSpec | None:
        """
        获取指定 shell 的 completion 元数据。

        :param shell_name: shell 名称
        :return: shell 元数据，不存在时返回 None
        """
        return self.specs.get(shell_name)

    def list_shell_names(self) -> list[str]:
        """
        获取已注册的 shell 名称列表。

        :return: shell 名称列表
        """
        return list(self.specs)


DEFAULT_COMPLETION_SHELL_SPECS: dict[str, CompletionShellSpec] = {
    'bash': CompletionShellSpec(
        name='bash',
        description='GNU Bash shell completion',
        generator='click',
        default_target='.local/share/ruoyi/completion/ruoyi.bash',
        default_rc_file='.bashrc',
        auto_discovery=False,
        supported=True,
    ),
    'zsh': CompletionShellSpec(
        name='zsh',
        description='Zsh shell completion',
        generator='click',
        default_target='.local/share/ruoyi/completion/ruoyi.zsh',
        default_rc_file='.zshrc',
        auto_discovery=False,
        supported=True,
    ),
    'fish': CompletionShellSpec(
        name='fish',
        description='Fish shell completion',
        generator='click',
        default_target='.config/fish/completions/ruoyi.fish',
        default_rc_file=None,
        auto_discovery=True,
        supported=True,
    ),
    'powershell': CompletionShellSpec(
        name='powershell',
        description='Windows PowerShell / PowerShell 7 completion',
        generator='custom',
        default_target='Documents/PowerShell/Profile/ruoyi.ps1',
        default_rc_file='Documents/PowerShell/Microsoft.PowerShell_profile.ps1',
        auto_discovery=False,
        supported=True,
    ),
}

COMPLETION_SHELL_SPEC_REGISTRY = CompletionShellSpecRegistry(specs=DEFAULT_COMPLETION_SHELL_SPECS)
