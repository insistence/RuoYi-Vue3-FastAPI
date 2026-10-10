from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from playwright.async_api import expect

from common.config import Config
from system.page import SystemPage

if TYPE_CHECKING:
    from playwright.async_api import Locator, Request, Response

    from common.browser_harness import BrowserHarness

pytestmark = pytest.mark.e2e
RESOURCE = '/system/plugin'
PLUGIN_ID = 'ai'
PLUGIN_WARNING = 601


def validate_operation_envelope(payload: dict) -> dict:
    """601 是明确的业务阻断；异常状态、缺失数据和不一致的成功标志均不能通过。"""
    data = payload['data']
    assert isinstance(data, dict) and isinstance(data['ok'], bool), payload
    assert payload['code'] == (HTTPStatus.OK if data['ok'] else PLUGIN_WARNING), payload
    assert payload['success'] is data['ok'], payload
    assert isinstance(data['message'], str) and data['message'], payload
    assert payload['msg'] == data['message'], payload
    return data


async def plugin_payload(response: Response) -> dict:
    """业务成功和业务阻断都必须是 HTTP 200，并进一步验证具体操作契约。"""
    assert response.status == HTTPStatus.OK, f'{response.url}: HTTP {response.status}'
    return validate_operation_envelope(await response.json())


def validate_capability(capability: dict, operation: str) -> bool:
    """以源码 AI 插件的运行模式验证阻断来源，不能把任意失败当作生产模式限制。"""
    assert capability['pluginId'] == PLUGIN_ID
    assert capability['frontendMode'] in {'dev', 'built'}
    assert capability['backendRuntimeMode'] in {'dev', 'service', 'maintenance'}
    assert capability['hasFrontendResources'] is True and capability['frontendBuildRequired'] is True
    frontend_blocked = capability['frontendMode'] == 'built'
    backend_blocked = capability['backendRuntimeMode'] == 'service'
    blocked = frontend_blocked or backend_blocked
    assert capability['frontendRuntimeManageable'] is (not frontend_blocked)
    assert capability['backendRuntimeManageable'] is (not backend_blocked)
    assert capability['runtimeManageable'] is (not blocked)
    assert (operation in capability['blockedOperations']) is blocked
    warnings = capability['warnings']
    assert isinstance(warnings, list) and len(warnings) == int(frontend_blocked) + int(backend_blocked)
    if backend_blocked:
        assert any('服务运行模式' in reason for reason in warnings)
    if frontend_blocked:
        assert any('已构建前端环境' in reason for reason in warnings)
    assert capability['primaryReason'] == (warnings[0] if blocked else '')
    return blocked


def validate_dependency_report(report: dict) -> None:
    """失败必须由实际缺失或版本不满足的依赖解释，而不是接口异常或空数据。"""
    assert report['pluginId'] == PLUGIN_ID
    dependencies = report['dependencies']
    assert isinstance(dependencies, list) and dependencies
    for item in dependencies:
        assert item['status'] in {'checked', 'skipped'}
        assert isinstance(item['installed'], bool) and isinstance(item['versionSatisfied'], bool)
        assert item['ok'] is (item['status'] == 'skipped' or (item['installed'] and item['versionSatisfied']))
        assert item['requirement'] and item['name'] and item['message']
    checked = [item for item in dependencies if item['status'] != 'skipped']
    assert report['missingDependencies'] == [item['name'] for item in checked if not item['installed']]
    assert report['unsatisfiedDependencies'] == [
        item['name'] for item in checked if item['installed'] and not item['versionSatisfied']
    ]
    assert report['dependencyOk'] is all(item['ok'] for item in dependencies)
    assert report['ok'] is report['dependencyOk']
    assert report['message'] == ('插件依赖已满足' if report['ok'] else '插件依赖存在问题')


