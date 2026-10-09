import json
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pytest
from fastapi import FastAPI
from starlette import status
from starlette.types import Message, Receive, Scope, Send

from plugins.core.manifest.v2 import FrontendBundleManifest
from plugins.core.runtime.asgi import PluginGatewayASGI, PluginLifespanManager
from plugins.core.runtime.bundle import PluginBundleASGI
from plugins.core.sdk import PluginRequestContext

_HTML_HEADERS = {'Accept': 'text/html,application/xhtml+xml;q=0.9'}
_CONFIG_SCRIPT = re.compile(r'<script id="ruoyi-plugin-config" type="application/json">(.*?)</script>')


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    root = tmp_path / 'web' / 'dist'
    (root / 'assets').mkdir(parents=True)
    (root / 'empty').mkdir()
    (root / 'index.html').write_text(
        '<!doctype html><html><head><script src="./assets/main.js"></script></head><body>首页</body></html>',
        encoding='utf-8',
    )
    (root / 'assets' / 'main.js').write_text('window.pluginLoaded = true;', encoding='utf-8')
    (root / 'assets' / 'main.css').write_text('body { color: red; }', encoding='utf-8')
    (root / 'assets' / 'code.wasm').write_bytes(b'\x00asm')
    (root / '.env').write_text('SECRET=hidden', encoding='utf-8')
    (tmp_path / 'private.txt').write_text('must not escape', encoding='utf-8')
    return root


def _mount_bundle(plugin_root: Path, *, spa_fallback: bool = True) -> FastAPI:
    child = FastAPI()

    @child.get('/api/ping')
    async def ping() -> dict[str, str]:
        return {'source': 'child-api'}

    parent = FastAPI()
    parent.mount(
        '/apps/demo',
        PluginBundleASGI(child, 'demo', plugin_root, FrontendBundleManifest(spaFallback=spa_fallback)),
    )
    return parent


@pytest.mark.asyncio
async def test_entry_deep_link_and_head_have_safe_injected_proxy_configuration(bundle_root: Path) -> None:
    app = _mount_bundle(bundle_root.parents[1])
    transport = httpx.ASGITransport(app=app, root_path='/gateway')
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        for path in ('/ui/', '/ui/index.html', '/ui/reports/monthly', '/ui/reports/monthly/'):
            response = await client.get('/gateway/apps/demo' + path, headers=_HTML_HEADERS)
            assert response.status_code == status.HTTP_200_OK
            match = _CONFIG_SCRIPT.search(response.text)
            assert match is not None
            assert json.loads(match.group(1)) == {
                'pluginId': 'demo',
                'uiBase': '/gateway/apps/demo/ui/',
                'apiBase': '/gateway/apps/demo/api/',
            }
            assert response.text.index('ruoyi-plugin-config') < response.text.index('src="./assets/main.js"')
            base = re.search(r'<base href="([^"]+)">', response.text)
            assert base is not None
            assert base.group(1) == '/gateway/apps/demo/ui/'
            assert urljoin(base.group(1), './assets/main.js') == '/gateway/apps/demo/ui/assets/main.js'
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['content-type'] == 'text/html; charset=utf-8'
            assert response.headers['x-frame-options'] == 'SAMEORIGIN'
            assert response.headers['content-security-policy'] == "frame-ancestors 'self'"
            assert response.headers['x-content-type-options'] == 'nosniff'
            head = await client.head('/gateway/apps/demo' + path, headers=_HTML_HEADERS)
            assert head.status_code == status.HTTP_200_OK
            assert head.content == b''
            assert head.headers['content-length'] == str(len(response.content))


@pytest.mark.asyncio
async def test_ui_redirect_retains_effective_mount_prefix_and_query(bundle_root: Path) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]), root_path='/gateway')
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/gateway/apps/demo/ui?view=reports%2Fmonthly')
    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers['location'] == '/gateway/apps/demo/ui/?view=reports%2Fmonthly'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('path', 'media_type'),
    [('assets/main.js', 'text/javascript'), ('assets/main.css', 'text/css'), ('assets/code.wasm', 'application/wasm')],
)
async def test_static_resources_have_explicit_mime_and_head_support(
    bundle_root: Path, path: str, media_type: str
) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/apps/demo/ui/' + path)
        head = await client.head('/apps/demo/ui/' + path)
    assert response.status_code == status.HTTP_200_OK
    assert response.content == (bundle_root / path).read_bytes()
    assert response.headers['content-type'].split(';')[0] == media_type
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['cache-control'] == 'no-cache'
    assert head.content == b''
    assert head.headers['content-length'] == response.headers['content-length']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'path',
    [
        'assets/missing.js',
        'assets/missing',
        'api/missing',
        'ws/missing',
        'docs/missing',
        'missing.json',
        'missing.html',
        'empty',
        'empty/',
        '.env',
        '%2e%2e/private.txt',
        '%2e%2e%5cprivate.txt',
        'C%3A/private.txt',
        'assets/main.js/',
        'reports//monthly',
        'assets/main.js%00',
    ],
)
async def test_missing_resources_directories_and_unsafe_paths_never_fall_back(bundle_root: Path, path: str) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/apps/demo/ui/' + path, headers=_HTML_HEADERS)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert b'ruoyi-plugin-config' not in response.content
    assert b'must not escape' not in response.content


