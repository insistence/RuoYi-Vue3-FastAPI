import hashlib
from types import SimpleNamespace

import httpx
import pytest
from starlette import status

from config.env import TransportCryptoConfig
from plugins.examples.python.bundle_demo.files import MAX_FILE_BYTES, MAX_FORM_BYTES, register_file_routes
from tests.plugins.core.runtime.test_browser_session import browser, issue  # noqa: F401
from tests.plugins.core.runtime.test_bundle_transport import _decrypt_response, _envelope, crypto  # noqa: F401


@pytest.mark.asyncio
async def test_file_routes_use_real_cookie_csrf_and_permission_checks(browser: SimpleNamespace) -> None:  # noqa: F811
    """真实插件门禁保护 multipart 和二进制响应，接口不需要主 Bearer。"""
    register_file_routes(browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view')
    issued = await issue(browser)
    headers = {'Origin': 'https://test', 'X-Plugin-CSRF': issued.json()['data']['csrfToken']}
    path = '/apps/browser_test/api/files/inspect'
    file = ('报告.txt', '文件内容'.encode(), 'text/plain')
    rejected = await browser.client.post(path, files={'file': file})
    assert rejected.status_code == status.HTTP_403_FORBIDDEN
    response = await browser.client.post(path, files={'file': file}, headers=headers)
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json() == {'filename': file[0], 'size': len(file[1]), 'sha256': hashlib.sha256(file[1]).hexdigest()}
    assert 'authorization' not in response.request.headers
    report = await browser.client.get('/apps/browser_test/api/files/report')
    assert report.headers['content-type'].startswith('text/csv')
    assert report.headers['cache-control'] == 'no-store'
    assert 'authenticated-plugin' in report.text
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=browser.app), base_url='https://test') as anonymous:
        assert (await anonymous.get('/apps/browser_test/api/files/report')).status_code == status.HTTP_401_UNAUTHORIZED
    browser.user.permissions = []
    assert (await browser.client.get('/apps/browser_test/api/files/report')).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
@pytest.mark.parametrize('extra_bytes', [1, MAX_FORM_BYTES * 2])
async def test_file_limits_are_enforced_on_actual_received_bytes(
    browser: SimpleNamespace,  # noqa: F811
    extra_bytes: int,
) -> None:
    """文件和整个 multipart 请求分别执行实际字节上限。"""
    register_file_routes(browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view')
    issued = await issue(browser)
    response = await browser.client.post(
        '/apps/browser_test/api/files/inspect',
        files={'file': ('large.bin', b'x' * (MAX_FILE_BYTES + extra_bytes))},
        headers={'Origin': 'https://test', 'X-Plugin-CSRF': issued.json()['data']['csrfToken']},
    )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE, response.text


@pytest.mark.asyncio
async def test_multiple_or_missing_upload_files_are_rejected(browser: SimpleNamespace) -> None:  # noqa: F811
    """单文件接口不能被表单重复文件绕过。"""
    register_file_routes(browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view')
    issued = await issue(browser)
    headers = {'Origin': 'https://test', 'X-Plugin-CSRF': issued.json()['data']['csrfToken']}
    path = '/apps/browser_test/api/files/inspect'
    multiple = await browser.client.post(path, files=[('file', ('a', b'1')), ('file', ('b', b'2'))], headers=headers)
    assert multiple.status_code == status.HTTP_400_BAD_REQUEST
    missing = await browser.client.post(path, data={'file': 'not a file'}, headers=headers)
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_required_transport_needs_explicit_file_endpoint_exclusions(
    browser: SimpleNamespace,  # noqa: F811
    crypto: SimpleNamespace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """文件接口例外必须由部署配置声明，普通 JSON API 仍强制加密。"""
    register_file_routes(browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view')
    session_path = '/plugin/runtime/browser_test/session'
    envelope, key = _envelope(crypto, 'POST', session_path, {})
    issued = await browser.client.post(
        '/plugin/runtime/browser_test/session',
        json=envelope,
        headers={'Authorization': f'Bearer {browser.token}', 'Origin': 'https://test', 'X-Transport-Encrypt': '1'},
    )
    assert issued.status_code == status.HTTP_200_OK
    csrf = _decrypt_response(issued, key, method='POST', path=session_path)['data']['csrfToken']
    upload_path = '/apps/browser_test/api/files/inspect'
    headers = {'Origin': 'https://test', 'X-Plugin-CSRF': csrf}
    files = {'file': ('test.txt', b'test')}
    report_path = '/apps/browser_test/api/files/report'
    assert (await browser.client.get(report_path)).status_code == status.HTTP_400_BAD_REQUEST
    blocked = await browser.client.post(upload_path, files=files, headers=headers)
    assert blocked.headers['x-transport-crypto-status'] == 'required_missing'
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_exclude_paths', f'{upload_path},{report_path}')
    upload = await browser.client.post(upload_path, files=files, headers=headers)
    assert upload.status_code == status.HTTP_200_OK
    assert upload.json()['sha256'] == hashlib.sha256(b'test').hexdigest()
    no_csrf = await browser.client.post(upload_path, files=files)
    assert no_csrf.status_code == status.HTTP_403_FORBIDDEN
    report = await browser.client.get(report_path)
    assert report.status_code == status.HTTP_200_OK and 'authenticated-plugin' in report.text
    regular = await browser.client.get('/apps/browser_test/api/info')
    assert regular.headers['x-transport-crypto-status'] == 'required_missing'


@pytest.mark.asyncio
@pytest.mark.parametrize('size', [0, MAX_FILE_BYTES])
async def test_empty_and_exact_limit_files_are_accepted(browser: SimpleNamespace, size: int) -> None:  # noqa: F811
    """合法零字节文件和恰好达到上限的文件不会因表单开销被误拒。"""
    register_file_routes(browser.runtime.loaded['browser_test'].lifespan.app, permission='browser_test:view')
    issued = await issue(browser)
    response = await browser.client.post(
        '/apps/browser_test/api/files/inspect',
        files={'file': ('boundary.bin', b'x' * size)},
        headers={'Origin': 'https://test', 'X-Plugin-CSRF': issued.json()['data']['csrfToken']},
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    assert response.json()['size'] == size
