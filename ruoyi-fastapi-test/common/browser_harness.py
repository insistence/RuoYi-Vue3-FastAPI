from __future__ import annotations

import asyncio
import hashlib
import json
import re
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from common.config import Config

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import APIRequestContext, APIResponse, Browser, BrowserContext, Page, Playwright, Response

_API_TIMEOUT_MS = 15000
_LOGIN_MAX_ATTEMPTS = 3
_LOGIN_MAX_WAIT_SECONDS = 60


async def _wait_for_login_retry(response: APIResponse | Response, attempt: int, waited: int) -> int:
    """API 与表单登录共用同一等待预算，仅使用后端实际返回的秒数。"""
    assert attempt + 1 < _LOGIN_MAX_ATTEMPTS, '登录 HTTP 429：已达到最大尝试次数'
    retry_after = response.headers.get('retry-after', '').strip()
    assert retry_after.isascii() and retry_after.isdecimal(), f'登录 HTTP 429：Retry-After 无效：{retry_after!r}'
    delay = int(retry_after)
    assert delay <= _LOGIN_MAX_WAIT_SECONDS - waited, '登录 HTTP 429：Retry-After 超出累计等待上限'
    await asyncio.sleep(delay)
    return waited + delay


async def _login_token(response: APIResponse | Response) -> str:
    """非限流错误必须失败，成功响应必须携带有效令牌。"""
    assert response.ok, f'登录 HTTP 状态异常：{response.status}'
    payload = await response.json()
    token = payload.get('token') or (payload.get('data') or {}).get('token')
    assert token, f'登录未返回令牌：{payload.get("msg", "未知错误")}'
    return token


def artifact_directory(root: Path, node_id: str) -> Path:
    """为每个用例生成稳定、无路径跳转且适合 Windows 的诊断目录。"""
    label = re.sub(r'[^a-zA-Z0-9_.-]+', '-', node_id).strip('-')[-80:] or 'test'
    digest = hashlib.sha256(node_id.encode()).hexdigest()[:12]
    return root / f'{label}-{digest}'


class BrowserHarness:
    """复用会话浏览器，每个用例独立管理上下文及失败诊断。"""

    def __init__(self, playwright: Playwright, browser: Browser, output: Path) -> None:
        self.playwright = playwright
        self.browser = browser
        self.output = output
        self.contexts: list[BrowserContext] = []
        self.api_contexts: list[APIRequestContext] = []
        self.events: list[dict[str, str]] = []
        self.token: str | None = None

    async def api_context(self, token: str | None = None) -> APIRequestContext:
        """创建随用例回收的 API 客户端。"""
        context = await self.playwright.request.new_context(
            base_url=Config.backend_url,
            extra_http_headers={'Authorization': f'Bearer {token}'} if token else {},
            timeout=_API_TIMEOUT_MS,
        )
        self.api_contexts.append(context)
        return context

    async def login(self) -> str:
        """用例内复用令牌；429 最多重试两次，总等待不超过 60 秒。"""
        if self.token:
            return self.token
        api = await self.api_context()
        waited = 0
        # 每次请求仍受 15 秒超时限制，三次请求加累计等待最多 105 秒。
        for attempt in range(_LOGIN_MAX_ATTEMPTS):
            response = await api.post('/login', form={'username': 'admin', 'password': 'admin123'})
            if response.status != HTTPStatus.TOO_MANY_REQUESTS:
                break
            waited = await _wait_for_login_retry(response, attempt, waited)
        self.token = await _login_token(response)
        return self.token

    async def login_through_page(self, page: Page, username: str = 'admin', password: str = 'admin123') -> str:
        """真实填写并提交登录表单，仅对 429 有界重试，不替换夹具的管理员令牌。"""
        await page.get_by_placeholder('账号').fill(username)
        await page.get_by_placeholder('密码').fill(password)
        waited = 0
        for attempt in range(_LOGIN_MAX_ATTEMPTS):
            async with page.expect_response(
                lambda response: response.request.method == 'POST' and urlparse(response.url).path.endswith('/login'),
                timeout=_API_TIMEOUT_MS,
            ) as pending:
                await page.get_by_role('button', name=re.compile(r'登\s*录')).click(timeout=_API_TIMEOUT_MS)
            response = await pending.value
            if response.status != HTTPStatus.TOO_MANY_REQUESTS:
                break
            waited = await _wait_for_login_retry(response, attempt, waited)
        token = await _login_token(response)
        await page.wait_for_url('**/index', timeout=30000)
        return token

    async def new_context(self, *, token: str | None = None, **options) -> BrowserContext:
        """每次调用均创建隔离上下文，不继承前一用例 Cookie 或本地存储。"""
        context = await self.browser.new_context(
            **{'base_url': Config.frontend_url, 'viewport': {'width': 1440, 'height': 1000}, **options}
        )
        self.contexts.append(context)
        context.set_default_timeout(15000)
        context.set_default_navigation_timeout(30000)
        await context.tracing.start(screenshots=True, snapshots=True, sources=True)
        context.on('page', self._record_page)
        if token:
            await context.add_cookies(
                [{'name': 'Admin-Token', 'value': token, 'url': Config.frontend_url, 'sameSite': 'Lax'}]
            )
        return context

    async def new_page(self, *, authenticated: bool = False, **options) -> Page:
        """创建可选已认证页面。"""
        token = await self.login() if authenticated else None
        context = await self.new_context(token=token, **options)
        return await context.new_page()

    def _record_page(self, page: Page) -> None:
        page.on('pageerror', lambda error: self.events.append({'kind': 'pageerror', 'message': str(error)}))
        page.on(
            'console',
            lambda message: (
                self.events.append({'kind': message.type, 'message': message.text})
                if message.type in {'warning', 'error'}
                else None
            ),
        )

    async def _save_screenshot(self, page: Page, context_index: int, page_index: int) -> None:
        if page.is_closed():
            return
        try:
            await page.screenshot(
                path=str(self.output / f'context-{context_index}-page-{page_index}.png'),
                full_page=True,
                timeout=5000,
            )
        except Exception as exc:
            self.events.append({'kind': 'screenshot-error', 'message': str(exc)})

    async def _finish_context(self, context: BrowserContext, index: int, *, failed: bool) -> None:
        try:
            if failed:
                for page_index, page in enumerate(context.pages):
                    await self._save_screenshot(page, index, page_index)
                await context.tracing.stop(path=str(self.output / f'context-{index}-trace.zip'))
            else:
                await context.tracing.stop()
        except Exception as exc:
            self.events.append({'kind': 'trace-error', 'message': str(exc)})
        finally:
            try:
                await context.close()
            except Exception as exc:
                self.events.append({'kind': 'context-close-error', 'message': str(exc)})

    async def _dispose_api(self, api: APIRequestContext) -> None:
        try:
            await api.dispose()
        except Exception as exc:
            self.events.append({'kind': 'api-dispose-error', 'message': str(exc)})

    async def finish(self, *, failed: bool) -> None:
        """失败时保留页面截图、trace 和控制台日志，再回收全部上下文。"""
        if failed:
            await asyncio.to_thread(self.output.mkdir, parents=True, exist_ok=True)
        for index, context in enumerate(self.contexts):
            await self._finish_context(context, index, failed=failed)
        for api in self.api_contexts:
            await self._dispose_api(api)
        self.contexts.clear()
        self.api_contexts.clear()
        if failed:
            await asyncio.to_thread(
                (self.output / 'browser-events.json').write_text,
                json.dumps(self.events, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
