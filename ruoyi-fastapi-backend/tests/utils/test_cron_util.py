import pickle
from datetime import datetime, timezone

import pytest

from utils.cron_util import CronUtil, MyCronTrigger


@pytest.mark.parametrize(
    ('expression', 'start', 'expected'),
    [
        (
            '0 30 2 * * ?',
            '2026-03-07T00:00:00+00:00',
            ['2026-03-07T07:30:00+00:00', '2026-03-09T06:30:00+00:00', '2026-03-10T06:30:00+00:00'],
        ),
        (
            '0 30 1 * * ?',
            '2026-10-31T00:00:00+00:00',
            ['2026-10-31T05:30:00+00:00', '2026-11-01T05:30:00+00:00', '2026-11-02T06:30:00+00:00'],
        ),
        (
            '0 30 2 * * ?',
            '2026-03-08T00:00:00+00:00',
            ['2026-03-09T06:30:00+00:00', '2026-03-10T06:30:00+00:00', '2026-03-11T06:30:00+00:00'],
        ),
        (
            '0 30 1 * * ?',
            '2026-11-01T00:00:00+00:00',
            ['2026-11-01T05:30:00+00:00', '2026-11-02T06:30:00+00:00', '2026-11-03T06:30:00+00:00'],
        ),
    ],
    ids=['before-gap', 'before-fold', 'on-gap', 'on-fold'],
)
def test_preview_matches_persisted_trigger_across_dst(expression: str, start: str, expected: list[str]) -> None:
    start_time = datetime.fromisoformat(start)
    preview = CronUtil.next_run_times(expression, 'America/New_York', start_time, 3)
    trigger = pickle.loads(pickle.dumps(MyCronTrigger.from_crontab(expression, 'America/New_York')))
    actual = []
    previous = None
    for _ in range(3):
        previous = trigger.get_next_fire_time(previous, previous or start_time)
        actual.append(previous.astimezone(timezone.utc))
    assert preview == actual == [datetime.fromisoformat(value) for value in expected]


@pytest.mark.parametrize(
    ('expression', 'expected'),
    [
        ('0 0 9 ? * 2', ['2026-02-02', '2026-02-09']),
        ('0 0 9 ? * 1#2', ['2026-02-08', '2026-03-08']),
        ('0 0 9 ? * 6L', ['2026-02-27', '2026-03-27']),
        ('0 0 9 1W * ?', ['2026-02-02', '2026-03-02']),
    ],
)
def test_quartz_week_and_workday_semantics(expression: str, expected: list[str]) -> None:
    times = CronUtil.next_run_times(expression, 'UTC', datetime(2026, 2, 1, tzinfo=timezone.utc), 2)
    assert [value.date().isoformat() for value in times] == expected


def test_cron_trigger_uses_explicit_business_timezone() -> None:
    trigger = MyCronTrigger.from_crontab('0 0 9 * * ?', 'Asia/Shanghai')
    fire_time = trigger.get_next_fire_time(None, datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert trigger.timezone.key == 'Asia/Shanghai'
    assert fire_time is not None
    assert fire_time.astimezone(timezone.utc) == datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
