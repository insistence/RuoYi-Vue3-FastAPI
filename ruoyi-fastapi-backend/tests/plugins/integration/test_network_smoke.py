import asyncio
import ipaddress
import json
import os
import shutil
import socket
import subprocess
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import WebSocket
from starlette import status

from plugins.examples.python.bundle_demo.events import register_event_routes
from tests.plugins.core.runtime.test_browser_session import browser  # noqa: F401

if os.environ.get('RUOYI_PLUGIN_NETWORK_SMOKE') == '1':
    from playwright.async_api import async_playwright, expect

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.browser,
    pytest.mark.skipif(os.environ.get('RUOYI_PLUGIN_NETWORK_SMOKE') != '1', reason='显式启用插件网络验收'),
]
PREFIX = '/gateway/apps/browser_test/'


def frontend_root() -> Path:
    """选择本次验收的真实 Web 工程，明确拒绝尚无对应宿主的框架。"""
    framework = os.environ.get('RUOYI_PLUGIN_FRONTEND_FRAMEWORK', 'vue3').strip().lower()
    if framework not in {'vue2', 'vue3'}:
        raise ValueError('插件网络验收仅支持 RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2 或 vue3')
    return Path(__file__).resolve().parents[4] / 'ruoyi-fastapi-frontend' / framework / 'web'


async def wait_until(predicate: Callable[[], bool], timeout: float = 15) -> None:
    """
    有界等待服务器启动或连接回收，不使用固定长睡眠。

    :param predicate: 待满足的状态条件
    :param timeout: 最长等待秒数
    :return: None
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('网络验收等待状态超时')
        await asyncio.sleep(0.05)


def certificate_files(directory: Path) -> tuple[Path, Path]:
    """
    为本次 loopback HTTPS 代理生成临时证书，不写入系统信任库。

    :param directory: 隔离测试目录
    :return: PEM 证书和私钥路径
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / 'certificate.pem', directory / 'key.pem'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


def prepare_network_host(fixture: SimpleNamespace) -> None:
    """
    为现有隔离鉴权夹具添加宿主导航与真实插件流端点。

    :param fixture: 使用生产门禁及会话协议的隔离运行时
    :return: None
    """
    app = fixture.app
    loaded = fixture.runtime.loaded['browser_test']
    loaded.gateway.connections.recheck_interval = 0.1
    register_event_routes(loaded.lifespan.app, permission='browser_test:view', interval=1.0)
    bundle = fixture.plugin.backend_path / 'web' / 'dist'
    shutil.copyfile(Path(__file__).with_name('network_bundle.html'), bundle / 'index.html')
    shutil.copyfile(frontend_root() / 'src/utils/pluginBridge.js', bundle / 'assets/bridge.js')

    @loaded.lifespan.app.websocket('/ws/events')
    async def events(websocket: WebSocket) -> None:
        websocket.state.plugin_context.require_permission('browser_test:view')
        await websocket.accept()
        await websocket.send_text('connected')
        await websocket.receive_text()

    @app.get('/getInfo')
    async def info() -> dict[str, Any]:
        return {
            'code': 200,
            'user': {'userId': 7, 'userName': 'network-smoke', 'nickName': '验收账号', 'timeZone': 'Asia/Shanghai'},
            'roles': ['tester'],
            'permissions': ['browser_test:view'],
            'appTimezone': 'Asia/Shanghai',
        }

    @app.get('/getRouters')
    async def routers() -> dict[str, Any]:
        return {
            'code': 200,
            'data': [
                {
                    'path': '/network',
                    'component': 'Layout',
                    'children': [
                        {
                            'path': 'plugin',
                            'component': 'PluginFrame',
                            'name': 'NetworkPlugin',
                            'meta': {'title': '插件网络验收', 'pluginId': 'browser_test'},
                        }
                    ],
                }
            ],
        }

    @app.get('/transport/crypto/frontend-config')
    async def crypto_policy() -> dict[str, Any]:
        return {
            'code': 200,
            'data': {
                'transportCryptoEnabled': False,
                'transportCryptoMode': 'off',
                'transportCryptoActive': False,
                'configExpireAt': 2100000000,
            },
        }

    @app.get('/system/config/configKey/{key}')
    async def config(key: str) -> dict[str, Any]:
        return {'code': 200, 'msg': '30'}

    @app.get('/system/notice/listTop')
    async def notices() -> dict[str, Any]:
        return {'code': 200, 'data': []}


