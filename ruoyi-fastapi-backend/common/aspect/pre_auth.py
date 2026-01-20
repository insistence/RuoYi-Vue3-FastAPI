import re
from typing import Literal, TypedDict

from fastapi import Depends, Request, params
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from common.context import RequestContext
from config.env import AppConfig
from config.get_db import get_db
from exceptions.exception import AuthException
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService


# 定义排除路由的字典结构
class ExcludeRoute(TypedDict, total=False):
    """
    排除路由的字典结构

    :param path: 路由路径（必填）
    :param methods: HTTP方法列表，空列表表示所有方法（可选，默认为[]）
    :param ignore_paths: 需要忽略的特定路径列表，即使匹配通配符也不排除（可选，默认为[]）
    """

    path: str
    methods: list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']]
    ignore_paths: list[str]


# 创建OAuth2PasswordBearer对象
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/login')


class PreAuth:
    """
    登录认证前置校验依赖类
    """

    def __init__(self, exclude_routes: list[ExcludeRoute] | None = None) -> None:
        """
        初始化登录认证前置校验依赖

        :param exclude_routes: 需要排除的路由列表，格式为：
                            [{'path': '/path1', 'methods': ['GET', 'POST']}, {'path': '/path2/{param}', 'methods': ['GET']}]
                            methods 可以是字符串或列表，空列表表示所有方法
        """
        self.exclude_routes = exclude_routes or []
        # 编译排除路径为正则表达式模式，并存储方法信息
        self.exclude_patterns = []

        for route in self.exclude_routes:
            # 使用TypedDict，确保路由字典包含path字段
            path = route.get('path', '')
            methods = route.get('methods', [])
            ignore_paths = route.get('ignore_paths', [])

            # 编译路径为正则表达式
            pattern = self._compile_path_pattern(path)
            # 存储编译后的模式和方法信息
            self.exclude_patterns.append(
                {
                    'pattern': pattern,
                    'methods': [method.upper() for method in methods],
                    'original_path': path,
                    'ignore_paths': ignore_paths,
                }
            )

    def _compile_path_pattern(self, path: str) -> re.Pattern:
        """
        将FastAPI路径转换为正则表达式模式

        :param path: FastAPI路径（如 /configKey/{config_key}）
        :return: 编译后的正则表达式模式
        """
        # 将FastAPI路径参数转换为正则表达式
        # 例如：/configKey/{config_key} -> /configKey/[^/]+
        pattern_str = re.sub(r'\{[^}]+\}', r'[^/]+', path)
        # 添加开始和结束锚点，确保精确匹配
        return re.compile(f'^{pattern_str}$')

    async def __call__(self, request: Request, db: AsyncSession = Depends(get_db)) -> CurrentUserModel | None:
        """
        执行登录认证校验

        :param request: 当前请求对象
        :param db: 数据库会话
        :return: 当前用户信息
        """
        # 获取当前请求路径和方法
        path = request.url.path
        method = request.method.upper()

        # 从配置中获取APP_ROOT_PATH
        app_root_path = AppConfig.app_root_path

        # 去掉APP_ROOT_PATH前缀
        if app_root_path and path.startswith(app_root_path):
            path = path[len(app_root_path) :]

        # 设置上下文变量
        RequestContext.set_current_exclude_patterns(self.exclude_patterns)

        # 检查路径和方法是否匹配排除模式
        for item in self.exclude_patterns:
            pattern = item['pattern']
            exclude_methods = item['methods']
            ignore_paths = item['ignore_paths']

            # 检查当前路径是否在忽略列表中
            if path in ignore_paths:
                continue

            # 检查路径是否匹配，并且methods为空列表（匹配所有方法）或者当前方法在允许列表中
            if pattern.match(path) and (not exclude_methods or method in exclude_methods):
                # 跳过认证
                return None

        # 否则执行正常认证
        token = request.headers.get('Authorization')
        if not token:
            raise AuthException(data='', message='用户未登录，请先完成登录')
        current_user = await LoginService.get_current_user(request, token, db)
        return current_user


def PreAuthDependency(exclude_routes: list[ExcludeRoute] | None = None) -> params.Depends:  # noqa: N802
    """
    登录认证前置校验依赖

    :param exclude_routes: 需要排除的路由列表，格式为：
                            [{'path': '/path1', 'methods': ['GET', 'POST']}, {'path': '/path2/{param}', 'methods': ['GET']}]
                            methods 可以是字符串或列表，空列表表示所有方法
    :return: 登录认证前置校验依赖
    """
    return Depends(PreAuth(exclude_routes))


def CurrentUserDependency() -> params.Depends:  # noqa: N802
    """
    当前登录用户信息依赖

    :return: 当前登录用户信息依赖
    """
    return Depends(LoginService.get_current_user)
