import os
from pathlib import Path
from typing import Literal

from config.env import AppConfig

PluginFrontendMode = Literal['dev', 'built']
PluginBackendRuntimeMode = Literal['dev', 'service']

BACKEND_ROOT_ENV_NAMES = ('RUOYI_PLUGIN_BACKEND_ROOT', 'RUOYI_BACKEND_ROOT')
FRONTEND_ROOT_ENV_NAMES = ('RUOYI_PLUGIN_FRONTEND_ROOT', 'RUOYI_FRONTEND_ROOT')


class PluginRuntimeEnvironmentService:
    """
    插件运行时环境服务。

    为插件运行时提供后端目录和 Python 可执行文件等路径信息。
    """

    def __init__(
        self,
        backend_root: Path | str | None = None,
        frontend_root: Path | str | None = None,
        python_executable: str | None = None,
    ) -> None:
        """
        初始化插件运行时环境服务。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录
        :param python_executable: Python 可执行文件路径
        :return: None
        """
        self.backend_root = self._resolve_backend_root(backend_root)
        self.frontend_root = self._resolve_frontend_root(self.backend_root, frontend_root)
        self.python_executable = python_executable or 'python'
        self.frontend_mode = self._get_frontend_mode()
        self.backend_runtime_mode = self._get_backend_runtime_mode()

    @staticmethod
    def _resolve_backend_root(backend_root: Path | str | None) -> Path:
        """
        解析后端项目根目录。

        :param backend_root: 显式传入的后端项目根目录
        :return: 后端项目根目录
        """
        if backend_root:
            return Path(backend_root).resolve()
        configured_backend_root = PluginRuntimeEnvironmentService._first_env_path(BACKEND_ROOT_ENV_NAMES)
        if configured_backend_root:
            return configured_backend_root.resolve()
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def _resolve_frontend_root(backend_root: Path, frontend_root: Path | str | None) -> Path:
        """
        解析前端项目根目录。

        解析顺序为：显式参数、环境变量、后端同级目录中的前端工程、按后端目录名推断。

        :param backend_root: 后端项目根目录
        :param frontend_root: 显式传入的前端项目根目录
        :return: 前端项目根目录
        """
        if frontend_root:
            return Path(frontend_root).resolve()
        configured_frontend_root = PluginRuntimeEnvironmentService._first_env_path(FRONTEND_ROOT_ENV_NAMES)
        if configured_frontend_root:
            return configured_frontend_root.resolve()
        sibling_frontend_root = PluginRuntimeEnvironmentService._find_sibling_frontend_root(backend_root)
        if sibling_frontend_root:
            return sibling_frontend_root.resolve()
        return backend_root.parent / PluginRuntimeEnvironmentService._infer_frontend_dir_name(backend_root.name)

    @staticmethod
    def _first_env_path(env_names: tuple[str, ...]) -> Path | None:
        """
        读取第一个已配置的目录环境变量。

        :param env_names: 环境变量名称列表
        :return: 已配置目录，未配置时返回 None
        """
        for env_name in env_names:
            value = os.getenv(env_name, '').strip()
            if value:
                return Path(value)
        return None

    @staticmethod
    def _find_sibling_frontend_root(backend_root: Path) -> Path | None:
        """
        从后端同级目录中寻找前端工程。

        :param backend_root: 后端项目根目录
        :return: 前端项目根目录，未找到时返回 None
        """
        parent = backend_root.parent
        if not parent.is_dir():
            return None
        candidates = [
            path
            for path in parent.iterdir()
            if path.is_dir()
            and path != backend_root
            and (path / 'package.json').is_file()
            and (path / 'plugins').is_dir()
        ]
        if not candidates:
            return None
        return sorted(candidates)[0]

    @staticmethod
    def _infer_frontend_dir_name(backend_dir_name: str) -> str:
        """
        根据后端目录名推断前端目录名。

        :param backend_dir_name: 后端目录名
        :return: 推断出的前端目录名
        """
        if 'backend' in backend_dir_name:
            return backend_dir_name.replace('backend', 'frontend', 1)
        return 'frontend'

    @staticmethod
    def _get_frontend_mode() -> PluginFrontendMode:
        """
        根据应用运行环境获取插件前端模式。

        :return: 插件前端模式
        """
        if AppConfig.app_env == 'dev':
            return 'dev'
        return 'built'

    @staticmethod
    def _get_backend_runtime_mode() -> PluginBackendRuntimeMode:
        """
        根据应用运行环境获取插件后端运行模式。

        :return: 插件后端运行模式
        """
        if AppConfig.app_env == 'dev':
            return 'dev'
        return 'service'

    def get_backend_dir(self) -> str:
        """
        获取后端项目根目录。

        :return: 后端项目根目录绝对路径
        """
        return str(self.backend_root)

    def get_backend_plugins_dir(self) -> str:
        """
        获取后端插件根目录。

        :return: 后端插件根目录绝对路径
        """
        return str(self.backend_root / 'plugins')

    def get_frontend_dir(self) -> str:
        """
        获取前端项目根目录。

        :return: 前端项目根目录绝对路径
        """
        return str(self.frontend_root)

    def get_frontend_plugins_dir(self) -> str:
        """
        获取前端插件根目录。

        :return: 前端插件根目录绝对路径
        """
        return str(self.frontend_root / 'plugins')

    def get_python_executable(self) -> str:
        """
        获取 Python 可执行文件。

        :return: Python 可执行文件路径
        """
        return self.python_executable

    def get_frontend_mode(self) -> PluginFrontendMode:
        """
        获取插件前端运行模式。

        :return: 插件前端运行模式
        """
        return self.frontend_mode

    def get_backend_runtime_mode(self) -> PluginBackendRuntimeMode:
        """
        获取插件后端运行模式。

        :return: 插件后端运行模式
        """
        return self.backend_runtime_mode


PLUGIN_RUNTIME_ENVIRONMENT = PluginRuntimeEnvironmentService()
