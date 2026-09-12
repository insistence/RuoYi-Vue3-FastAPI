from datetime import date, datetime, timezone

import pytest

from exceptions.exception import ServiceWarning
from utils.time_util import GenTimeUtil, TimezoneUtil


def test_utc_now_returns_aware_utc_datetime() -> None:
    now = TimezoneUtil.utc_now()

    assert now.tzinfo is timezone.utc
    assert now.utcoffset().total_seconds() == 0


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match='必须携带时区信息'):
        TimezoneUtil.ensure_aware(datetime(2026, 8, 28, 10, 0, 0))


def test_datetime_is_normalized_to_utc_and_business_timezone() -> None:
    shanghai_time = datetime.fromisoformat('2026-08-28T10:30:00+08:00')

    assert TimezoneUtil.to_utc(shanghai_time) == datetime(2026, 8, 28, 2, 30, tzinfo=timezone.utc)
    assert TimezoneUtil.to_business_time(TimezoneUtil.to_utc(shanghai_time), 'Asia/Shanghai') == shanghai_time


def test_to_utc_milliseconds_truncates_sub_millisecond_precision() -> None:
    value = datetime.fromisoformat('2026-08-28T10:30:00.123999+08:00')

    assert TimezoneUtil.to_utc_milliseconds(value) == datetime(2026, 8, 28, 2, 30, 0, 123000, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ('day', 'zone', 'expected_start', 'expected_end'),
    [
        (date(2026, 8, 28), 'Asia/Shanghai', '2026-08-27T16:00:00+00:00', '2026-08-28T16:00:00+00:00'),
        (date(2026, 3, 8), 'America/New_York', '2026-03-08T05:00:00+00:00', '2026-03-09T04:00:00+00:00'),
        (date(2026, 11, 1), 'America/New_York', '2026-11-01T04:00:00+00:00', '2026-11-02T05:00:00+00:00'),
    ],
    ids=['normal-day', 'dst-gap-23-hours', 'dst-fold-25-hours'],
)
def test_local_date_range_uses_utc_half_open_interval(
    day: date, zone: str, expected_start: str, expected_end: str
) -> None:
    start, end = TimezoneUtil.local_date_range_to_utc(day, day, zone)

    assert start == datetime.fromisoformat(expected_start)
    assert end == datetime.fromisoformat(expected_end)


def test_format_rfc3339_uses_utc_and_millisecond_precision() -> None:
    value = datetime.fromisoformat('2026-08-28T10:30:00.123456+08:00')

    assert TimezoneUtil.format_rfc3339(value) == '2026-08-28T02:30:00.123Z'


class TestGenTimeUtil:
    """生成器时间工具保留数据库时区语义并拒绝含义不明确的列。"""

    @pytest.mark.parametrize(
        ('column_type', 'expected'),
        [
            ('TIMESTAMP(3) WITH TIME ZONE', 'timestamp with time zone'),
            ('TIME(6) WITHOUT TIME ZONE', 'time without time zone'),
            ('DATETIME(3)', 'datetime'),
            ('BIGINT unsigned', 'bigint'),
        ],
    )
    def test_normalization_preserves_timezone_qualifiers(self, column_type: str, expected: str) -> None:
        assert GenTimeUtil.normalize_db_type(column_type) == expected

    @pytest.mark.parametrize('column_type', ['TIME(3) WITH TIME ZONE', 'timetz'])
    def test_time_with_timezone_requires_an_explicit_storage_decision(self, column_type: str) -> None:
        with pytest.raises(ServiceWarning) as error:
            GenTimeUtil.get_time_semantics(column_type, 'postgresql')

        assert 'TIME WITHOUT TIME ZONE' in error.value.message

    @pytest.mark.parametrize('db_type', ['mysql', 'postgresql'])
    def test_non_time_columns_do_not_receive_time_semantics(self, db_type: str) -> None:
        assert GenTimeUtil.get_time_semantics('varchar(64)', db_type) is None
