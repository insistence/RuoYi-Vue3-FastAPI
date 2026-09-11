import json
from datetime import datetime, timezone

import pytest

from utils.response_util import ResponseUtil


def test_response_util_serializes_nested_datetimes_as_fixed_utc_rfc3339() -> None:
    response = ResponseUtil.success(data={'createdAt': datetime(2026, 8, 28, 10, 30, 0, 123456, tzinfo=timezone.utc)})
    payload = json.loads(response.body)

    assert payload['data']['createdAt'] == '2026-08-28T10:30:00.123Z'
    assert payload['time'].endswith('Z')
    assert payload['time'][-5] == '.'


def test_response_util_rejects_naive_datetime_output() -> None:
    with pytest.raises(ValueError, match='必须携带时区'):
        ResponseUtil.success(data={'createdAt': datetime(2026, 8, 28, 10, 30)})
