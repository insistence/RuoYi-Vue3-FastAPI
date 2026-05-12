from types import SimpleNamespace

from pytest import MonkeyPatch

from cli.runtime.app import AppRuntimeService
from cli.runtime.app.gateway import AppInfrastructureGateway
from cli.runtime.app.support import AppSnapshotSupport
from cli.runtime.base import RuntimeEnvironmentService

REDIS_PORT = 6379


class FakeRuntimeEnvironment(RuntimeEnvironmentService):
    """
    模拟运行时环境服务。
    """

    @staticmethod
    def get_backend_dir() -> str:
        """
        返回固定后端目录。

        :return: 固定目录
        """
        return '/tmp/ruoyi-backend'

    @staticmethod
    def get_python_executable() -> str:
        """
        返回固定 Python 可执行文件。

        :return: Python 可执行文件路径
        """
        return '/usr/bin/python3'


def test_app_snapshot_support_builds_config_snapshot() -> None:
    """
    校验应用快照支持对象会构建应用配置快照。

    :return: None
    """
    gateway = AppInfrastructureGateway()
    support = AppSnapshotSupport(gateway, FakeRuntimeEnvironment())

    fake_env_module = SimpleNamespace(
        AppConfig=SimpleNamespace(
            app_env='dev',
            app_name='ruoyi',
            app_host='127.0.0.1',
            app_port=8080,
            app_root_path='/api',
            app_reload=True,
            app_workers=1,
            app_disable_swagger=False,
            app_disable_redoc=False,
        ),
        DataBaseConfig=SimpleNamespace(
            db_type='mysql',
            db_host='127.0.0.1',
            db_port=3306,
            db_database='ruoyi',
        ),
        RedisConfig=SimpleNamespace(redis_host='127.0.0.1', redis_port=REDIS_PORT),
        LogConfig=SimpleNamespace(loguru_level='INFO'),
        TransportCryptoConfig=SimpleNamespace(
            transport_crypto_enabled=True,
            transport_crypto_mode='strict',
        ),
    )

    def _fake_get_env_module() -> SimpleNamespace:
        return fake_env_module

    object.__setattr__(gateway, 'get_env_module', _fake_get_env_module)

    payload = support.build_app_config_snapshot()

    assert payload['env'] == 'dev'
    assert payload['dbType'] == 'mysql'
    assert payload['redisPort'] == REDIS_PORT
    assert payload['transportCryptoMode'] == 'strict'


def test_app_snapshot_support_builds_env_snapshot(monkeypatch: MonkeyPatch) -> None:
    """
    校验应用快照支持对象会构建环境解析快照。

    :param monkeypatch: pytest monkeypatch 工具
    :return: None
    """
    gateway = AppInfrastructureGateway()
    support = AppSnapshotSupport(gateway, FakeRuntimeEnvironment())
    fake_env_module = SimpleNamespace(
        AppConfig=SimpleNamespace(app_env='prod'),
    )

    def _fake_get_env_module() -> SimpleNamespace:
        return fake_env_module

    object.__setattr__(gateway, 'get_env_module', _fake_get_env_module)
    monkeypatch.setenv('APP_ENV', 'test')

    payload = support.build_app_env_snapshot()

    assert payload == {
        'cliEnv': 'test',
        'configEnv': 'prod',
        'appEnv': 'test',
        'envFile': '.env.test',
        'envFilePath': '/tmp/ruoyi-backend/.env.test',
        'envFileExists': False,
        'backendDir': '/tmp/ruoyi-backend',
        'pythonExecutable': '/usr/bin/python3',
    }


def test_app_runtime_service_builds_app_instance() -> None:
    """
    校验应用运行时 facade 会通过基础设施网关构建应用实例。

    :return: None
    """
    gateway = AppInfrastructureGateway()
    service = AppRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(),
        infrastructure_gateway=gateway,
    )

    class FakeServerModule:
        """
        模拟 server 模块。
        """

        @staticmethod
        def create_app() -> dict[str, str]:
            """
            返回模拟应用实例。

            :return: 模拟应用实例
            """
            return {'app': 'ok'}

    def _fake_get_server_module() -> FakeServerModule:
        return FakeServerModule()

    object.__setattr__(gateway, 'get_server_module', _fake_get_server_module)

    payload = service.build_app_instance()

    assert payload == {'app': 'ok'}
