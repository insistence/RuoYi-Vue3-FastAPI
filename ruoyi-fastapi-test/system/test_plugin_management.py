from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from playwright.async_api import expect

from system.page import SystemPage

if TYPE_CHECKING:
    from playwright.async_api import Locator

    from common.browser_harness import BrowserHarness

pytestmark = pytest.mark.e2e
RESOURCE = '/system/plugin'
PLUGIN_ID = 'ai'


def table_rows(scope: Locator) -> Locator:
    """只计当前可见主表格，避免 Vue2 固定列镜像被重复计算。"""
    return scope.locator('.el-table__body-wrapper:visible .el-table__row')


async def open_plugins(browser_harness: BrowserHarness) -> tuple[SystemPage, dict]:
    """使用真实登录和列表，定位项目自带的 AI 插件。"""
    view = SystemPage()
    await view.setup(browser_harness)
    payload = await view.open('/system/plugin', f'{RESOURCE}/list')
    plugin = view.record(payload, 'pluginId', PLUGIN_ID)
    await expect(view.row(PLUGIN_ID)).to_have_count(1)
    return view, plugin


async def plugin_action(view: SystemPage, label: str) -> None:
    """Vue2 横向溢出时点击固定操作列，Vue3 点击主表格操作。"""
    fixed = view.page.locator('.app-main .el-table__fixed-right:visible .el-table__row').filter(
        has=view.page.get_by_text(PLUGIN_ID, exact=True)
    )
    row = fixed if await fixed.count() else view.row(PLUGIN_ID)
    await row.get_by_role('button', name=label, exact=True).click()


async def close_dialog(view: SystemPage) -> None:
    """等待弹窗关闭，确保后续请求来自主页面。"""
    await view.dialog.get_by_role('button', name=re.compile(r'^关\s*闭$')).click()
    await expect(view.dialog).to_have_count(0)


async def assert_unchanged(view: SystemPage, before: dict) -> None:
    """计划查看不能修改插件的安装版本、启用设置或状态。"""
    response = await view.api.get(f'{RESOURCE}/{PLUGIN_ID}')
    assert response.ok
    payload = await response.json()
    assert payload['code'] == HTTPStatus.OK, payload
    for key in ('installedVersion', 'enabled', 'status'):
        assert payload['data'].get(key) == before.get(key), key


async def verify_manifest_tabs(view: SystemPage, detail: dict) -> None:
    """逐项核对清单声明，不能只验证标签页标题存在。"""
    dialog = view.dialog
    for tab, records, field in (
        ('菜单', detail.get('frontend', {}).get('menus', []), 'name'),
        ('权限', detail.get('permissions', []), 'code'),
        ('配置', detail.get('config', []), 'key'),
    ):
        await dialog.get_by_role('tab', name=tab, exact=True).click()
        rows = table_rows(dialog)
        await expect(rows).to_have_count(len(records))
        for record in records:
            await expect(rows.filter(has_text=record[field])).to_have_count(1)
    await dialog.get_by_role('tab', name='依赖', exact=True).click()
    for kind in ('python', 'npm', 'npmDev'):
        for requirement in detail.get('dependencies', {}).get(kind, []):
            await expect(dialog.get_by_text(requirement, exact=True).first).to_be_visible()


async def verify_metrics(view: SystemPage) -> None:
    """运行观测的条数和空态都与当前进程真实响应一致。"""
    dialog = view.dialog
    metrics = dialog.locator('.plugin-metrics')
    for trigger in (
        dialog.get_by_role('tab', name='运行观测', exact=True).click,
        view.button(metrics, '刷新指标').click,
    ):
        current = await view.action(trigger, f'{RESOURCE}/runtime/metrics')
        data = current['data']
        await expect(metrics.locator('.metrics-record')).to_have_count(len(data.get('series', [])))
        if not data.get('series'):
            message = (
                '当前进程未启用运行观测'
                if data.get('supported') is False
                else '暂无该插件的运行指标，仅支持已加载的 v2 插件'
            )
            await expect(metrics.get_by_text(message, exact=True)).to_be_visible()
        await expect(metrics.locator('[role=status]')).to_contain_text('查询时间：')


