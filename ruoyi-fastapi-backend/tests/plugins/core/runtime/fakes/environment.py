import sys
from pathlib import Path

from plugins.core.environment import PluginRuntimeEnvironmentService


class FakeRuntimeEnvironment:
    """
    测试用运行时环境服务。
    """

    def __init__(self, backend_dir: Path, frontend_dir: Path | None = None) -> None:
        """初始化测试用运行时环境服务。"""
        self.backend_dir = backend_dir
        self.frontend_dir = frontend_dir or Path(
            PluginRuntimeEnvironmentService(backend_root=backend_dir).get_frontend_dir()
        )
        self.frontend_mode = 'dev'
        self.backend_runtime_mode = 'dev'

    def get_backend_dir(self) -> str:
        """获取后端项目根目录。"""
        return str(self.backend_dir)

    def get_backend_plugins_dir(self) -> str:
        """获取后端插件根目录。"""
        return str(self.backend_dir / 'plugins')

    def get_frontend_dir(self) -> str:
        """获取前端项目根目录。"""
        return str(self.frontend_dir)

    def get_frontend_plugins_dir(self) -> str:
        """获取前端插件根目录。"""
        return str(self.frontend_dir / 'plugins')

    @staticmethod
    def get_python_executable() -> str:
        """获取测试用 Python 解释器。"""
        return sys.executable

    def get_frontend_mode(self) -> str:
        """获取测试用前端模式。"""
        return self.frontend_mode

    def get_backend_runtime_mode(self) -> str:
        """获取测试用后端运行模式。"""
        return self.backend_runtime_mode
