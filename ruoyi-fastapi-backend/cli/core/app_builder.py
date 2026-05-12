import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

import typer

from cli.output import OutputRenderer
from cli.runtime.base import RUNTIME_ENVIRONMENT


@dataclass(frozen=True)
class ProjectRuntimeLocator:
    """
    CLI 项目运行时定位器。

    该对象负责判断当前目录是否为后端项目根目录、注入 `sys.path`，
    并为配置导入阶段提取最小化的 `argv` 参数。
    """

    def is_backend_project_dir(self, project_dir: Path) -> bool:
        """
        判断给定目录是否为后端项目根目录。

        :param project_dir: 待检查目录
        :return: 是否为后端项目根目录
        """
        return RUNTIME_ENVIRONMENT.is_backend_project_dir(project_dir)

    def ensure_backend_dir_on_sys_path(self) -> Path:
        """
        将当前后端项目根目录加入 `sys.path` 首位。

        :return: 当前后端项目根目录
        :raises typer.Exit: 当前目录不是后端项目根目录时退出命令
        """
        project_dir = Path.cwd().resolve()
        if not self.is_backend_project_dir(project_dir):
            typer.echo('`ruoyi` 命令需在 `ruoyi-fastapi-backend` 目录下执行', err=True)
            raise typer.Exit(code=2)

        project_dir_str = str(project_dir)
        if sys.path and sys.path[0] == project_dir_str:
            return project_dir

        sys.path.insert(0, project_dir_str)
        return project_dir

    def extract_import_argv(self, argv: list[str] | None = None) -> list[str]:
        """
        提取供配置模块导入阶段使用的最小参数集。

        :param argv: 原始命令行参数列表
        :return: 仅保留程序名和 `--env` 的参数列表
        """
        current_argv = argv or sys.argv
        program_name = current_argv[0] if current_argv else 'ruoyi'
        import_argv = [program_name]
        env_value = ''
        current_args = current_argv[1:]
        for index, argument in enumerate(current_args):
            if argument.startswith('--env='):
                env_value = argument.split('=', 1)[1].strip()
                break
            if argument == '--env' and index + 1 < len(current_args):
                env_value = current_args[index + 1].strip()
                break

        if env_value:
            import_argv.extend(['--env', env_value])
        return import_argv


@dataclass(frozen=True)
class CliCommandGroupRegistry:
    """
    CLI 命令组注册表。

    该注册表集中维护根 CLI 需要挂载的业务命令组模块路径，
    避免命令组声明散落在应用构建器主体中。

    :param command_modules: 命令组到模块路径的映射
    """

    command_modules: dict[str, str]


@dataclass(frozen=True)
class CliExtensionRegistration:
    """
    CLI 扩展入口注册描述。

    :param module_path: 扩展模块导入路径
    :param attach: 已加载模块挂载到根 CLI 的函数
    """

    module_path: str
    attach: Callable[[typer.Typer, object], None]


@dataclass(frozen=True)
class CliExtensionRegistry:
    """
    CLI 扩展入口注册表。

    该注册表集中维护 completion、wizard、TUI 等扩展入口的模块路径与
    挂载方式，避免这些规则继续散落在注册器主体中。

    :param registrations: 扩展注册描述列表
    """

    registrations: tuple[CliExtensionRegistration, ...]


@dataclass(frozen=True)
class CliCommandGroupRegistrar:
    """
    CLI 命令组注册器。

    该对象负责根据命令组注册表向根 Typer 应用挂载业务命令组。

    :param command_group_registry: CLI 命令组注册表
    """

    command_group_registry: CliCommandGroupRegistry
    module_loader: 'CliModuleLoader' = field(default_factory=lambda: DEFAULT_CLI_MODULE_LOADER)

    def register(self, cli: typer.Typer) -> None:
        """
        向根应用注册业务命令组。

        :param cli: 根 Typer 应用
        :return: None
        """
        for command_name, module_path in self.command_group_registry.command_modules.items():
            command_module = self.module_loader.load(module_path)
            cli.add_typer(command_module.app, name=command_name)


class CliExtensionMountSupport:
    """
    CLI 扩展入口挂载支持对象。

    该对象负责封装不同扩展模块挂载到根 CLI 的差异，避免扩展注册器本体
    继续堆积 `if/else` 或硬编码模块处理逻辑。
    """

    @staticmethod
    def attach_completion(cli: typer.Typer, module: object) -> None:
        """
        挂载 completion 扩展入口。

        :param cli: 根 Typer 应用
        :param module: 已加载模块
        :return: None
        """
        cli.add_typer(module.COMPLETION_COMMAND_BUILDER.build(cli), name='completion')

    @staticmethod
    def attach_wizard(cli: typer.Typer, module: object) -> None:
        """
        挂载 wizard 扩展入口。

        :param cli: 根 Typer 应用
        :param module: 已加载模块
        :return: None
        """
        cli.add_typer(module.WIZARD_COMMAND_BUILDER.build(), name='wizard')

    @staticmethod
    def attach_tui(cli: typer.Typer, module: object) -> None:
        """
        挂载 TUI 扩展入口。

        :param cli: 根 Typer 应用
        :param module: 已加载模块
        :return: None
        """
        module.TUI_COMMAND_REGISTRATION.register(cli)


