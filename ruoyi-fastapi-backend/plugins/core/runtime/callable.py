import importlib
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from plugins.core.discovery.scanner import DiscoveredPlugin


@dataclass(frozen=True)
class LoadedPluginCallable:
    """
    已加载的插件 callable。

    :param module_name: 完整 Python 模块名
    :param callable_name: callable 名称
    :param callable_object: callable 对象
    """

    module_name: str
    callable_name: str
    callable_object: Callable[..., object]


class PluginCallableLoader:
    """
    插件 callable 加载器。

    使用 Loader 模式统一插件生命周期钩子、健康检查等 manifest callable 的模块边界校验、
    本地文件加载和 Python import fallback。
    """

    def __init__(self, discovered_plugin: DiscoveredPlugin, *, label: str) -> None:
        """
        初始化插件 callable 加载器。

        :param discovered_plugin: 已发现插件对象
        :param label: callable 类型标签，用于错误信息
        :return: None
        """
        self.discovered_plugin = discovered_plugin
        self.label = label

    def load(self, callable_path: str) -> LoadedPluginCallable:
        """
        加载插件 callable。

        :param callable_path: manifest 中声明的 callable 路径，格式为 <module_path>:<callable_name>
        :return: 已加载 callable
        """
        module_path, callable_name = callable_path.split(':', maxsplit=1)
        module_name = self.resolve_module_name(module_path)
        module = self.import_module(module_name)
        callable_object = getattr(module, callable_name, None)
        if not callable(callable_object):
            raise RuntimeError(f'插件 {self.label} 不存在或不可调用：{callable_path}')

        return LoadedPluginCallable(
            module_name=module_name,
            callable_name=callable_name,
            callable_object=callable_object,
        )

    def resolve_module_name(self, module_path: str) -> str:
        """
        解析插件 callable 模块名。

        :param module_path: manifest 中声明的模块路径
        :return: 完整 Python 模块名
        """
        plugin_module = self.discovered_plugin.manifest.backend.module
        if module_path == plugin_module or module_path.startswith(f'{plugin_module}.'):
            return module_path
        if module_path.startswith('plugins.'):
            raise RuntimeError(f'{self.label} 只能指向当前插件模块：{module_path}')

        return f'{plugin_module}.{module_path}'

    def import_module(self, module_name: str) -> ModuleType:
        """
        导入插件 callable 模块。

        :param module_name: 完整 Python 模块名
        :return: Python 模块对象
        """
        module_file = self.resolve_module_file(module_name)
        if module_file:
            return self.load_module_from_file(module_name, module_file)

        backend_root = self.resolve_backend_root()
        backend_root_text = str(backend_root)
        path_inserted = backend_root_text not in sys.path
        if path_inserted:
            sys.path.insert(0, backend_root_text)
        try:
            return importlib.import_module(module_name)
        finally:
            if path_inserted:
                sys.path.remove(backend_root_text)

    def resolve_module_file(self, module_name: str) -> Path | None:
        """
        解析当前插件 callable 模块文件。

        :param module_name: 完整 Python 模块名
        :return: 模块文件路径
        """
        plugin_module = self.discovered_plugin.manifest.backend.module
        if module_name != plugin_module and not module_name.startswith(f'{plugin_module}.'):
            return None

        relative_module = module_name.removeprefix(plugin_module).lstrip('.')
        if not relative_module:
            module_file = self.discovered_plugin.backend_path / '__init__.py'
        else:
            module_file = self.discovered_plugin.backend_path.joinpath(*relative_module.split('.')).with_suffix('.py')

        return module_file if module_file.is_file() else None

    @staticmethod
    def load_module_from_file(module_name: str, module_file: Path) -> ModuleType:
        """
        从文件加载插件 callable 模块。

        :param module_name: 完整 Python 模块名
        :param module_file: 模块文件路径
        :return: Python 模块对象
        """
        module_spec = importlib.util.spec_from_file_location(module_name, module_file)
        if module_spec is None or module_spec.loader is None:
            raise RuntimeError(f'插件 callable 模块加载失败：{module_file}')
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)

        return module

    def resolve_backend_root(self) -> Path:
        """
        解析后端工程根目录。

        :return: 后端工程根目录
        """
        return self.discovered_plugin.backend_path.resolve().parents[1]
