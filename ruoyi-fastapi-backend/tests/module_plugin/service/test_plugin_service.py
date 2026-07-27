from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import module_plugin.service.plugin_service as plugin_service_module
from config.database import Base
from module_plugin.service.plugin_service import (
    PluginOperationService,
    get_plugin_operation_service,
    get_plugin_runtime_service,
)
from plugins.core.management.entity.do.models import SysPluginOperationLog
from plugins.core.management.service.service import PluginService


def test_get_plugin_operation_service_reuses_singleton() -> None:
    """校验 Web 侧插件操作服务懒加载后复用同一实例。"""
    plugin_service_module._PLUGIN_OPERATION_SERVICE_CACHE.clear()
    first_service = get_plugin_operation_service()
    second_service = get_plugin_operation_service()

    assert first_service is second_service


def test_get_plugin_runtime_service_reuses_singleton() -> None:
    """校验 Web 侧插件运行时服务懒加载后复用同一实例。"""
    plugin_service_module._PLUGIN_RUNTIME_SERVICE_CACHE.clear()
    first_service = get_plugin_runtime_service()
    second_service = get_plugin_runtime_service()

    assert first_service is second_service


@pytest.mark.asyncio
async def test_plugin_diagnose_with_audit_filters_recent_logs(tmp_path: Path) -> None:
    """校验插件诊断包会返回目标插件最近审计记录。"""
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
                    """返回测试用插件诊断结果。"""
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
