from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from exceptions.exception import AuthException
from module_admin.entity.vo.online_vo import OnlineQueryModel
from module_admin.service.online_service import OnlineService


@pytest.mark.asyncio
async def test_online_list_skips_tokens_that_cannot_be_decoded() -> None:
    redis = SimpleNamespace(
        keys=AsyncMock(return_value=['access_token:stale-session']),
        get=AsyncMock(return_value='invalid-token'),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    with patch(
        'module_admin.service.online_service.JwtUtil.decode',
        side_effect=AuthException(data='', message='用户token已失效，请重新登录'),
    ):
        result = await OnlineService.get_online_list_services(request, OnlineQueryModel())

    assert result == []