async def test_plugin_search_detail_and_metrics(browser_harness: BrowserHarness) -> None:
    """插件搜索、无匹配结果、重置、清单详情和运行指标。"""
    view, plugin = await open_plugins(browser_harness)
    result = await view.search({'插件ID': PLUGIN_ID, '插件名称': plugin['pluginName']})
    assert len(view.records(result)) == 1
    assert view.record(result, 'pluginId', PLUGIN_ID)['pluginName'] == plugin['pluginName']
    await expect(view.rows).to_have_count(1)
    empty = await view.search({'插件ID': f'e2e-missing-{uuid4().hex}'})
    assert empty['total'] == 0 and view.records(empty) == []
    await expect(view.rows).to_have_count(0)
    restored = await view.reset()
    assert view.record(restored, 'pluginId', PLUGIN_ID)['pluginName'] == plugin['pluginName']
    for label in ('插件ID', '插件名称'):
        await expect(view.input(view.form, label)).to_have_value('')
    detail = (await view.action(lambda: plugin_action(view, '详情'), f'{RESOURCE}/{PLUGIN_ID}'))['data']
    await expect(view.dialog).to_contain_text('插件详情')
    await expect(
        view.dialog.locator('.el-tab-pane:visible').get_by_text(detail['pluginName'], exact=True)
    ).to_be_visible()
    await verify_manifest_tabs(view, detail)
    await verify_metrics(view)
    await close_dialog(view)
    await assert_unchanged(view, plugin)


async def test_plugin_dependency_report_and_plan(browser_harness: BrowserHarness) -> None:
    """真实依赖报告及 Web 只生成计划策略，绝不执行依赖安装。"""
    view, plugin = await open_plugins(browser_harness)
    endpoint = f'{RESOURCE}/{PLUGIN_ID}/dependencies'
    async with view.page.expect_response(lambda response: view.matches(response, endpoint, 'GET')) as pending:
        await plugin_action(view, '依赖')
    response = await pending.value
    assert response.ok
    report = await response.json()
    assert report['data']['pluginId'] == PLUGIN_ID
    assert isinstance(report['data']['dependencies'], list)
    assert report['code'] == (HTTPStatus.OK if report['data']['ok'] else HTTPStatus.INTERNAL_SERVER_ERROR)
    await expect(view.dialog).to_contain_text('插件依赖')
    if report['code'] == HTTPStatus.OK:
        await expect(table_rows(view.dialog)).to_have_count(len(report['data']['dependencies']))
    else:
        await expect(view.dialog.locator('.el-alert').first).to_contain_text(report['msg'])
    async with view.page.expect_response(
        lambda result: view.matches(result, f'{endpoint}/install', 'POST')
    ) as preview_response:
        await view.button(view.dialog, '生成安装计划').click()
    response = await preview_response.value
    assert parse_qs(urlsplit(response.url).query)['dryRun'] == ['true']
    preview = (await view.payload(response))['data']
    assert preview['dryRun'] is True
    assert preview['policy']['mode'] == 'plan_only'
    assert preview['policy']['allowed'] is (not bool(preview['plan']))
    await expect(table_rows(view.dialog)).to_have_count(len(preview['dependencies']))
    for dependency in preview['dependencies']:
        await expect(table_rows(view.dialog).filter(has_text=dependency['requirement'])).to_have_count(1)
    await expect(view.button(view.dialog, '执行依赖安装')).to_be_disabled()
    await view.dialog.get_by_role('tab', name='安装计划', exact=True).click()
    await expect(table_rows(view.dialog)).to_have_count(len(preview['plan']))
    for item in preview['plan']:
        await expect(view.dialog.get_by_text(item['commandText'], exact=True)).to_be_visible()
    await view.dialog.get_by_role('tab', name='策略判定', exact=True).click()
    await expect(view.dialog.locator('.el-descriptions')).to_contain_text('plan_only')
    await expect(view.dialog.locator('.el-descriptions')).to_contain_text('阻断' if preview['plan'] else '允许')
    await close_dialog(view)
    await assert_unchanged(view, plugin)


