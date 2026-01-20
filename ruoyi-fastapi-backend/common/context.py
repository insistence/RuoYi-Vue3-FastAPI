import re
from contextvars import ContextVar, Token
from typing import Literal

from exceptions.exception import LoginException
from module_admin.entity.vo.user_vo import CurrentUserModel

# 定义上下文变量
# 存储当前请求的编译后的排除路由模式列表
current_exclude_patterns: ContextVar[
    list[dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]] | None
] = ContextVar('current_exclude_patterns', default=None)
# 存储当前用户信息
current_user: ContextVar[CurrentUserModel | None] = ContextVar('current_user', default=None)


class RequestContext:
    """
    请求上下文管理类，用于设置和清理上下文变量
    """

    @staticmethod
    def set_current_exclude_patterns(
        exclude_patterns: list[
            dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]
        ],
    ) -> Token:
        """
        设置当前请求的编译后的排除路由模式列表

        :param exclude_patterns: 编译后的排除路由模式列表
        :return: 上下文变量令牌，用于重置
        """
        return current_exclude_patterns.set(exclude_patterns)

    @staticmethod
    def get_current_exclude_patterns() -> list[
        dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]
    ]:
        """
        获取当前请求的编译后的排除路由模式列表

        :return: 编译后的排除路由模式列表
        """
        _exclude_patterns = current_exclude_patterns.get()
        if _exclude_patterns is None:
            _exclude_patterns = []
        return _exclude_patterns

    @staticmethod
    def set_current_user(user: CurrentUserModel) -> Token:
        """
        设置当前用户信息

        :param user: 用户信息
        :return: 上下文变量令牌，用于重置
        """
        return current_user.set(user)

    @staticmethod
    def get_current_user() -> CurrentUserModel:
        """
        获取当前用户信息

        :return: 用户信息
        """
        _current_user = current_user.get()
        if _current_user is None:
            raise LoginException(data='', message='当前用户信息为空，请检查是否已登录')
        return _current_user

    @staticmethod
    def reset_current_exclude_patterns(token: Token) -> None:
        """
        重置当前请求的编译后的排除路由模式列表

        :param token: 设置编译后的排除路由模式列表时返回的令牌
        """
        current_exclude_patterns.reset(token)

    @staticmethod
    def reset_current_user(token: Token) -> None:
        """
        重置当前用户信息

        :param token: 设置用户信息时返回的令牌
        """
        current_user.reset(token)

    @staticmethod
    def clear_all() -> None:
        """
        清除所有上下文变量
        """
        current_exclude_patterns.set(None)
        current_user.set(None)