def validate_install_plan(payload: dict, capability: dict) -> bool:
    """AI 无插件间依赖；只有明确的环境能力限制可以阻断其拓扑计划。"""
    blocked = validate_capability(capability, 'batch_install')
    assert payload['operation'] == 'install'
    assert payload['databaseAvailable'] is True and payload['databaseError'] is None
    plan = payload['plan']
    assert plan['requestedPluginIds'] == [PLUGIN_ID] and plan['operation'] == 'install'
    assert plan['ok'] is True and plan['orderedPluginIds'] == [PLUGIN_ID]
    assert plan['blockers'] == [] and plan['blockerCount'] == 0
    assert len(plan['items']) == 1 and plan['items'][0]['pluginId'] == PLUGIN_ID
    assert plan['items'][0]['ready'] is True
    assert payload['ok'] is (not blocked)
    if blocked:
        assert payload['message'] == '插件批量操作计划存在环境阻断项'
        assert len(payload['capabilityBlockers']) == 1
        blocker = payload['capabilityBlockers'][0]
        assert blocker['pluginId'] == PLUGIN_ID and blocker['operation'] == 'batch_install'
        assert blocker['capability'] == capability and blocker['message'] == capability['primaryReason']
    else:
        assert payload['message'] == '插件批量操作计划生成完成'
        assert not payload.get('capabilityBlockers')
    return blocked


def record_plugin_writes(view: SystemPage) -> list[Request]:
    """记录浏览器真实请求，最终只允许显式 dry-run 的依赖计划请求。"""
    writes: list[Request] = []
    view.page.on(
        'request',
        lambda request: (
            writes.append(request) if request.method != 'GET' and f'{RESOURCE}/' in urlsplit(request.url).path else None
        ),
    )
    return writes


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


async def plugin_row(view: SystemPage) -> Locator:
    """Vue2 横向溢出时点击固定操作列，Vue3 点击主表格操作。"""
    fixed = view.page.locator('.app-main .el-table__fixed-right:visible .el-table__row').filter(
        has=view.page.get_by_text(PLUGIN_ID, exact=True)
    )
    return fixed if await fixed.count() else view.row(PLUGIN_ID)


async def plugin_action(view: SystemPage, label: str) -> None:
    """操作插件所在行，兼容两套组件库的固定列。"""
    await (await plugin_row(view)).get_by_role('button', name=label, exact=True).click()


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


async def request_dependency_preview(view: SystemPage, endpoint: str) -> dict:
    """只点击生成计划，并强制核对实际请求携带 dryRun=true。"""
    async with view.page.expect_response(
        lambda result: view.matches(result, f'{endpoint}/install', 'POST')
    ) as preview_response:
        await view.button(view.dialog, '生成安装计划').click()
    response = await preview_response.value
    assert parse_qs(urlsplit(response.url).query)['dryRun'] == ['true']
    return await plugin_payload(response)


def validate_blocked_preview(preview: dict, capability: dict) -> None:
    """服务模式的预演拒绝也必须有结构化能力依据，不接受普通 601 异常。"""
    assert validate_capability(capability, 'dependency_install') is True
    assert preview['ok'] is False and preview['status'] == 'blocked'
    assert preview['pluginId'] == PLUGIN_ID and preview['operation'] == 'dependency_install'
    assert preview['dryRun'] is True
    assert preview['capability'] == capability
    assert preview['message'] == '当前环境不允许执行该插件操作'
    assert '开发模式或维护窗口' in preview['suggestion']
    assert not preview.get('plan') and not preview.get('results')


async def verify_dependency_preview(view: SystemPage, preview: dict, report: dict) -> None:
    """开发模式必须完整展示真实预演报告，并且保持实际安装不可执行。"""
    assert preview['ok'] is True and preview['dryRun'] is True
    assert preview['pluginId'] == PLUGIN_ID and preview['operation'] == 'dependency_install'
    assert preview['message'] == '插件依赖安装演练完成，未执行实际安装'
    assert preview['dependencies'] == report['dependencies'] and preview['capability'] == report['capability']
    assert not preview.get('results')
    assert preview['policy']['mode'] == 'plan_only'
    assert preview['policy']['allowed'] is (not bool(preview['plan']))
    assert preview['planCount'] == len(preview['plan'])
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


