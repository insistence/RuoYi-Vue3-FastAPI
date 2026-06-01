import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from config.database import Base  # noqa: E402
from module_plugin.service.plugin_service import PluginOperationService  # noqa: E402
from plugins.core.management.entity.do.models import SysPluginOperationLog  # noqa: E402
from plugins.core.management.service.service import PluginService  # noqa: E402


@pytest.mark.asyncio
async def test_plugin_operation_service_delegates_install_with_dry_run() -> None:
    """
    校验插件操作服务会透传安装预演参数。

    :return: None
    """

    class FakeRuntimeService:
        """
        测试用插件运行时服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件运行时服务。

            :return: None
            """
            self.called_with = None

        async def install_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, object]:
            """
            记录插件安装调用参数。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :return: 插件安装结果
            """
            self.called_with = (plugin_id, dry_run)
            return {'ok': True, 'pluginId': plugin_id, 'dryRun': dry_run}

    fake_runtime_service = FakeRuntimeService()
    operation_service = PluginOperationService(runtime_service=fake_runtime_service)

    result = await operation_service.install_plugin_services('demo', dry_run=True)

    assert result['ok'] is True
    assert fake_runtime_service.called_with == ('demo', True)


@pytest.mark.asyncio
async def test_plugin_operation_service_delegates_upgrade_with_dry_run() -> None:
    """
    校验插件操作服务会透传升级预演参数。

    :return: None
    """

    class FakeRuntimeService:
        """
        测试用插件运行时服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件运行时服务。

            :return: None
            """
            self.called_with = None

        async def upgrade_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, object]:
            """
            记录插件升级调用参数。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :return: 插件升级结果
            """
            self.called_with = (plugin_id, dry_run)
            return {'ok': True, 'pluginId': plugin_id, 'dryRun': dry_run}

    fake_runtime_service = FakeRuntimeService()
    operation_service = PluginOperationService(runtime_service=fake_runtime_service)

    result = await operation_service.upgrade_plugin_services('demo', dry_run=True)

    assert result['ok'] is True
    assert fake_runtime_service.called_with == ('demo', True)


@pytest.mark.asyncio
async def test_plugin_operation_service_delegates_uninstall_with_dry_run() -> None:
    """
    校验插件操作服务会透传安全卸载预演参数。

    :return: None
    """

    class FakeRuntimeService:
        """
        测试用插件运行时服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件运行时服务。

            :return: None
            """
            self.called_with = None

        async def uninstall_plugin(self, plugin_id: str, *, dry_run: bool = False) -> dict[str, object]:
            """
            记录插件安全卸载调用参数。

            :param plugin_id: 插件ID
            :param dry_run: 是否仅预演
            :return: 插件安全卸载结果
            """
            self.called_with = (plugin_id, dry_run)
            return {'ok': True, 'pluginId': plugin_id, 'dryRun': dry_run}

    fake_runtime_service = FakeRuntimeService()
    operation_service = PluginOperationService(runtime_service=fake_runtime_service)

    result = await operation_service.uninstall_plugin_services('demo', dry_run=True)

    assert result['ok'] is True
    assert fake_runtime_service.called_with == ('demo', True)


@pytest.mark.asyncio
async def test_plugin_operation_service_delegates_check() -> None:
    """
    校验插件操作服务会透传检查调用。

    :return: None
    """

    class FakeRuntimeService:
        """
        测试用插件运行时服务。
        """

        def __init__(self) -> None:
            """
            初始化测试用插件运行时服务。

            :return: None
            """
            self.called_with = None

        def check_plugin(self, plugin_id: str) -> dict[str, object]:
            """
            记录插件检查调用参数。

            :param plugin_id: 插件ID
            :return: 插件检查结果
            """
            self.called_with = plugin_id
            return {'ok': True, 'pluginId': plugin_id}

    fake_runtime_service = FakeRuntimeService()
    operation_service = PluginOperationService(runtime_service=fake_runtime_service)

    result = await operation_service.check_plugin_services('demo')

    assert result['ok'] is True
    assert fake_runtime_service.called_with == 'demo'


@pytest.mark.asyncio
async def test_plugin_diagnose_with_audit_filters_recent_logs(tmp_path: Path) -> None:
    """
    校验插件诊断包会返回目标插件最近审计记录。

    :param tmp_path: pytest 临时目录
    :return: None
    """
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SysPluginOperationLog.__table__])

    try:
        async with session_maker() as session:
            await PluginService.add_plugin_operation_log_services(
                session,
                {
                    'ok': True,
                    'operation': 'install',
                    'message': 'demo installed',
                    'pluginId': 'demo',
                    'summary': {'total': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0},
                },
                dry_run=False,
                continue_on_error=False,
            )
            await PluginService.add_plugin_operation_log_services(
                session,
                {
                    'ok': True,
                    'operation': 'install',
                    'message': 'other installed',
                    'pluginId': 'other',
                    'summary': {'total': 1, 'succeeded': 1, 'failed': 0, 'skipped': 0},
                },
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()

            class FakeRuntimeService:
                """
                测试用插件运行时服务。
                """

                async def diagnose_plugin(self, plugin_id: str) -> dict[str, object]:
                    """
                    生成测试用插件诊断包。

                    :param plugin_id: 插件ID
                    :return: 插件诊断包
                    """
                    return {
                        'ok': True,
                        'message': '插件诊断包生成完成',
                        'pluginId': plugin_id,
                        'audit': {'available': False, 'items': []},
                    }

            payload = await PluginOperationService(
                runtime_service=FakeRuntimeService()
            ).diagnose_plugin_with_audit_services(session, 'demo')

        assert payload['audit']['available'] is True
        assert payload['audit']['count'] == 1
        assert payload['audit']['items'][0]['pluginIds'] == ['demo']
        assert payload['audit']['items'][0]['operation'] == 'install'
    finally:
        await engine.dispose()
