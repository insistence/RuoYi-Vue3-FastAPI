from datetime import date, datetime, time, timedelta, timezone

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.engine import Dialect

from common.types import ApiUtcDateTime, BusinessDate, BusinessTime, DbUtcDateTime


class TimestampModel(BaseModel):
    occurred_at: ApiUtcDateTime


class TestApiUtcDateTime:
    """API时刻类型的校验和序列化。"""

    @pytest.mark.parametrize(
        'value',
        [
            datetime(2026, 8, 28, 10, 30, 0, 123456, tzinfo=timezone(timedelta(hours=8))),
            '2026-08-28T10:30:00.123456+08:00',
            '2026-08-28t02:30:00.123456z',
        ],
    )
    def test_aware_inputs_keep_the_same_instant(self, value: object) -> None:
        model = TimestampModel(occurred_at=value)

        assert model.occurred_at == datetime(2026, 8, 28, 2, 30, 0, 123000, tzinfo=timezone.utc)
        assert model.occurred_at.tzinfo is timezone.utc
        assert model.model_dump(mode='json')['occurred_at'] == '2026-08-28T02:30:00.123Z'
        assert model.model_dump_json() == '{"occurred_at":"2026-08-28T02:30:00.123Z"}'

    @pytest.mark.parametrize(
        'value',
        [
            '2026-08-28T10:30:00',
            1_777_000_000,
            '1777000000',
            '2026-02-30T10:00:00Z',
            '2026-08-28 10:00:00Z',
            '20260828T10:00:00Z',
            '2026-08-28T10:00:00+0800',
            '2026-08-28T10:00:00+08:99',
            '2026-08-28T25:00:00Z',
        ],
    )
    def test_datetime_requires_a_complete_valid_rfc3339_instant(self, value: object) -> None:
        with pytest.raises(ValidationError, match='RFC 3339'):
            TimestampModel(occurred_at=value)


class TestDbUtcDateTime:
    """数据库时刻类型的读写和精度。"""

    @pytest.mark.parametrize('dialect', [mysql.dialect(), postgresql.dialect(), sqlite.dialect()])
    def test_null_values_round_trip(self, dialect: Dialect) -> None:
        column_type = DbUtcDateTime()

        assert column_type.process_bind_param(None, dialect) is None
        assert column_type.process_result_value(None, dialect) is None

    @pytest.mark.parametrize(
        ('dialect', 'expected'),
        [
            (mysql.dialect(), 'DATETIME(3)'),
            (postgresql.dialect(), 'TIMESTAMP(3) WITH TIME ZONE'),
            (sqlite.dialect(), 'DATETIME'),
        ],
    )
    def test_column_uses_the_database_time_representation(self, dialect: Dialect, expected: str) -> None:
        assert DbUtcDateTime().compile(dialect=dialect) == expected

    @pytest.mark.parametrize(
        ('dialect', 'stored_timezone'),
        [(mysql.dialect(), None), (postgresql.dialect(), timezone.utc), (sqlite.dialect(), None)],
    )
    def test_database_roundtrip_preserves_utc_and_millisecond_precision(
        self, dialect: Dialect, stored_timezone: timezone | None
    ) -> None:
        column_type = DbUtcDateTime()
        value = datetime(2026, 8, 28, 10, 30, 0, 123456, tzinfo=timezone(timedelta(hours=8)))
        stored = column_type.process_bind_param(value, dialect)

        assert stored == datetime(2026, 8, 28, 2, 30, 0, 123000, tzinfo=stored_timezone)
        assert stored.tzinfo is stored_timezone
        restored = column_type.process_result_value(stored, dialect)
        assert restored == datetime(2026, 8, 28, 2, 30, 0, 123000, tzinfo=timezone.utc)
        assert restored.tzinfo is timezone.utc

    def test_rejects_naive_values(self) -> None:
        with pytest.raises(ValueError, match='只接受携带时区信息'):
            DbUtcDateTime().process_bind_param(datetime(2026, 8, 28, 10, 30), sqlite.dialect())


class TestBusinessDate:
    """纯日期保持日历语义，不转换为真实时刻。"""

    @pytest.mark.parametrize('value', ['2000-02-29', date(2000, 2, 29)])
    def test_valid_date_keeps_its_calendar_value(self, value: object) -> None:
        adapter = TypeAdapter(BusinessDate)
        result = adapter.validate_python(value)

        assert type(result) is date
        assert result == date(2000, 2, 29)
        assert adapter.dump_json(result) == b'"2000-02-29"'

    @pytest.mark.parametrize(
        'value',
        [
            '2026-02-29',
            '20000229',
            '2000-02-29T00:00:00Z',
            datetime(2000, 2, 29, tzinfo=timezone.utc),
            951782400,
        ],
    )
    def test_invalid_dates_and_instants_are_rejected(self, value: object) -> None:
        with pytest.raises(ValidationError, match='YYYY-MM-DD'):
            TypeAdapter(BusinessDate).validate_python(value)


class TestBusinessTime:
    """一天内时间保留小数秒，并拒绝时区和持续时长。"""

    @pytest.mark.parametrize('value', ['09:15:00.123456', time(9, 15, 0, 123456)])
    def test_valid_time_keeps_fractional_seconds(self, value: object) -> None:
        adapter = TypeAdapter(BusinessTime)
        result = adapter.validate_python(value)

        assert result == time(9, 15, 0, 123456)
        assert result.tzinfo is None
        assert adapter.dump_json(result) == b'"09:15:00.123456"'

    @pytest.mark.parametrize(
        'value', ['09:15', '24:00:00', '36:00:00', '09:15:00Z', time(9, tzinfo=timezone.utc), 3600]
    )
    def test_incomplete_times_offsets_and_durations_are_rejected(self, value: object) -> None:
        with pytest.raises(ValidationError, match='一天内时间'):
            TypeAdapter(BusinessTime).validate_python(value)
