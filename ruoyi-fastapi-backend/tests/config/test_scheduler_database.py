from unittest.mock import MagicMock

import pytest

from config.env import DataBaseConfig
from config.get_scheduler import SchedulerUtil


def test_scheduler_database_engines_keep_jobstore_logging_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    jobstore_engine = MagicMock()
    listener_engine = MagicMock()
    create_engine = MagicMock(return_value=jobstore_engine)

    monkeypatch.setattr(SchedulerUtil, '_jobstore_engine', None)
    monkeypatch.setattr(SchedulerUtil, '_listener_engine', None)
    monkeypatch.setattr(SchedulerUtil, '_session_local', None)
    monkeypatch.setattr(SchedulerUtil, '_disposed_sync_engines', False)
    monkeypatch.setattr('config.get_scheduler.create_sync_db_engine', create_engine)
    monkeypatch.setattr('config.get_scheduler.DataSourceRegistry.get_sync_engine', lambda _name: listener_engine)

    assert SchedulerUtil._get_jobstore_engine() is jobstore_engine
    assert SchedulerUtil._get_listener_engine() is listener_engine
    assert jobstore_engine is not listener_engine
    create_engine.assert_called_once_with(echo=False, config=DataBaseConfig.get_source())


def test_scheduler_cleanup_does_not_dispose_registry_listener_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    jobstore_engine = MagicMock()
    listener_engine = MagicMock()
    monkeypatch.setattr(SchedulerUtil, '_jobstore_engine', jobstore_engine)
    monkeypatch.setattr(SchedulerUtil, '_listener_engine', listener_engine)
    monkeypatch.setattr(SchedulerUtil, '_session_local', MagicMock())
    monkeypatch.setattr(SchedulerUtil, '_disposed_sync_engines', False)

    SchedulerUtil._dispose_sync_engines()

    jobstore_engine.dispose.assert_called_once_with()
    listener_engine.dispose.assert_not_called()
    assert SchedulerUtil._jobstore_engine is None
    assert SchedulerUtil._listener_engine is None
