from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest

from common.browser_harness import BrowserHarness, artifact_directory
from common.config import Config
from prepare_e2e_compose import isolate_compose

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Browser, Playwright

pytestmark = pytest.mark.harness


def test_artifact_paths_cannot_escape_output(tmp_path: Path) -> None:
    first = artifact_directory(tmp_path, '../../a/test_login.py::test_a[UTC]')
    second = artifact_directory(tmp_path, '../../b/test_login.py::test_a[UTC]')
    assert first.parent == second.parent == tmp_path
    assert first != second
    assert ':' not in first.name


async def test_contexts_share_browser_but_not_authentication(
    e2e_browser: tuple[Playwright, Browser], tmp_path: Path
) -> None:
    first = BrowserHarness(*e2e_browser, tmp_path / 'first')
    second = BrowserHarness(*e2e_browser, tmp_path / 'second')
    try:
        signed_in = await first.new_context(token='test-token')
        anonymous = await second.new_context()
        assert signed_in.browser is anonymous.browser is e2e_browser[1]
        assert (await signed_in.cookies(Config.frontend_url))[0]['value'] == 'test-token'
        assert await anonymous.cookies(Config.frontend_url) == []
    finally:
        await first.finish(failed=False)
        await second.finish(failed=False)
    assert e2e_browser[1].contexts == []


async def test_failed_case_keeps_trace_screenshot_and_console(
    e2e_browser: tuple[Playwright, Browser], tmp_path: Path
) -> None:
    harness = BrowserHarness(*e2e_browser, tmp_path)
    page = await harness.new_page()
    await page.set_content('<h1>Failure diagnostics</h1>')
    await page.evaluate("console.error('diagnostic-sentinel')")
    await harness.finish(failed=True)
    assert await asyncio.to_thread((tmp_path / 'context-0-page-0.png').is_file)
    assert await asyncio.to_thread((tmp_path / 'context-0-trace.zip').is_file)
    events = json.loads(await asyncio.to_thread((tmp_path / 'browser-events.json').read_text, encoding='utf-8'))
    assert {'kind': 'error', 'message': 'diagnostic-sentinel'} in events
    assert e2e_browser[1].contexts == []


def test_compose_isolation_removes_shared_resources() -> None:
    config = {
        'services': {
            'ruoyi-frontend': {'build': {'context': '/frontend'}, 'container_name': 'shared', 'ports': ['80:80']},
            'ruoyi-backend-my': {'build': {'context': '/backend'}, 'ports': ['9099:9099']},
            'ruoyi-mysql': {'image': 'mysql:8.0', 'container_name': 'shared-db', 'ports': ['3306:3306']},
        },
        'networks': {'default': {'name': 'shared-network', 'external': True}},
        'volumes': {'data': {'name': 'shared-data', 'external': True}},
    }
    isolated = isolate_compose(config, 'ruoyi-ci-test', '3.12')
    assert config['services']['ruoyi-mysql']['container_name'] == 'shared-db'
    assert all('container_name' not in service for service in isolated['services'].values())
    assert isolated['services']['ruoyi-mysql']['ports'] == []
    assert isolated['services']['ruoyi-frontend']['ports'][0]['host_ip'] == '127.0.0.1'
    assert isolated['services']['ruoyi-frontend']['ports'][0]['published'] == '0'
    assert isolated['networks']['default'] == {'name': 'ruoyi-ci-test-default'}
    assert isolated['volumes']['data'] == {'name': 'ruoyi-ci-test-data'}


def test_compose_requires_dedicated_project_prefix() -> None:
    with pytest.raises(ValueError, match='ruoyi-ci-'):
        isolate_compose({'services': {}}, 'production', '3.12')
