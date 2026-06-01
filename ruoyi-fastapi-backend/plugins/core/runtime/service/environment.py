from pathlib import Path
from typing import Literal

from config.env import AppConfig

PluginFrontendMode = Literal['dev', 'built']
PluginBackendRuntimeMode = Literal['dev', 'service']


class PluginRuntimeEnvironmentService:
    """
    插件运行时环境服务。

    为插件运行时提供后端目录和 Python 可执行文件等路径信息。
    """

    def __init__(
        self,
        backend_root: Path | None = None,
        python_executable: str | None = None,
    ) -> None:
        """
        初始化插件运行时环境服务。

        :param backend_root: 后端项目根目录
        :param python_executable: Python 可执行文件路径
        :return: None
        """
        self.backend_root = backend_root or Path(__file__).parents[4]
        self.python_executable = python_executable or 'python'
        self.frontend_mode = self._get_frontend_mode()
        self.backend_runtime_mode = self._get_backend_runtime_mode()

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
