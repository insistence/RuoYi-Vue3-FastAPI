from http import HTTPStatus
from urllib.parse import urlparse

import pytest
from playwright.async_api import expect

from common.browser_harness import BrowserHarness
from common.config import Config

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_server_monitor_page(browser_harness: BrowserHarness) -> None:
    """以本次接口快照验证 CPU、内存、解释器、主机与磁盘的实际值。"""
    page = await browser_harness.new_page(authenticated=True)
    async with page.expect_response(
        lambda response: (
            urlparse(response.url).path.endswith('/monitor/server')
            and response.request.resource_type in {'xhr', 'fetch'}
        )
    ) as pending:
        await page.goto(Config.frontend_url + '/monitor/server')
    response = await pending.value
    assert response.status == HTTPStatus.OK
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK, payload
    data = payload['data']
    metrics = {
        '核心数': data['cpu']['cpuNum'],
        '用户使用率': f'{data["cpu"]["used"]:g}%',
        '系统使用率': f'{data["cpu"]["sys"]:g}%',
        '当前空闲率': f'{data["cpu"]["free"]:g}%',
        '服务器名称': data['sys']['computerName'],
        '操作系统': data['sys']['osName'],
        '服务器IP': data['sys']['computerIp'],
        '系统架构': data['sys']['osArch'],
        'Python名称': data['py']['name'],
        'Python版本': data['py']['version'],
        '安装路径': data['py']['home'],
        '项目路径': data['sys']['userDir'],
    }
    for label, value in metrics.items():
        cell = page.get_by_text(label, exact=True).locator('xpath=ancestor::td/following-sibling::td[1]')
        await expect(cell).to_have_text(str(value))
    memory = page.locator('.el-card').filter(has=page.locator('.el-card__header').filter(has_text='内存'))
    for label, key in (('总内存', 'total'), ('已用内存', 'used'), ('剩余内存', 'free')):
        cells = memory.locator('tr').filter(has=page.get_by_text(label, exact=True)).locator('td')
        await expect(cells.nth(1)).to_have_text(str(data['mem'][key]))
        await expect(cells.nth(2)).to_have_text(str(data['py'][key]))
    disks = page.locator('.el-card').filter(has=page.get_by_text('磁盘状态', exact=True)).locator('tbody tr')
    assert data['sysFiles'], '服务监控应返回实际磁盘信息'
    await expect(disks).to_have_count(len(data['sysFiles']))
    for index, disk in enumerate(data['sysFiles']):
        await expect(disks.nth(index).locator('td')).to_have_text(
            [str(disk[key]) for key in ('dirName', 'sysTypeName', 'typeName', 'total', 'free', 'used')]
            + [f'{disk["usage"]}%']
        )
