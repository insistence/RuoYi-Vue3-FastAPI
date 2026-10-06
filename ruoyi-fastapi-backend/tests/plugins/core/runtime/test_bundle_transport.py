import base64
import json
import os
import secrets
import time
from types import SimpleNamespace

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from starlette import status

from config.env import AppConfig, TransportCryptoConfig
from tests.plugins.core.runtime.test_browser_session import browser  # noqa: F401
from utils.transport_crypto_util import TransportCryptoMonitorUtil, TransportKeyProvider


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


@pytest.fixture
def crypto(browser: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:  # noqa: F811
    """只替换配置密钥和监控存储；保留真实解密、重放校验、Cookie 认证和加密响应。"""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    settings = {
        'transport_crypto_enabled': True,
        'transport_crypto_mode': 'required',
        'transport_crypto_enabled_paths': '',
        'transport_crypto_required_paths': '',
        'transport_crypto_exclude_paths': '',
        'transport_crypto_kid': 'plugin-transport-test',
        'transport_crypto_private_key': private_pem,
        'transport_crypto_public_key': public_pem,
        'transport_crypto_legacy_key_pairs': '[]',
        'transport_crypto_clock_skew_seconds': 300,
        'transport_crypto_replay_ttl_seconds': 300,
    }
    for name, value in settings.items():
        monkeypatch.setattr(TransportCryptoConfig, name, value)
    monkeypatch.setattr(TransportKeyProvider, '_key_pairs', None)
    # MemoryRedis 负责会话和原子 NX 防重放；监控使用现有进程内回退，避免要求 Redis pipeline。
    monkeypatch.setattr(TransportCryptoMonitorUtil, '_get_redis_client', lambda app: None)
    return SimpleNamespace(public_key=public_key, kid=settings['transport_crypto_kid'])


def _envelope(crypto: SimpleNamespace, method: str, path: str, payload: object) -> tuple[dict, bytes]:
    """按浏览器协议构造信封，每个请求使用独立 AES key、IV 和防重放 nonce。"""
    aes_key = os.urandom(32)
    iv = os.urandom(12)
    aad = {'method': method, 'path': path}
    encrypted_key = crypto.public_key.encrypt(
        aes_key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    return {
        'v': '1',
        'alg': TransportCryptoConfig.transport_crypto_algorithm,
        'kid': crypto.kid,
        'ts': int(time.time()),
        'nonce': secrets.token_urlsafe(24),
        'ek': _encode(encrypted_key),
        'iv': _encode(iv),
        'ct': _encode(AESGCM(aes_key).encrypt(iv, _json_bytes(payload), _json_bytes(aad))),
        'aad': aad,
    }, aes_key


def _decrypt_response(response: httpx.Response, aes_key: bytes, *, method: str, path: str) -> dict:
    assert response.headers['x-body-encrypted'] == '1', response.text
    envelope = response.json()
    expected_aad = {'method': method, 'path': path, 'direction': 'response'}
    assert envelope['aad'] == expected_aad
    assert envelope['alg'] == 'AES_256_GCM'
    plaintext = AESGCM(aes_key).decrypt(_decode(envelope['iv']), _decode(envelope['ct']), _json_bytes(expected_aad))
    return json.loads(plaintext)


@pytest.mark.asyncio
@pytest.mark.parametrize('root_path', ['', '/prefix'])
async def test_encrypted_session_cookie_and_plugin_api_keep_outer_aad(
    browser: SimpleNamespace,  # noqa: F811
    crypto: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    root_path: str,
) -> None:
    monkeypatch.setattr(AppConfig, 'app_root_path', root_path)
    transport = httpx.ASGITransport(app=browser.app, root_path=root_path)
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        session_path = '/plugin/runtime/browser_test/session'
        envelope, aes_key = _envelope(crypto, 'POST', session_path, {})
        issued = await client.post(
            root_path + session_path,
            json=envelope,
            headers={
                'Authorization': f'Bearer {browser.token}',
                'Origin': 'https://test',
                'X-Transport-Encrypt': '1',
            },
        )
        assert issued.status_code == status.HTTP_200_OK, issued.text
        data = _decrypt_response(issued, aes_key, method='POST', path=session_path)['data']
        assert data['uiBase'] == f'{root_path}/apps/browser_test/ui/'
        assert data['apiBase'] == f'{root_path}/apps/browser_test/api/'
        assert browser.token not in issued.text
        assert issued.headers['cache-control'] == 'no-store'
        cookies = issued.headers.get_list('set-cookie')
        assert len(cookies) == 1
        assert f'Path={root_path}/apps/browser_test/' in cookies[0]
        assert all(attribute in cookies[0] for attribute in ('HttpOnly', 'Secure', 'SameSite=strict'))

        info_path = '/apps/browser_test/api/info'
        envelope, aes_key = _envelope(crypto, 'GET', info_path, {'query': '仅存在于密文'})
        info = await client.get(
            root_path + info_path,
            params={'__enc': _encode(_json_bytes(envelope))},
            headers={'X-Transport-Encrypt': '1'},
        )
        assert info.status_code == status.HTTP_200_OK, info.text
        assert _decrypt_response(info, aes_key, method='GET', path=info_path) == {
            'pluginId': 'browser_test',
            'userId': browser.user.user.user_id,
        }
        assert 'authorization' not in info.request.headers
        assert 'cookie' in info.request.headers

        echo_path = '/apps/browser_test/api/echo'
        payload = {'secret': '插件请求与响应保密', 'number': 17}
        envelope, aes_key = _envelope(crypto, 'POST', echo_path, payload)
        echo = await client.post(
            root_path + echo_path,
            json=envelope,
            headers={
                'X-Transport-Encrypt': '1',
                'Origin': 'https://test',
                'X-Plugin-CSRF': data['csrfToken'],
            },
        )
        assert echo.status_code == status.HTTP_200_OK, echo.text
        assert _decrypt_response(echo, aes_key, method='POST', path=echo_path) == payload
        assert payload['secret'] not in echo.text

        # 加密不能替代 CSRF；门禁拒绝响应也使用同一个请求协商的 AES 密钥。
        envelope, aes_key = _envelope(crypto, 'POST', echo_path, payload)
        rejected = await client.post(
            root_path + echo_path,
            json=envelope,
            headers={'X-Transport-Encrypt': '1', 'Origin': 'https://test'},
        )
        assert rejected.status_code == status.HTTP_403_FORBIDDEN
        assert _decrypt_response(rejected, aes_key, method='POST', path=echo_path)['code'] == status.HTTP_403_FORBIDDEN

        # 同一个已认证 Cookie 对 API 仍需信封，对只读 UI 则使用普通 HTTPS。
        plain_api = await client.get(root_path + info_path)
        assert plain_api.status_code == status.HTTP_400_BAD_REQUEST
        assert plain_api.headers['x-transport-crypto-status'] == 'required_missing'
        page = await client.get(f'{root_path}/apps/browser_test/ui/', headers={'Accept': 'text/html'})
        assert page.status_code == status.HTTP_200_OK
        assert page.headers['content-type'].startswith('text/html')
        assert 'x-body-encrypted' not in page.headers
        assert data['uiBase'] in page.text and 'ruoyi-plugin-config' in page.text
        asset = await client.get(f'{root_path}/apps/browser_test/ui/assets/app.js')
        assert asset.status_code == status.HTTP_200_OK
        assert 'x-body-encrypted' not in asset.headers

    async with httpx.AsyncClient(transport=transport, base_url='https://test') as anonymous:
        page = await anonymous.get(f'{root_path}/apps/browser_test/ui/', headers={'Accept': 'text/html'})
        assert page.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'x-transport-crypto-status' not in page.headers
        assert 'Bundle' not in page.text


@pytest.mark.asyncio
@pytest.mark.parametrize('wrong_path', ['/api/info', '/apps/other/api/info'])
async def test_plugin_api_rejects_aad_without_its_full_namespace(
    browser: SimpleNamespace,  # noqa: F811
    crypto: SimpleNamespace,
    wrong_path: str,
) -> None:
    envelope, _ = _envelope(crypto, 'GET', wrong_path, {})
    response = await browser.client.get(
        '/apps/browser_test/api/info',
        params={'__enc': _encode(_json_bytes(envelope))},
        headers={'X-Transport-Encrypt': '1'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.headers['x-transport-crypto-status'] == 'aad_mismatch'
    browser.login.assert_not_awaited()
