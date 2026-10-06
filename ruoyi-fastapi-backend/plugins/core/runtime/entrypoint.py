import base64
import hashlib
import importlib.metadata
import importlib.util
import inspect
import platform
import sys
import sysconfig
from dataclasses import dataclass
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from types import ModuleType
from typing import Any

from packaging.tags import parse_tag, sys_tags
from packaging.utils import canonicalize_name
from packaging.version import Version

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.sdk import PluginDefinition, PluginHostContext


@dataclass(frozen=True)
class PluginModuleLocation:
    """
    静态定位结果，不执行包初始化或原生模块代码。

    :param module_name: 插件模块完整名称
    :param path: 模块文件的绝对路径
    :param is_package: 模块是否为 Python 包
    """

    module_name: str
    path: Path
    is_package: bool = False


class PluginEntrypointLoader:
    """
    只加载当前插件目录下的模块，拒绝复用其他版本或其他路径的缓存。
    """

    def __init__(self, plugin: DiscoveredPlugin) -> None:
        """
        初始化显式入口加载器并确认插件使用 v2 清单。

        :param plugin: 待加载的已发现插件
        :return: None
        """
        self.plugin = plugin
        self.backend = plugin.manifest.backend
        if not plugin.manifest.uses_entrypoint:
            raise ValueError('显式入口加载器仅用于 manifestVersion 2')

    @property
    def module_root(self) -> Path:
        """
        获取当前交付类型对应的模块根目录。

        :return: Python 插件目录或原生发行包安装目录的绝对路径
        """
        if self.plugin.manifest.runtime_kind == 'native':
            return self._contained(self.plugin.backend_path / self.backend.native.module_root)
        return self.plugin.backend_path.resolve()

    def _contained(self, path: Path) -> Path:
        """
        解析真实路径并确认其位于当前插件目录内。

        :param path: 待校验的模块或资源路径
        :return: 通过目录边界校验的绝对路径
        """
        resolved = path.resolve()
        if not resolved.is_relative_to(self.plugin.backend_path.resolve()):
            raise ValueError(f'模块或资源路径越过插件根目录：{path}')
        return resolved

    def locate_module(self, module_name: str) -> PluginModuleLocation:
        """
        仅检查磁盘文件，不调用可能执行父包代码的 find_spec。

        :param module_name: 当前插件命名空间内的完整模块名
        :return: 模块文件路径及包类型信息
        """
        prefix = self.backend.module
        if module_name != prefix and not module_name.startswith(f'{prefix}.'):
            raise ValueError(f'入口或回调必须位于当前插件模块：{module_name}')
        parts = module_name.removeprefix(prefix).lstrip('.').split('.') if module_name != prefix else []
        root = self.module_root
        if self.plugin.manifest.runtime_kind == 'native':
            root = self._contained(root / prefix)
        target = root.joinpath(*parts)
        candidates: list[tuple[Path, bool]] = []
        if parts or self.plugin.manifest.runtime_kind == 'native':
            candidates.extend((target.with_name(target.name + suffix), False) for suffix in EXTENSION_SUFFIXES)
            candidates.append((target.with_suffix('.py'), False))
        candidates.append((target / '__init__.py', True))
        for path, is_package in candidates:
            if path.is_file():
                return PluginModuleLocation(module_name, self._contained(path), is_package)
        raise ImportError(f'插件模块不存在：{module_name}')

    def check_entrypoint(self) -> PluginModuleLocation:
        """
        执行静态来源和原生平台校验，不执行入口。

        :return: 通过来源及平台校验的入口模块位置
        """
        module_name = self.backend.entrypoint.split(':', 1)[0]
        location = self.locate_module(module_name)
        if self.plugin.manifest.runtime_kind == 'native':
            if not any(location.path.name.endswith(suffix) for suffix in EXTENSION_SUFFIXES):
                raise ValueError('native entrypoint 必须位于原生 Python 扩展模块')
            self._check_native_distribution(location)
        return location

    def _check_native_distribution(self, location: PluginModuleLocation) -> None:
        """
        校验原生发行包版本、平台标签及入口文件摘要。

        :param location: 已定位的原生入口模块
        :return: None
        """
        if platform.python_implementation() != 'CPython' or sysconfig.get_config_var('Py_GIL_DISABLED'):
            raise ValueError('当前 native 运行时仅支持带 GIL 的 CPython')
        expected = canonicalize_name(self.backend.native.distribution)
        matches = [
            dist
            for dist in importlib.metadata.distributions(path=[str(self.module_root)])
            if canonicalize_name(dist.metadata.get('Name', '')) == expected
        ]
        if len(matches) != 1:
            raise ValueError('native.moduleRoot 必须包含唯一匹配的已安装 wheel 元数据')
        dist = matches[0]
        if Version(dist.version) != Version(self.plugin.manifest.version):
            raise ValueError('原生发行包版本必须与插件版本一致')
        wheel_metadata = dist.read_text('WHEEL') or ''
        tags = set()
        for line in wheel_metadata.splitlines():
            if line.startswith('Tag: '):
                tags.update(parse_tag(line.removeprefix('Tag: ').strip()))
        if not any(tag.abi != 'none' and tag.platform != 'any' for tag in tags.intersection(sys_tags())):
            raise ValueError('原生 wheel 平台、Python 或 ABI 与当前解释器不兼容')
        entries = [entry for entry in dist.files or [] if Path(dist.locate_file(entry)).resolve() == location.path]
        if len(entries) != 1 or entries[0].hash is None or entries[0].hash.mode != 'sha256':
            raise ValueError('原生入口必须包含在发行包 RECORD 中并声明 SHA256')
        digest = hashlib.sha256(location.path.read_bytes()).digest()
        actual = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
        if actual != entries[0].hash.value:
            raise ValueError('原生入口 SHA256 与发行包 RECORD 不一致')

    def import_module(self, module_name: str) -> ModuleType:
        """
        按绑定路径依次加载包和模块，失败时移除本次新增的插件模块。

        :param module_name: 当前插件命名空间内的完整模块名
        :return: 已从绑定路径加载的模块对象
        """
        self.locate_module(module_name)
        before = set(sys.modules)
        try:
            prefix = self.backend.module
            names = [prefix]
            suffix = module_name.removeprefix(prefix).lstrip('.')
            if suffix:
                for part in suffix.split('.'):
                    names.append(f'{names[-1]}.{part}')
            for name in names:
                self._import_one(name)
            return sys.modules[module_name]
        except BaseException:
            for name in set(sys.modules) - before:
                if name == self.backend.module or name.startswith(f'{self.backend.module}.'):
                    failed_module = sys.modules.pop(name, None)
                    parent_name, _, child_name = name.rpartition('.')
                    parent = sys.modules.get(parent_name)
                    if parent is not None and getattr(parent, child_name, None) is failed_module:
                        delattr(parent, child_name)
            raise

    def _import_one(self, module_name: str) -> ModuleType:
        """
        校验模块缓存来源，或从已定位的文件加载单个模块。

        :param module_name: 当前插件命名空间内的完整模块名
        :return: 来源路径一致的模块对象
        """
        location = self.locate_module(module_name)
        cached = sys.modules.get(module_name)
        if cached is not None:
            origin = getattr(cached, '__file__', None)
            if not origin or Path(origin).resolve() != location.path:
                raise ImportError(f'插件模块已从其他路径加载，必须重启进程：{module_name}')
            return cached
        spec = importlib.util.spec_from_file_location(
            module_name,
            location.path,
            submodule_search_locations=[str(location.path.parent)] if location.is_package else None,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f'无法创建插件模块加载器：{module_name}')
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        parent_name, _, child_name = module_name.rpartition('.')
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, module)
        return module

    def load_callable(self, callable_path: str) -> Any:
        """
        v2 回调使用固定参数协议，不依赖原生函数 inspect.signature。

        :param callable_path: 采用模块路径与函数名冒号分隔格式的入口或回调路径
        :return: 通过可调用性校验的入口或回调对象
        """
        module_name, callable_name = callable_path.split(':', 1)
        module = self.import_module(module_name)
        callback = getattr(module, callable_name, None)
        if not callable(callback):
            raise TypeError(f'插件入口或回调不可调用：{callable_path}')
        return callback

    def load(self, host: PluginHostContext) -> PluginDefinition:
        """
        加载入口并验证能力对象；工厂必须同步、快速且无资源副作用。

        :param host: 与当前插件身份及资源目录绑定的宿主上下文
        :return: 通过协议校验的插件能力定义
        """
        self.check_entrypoint()
        if host.plugin_id != self.plugin.manifest.id or host.resource_root != self.plugin.backend_path.resolve():
            raise ValueError('HostContext 与待加载插件不匹配')
        factory = self.load_callable(self.backend.entrypoint)
        definition = factory(host)
        if inspect.isawaitable(definition):
            if inspect.iscoroutine(definition):
                definition.close()
            raise TypeError('插件入口工厂必须同步返回 PluginDefinition，资源初始化请使用生命周期')
        if not isinstance(definition, PluginDefinition):
            raise TypeError('插件入口必须返回 PluginDefinition')
        definition.validate(self.plugin.manifest.integration_kind)
        return definition