async def verify_dependency_report_dialog(view: SystemPage, report: dict) -> None:
    """Vue2 的 601 拒绝值是 error，但警告 toast 必须展示真实依赖异常信息。"""
    assert Config.frontend_framework in {'vue2', 'vue3'}
    if not report['ok']:
        await expect(
            view.page.locator('.el-message--warning:visible').filter(has_text=report['message']).first
        ).to_be_visible()
    await expect(view.dialog).to_contain_text('插件依赖')
    alert = view.dialog.locator('.el-alert').first
    await expect(alert).to_have_class(re.compile(r'el-alert--success' if report['ok'] else r'el-alert--warning'))
    message = 'error' if not report['ok'] and Config.frontend_framework == 'vue2' else report['message']
    await expect(alert.locator('.el-alert__title')).to_have_text(message)
    await expect(table_rows(view.dialog)).to_have_count(len(report['dependencies']) if report['ok'] else 0)
    await expect(view.button(view.dialog, '执行依赖安装')).to_be_disabled()


async def test_plugin_dependency_report_and_plan(browser_harness: BrowserHarness) -> None:
    """验证真实依赖异常、开发模式只生成计划，以及生产模式能力阻断。"""
    view, plugin = await open_plugins(browser_harness)
    writes = record_plugin_writes(view)
    endpoint = f'{RESOURCE}/{PLUGIN_ID}/dependencies'
    async with view.page.expect_response(lambda response: view.matches(response, endpoint, 'GET')) as pending:
        await plugin_action(view, '依赖')
    report = await plugin_payload(await pending.value)
    validate_dependency_report(report)
    assert report['capability'] == plugin['capability']
    blocked = validate_capability(report['capability'], 'dependency_install')
    await verify_dependency_report_dialog(view, report)
    if blocked and report['ok']:
        # 成功报告保留 capability，界面直接禁用预演入口。
        await expect(view.button(view.dialog, '生成安装计划')).to_be_disabled()
        assert writes == []
    else:
        # 依赖异常时现有界面只保留错误消息；真实预演仍须由后端能力检查保护。
        preview = await request_dependency_preview(view, endpoint)
        if blocked:
            validate_blocked_preview(preview, report['capability'])
            await expect(
                view.page.locator('.el-message--warning:visible').filter(has_text=preview['message']).first
            ).to_be_visible()
            await expect(table_rows(view.dialog)).to_have_count(0)
            await expect(view.button(view.dialog, '执行依赖安装')).to_be_disabled()
            await expect(view.dialog.get_by_role('tab', name='策略判定', exact=True)).to_have_count(0)
        else:
            await verify_dependency_preview(view, preview, report)
        assert len(writes) == 1 and writes[0].method == 'POST'
        assert urlsplit(writes[0].url).path.endswith(f'{endpoint}/install')
        assert parse_qs(urlsplit(writes[0].url).query)['dryRun'] == ['true']
    await close_dialog(view)
    await assert_unchanged(view, plugin)


async def test_plugin_install_plan(browser_harness: BrowserHarness) -> None:
    """选中插件生成拓扑安装计划，核对计划与阻塞原因后退出。"""
    view, plugin = await open_plugins(browser_harness)
    writes = record_plugin_writes(view)
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
    payload = await plugin_payload(response)
    blocked = validate_install_plan(payload, plugin['capability'])
    if blocked:
        await expect(
            view.page.locator('.el-message--warning:visible').filter(has_text=payload['message']).first
        ).to_be_visible()
        await expect(view.dialog).to_have_count(0)
        await expect(view.button(view.page, '执行计划：安装')).to_have_count(0)
        actions = (await plugin_row(view)).get_by_role('button', name=re.compile(r'^(安装|升级|卸载)$'))
        assert await actions.count() > 0
        for action in await actions.all():
            await expect(action).to_be_disabled()
    else:
        await verify_install_plan_dialog(view, payload)
        await close_dialog(view)
    assert writes == [], '查看拓扑计划不得发出插件写请求'
    await assert_unchanged(view, plugin)


async def verify_install_plan_dialog(view: SystemPage, payload: dict) -> None:
    """可操作环境展示拓扑细节，但用例始终不点击实际执行入口。"""
    plan = payload['plan']
    await expect(view.dialog).to_contain_text('插件安装计划')
    await expect(view.button(view.dialog, '执行计划：安装')).to_be_enabled()
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
