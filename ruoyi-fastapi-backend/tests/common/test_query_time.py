from datetime import datetime, timezone
from typing import Annotated

import pytest
from fastapi import FastAPI, Query, status
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Select

from module_admin.dao.config_dao import ConfigDao
from module_admin.entity.vo.config_vo import ConfigPageQueryModel
from module_admin.entity.vo.file_vo import FileInfoQueryModel
from module_admin.entity.vo.job_vo import JobModel
from plugins.core.manifest.schema import PluginJobManifest
from utils.page_util import PageUtil
from utils.time_util import TimezoneUtil


@pytest.mark.parametrize('zone', ['', 'Invalid/Zone', '/etc/localtime', '../UTC', 'UTC+08:00'])
def test_invalid_timezone_is_a_model_validation_error(zone: str) -> None:
    with pytest.raises(ValidationError, match='IANA'):
        JobModel(timeZone=zone)
    with pytest.raises(ValidationError, match='IANA'):
        PluginJobManifest(
            id='daily', callable='module_task.scheduler_test.job', cronExpression='0 0 9 * * ?', timeZone=zone
        )


def test_http_boundaries_return_validation_errors() -> None:
    app = FastAPI()

    @app.get('/query')
    def date_query(query: Annotated[ConfigPageQueryModel, Query()]) -> dict:
        return query.model_dump()

    with TestClient(app, raise_server_exceptions=False) as client:
        assert (
            client.get('/query', params={'beginTime': '2026-02-30'}).status_code
            == status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        assert (
            client.get('/query', params={'beginTime': '2026-08-29', 'endTime': '2026-08-28'}).status_code
            == status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        assert client.get('/query', params={'endTime': '2026-08-28'}).status_code == status.HTTP_200_OK


def test_instant_query_compares_instants_instead_of_offset_strings() -> None:
    query = FileInfoQueryModel(beginTime='2026-08-28T10:00:00+08:00', endTime='2026-08-28T03:00:00Z')
    assert TimezoneUtil.rfc3339_range_to_utc(query.begin_time, query.end_time) == (
        datetime(2026, 8, 28, 2, tzinfo=timezone.utc),
        datetime(2026, 8, 28, 3, tzinfo=timezone.utc),
    )
    with pytest.raises(ValidationError):
        FileInfoQueryModel(beginTime='2026-08-28T03:00:00Z', endTime='2026-08-28T10:00:00+08:00')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('boundaries', 'expected_times'),
    [
        ({'beginTime': '2026-08-28'}, [datetime(2026, 8, 27, 16, tzinfo=timezone.utc)]),
        ({'endTime': '2026-08-28'}, [datetime(2026, 8, 28, 16, tzinfo=timezone.utc)]),
        ({}, []),
    ],
    ids=['lower-only', 'upper-only', 'unbounded'],
)
async def test_date_query_filters_only_provided_boundaries_in_business_timezone(
    monkeypatch: pytest.MonkeyPatch, boundaries: dict[str, str], expected_times: list[datetime]
) -> None:
    async def capture_query(_db: object, query: Select, *args: object) -> Select:
        return query

    monkeypatch.setattr(PageUtil, 'paginate', capture_query)
    monkeypatch.setattr(TimezoneUtil, 'get_request_timezone', lambda: 'Asia/Shanghai')
    query = await ConfigDao.get_config_list(None, ConfigPageQueryModel(**boundaries))
    sql = str(query)
    assert ('sys_config.create_time >=' in sql) == ('beginTime' in boundaries)
    assert ('sys_config.create_time <' in sql) == ('endTime' in boundaries)
    assert [value for value in query.compile().params.values() if isinstance(value, datetime)] == expected_times
