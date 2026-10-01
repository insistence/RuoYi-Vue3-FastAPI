import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from config.env import OidcConfig
from module_identity.controller.auth_center_controller import auth_center_controller

_HTTP_OK = 200


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_public_status_tracks_config_without_auth_or_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    """未初始化 Redis、数据库及密钥的匿名请求仍可读取最新开关。"""
    app = FastAPI()
    app.include_router(auth_center_controller)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        for current in (enabled, not enabled):
            monkeypatch.setattr(OidcConfig, 'oidc_enabled', current)
            response = await client.get('/auth/status')
            assert response.status_code == _HTTP_OK
            assert response.json()['data'] == {'enabled': current}
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['pragma'] == 'no-cache'