@pytest.mark.asyncio
@pytest.mark.parametrize('accept', ['*/*', 'application/json', 'text/html;q=0', 'text/html;q=invalid'])
async def test_html_navigation_requires_explicit_acceptable_html(bundle_root: Path, accept: str) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        entry = await client.get('/apps/demo/ui/', headers={'Accept': accept})
        missing = await client.get('/apps/demo/ui/reports/monthly', headers={'Accept': accept})
    assert entry.status_code == status.HTTP_406_NOT_ACCEPTABLE
    assert missing.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_no_fallback_mode_and_unsupported_methods_do_not_return_html(bundle_root: Path) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1], spa_fallback=False))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        missing = await client.get('/apps/demo/ui/reports', headers=_HTML_HEADERS)
        for path in ('/ui/', '/ui/reports', '/ui/assets/main.js'):
            response = await client.post('/apps/demo' + path, headers=_HTML_HEADERS)
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
            assert response.headers['allow'] == 'GET, HEAD'
            assert not response.content
    assert missing.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_api_unknown_routes_and_non_http_scopes_are_delegated(bundle_root: Path) -> None:
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/apps/demo/api/ping', headers=_HTML_HEADERS)
        missing = await client.get('/apps/demo/api/missing', headers=_HTML_HEADERS)
    assert response.json() == {'source': 'child-api'}
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert b'ruoyi-plugin-config' not in missing.content
    reached = []

    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(scope)

    bundle = PluginBundleASGI(child, 'demo', bundle_root.parents[1], FrontendBundleManifest())
    for scope in ({'type': 'lifespan'}, {'type': 'websocket', 'path': '/ui/events'}):
        await bundle(scope, None, None)
        assert reached[-1] is scope


@pytest.mark.asyncio
async def test_outer_gateway_authentication_covers_ui_and_assets(bundle_root: Path) -> None:
    async def child(scope: Scope, receive: Receive, send: Send) -> None:
        pytest.fail('unauthorized request reached the child')

    async def deny(scope: Scope) -> PluginRequestContext:
        raise LookupError('unauthenticated')

    manager = PluginLifespanManager(child, managed=False)
    await manager.startup()
    bundle = PluginBundleASGI(child, 'demo', bundle_root.parents[1], FrontendBundleManifest())
    parent = FastAPI()
    parent.mount('/apps/demo', PluginGatewayASGI(bundle, manager, deny))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=parent), base_url='https://test') as client:
        for path in ('/ui', '/ui/', '/ui/index.html', '/ui/assets/main.js', '/ui/reports'):
            response = await client.get('/apps/demo' + path, headers=_HTML_HEADERS)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert b'ruoyi-plugin-config' not in response.content
    await manager.shutdown()


@pytest.mark.asyncio
async def test_symlink_escape_is_rejected_at_configuration_and_request_time(bundle_root: Path) -> None:
    outside = bundle_root.parents[1] / 'private.txt'
    try:
        (bundle_root / 'leak.txt').symlink_to(outside)
    except OSError as exc:
        pytest.skip(f'当前文件系统不允许创建符号链接：{exc}')
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/apps/demo/ui/leak.txt', headers=_HTML_HEADERS)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    outside_html = outside.with_suffix('.html')
    outside_html.write_text('<html>private</html>', encoding='utf-8')
    (bundle_root / 'escape.html').symlink_to(outside_html)
    with pytest.raises(ValueError, match='越界'):
        PluginBundleASGI(FastAPI(), 'demo', bundle_root.parents[1], FrontendBundleManifest(entry='escape.html'))


@pytest.mark.asyncio
async def test_configuration_json_cannot_close_script_and_has_no_request_secrets(bundle_root: Path) -> None:
    child = FastAPI()
    bundle = PluginBundleASGI(
        child, 'demo</script><script>alert(1)</script>', bundle_root.parents[1], FrontendBundleManifest()
    )
    messages = []

    async def send(message: Message) -> None:
        messages.append(message)

    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/apps/demo/ui/',
        'root_path': '/apps/demo',
        'headers': [(b'accept', b'text/html'), (b'cookie', b'secret-session=top-secret')],
        'query_string': b'token=must-not-be-injected',
    }
    await bundle(scope, None, send)
    body = b''.join(message.get('body', b'') for message in messages).decode()
    match = _CONFIG_SCRIPT.search(body)
    assert match is not None
    assert json.loads(match.group(1))['pluginId'] == bundle.plugin_id
    assert '<script>alert(1)</script>' not in body
    assert 'top-secret' not in body
    assert 'must-not-be-injected' not in body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'html',
    [
        '<!doctype html><html><head><base href="https://other.example/"></head><body></body></html>',
        '<!doctype html><html><body>no head</body></html>',
        '<!doctype html><body>no html or head element</body>',
    ],
)
async def test_runtime_base_is_first_and_preserves_doctype(bundle_root: Path, html: str) -> None:
    (bundle_root / 'index.html').write_text(html, encoding='utf-8')
    transport = httpx.ASGITransport(app=_mount_bundle(bundle_root.parents[1]))
    async with httpx.AsyncClient(transport=transport, base_url='https://test') as client:
        response = await client.get('/apps/demo/ui/deep/link', headers=_HTML_HEADERS)
    assert response.status_code == status.HTTP_200_OK
    assert response.text.startswith('<!doctype html>')
    assert re.search(r'<base href="([^"]+)">', response.text).group(1) == '/apps/demo/ui/'


def test_missing_bundle_or_entry_is_rejected_before_activation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='目录不存在'):
        PluginBundleASGI(FastAPI(), 'demo', tmp_path, FrontendBundleManifest())
    (tmp_path / 'web' / 'dist').mkdir(parents=True)
    with pytest.raises(ValueError, match='入口不存在'):
        PluginBundleASGI(FastAPI(), 'demo', tmp_path, FrontendBundleManifest())
