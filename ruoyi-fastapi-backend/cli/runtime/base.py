import getpass
import os
import sys
from pathlib import Path


class RuntimeEnvironmentService:
    """
    CLI 运行时环境服务。

    该服务集中管理后端根目录解析、Python 解释器定位等稳定运行时能力，
    避免调用方继续依赖零散模块级函数。
    """

    @staticmethod
    def is_backend_project_dir(project_dir: Path) -> bool:
        """
        判断目录是否为后端项目根目录。

        :param project_dir: 待检查目录
        :return: 是否为后端项目根目录
        """
        return (
            (project_dir / 'app.py').exists()
            and (project_dir / 'config' / 'env.py').exists()
            and (project_dir / 'cli').is_dir()
        )

    def get_backend_dir(self) -> str:
        """
        获取后端根目录绝对路径。

        :return: 后端根目录绝对路径
        """
        current_dir = Path.cwd().resolve()
        if self.is_backend_project_dir(current_dir):
            return str(current_dir)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @staticmethod
    def get_python_executable() -> str:
        """
        获取当前 CLI 进程使用的 Python 解释器。

        :return: Python 解释器路径或命令名
        """
        return sys.executable or 'python'


class RuntimeOperatorService:
    """
    CLI 运行时操作者解析服务。

    该服务集中提供当前 CLI 进程的操作者名称解析能力，
    避免各领域运行时对象继续复制相同的 `getpass.getuser()` 回退逻辑。
    """

    @staticmethod
    def resolve_operator() -> str:
        """
        解析当前 CLI 操作者名称。

        :return: 操作者名称
        """
        try:
            return getpass.getuser() or 'ruoyi-cli'
        except Exception:
            return 'ruoyi-cli'


RUNTIME_ENVIRONMENT = RuntimeEnvironmentService()
RUNTIME_OPERATOR = RuntimeOperatorService()