@asynccontextmanager
async def network_servers(fixture: SimpleNamespace, directory: Path, output: Path) -> AsyncIterator[str]:
    """
    启动真实 Uvicorn socket 与对应 Vue 框架的 TLS 代理，并在失败时一并回收。

    :param fixture: 隔离宿主应用
    :param directory: 证书及就绪文件目录
    :param output: 诊断日志目录
    :return: 代理 HTTPS 来源地址
    """
    frontend = frontend_root()
    cert_path, key_path = certificate_files(directory)
    node_environment = os.environ.copy()
    if frontend.parent.name == 'vue2':
        options = node_environment.get('NODE_OPTIONS', '')
        if '--openssl-legacy-provider' not in options.split():
            node_environment['NODE_OPTIONS'] = (options + ' --openssl-legacy-provider').strip()
    server = uvicorn.Server(
        uvicorn.Config(
            fixture.app,
            host='127.0.0.1',
            root_path='/gateway',
            lifespan='off',
            log_level='warning',
            access_log=False,
            proxy_headers=True,
            forwarded_allow_ips='127.0.0.1',
            timeout_graceful_shutdown=3,
        )
    )
    # 本场景验证 runtime drain 后 Uvicorn 正常退出，不发送进程信号。
    with socket.socket() as listener, (output / 'frontend.log').open('w', encoding='utf-8') as log:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        serving = asyncio.create_task(server.serve(sockets=[listener]))
        process = None
        try:
            await wait_until(lambda: server.started or serving.done())
            assert server.started, 'Uvicorn 未能启动'
            ready = directory / 'frontend-ready.json'
            process = await asyncio.create_subprocess_exec(
                shutil.which('node') or 'node',
                str(frontend / 'tests/plugins/network-smoke/server.mjs'),
                f'http://127.0.0.1:{listener.getsockname()[1]}',
                str(cert_path),
                str(key_path),
                str(ready),
                cwd=frontend,
                env=node_environment,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            await wait_until(
                lambda: ready.exists() or process.returncode is not None,
                timeout=180 if frontend.parent.name == 'vue2' else 60,
            )
            assert ready.exists(), f'前端代理启动失败，见 {output / "frontend.log"}'
            yield f'https://127.0.0.1:{json.loads(ready.read_text())["port"]}'
        finally:
            try:
                await fixture.runtime.shutdown()
            finally:
                server.should_exit = True
                try:
                    await asyncio.wait_for(serving, timeout=10)
                finally:
                    if process is not None:
                        if process.returncode is None:
                            try:
                                await asyncio.wait_for(process.communicate(input=b'stop\n'), timeout=10)
                            except TimeoutError:
                                process.kill()
                                await asyncio.wait_for(process.wait(), timeout=5)
                        assert process.returncode == 0, '前端代理未正常退出'


async def open_socket(page: Any, origin: str) -> None:
    """
    由浏览器通过真实代理携带限定路径 Cookie 握手 WebSocket。

    :param page: 宿主浏览器页面
    :param origin: HTTPS 代理来源
    :return: None
    """
    await page.evaluate(
        """url => new Promise((resolve, reject) => {
      window.socketCode = null;
      window.smokeSocket = new WebSocket(url);
      const timer = setTimeout(() => {
        window.smokeSocket.close();
        reject(new Error('WebSocket greeting timed out'));
      }, 10000);
      window.smokeSocket.onmessage = () => { clearTimeout(timer); resolve(); };
      window.smokeSocket.onerror = () => {
        clearTimeout(timer);
        reject(new Error('WebSocket handshake failed'));
      };
      window.smokeSocket.onclose = event => {
        clearTimeout(timer);
        window.socketCode = event.code;
        reject(new Error('WebSocket closed before greeting'));
      };
    })""",
        origin.replace('https:', 'wss:') + PREFIX + 'ws/events',
    )


async def verify_browser_session(context: Any, page: Any, origin: str) -> Any:
    """
    通过真实签发响应验证 iframe 会话、Cookie 边界和写请求来源检查。

    :param context: 共享浏览器 Cookie 的隔离上下文
    :param page: 宿主浏览器页面
    :param origin: HTTPS 代理地址
    :return: 已完成宿主握手的插件 iframe 定位器
    """
    async with page.expect_response(origin + '/gateway/plugin/runtime/browser_test/session') as issuing:
        await page.goto(origin + '/network/plugin')
    issued = await issuing.value
    assert issued.status == status.HTTP_200_OK
    csrf = (await issued.json())['data']['csrfToken']
    frame = page.frame_locator('.plugin-frame iframe')
    await expect(frame.locator('#ready')).to_have_text('宿主已连接', timeout=60000)
    cookies = await context.cookies(origin + PREFIX)
    cookie = next(item for item in cookies if item['name'] == 'Plugin-Session-browser_test')
    assert cookie['httpOnly'] and cookie['secure'] and cookie['sameSite'] == 'Strict'
    assert cookie['path'] == PREFIX
    assert 'Plugin-Session-' not in await frame.locator('body').evaluate('element => element.ownerDocument.cookie')
    await frame.locator('#echo').click()
    await expect(frame.locator('#echo-result')).to_have_text('network')
    for headers in (
        {'Origin': origin},
        {'Origin': origin, 'X-Plugin-CSRF': 'wrong'},
        {'Origin': 'https://other.example', 'X-Plugin-CSRF': csrf},
    ):
        rejected = await context.request.post(
            origin + PREFIX + 'api/echo', data={'message': 'blocked'}, headers=headers
        )
        assert rejected.status == status.HTTP_403_FORBIDDEN
    rejected = await context.request.get(
        origin + '/dev-api/system/private', headers={'Cookie': f'{cookie["name"]}={cookie["value"]}'}
    )
    assert rejected.status == status.HTTP_401_UNAUTHORIZED
    return frame


async def start_browser_streams(page: Any, frame: Any, origin: str) -> None:
    """
    从新游标建立 SSE 和 WebSocket，为独立的关闭场景保留事件余量。

    :param page: 宿主浏览器页面
    :param frame: 已连接的插件 iframe 定位器
    :param origin: HTTPS 代理地址
    :return: None
    """
    await frame.locator('#reset').click()
    await frame.locator('#start').click()
    await expect(frame.locator('#stream-state')).to_have_text('接收中')
    await open_socket(page, origin)


async def verify_browser_streams(fixture: SimpleNamespace, page: Any, frame: Any, origin: str) -> None:
    """
    验证真实流增量、取消、游标恢复，以及撤权、主会话失效和停机回收。

    :param fixture: 隔离宿主运行时和可控账号状态
    :param page: 宿主浏览器页面
    :param frame: 已连接的插件 iframe 定位器
    :param origin: HTTPS 代理地址
    :return: None
    """
    loaded = fixture.runtime.loaded['browser_test']
    connections = loaded.gateway.connections.connections
    await frame.locator('#start').click()
    await expect(frame.locator('#stream-state')).to_have_text('接收中')
    assert connections, 'SSE 必须在网络响应仍未结束时增量到达'
    await frame.locator('#stop').click()
    await expect(frame.locator('#stream-state')).to_contain_text('取消')
    await wait_until(lambda: not connections)
    last_id = int(await frame.locator('#events li').last.inner_text())
    await frame.locator('#start').click()
    await expect(frame.locator('#events li').first).to_have_text(str(last_id + 1))
    await frame.locator('#stop').click()
    await expect(frame.locator('#stream-state')).to_contain_text('取消')
    await wait_until(lambda: not connections)
    await start_browser_streams(page, frame, origin)
    live = fixture.runtime.diagnostic_snapshot().plugins[0]
    assert live.ready and live.connections.sse == 1 and live.connections.websocket == 1
    fixture.user.permissions = []
    await expect(frame.locator('#stream-state')).to_contain_text('宿主关闭')
    await page.wait_for_function('window.socketCode === 1008')
    await wait_until(lambda: not connections)
    revoked = fixture.runtime.diagnostic_snapshot().plugins[0]
    assert revoked.connections.sse == 0 and revoked.connections.websocket == 0
    fixture.user.permissions = ['browser_test:view']
    await start_browser_streams(page, frame, origin)
    fixture.redis.values.pop(fixture.main_key)
    await expect(frame.locator('#stream-state')).to_contain_text('宿主关闭')
    await page.wait_for_function('window.socketCode === 1008')
    await wait_until(lambda: not connections)
    await fixture.redis.set(fixture.main_key, fixture.token, ex=1800)
    await start_browser_streams(page, frame, origin)
    await fixture.runtime.shutdown()
    await expect(frame.locator('#stream-state')).to_contain_text('宿主关闭')
    await page.wait_for_function('window.socketCode === 1012')
    assert not connections and not loaded.lifespan.has_pending_task
    stopped = fixture.runtime.diagnostic_snapshot().plugins[0]
    assert stopped.closing and not stopped.ready and not stopped.active
    assert stopped.connections.sse == 0 and stopped.connections.websocket == 0
    assert stopped.pending_connection_tasks == 0 and not stopped.lifespan.task_active


async def verify_browser(fixture: SimpleNamespace, origin: str, output: Path) -> None:
    """
    验证真实 Vue iframe、Cookie/CSRF、流增量、恢复、撤权及主动关闭。

    :param fixture: 隔离宿主运行时和可控账号状态
    :param origin: HTTPS 代理地址
    :param output: 失败截图与 Playwright trace 目录
    :return: None
    """
    async with async_playwright() as playwright:
        executable = os.environ.get('RUOYI_SMOKE_BROWSER_EXECUTABLE')
        launched = await playwright.chromium.launch(executable_path=executable or None, headless=True)
        try:
            context = await launched.new_context(ignore_https_errors=True)
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            await context.add_cookies([{'name': 'Admin-Token', 'value': fixture.token, 'url': origin}])
            page = await context.new_page()
            page.set_default_timeout(30000)
            errors: list[str] = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            failed = False
            try:
                frame = await verify_browser_session(context, page, origin)
                await verify_browser_streams(fixture, page, frame, origin)
                assert not errors, errors
                await page.screenshot(path=str(output / 'passed.png'), full_page=True)
            except BaseException:
                failed = True
                with suppress(Exception):
                    await page.screenshot(path=str(output / 'failed.png'), full_page=True)
                raise
            finally:
                if failed:
                    with suppress(Exception):
                        await context.tracing.stop(path=str(output / 'trace.zip'))
                    with suppress(Exception):
                        await context.close()
                else:
                    try:
                        await context.tracing.stop(path=str(output / 'trace.zip'))
                    finally:
                        await context.close()
        finally:
            with suppress(Exception):
                await launched.close()


async def test_plugin_network_smoke(browser: SimpleNamespace, tmp_path: Path) -> None:  # noqa: F811
    """通过真实 TLS 代理与 Vue 页面验收插件网络协议，测试数据全程隔离。"""
    default_output = f'target/plugin-network-smoke/{frontend_root().parent.name}'
    output = await asyncio.to_thread(Path(os.environ.get('RUOYI_SMOKE_OUTPUT', default_output)).resolve)
    output.mkdir(parents=True, exist_ok=True)
    prepare_network_host(browser)
    async with network_servers(browser, tmp_path, output) as origin:
        async with httpx.AsyncClient(verify=False, trust_env=False) as client:
            response = await client.get(origin + PREFIX + 'ui/', headers={'Accept': 'text/html'})
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        await verify_browser(browser, origin, output)
