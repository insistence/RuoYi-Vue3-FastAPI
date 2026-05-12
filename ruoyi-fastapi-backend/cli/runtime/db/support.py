import os
import subprocess
from typing import Any

from cli.exit_codes import DATABASE_ERROR
from cli.runtime.base import RuntimeEnvironmentService

from .gateway import DatabaseInfrastructureGateway


class DatabaseRevisionSupport:
    """
    数据库迁移版本支持对象。

    该对象负责 Alembic script directory 构建、修订版本规整和
    版本对象序列化，避免主运行时服务继续承载迁移元数据细节。

    :param infrastructure_gateway: 数据库基础设施网关
    :param runtime_environment: 运行时环境服务
    """

    def __init__(
        self,
        infrastructure_gateway: DatabaseInfrastructureGateway,
        runtime_environment: RuntimeEnvironmentService,
    ) -> None:
        """
        初始化数据库迁移版本支持对象。

        :param infrastructure_gateway: 数据库基础设施网关
        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway
        self.runtime_environment = runtime_environment

    def build_alembic_script_directory(self) -> Any:
        """
        基于当前后端目录构建 Alembic 脚本目录对象。

        :return: Alembic 脚本目录对象
        """
        config_class = self.infrastructure_gateway.get_alembic_config_class()
        script_directory_class = self.infrastructure_gateway.get_alembic_script_directory_class()
        config = config_class(os.path.join(self.runtime_environment.get_backend_dir(), 'alembic.ini'))
        return script_directory_class.from_config(config)

    @staticmethod
    def normalize_revision_value(value: Any) -> list[str]:
        """
        规范化 Alembic 修订版本引用值。

        :param value: 原始修订版本引用
        :return: 规范化后的修订版本列表
        """
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    def serialize_revision(self, script_revision: Any) -> dict[str, Any]:
        """
        序列化 Alembic 修订版本对象。

        :param script_revision: Alembic 修订版本对象
        :return: 序列化后的修订版本字典
        """
        return {
            'revision': str(script_revision.revision),
            'downRevisions': self.normalize_revision_value(script_revision.down_revision),
            'branchLabels': sorted(str(item) for item in script_revision.branch_labels or []),
            'dependsOn': self.normalize_revision_value(script_revision.dependencies),
            'doc': (script_revision.doc or '').strip(),
            'path': str(script_revision.path),
        }


class DatabaseAlembicCommandSupport:
    """
    数据库 Alembic 命令支持对象。

    该对象负责 Alembic 命令组装与子进程执行，
    避免主运行时服务继续承载命令行桥接细节。

    :param runtime_environment: 运行时环境服务
    """

    def __init__(self, runtime_environment: RuntimeEnvironmentService) -> None:
        """
        初始化数据库 Alembic 命令支持对象。

        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.runtime_environment = runtime_environment

    def build_alembic_command(self, command: str, *arguments: str) -> list[str]:
        """
        构建 Alembic 命令。

        :param command: Alembic 子命令名称
        :param arguments: Alembic 子命令参数列表
        :return: Alembic 命令参数列表
        """
        alembic_ini_path = os.path.join(self.runtime_environment.get_backend_dir(), 'alembic.ini')
        return ['alembic', '-c', alembic_ini_path, command, *arguments]

    def run_alembic_command(
        self,
        command: str,
        *arguments: str,
        success_message: str,
        failure_message: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        执行 Alembic 命令并返回统一结果。

        :param command: Alembic 子命令名称
        :param arguments: Alembic 子命令参数列表
        :param success_message: 成功提示信息
        :param failure_message: 失败提示信息
        :param dry_run: 是否仅演练执行
        :return: Alembic 执行结果
        """
        command_arguments = self.build_alembic_command(command, *arguments)
        if dry_run:
            return {
                'ok': True,
                'message': f'{success_message}（dry-run）',
                'dryRun': True,
                'command': command_arguments,
                'cwd': self.runtime_environment.get_backend_dir(),
            }

        try:
            completed = subprocess.run(
                command_arguments,
                cwd=self.runtime_environment.get_backend_dir(),
                env={**os.environ, 'APP_ENV': os.environ.get('APP_ENV', 'dev')},
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                return {
                    'ok': False,
                    'message': failure_message,
                    'error': completed.stderr.strip() or completed.stdout.strip(),
                    'exit_code': DATABASE_ERROR,
                }

            payload: dict[str, Any] = {'ok': True, 'message': success_message}
            stdout = completed.stdout.strip()
            if stdout:
                payload['stdout'] = stdout
            return payload
        except Exception as exc:
            return {'ok': False, 'message': failure_message, 'error': str(exc), 'exit_code': DATABASE_ERROR}
