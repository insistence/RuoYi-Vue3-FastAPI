from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from common.browser_harness import BrowserHarness, artifact_directory
from common.config import Config

E2E_OUTPUT_ROOT = Path(os.environ.get('E2E_OUTPUT_DIR', 'target/e2e')).resolve()

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator

    from playwright.async_api import Browser, Playwright


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator:
    """在浏览器 fixture 回收前保存调用结果，确保断言失败仍能导出诊断。"""
    result = yield
    report = result.get_result()
    setattr(item, f'rep_{report.when}', report)


@pytest_asyncio.fixture(scope='session', loop_scope='session')
async def e2e_browser() -> AsyncIterator[tuple[Playwright, Browser]]:
    """一次 pytest 会话只启动一个 Chromium 进程。"""
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            channel=Config.browser_channel,
            executable_path=os.environ.get('TEST_BROWSER_EXECUTABLE') or None,
        )
        try:
            yield playwright, browser
        finally:
            await browser.close()


@pytest_asyncio.fixture(loop_scope='session')
async def browser_harness(
    e2e_browser: tuple[Playwright, Browser], request: pytest.FixtureRequest
) -> AsyncIterator[BrowserHarness]:
    """每个用例有自己的上下文、诊断目录和 API 客户端。"""
    harness = BrowserHarness(*e2e_browser, artifact_directory(E2E_OUTPUT_ROOT, request.node.nodeid))
    try:
        yield harness
    finally:
        failed = any(
            getattr(request.node, f'rep_{phase}', None).failed
            for phase in ('setup', 'call')
            if hasattr(request.node, f'rep_{phase}')
        )
        await harness.finish(failed=failed)