@dataclass(frozen=True)
class CliExtensionRegistrar:
    """
    CLI 扩展入口注册器。

    该对象负责向根 Typer 应用挂载 completion、wizard 与 TUI
    等扩展入口。
    """

    extension_registry: CliExtensionRegistry
    module_loader: 'CliModuleLoader' = field(default_factory=lambda: DEFAULT_CLI_MODULE_LOADER)

    def register(self, cli: typer.Typer) -> None:
        """
        向根应用注册扩展入口。

        :param cli: 根 Typer 应用
        :return: None
        """
        for registration in self.extension_registry.registrations:
            extension_module = self.module_loader.load(registration.module_path)
            registration.attach(cli, extension_module)


@dataclass(frozen=True)
class CliRootOptionInitializer:
    """
    CLI 根级选项初始化器。

    该对象负责将根级 `--color`、`--icon` 选项映射到共享输出渲染器，
    避免根回调继续内联输出配置逻辑。

    :param output_renderer: 根命令共享的输出渲染器
    """

    output_renderer: OutputRenderer

    def initialize(self, *, color: str, icon: str) -> None:
        """
        初始化根级输出选项。

        :param color: 文本输出颜色模式
        :param icon: 文本输出图标模式
        :return: None
        """
        self.output_renderer.set_color_mode(color)
        self.output_renderer.set_icon_mode(icon)


@dataclass(frozen=True)
class CliRootCallbackRegistrar:
    """
    CLI 根回调注册器。

    该对象负责把根级 `--color`、`--icon` 选项回调挂载到 Typer 根应用，
    让 `CliApplicationBuilder` 更专注于整体装配流程。

    :param root_option_initializer: 根级选项初始化器
    """

    root_option_initializer: CliRootOptionInitializer

    def register(self, cli: typer.Typer) -> None:
        """
        向根应用注册回调。

        :param cli: 根 Typer 应用
        :return: None
        """

        @cli.callback()
        def root_callback(
            color: Annotated[
                Literal['auto', 'always', 'never'],
                typer.Option('--color', help='文本输出颜色模式'),
            ] = 'always',
            icon: Annotated[
                Literal['emoji', 'ascii', 'none'],
                typer.Option('--icon', help='文本输出图标模式'),
            ] = 'emoji',
        ) -> None:
            """
            初始化 CLI 根级运行参数。

            :param color: 文本输出颜色模式
            :param icon: 文本输出图标模式
            :return: None
            """
            self.root_option_initializer.initialize(color=color, icon=icon)


@dataclass(frozen=True)
class CliModuleLoader:
    """
    CLI 模块加载服务。

    该对象负责集中执行命令组与扩展入口所需的延迟导入，
    让注册器本身更专注于挂载动作。
    """

    @staticmethod
    def load(module_path: str) -> object:
        """
        按模块路径加载模块对象。

        :param module_path: 模块导入路径
        :return: 已加载模块
        """
        return importlib.import_module(module_path)


@dataclass
class CliApplicationBuilder:
    """
    CLI 根应用构建器。

    :param output_renderer: 根命令共享的输出渲染器
    :param command_group_registrar: CLI 命令组注册器
    :param extension_registrar: CLI 扩展入口注册器
    """

    output_renderer: OutputRenderer
    command_group_registrar: CliCommandGroupRegistrar = field(
        default_factory=lambda: CliCommandGroupRegistrar(DEFAULT_COMMAND_GROUP_REGISTRY)
    )
    extension_registrar: CliExtensionRegistrar = field(
        default_factory=lambda: CliExtensionRegistrar(DEFAULT_CLI_EXTENSION_REGISTRY)
    )
    root_option_initializer: CliRootOptionInitializer = field(init=False)
    root_callback_registrar: CliRootCallbackRegistrar = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化根应用构建器依赖。

        :return: None
        """
        self.root_option_initializer = CliRootOptionInitializer(self.output_renderer)
        self.root_callback_registrar = CliRootCallbackRegistrar(self.root_option_initializer)

    def build(self) -> typer.Typer:
        """
        构建 Typer 根应用并注册全部命令组。

        :return: Typer 根应用
        """
        cli = typer.Typer(
            name='ruoyi',
            help='RuoYi FastAPI 后端统一命令入口',
            no_args_is_help=True,
            add_completion=False,
            context_settings={'help_option_names': ['-h', '--help']},
        )
        self.root_callback_registrar.register(cli)
        self.command_group_registrar.register(cli)
        self.extension_registrar.register(cli)
        return cli


DEFAULT_COMMAND_GROUP_REGISTRY = CliCommandGroupRegistry(
    command_modules={
        'app': 'cli.groups.app',
        'db': 'cli.groups.db',
        'ops': 'cli.groups.ops',
        'cache': 'cli.groups.cache',
        'job': 'cli.groups.job',
        'config': 'cli.groups.config',
        'crypto': 'cli.groups.crypto',
        'gen': 'cli.groups.gen',
        'dev': 'cli.groups.dev',
    }
)
DEFAULT_CLI_EXTENSION_REGISTRY = CliExtensionRegistry(
    registrations=(
        CliExtensionRegistration('cli.completion.commands', CliExtensionMountSupport.attach_completion),
        CliExtensionRegistration('cli.wizard.commands', CliExtensionMountSupport.attach_wizard),
        CliExtensionRegistration('cli.tui', CliExtensionMountSupport.attach_tui),
    )
)
DEFAULT_CLI_MODULE_LOADER = CliModuleLoader()
