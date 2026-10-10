import re

from playwright.async_api import Locator

from common.browser_harness import BrowserHarness


class BasePageTest:
    harness = None
    context = None
    page = None
    token = None

    async def setup(self, harness: BrowserHarness) -> None:
        """创建独立上下文，浏览器和诊断资源由会话 fixture 管理。"""
        self.harness = harness
        self.token = await harness.login()
        self.context = await harness.new_context(token=self.token)
        self.page = await self.context.new_page()

    async def goto_page(self, url: str) -> None:
        """访问指定页面"""
        await self.page.goto(url)

    async def select_department(self, dialog: Locator, label: str, department: str) -> None:
        """兼容 Element Plus 树选择器与 Vue2 的 vue-treeselect。"""
        field = dialog.locator('.el-form-item').filter(has_text=label)
        await field.locator('.el-select__wrapper, .vue-treeselect__control').click()
        menu = self.page.locator('.el-popper:visible, .vue-treeselect__menu-container:visible')
        await menu.get_by_text(department, exact=True).click()

    async def wait_for_page_title(self, title_text: str, timeout: int = 10000) -> None:
        """等待页面标题出现"""
        await self.page.wait_for_selector(f'div:has-text("{title_text}")', timeout=timeout)
        page_title = await self.page.inner_text(f'div:has-text("{title_text}")')
        assert title_text in page_title

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> None:
        """等待选择器出现"""
        await self.page.wait_for_selector(selector, timeout=timeout)

    async def query_selector(self, selector: str) -> any:
        """查询选择器元素"""
        return await self.page.query_selector(selector)

    async def click_button(self, button_text: str) -> None:
        """点击按钮"""
        button = await self.page.wait_for_selector(f'text="{button_text}"', timeout=5000)
        await button.click()

    async def fill_input(self, selector: str, value: str) -> None:
        """填充输入框"""
        await self.page.fill(selector, value)

    async def get_text_content(self, selector: str) -> str:
        """获取元素文本内容"""
        element = await self.page.query_selector(selector)
        if element:
            return await element.text_content()
        return None

    async def get_table_total_rows(self) -> int:
        """获取表格总行数"""
        element = self.page.locator('span.el-pagination__total').first
        text = await element.text_content()

        # 提取数字
        number = re.search(r'\d+', text).group()
        return int(number)
