from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING

from common.config import Config

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import APIRequestContext, Browser, BrowserContext, Page, Playwright


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
            timeout=15000,
        )
        self.api_contexts.append(context)
        return context

    async def login(self) -> str:
        """通过测试环境登录，当前用例内复用令牌。"""
        if self.token:
            return self.token
        api = await self.api_context()
        response = await api.post('/login', form={'username': 'admin', 'password': 'admin123'})
        assert response.ok, f'登录 HTTP 状态异常：{response.status}'
        payload = await response.json()
        self.token = payload.get('token') or (payload.get('data') or {}).get('token')
        assert self.token, f'登录未返回令牌：{payload.get("msg", "未知错误")}'
        return self.token

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
