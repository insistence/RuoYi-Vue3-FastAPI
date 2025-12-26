import re

from playwright.async_api._context_manager import PlaywrightContextManager

from common.login_helper import LoginHelper


class BasePageTest:
    browser = None
    context = None
    page = None
    token = None

    async def setup(self, playwright: PlaywrightContextManager) -> None:
        """初始化浏览器和登录"""
        # 首先登录获取token
        helper = LoginHelper()
        self.token = helper.login(username='admin', password='admin123')
        assert self.token is not None, '登录应该成功'

        # 启动浏览器
        self.browser = await playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()
        # 设置认证token
        await self.context.add_cookies(
            [
                {
                    'name': 'Admin-Token',
                    'value': self.token,
                    'domain': 'localhost',
                    'path': '/',
                    'httpOnly': False,
                    'secure': False,
                }
            ]
        )
        self.page = await self.context.new_page()

    async def teardown(self) -> None:
        """清理资源"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

    async def goto_page(self, url: str) -> None:
        """访问指定页面"""
        await self.page.goto(url)

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
