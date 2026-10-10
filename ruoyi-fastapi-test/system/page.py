from __future__ import annotations

import re
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from playwright.async_api import expect

from common.base_page_test import BasePageTest
from common.config import Config

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from playwright.async_api import APIRequestContext, Locator, Page, Response

    from common.browser_harness import BrowserHarness


class SystemPage(BasePageTest):
    """通过真实界面操作与真实接口结果同步系统管理测试。"""

    api: APIRequestContext
    list_path: str

    async def setup(self, harness: BrowserHarness) -> None:
        """复用浏览器登录，并保留仅用于持久化核验和失败清理的 API 客户端。"""
        await super().setup(harness)
        self.api = await harness.api_context(self.token)

    @property
    def form(self) -> Locator:
        """当前页面可见的查询表单。"""
        return self.page.locator('.app-main .app-container .el-form:visible').first

    @property
    def dialog(self) -> Locator:
        """Element UI 和 Element Plus 共用的可见弹窗。"""
        return self.page.locator('.el-dialog:visible')

    @property
    def rows(self) -> Locator:
        """主表格数据行，不重复计算 Element UI 固定列的镜像表格。"""
        return self.page.locator('.el-table__body-wrapper:visible .el-table__row')

    def row(self, identity: str) -> Locator:
        """按当前测试记录的精确文本定位，避免误操作列表第一条业务数据。"""
        return self.rows.filter(has=self.page.get_by_text(identity, exact=True))

    @staticmethod
    def button(scope: Locator | Page, label: str) -> Locator:
        """图标字体可能进入 Vue2 可访问名称，因此按完整文字后缀匹配。"""
        return scope.get_by_role('button', name=re.compile(rf'{re.escape(label)}\s*$'))

    def field(self, scope: Locator, label: str) -> Locator:
        """两种组件库都按真实表单标签定位，不依赖 Vue3 自动生成的 input id。"""
        labels = self.page.locator('.el-form-item__label').filter(
            has_text=re.compile(rf'^\s*{re.escape(label)}\s*[:：]?\s*$')
        )
        return scope.locator('.el-form-item:visible').filter(has=labels)

    def input(self, scope: Locator, label: str) -> Locator:
        """返回字段内的文本、密码或数字输入框。"""
        return self.field(scope, label).locator('input:not([type=radio]):not([type=checkbox]), textarea').first

    async def fill(self, scope: Locator, label: str, value: str) -> None:
        """填写真实输入控件，触发框架正常的输入事件。"""
        await self.input(scope, label).fill(value)

    async def choose(self, scope: Locator, label: str, option: str) -> None:
        """选择两种 Element 组件库中的下拉选项。"""
        await self.field(scope, label).locator('.el-select').click()
        choices = self.page.locator('.el-select-dropdown:visible .el-select-dropdown__item').filter(
            has_text=re.compile(rf'^\s*{re.escape(option)}\s*$')
        )
        await choices.click()

    async def radio(self, scope: Locator, label: str, option: str) -> None:
        """选择并核对单选项。"""
        choice = (
            self.field(scope, label).locator('.el-radio').filter(has_text=re.compile(rf'^\s*{re.escape(option)}\s*$'))
        )
        await choice.click()
        await expect(choice.locator('input[type=radio]')).to_be_checked()

    async def choose_department(self, scope: Locator, label: str, department: str) -> None:
        """覆盖 Vue2 的 Treeselect 与 Vue3 的 TreeSelect 实际节点。"""
        await self.field(scope, label).locator('.el-select__wrapper, .vue-treeselect__control').click()
        node = self.page.locator(
            '.el-select-dropdown:visible .el-tree-node__content .el-select-dropdown__item, '
            '.vue-treeselect__menu .vue-treeselect__label:visible'
        ).filter(has_text=re.compile(rf'^\s*{re.escape(department)}(?:\s*\(\d+\))?\s*$'))
        await node.click()

    @staticmethod
    def matches(response: Response, path: str, method: str) -> bool:
        """同时匹配请求方法和 API 路径，兼容两套开发代理前缀。"""
        return response.request.method == method and urlsplit(response.url).path.rstrip('/').endswith(path)

    @staticmethod
    async def payload(response: Response) -> dict:
        """HTTP 与应用状态都必须成功，不让 200 包装的业务错误通过测试。"""
        assert response.ok, f'{response.request.method} {response.url}: HTTP {response.status}'
        payload = await response.json()
        assert payload.get('code') == HTTPStatus.OK, f'{response.url}: {payload}'
        return payload

    async def action(self, trigger: Callable[[], Awaitable[None]], path: str, method: str = 'GET') -> dict:
        """先监听目标响应，再执行点击，避免固定睡眠和遗漏快速响应。"""
        async with self.page.expect_response(lambda response: self.matches(response, path, method)) as response_info:
            await trigger()
        return await self.payload(await response_info.value)

    async def rendered(self) -> None:
        """等待列表遮罩消失；具体行和值由调用方继续断言。"""
        await expect(self.page.locator('.app-main .el-loading-mask:visible')).to_have_count(0)
        await expect(self.page.locator('.app-main .el-table:visible').first).to_be_visible()

    async def open(self, route: str, list_path: str) -> dict:
        """打开真实管理页面并核对首个列表响应。"""
        self.list_path = list_path
        payload = await self.action(lambda: self.page.goto(Config.frontend_url + route), list_path)
        await self.rendered()
        return payload

    async def search(self, fields: dict[str, str] | None = None) -> dict:
        """按界面查询并返回真实响应。"""
        for label, value in (fields or {}).items():
            await self.fill(self.form, label, value)
        payload = await self.action(self.button(self.form, '搜索').click, self.list_path)
        await self.rendered()
        return payload

    async def reset(self) -> dict:
        """通过重置按钮恢复查询条件。"""
        payload = await self.action(self.button(self.form, '重置').click, self.list_path)
        await self.rendered()
        return payload

    async def add(self) -> Locator:
        """打开新增弹窗。"""
        await self.button(self.page, '新增').first.click()
        await expect(self.dialog).to_be_visible()
        return self.dialog

    async def edit(self, identity: str, resource: str, record_id: int) -> Locator:
        """从目标记录打开编辑弹窗，并等待详情加载。"""
        await self.action(lambda: self.row_action(identity, '修改'), f'{resource}/{record_id}')
        await expect(self.dialog).to_be_visible()
        return self.dialog

    async def save(self, resource: str, method: str) -> dict:
        """保存表单，要求写请求、列表刷新和弹窗关闭全部完成。"""
        dialog = self.dialog
        async with self.page.expect_response(lambda response: self.matches(response, self.list_path, 'GET')) as listed:
            await self.action(dialog.get_by_role('button', name=re.compile(r'^确\s*定$')).click, resource, method)
        payload = await self.payload(await listed.value)
        await expect(dialog).to_have_count(0)
        await self.rendered()
        return payload

    async def delete(self, identity: str, resource: str, record_id: int) -> dict:
        """删除本用例创建的目标行，并核对其消失。"""
        await self.row_action(identity, '删除')
        payload = await self.confirm_refresh(f'{resource}/{record_id}')
        await expect(self.row(identity)).to_have_count(0)
        return payload

    async def row_action(self, identity: str, action: str) -> None:
        """兼容 Vue2 文本/更多菜单和 Vue3 用户角色页的图标按钮。"""
        row = self.row(identity)
        named = self.button(row, action)
        if await named.count():
            await named.click()
            return
        more = self.button(row, '更多')
        if action not in {'修改', '删除'} and await more.count():
            await more.hover()
            await (
                self.page.locator('.el-dropdown-menu:visible .el-dropdown-menu__item')
                .filter(has_text=re.compile(rf'^\s*{re.escape(action)}\s*$'))
                .click()
            )
            return
        # 两套源码中操作顺序固定，Vue3 的 tooltip 不提供按钮 accessible name。
        positions = {'修改': 0, '删除': 1, '重置密码': 2, '数据权限': 2, '分配角色': 3, '分配用户': 3}
        await row.get_by_role('button').nth(positions[action]).click()

    async def toggle_status(self, identity: str, resource: str, record_id: int) -> None:
        """停用再启用，并逐次重读保存状态，不依赖成功 toast。"""
        for status in ('1', '0'):
            await self.row(identity).locator('.el-switch').click()
            confirmation = self.page.locator('.el-message-box:visible')
            await self.action(
                confirmation.get_by_role('button', name=re.compile(r'^确\s*定$')).click,
                f'{resource}/changeStatus',
                'PUT',
            )
            await expect(confirmation).to_have_count(0)
            await self.persisted(resource, record_id, {'status': status})

    async def confirm_refresh(self, path: str, method: str = 'DELETE') -> dict:
        """确认危险操作，并等待操作及其列表刷新均成功。"""
        confirmation = self.page.locator('.el-message-box:visible')
        await expect(confirmation).to_be_visible()
        async with self.page.expect_response(lambda response: self.matches(response, self.list_path, 'GET')) as listed:
            await self.action(confirmation.get_by_role('button', name=re.compile(r'^确\s*定$')).click, path, method)
        payload = await self.payload(await listed.value)
        await expect(confirmation).to_have_count(0)
        await self.rendered()
        return payload

    async def persisted(self, resource: str, record_id: int, expected: dict) -> dict:
        """从真实后端重读已保存数据，防止仅验证成功提示或前端本地状态。"""
        response = await self.api.get(f'{resource}/{record_id}')
        assert response.ok
        payload = await response.json()
        assert payload.get('code') == HTTPStatus.OK, payload
        record = payload['data']
        for key, value in expected.items():
            assert record[key] == value, f'{key}: {record[key]!r} != {value!r}'
        return record

    @staticmethod
    def records(payload: dict) -> list[dict]:
        """兼容分页 rows 与树形列表 data 的真实响应格式。"""
        rows = payload.get('rows', payload.get('data', []))
        assert isinstance(rows, list), payload
        return rows

    @classmethod
    def record(cls, payload: dict, field: str, value: str) -> dict:
        """查询必须返回且仅返回一个目标记录。"""
        records = [row for row in cls.records(payload) if row[field] == value]
        assert len(records) == 1, f'未找到唯一的 {field}={value!r}: {payload}'
        return records[0]

    async def cleanup(self, resource: str, field: str, values: Sequence[str], id_key: str) -> None:
        """失败时只清理精确匹配本用例唯一标识的数据，不触碰预置记录。"""
        for value in values:
            response = await self.api.get(f'{resource}/list', params={field: value, 'pageSize': 1000, 'pageNum': 1})
            assert response.ok
            payload = await response.json()
            assert payload.get('code') == HTTPStatus.OK, payload
            for record in self.records(payload):
                if record[field] == value:
                    deleted = await self.api.delete(f'{resource}/{record[id_key]}')
                    assert deleted.ok
                    result = await deleted.json()
                    assert result.get('code') == HTTPStatus.OK, result