async def test_plugin_install_plan(browser_harness: BrowserHarness) -> None:
    """选中插件生成拓扑安装计划，核对计划与阻塞原因后退出。"""
    view, plugin = await open_plugins(browser_harness)
    plan_button = view.button(view.page.locator('.app-main'), '安装计划')
    await expect(plan_button).to_be_disabled()
    await view.row(PLUGIN_ID).locator('.el-checkbox').click()
    await expect(view.row(PLUGIN_ID).locator('.el-checkbox input[type=checkbox]')).to_be_checked()
    await expect(plan_button).to_be_enabled()
    async with view.page.expect_response(lambda result: view.matches(result, f'{RESOURCE}/plan', 'GET')) as planned:
        await plan_button.click()
    response = await planned.value
    query = parse_qs(urlsplit(response.url).query)
    assert query['operation'] == ['install'] and query['pluginIds'] == [PLUGIN_ID]
    payload = (await view.payload(response))['data']
    plan = payload['plan']
    assert plan['requestedPluginIds'] == [PLUGIN_ID] and plan['operation'] == 'install'
    await expect(view.dialog).to_contain_text('插件安装计划')
    await expect(table_rows(view.dialog)).to_have_count(len(plan['items']))
    for item in plan['items']:
        await expect(table_rows(view.dialog).filter(has_text=item['pluginId'])).to_have_count(1)
    await expect(view.dialog.locator('.plan-summary-item').filter(has_text='目标插件')).to_contain_text('1')
    await view.dialog.get_by_role('tab', name='阻塞原因', exact=True).click()
    await expect(table_rows(view.dialog)).to_have_count(len(plan['blockers']))
    for blocker in plan['blockers']:
        await expect(view.dialog.get_by_text(blocker['message'], exact=True).first).to_be_visible()
    await view.dialog.get_by_role('tab', name='执行结果', exact=True).click()
    await expect(table_rows(view.dialog)).to_have_count(0)
    await close_dialog(view)
    await assert_unchanged(view, plugin)


async def test_plugin_audit_query_and_reset(browser_harness: BrowserHarness) -> None:
    """真实操作审计的筛选、空态与重置，不通过安装插件制造审计记录。"""
    view, _ = await open_plugins(browser_harness)
    endpoint = f'{RESOURCE}/operation-log/list'
    original = await view.action(view.button(view.page, '审计记录').click, endpoint)
    drawer = view.page.locator('.el-drawer:visible')
    await expect(drawer).to_contain_text('插件操作审计')
    await expect(table_rows(drawer)).to_have_count(len(original['rows']))
    await drawer.get_by_placeholder('请输入插件ID', exact=True).fill(PLUGIN_ID)
    await view.choose(drawer, '状态', '预演')
    async with view.page.expect_response(lambda response: view.matches(response, endpoint, 'GET')) as filtered:
        await view.button(drawer, '搜索').click()
    response = await filtered.value
    query = parse_qs(urlsplit(response.url).query)
    assert query['pluginId'] == [PLUGIN_ID] and query['status'] == ['dry_run']
    selected = await view.payload(response)
    assert all(PLUGIN_ID in record['pluginIds'] and record['status'] == 'dry_run' for record in selected['rows'])
    await expect(table_rows(drawer)).to_have_count(len(selected['rows']))
    await drawer.get_by_placeholder('请输入插件ID', exact=True).fill(f'e2e-missing-{uuid4().hex}')
    empty = await view.action(view.button(drawer, '搜索').click, endpoint)
    assert empty['total'] == 0 and empty['rows'] == []
    await expect(table_rows(drawer)).to_have_count(0)
    restored = await view.action(view.button(drawer, '重置').click, endpoint)
    await expect(drawer.get_by_placeholder('请输入插件ID', exact=True)).to_have_value('')
    assert restored['total'] == original['total']
    await expect(table_rows(drawer)).to_have_count(len(restored['rows']))
    await drawer.get_by_role('button', name=re.compile(r'^关\s*闭$')).click()
    await expect(drawer).to_have_count(0)
