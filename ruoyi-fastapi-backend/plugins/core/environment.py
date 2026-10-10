import os
from pathlib import Path
from typing import Literal

from config.env import AppConfig
from plugins.core.frontend import (
    PluginFrontendFrameworkResolver,
    resolve_frontend_framework_request,
    resolve_frontend_root,
)

PluginFrontendMode = Literal['dev', 'built']
PluginBackendRuntimeMode = Literal['dev', 'service', 'maintenance']

BACKEND_ROOT_ENV_NAMES = ('RUOYI_PLUGIN_BACKEND_ROOT', 'RUOYI_BACKEND_ROOT')


class PluginRuntimeEnvironmentService:
    """
    插件运行时环境服务。

    为插件运行时提供前后端工程目录、Python 可执行文件和运行模式。
    """

    def __init__(
        self,
        backend_root: Path | str | None = None,
        frontend_root: Path | str | None = None,
        python_executable: str | None = None,
        frontend_framework: str = 'auto',
    ) -> None:
        """
        初始化插件运行时环境服务。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录或统一前端目录
        :param python_executable: Python 可执行文件路径
        :param frontend_framework: 前端框架标识，auto 使用环境变量，未配置时默认 vue3
        :return: None
        """
        self.backend_root = self._resolve_backend_root(backend_root)
        self.frontend_root = resolve_frontend_root(self.backend_root, frontend_root, frontend_framework)
        self.frontend_framework = resolve_frontend_framework_request(self.frontend_root, frontend_framework)
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

    def get_frontend_framework(self, frontend_root: Path | str | None = None) -> str:
        """
        获取指定前端工程的框架标识，保留当前工程的显式选择。

        其他工程按自身目录和依赖解析，不沿用当前工程的框架标识。
        仅在需要前端依赖时解析，避免后端独立运行时要求存在前端文件。

        :param frontend_root: 前端工程根目录，未指定时使用当前工程
        :return: 前端框架标识
        """
        root = Path(os.path.abspath(frontend_root)) if frontend_root is not None else self.frontend_root
        framework = self.frontend_framework if root == self.frontend_root else 'auto'
        return PluginFrontendFrameworkResolver.resolve(root, framework)

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
