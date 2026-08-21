from datetime import datetime

from plugins.core.management.dao.dao import PluginDao
from plugins.core.management.entity.do.models import SysPluginMigration
from plugins.core.management.entity.vo.schemas import PluginMigrationModel, PluginModel


def test_plugin_persistence_payload_ignores_client_audit_times() -> None:
    now = datetime(2026, 8, 21, 12, 0, 0)
    payload = PluginDao.dump_plugin_persistence_payload(
        PluginModel(
            pluginId='demo',
            pluginName='Demo',
            version='1.0.0',
            createTime=now,
            updateTime=now,
        )
    )

    assert 'create_time' not in payload
    assert 'update_time' not in payload


def test_existing_migration_update_uses_onupdate_not_external_time() -> None:
    now = datetime(2026, 8, 21, 12, 0, 0)
    payload = PluginMigrationModel(
        pluginId='demo',
        migrationPath='migrations/001.sql',
        migrationChecksum='checksum',
        updateTime=datetime(2000, 1, 1),
    ).model_dump(exclude_unset=True)

    PluginDao._apply_migration_observability_payload(payload, SysPluginMigration(), now)

    assert 'update_time' not in payload
