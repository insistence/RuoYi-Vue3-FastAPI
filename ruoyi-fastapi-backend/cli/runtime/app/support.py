import os
from pathlib import Path
from typing import Any

from cli.runtime.base import RuntimeEnvironmentService

from .gateway import AppInfrastructureGateway


class AppSnapshotSupport:
    """
    应用快照支持对象。

    该对象负责应用配置快照和环境快照的构建，
    避免主运行时服务继续承载快照字段拼装细节。

    :param infrastructure_gateway: 应用基础设施网关
    :param runtime_environment: 运行时环境服务
    """

    def __init__(
        self,
        infrastructure_gateway: AppInfrastructureGateway,
        runtime_environment: RuntimeEnvironmentService,
    ) -> None:
        """
        初始化应用快照支持对象。

        :param infrastructure_gateway: 应用基础设施网关
        :param runtime_environment: 运行时环境服务
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway
        self.runtime_environment = runtime_environment

    def build_app_config_snapshot(self) -> dict[str, Any]:
        """
        读取当前运行环境的应用配置快照。

        :return: 应用配置快照
        """
        env_module = self.infrastructure_gateway.get_env_module()
        app_config = env_module.AppConfig
        database_config = env_module.DataBaseConfig
        log_config = env_module.LogConfig
        redis_config = env_module.RedisConfig
        transport_crypto_config = env_module.TransportCryptoConfig
        return {
            'env': app_config.app_env,
            'name': app_config.app_name,
            'host': app_config.app_host,
            'port': app_config.app_port,
            'rootPath': app_config.app_root_path,
            'reload': app_config.app_reload,
            'workers': app_config.app_workers,
            'disableSwagger': app_config.app_disable_swagger,
            'disableRedoc': app_config.app_disable_redoc,
            'dbType': database_config.db_type,
            'dbHost': database_config.db_host,
            'dbPort': database_config.db_port,
            'dbDatabase': database_config.db_database,
            'redisHost': redis_config.redis_host,
            'redisPort': redis_config.redis_port,
            'logLevel': log_config.loguru_level,
            'transportCryptoEnabled': transport_crypto_config.transport_crypto_enabled,
            'transportCryptoMode': transport_crypto_config.transport_crypto_mode,
        }

    def build_app_env_snapshot(self) -> dict[str, Any]:
        """
        读取当前 CLI 进程的环境解析结果快照。

        :return: 环境解析结果快照
        """
        env_module = self.infrastructure_gateway.get_env_module()
        app_config = env_module.AppConfig
        backend_dir = Path(self.runtime_environment.get_backend_dir())
        resolved_env = os.environ.get('APP_ENV', '') or 'dev'
        env_file_name = f'.env.{resolved_env}'
        env_file_path = backend_dir / env_file_name
        return {
            'cliEnv': resolved_env,
            'configEnv': app_config.app_env,
            'appEnv': os.environ.get('APP_ENV', ''),
            'envFile': env_file_name,
            'envFilePath': str(env_file_path),
            'envFileExists': env_file_path.exists(),
            'backendDir': str(backend_dir),
            'pythonExecutable': self.runtime_environment.get_python_executable(),
        }
