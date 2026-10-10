import argparse
import asyncio
import json
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Route, async_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
TOKEN = 'isolated-mobile-smoke-token'
USER = {
    'userId': 7,
    'userName': 'ci-user',
    'nickName': '移动端 CI',
    'avatar': '',
    'phonenumber': '13800000000',
    'email': 'mobile-ci@example.test',
    'createTime': '2026-01-01T00:00:00Z',
    'timeZone': 'America/New_York',
}


def create_api_handler(errors: list[str], observed: list[dict[str, Any]]) -> Callable[[Route], Awaitable[None]]:
    """
    创建隔离 API 处理函数，向共享记录追加请求及异常。

    :param errors: 本次验收收集的异常说明
    :param observed: 实际发出的 API 请求记录
    :return: 供浏览器路由使用的异步处理函数
    """

    async def api(route: Route) -> None:
        """
        隔离 API 边界，记录真实构建发出的认证和时区请求。

        :param route: 当前浏览器 API 请求
        :return: None
        """
        request = route.request
        path = urlparse(request.url).path
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'}
        if request.method == 'OPTIONS':
            await route.fulfill(status=204, headers=headers)
            return
        observed.append(
            {
                'path': path,
                'method': request.method,
                'authorization': request.headers.get('authorization'),
                'timezone': request.headers.get('x-timezone'),
            }
        )
        payload: dict[str, Any]
        if path == '/transport/crypto/frontend-config':
            payload = {
                'code': 200,
                'data': {
                    'transportCryptoEnabled': False,
                    'transportCryptoMode': 'off',
                    'transportCryptoActive': False,
                    'configExpireAt': int(time.time()) + 600,
                },
            }
        elif path == '/captchaImage':
            payload = {'code': 200, 'captchaEnabled': False}
        elif path == '/login':
            if 'ci-user' not in (request.post_data or ''):
                errors.append('登录请求未包含输入的用户名')
            payload = {'code': 200, 'token': TOKEN}
        elif path == '/getInfo':
            payload = {
                'code': 200,
                'user': USER,
                'roles': ['admin'],
                'permissions': ['*:*:*'],
                'appTimezone': 'Asia/Shanghai',
            }
        elif path == '/system/user/profile':
            payload = {'code': 200, 'data': USER, 'postGroup': 'CI', 'roleGroup': '管理员'}
        elif path == '/logout':
            payload = {'code': 200}
        else:
            errors.append(f'未预期的 API 请求：{path}')
            await route.fulfill(status=500, json={'code': 500, 'msg': 'unexpected smoke request'}, headers=headers)
            return
        await route.fulfill(json=payload, headers=headers)

    return api


async def run_smoke(framework: str, base_url: str, output: Path) -> None:
    """
    使用真实 H5 构建验证登录、持久化身份和个人资料页。

    :param framework: vue2 或 vue3
    :param base_url: 仅用于本次测试的静态文件服务器
    :param output: 浏览器报告目录
    :return: None
    """
    logs: list[str] = []
    errors: list[str] = []
    observed: list[dict[str, Any]] = []
    api = create_api_handler(errors, observed)

    async with async_playwright() as playwright:
        executable = os.environ.get('RUOYI_SMOKE_BROWSER_EXECUTABLE')
        browser = await playwright.chromium.launch(
            headless=True, **({'executable_path': executable} if executable else {})
        )
        context = await browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='UTC')
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        await context.route('http://localhost:9099/**', api)
        page = await context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: logs.append(f'{message.type}: {message.text}'))
        failed = False
        try:
            await page.goto(f'{base_url}/#/pages/login')
            await expect(page.locator('input[type="text"]')).to_be_visible(timeout=30000)
            await expect(page.locator('input')).to_have_count(2, timeout=15000)
            await page.locator('input[type="text"]').fill('ci-user')
            await page.locator('input[type="password"]').fill('ci-test-password')
            await page.locator('uni-button').filter(has_text=re.compile(r'登\s*录')).click()
            await expect(page).to_have_url(re.compile(r'/pages/index'), timeout=30000)
            await page.goto(f'{base_url}/#/pages/mine/info/index')
            await expect(page.get_by_text(USER['nickName'], exact=True)).to_be_visible(timeout=30000)
            await expect(page.get_by_text('2025-12-31 19:00:00', exact=True)).to_be_visible(timeout=15000)
            profile_requests = [request for request in observed if request['path'] == '/system/user/profile']
            assert profile_requests, '个人资料页未发送真实 API 请求'
            assert all(request['authorization'] == f'Bearer {TOKEN}' for request in profile_requests)
            assert all(request['timezone'] == 'America/New_York' for request in profile_requests)
            assert not errors, errors
            (output / 'result.json').write_text(
                json.dumps({'framework': framework, 'ok': True, 'requests': observed}, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            print(f'{framework}: H5 login, persisted session and timezone profile PASS')
        except BaseException:
            failed = True
            await page.screenshot(path=str(output / 'failure.png'), full_page=True)
            (output / 'page.html').write_text(await page.content(), encoding='utf-8')
            raise
        finally:
            (output / 'browser.log').write_text('\n'.join([*logs, *errors]), encoding='utf-8')
            await context.tracing.stop(**({'path': str(output / 'trace.zip')} if failed else {}))
            await context.close()
            await browser.close()


def main() -> None:
    """
    在独立临时端口启动 H5 静态服务，结束后关闭自身创建的资源。

    :return: None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--framework', choices=('vue2', 'vue3'), required=True)
    args = parser.parse_args()
    distribution = ROOT / 'ruoyi-fastapi-frontend' / args.framework / 'mobile/dist/build/h5'
    if not (distribution / 'index.html').is_file():
        raise SystemExit(f'请先构建 H5：{distribution}')
    output = ROOT / 'target/ci/mobile-smoke' / args.framework
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(distribution)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        asyncio.run(run_smoke(args.framework, f'http://127.0.0.1:{server.server_port}', output))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
