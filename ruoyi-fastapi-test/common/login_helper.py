import requests

from common.config import Config


class LoginHelper:
    """
    登录辅助类
    """

    def __init__(self, base_url: str = Config.frontend_url) -> None:
        self.base_url = base_url
        self.session = requests.Session()

    def login(self, username: str = 'admin', password: str = 'admin123', max_retries: int = 3) -> str | None:
        """
        执行登录操作（在测试环境中，验证码已禁用）
        """
        for _attempt in range(max_retries):
            # 在测试环境中，验证码已禁用，所以直接登录
            login_data = {'username': username, 'password': password}

            headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Referer': f'{self.base_url}/login'}

            response = self.session.post(f'{Config.backend_url}/login', data=login_data, headers=headers)

            http_ok = 200
            if response.status_code == http_ok:
                result = response.json()
                # 检查登录是否成功 - 可能是 code=200 或 success=true
                if result.get('code') == http_ok or result.get('success'):
                    # 尝试从不同可能的位置获取token
                    token = result.get('token')  # 直接在根级别
                    if not token:
                        token = result.get('data', {}).get('token')  # 在data对象内

                    if token:
                        print('登录成功')
                        return token
                    print(f'登录失败: 响应中未找到token - {result}')
                else:
                    print(f'登录失败: {result.get("msg", "未知错误")}')
            else:
                print(f'登录请求失败: 状态码 {response.status_code}')

        print('登录失败，已达到最大重试次数')
        return None


# 使用示例
if __name__ == '__main__':
    helper = LoginHelper()
    token = helper.login()
    if token:
        print(f'获取到token: {token}')
    else:
        print('登录失败')
