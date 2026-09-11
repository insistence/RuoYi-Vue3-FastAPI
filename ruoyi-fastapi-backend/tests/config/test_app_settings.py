import pytest
from pydantic import ValidationError

from config.env import AppSettings


def test_app_timezone_accepts_valid_iana_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('APP_TIMEZONE', 'America/New_York')

    assert AppSettings(_env_file=None).app_timezone == 'America/New_York'


@pytest.mark.parametrize('timezone_name', ['', 'Not/A-Timezone'])
def test_app_timezone_rejects_invalid_name(timezone_name: str) -> None:
    with pytest.raises(ValidationError, match='APP_TIMEZONE'):
        AppSettings(_env_file=None, app_timezone=timezone_name)
