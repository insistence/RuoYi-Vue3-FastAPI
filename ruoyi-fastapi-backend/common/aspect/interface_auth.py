from typing import Union

from fastapi import Depends, Request, params

from common.context import RequestContext
from exceptions.exception import PermissionException
from utils.dependency_util import DependencyUtil


class CheckUserInterfaceAuth:
    """
    校验当前用户是否具有相应的接口权限
    """

    def __init__(self, perm: Union[str, list], is_strict: bool = False) -> None:
        """
        校验当前用户是否具有相应的接口权限

        :param perm: 权限标识
        :param is_strict: 当传入的权限标识是list类型时，是否开启严格模式，开启表示会校验列表中的每一个权限标识，所有的校验结果都需要为True才会通过
        """
        self.perm = perm
        self.is_strict = is_strict

    def __call__(self, request: Request) -> bool:
        DependencyUtil.check_exclude_routes(
            request, err_msg='当前路由不在认证规则内，不可使用CheckUserInterfaceAuth依赖项'
        )
        current_user = RequestContext.get_current_user()
        user_auth_list = current_user.permissions
        if '*:*:*' in user_auth_list:
            return True
        if isinstance(self.perm, str) and self.perm in user_auth_list:
            return True
        if isinstance(self.perm, list):
            if self.is_strict:
                if all(perm_str in user_auth_list for perm_str in self.perm):
                    return True
            elif any(perm_str in user_auth_list for perm_str in self.perm):
                return True
        raise PermissionException(data='', message='该用户无此接口权限')


class CheckRoleInterfaceAuth:
    """
    根据角色校验当前用户是否具有相应的接口权限
    """

    def __init__(self, role_key: Union[str, list], is_strict: bool = False) -> None:
        """
        根据角色校验当前用户是否具有相应的接口权限

        :param role_key: 角色标识
        :param is_strict: 当传入的角色标识是list类型时，是否开启严格模式，开启表示会校验列表中的每一个角色标识，所有的校验结果都需要为True才会通过
        """
        self.role_key = role_key
        self.is_strict = is_strict

    def __call__(self, request: Request) -> bool:
        DependencyUtil.check_exclude_routes(
            request, err_msg='当前路由不在认证规则内，不可使用CheckRoleInterfaceAuth依赖项'
        )
        current_user = RequestContext.get_current_user()
        user_role_list = current_user.user.role
        user_role_key_list = [role.role_key for role in user_role_list]
        if isinstance(self.role_key, str) and self.role_key in user_role_key_list:
            return True
        if isinstance(self.role_key, list):
            if self.is_strict:
                if all(role_key_str in user_role_key_list for role_key_str in self.role_key):
                    return True
            elif any(role_key_str in user_role_key_list for role_key_str in self.role_key):
                return True
        raise PermissionException(data='', message='该用户无此接口权限')


def UserInterfaceAuthDependency(perm: Union[str, list], is_strict: bool = False) -> params.Depends:  # noqa: N802
    """
    根据权限标识校验当前用户接口权限依赖

    :param perm: 权限标识
    :param is_strict: 当传入的权限标识是list类型时，是否开启严格模式，开启表示会校验列表中的每一个权限标识，所有的校验结果都需要为True才会通过
    :return: 根据权限标识校验当前用户接口权限依赖
    """
    return Depends(CheckUserInterfaceAuth(perm, is_strict))


def RoleInterfaceAuthDependency(role_key: Union[str, list], is_strict: bool = False) -> params.Depends:  # noqa: N802
    """
    根据角色校验当前用户接口权限依赖

    :param role_key: 角色标识
    :param is_strict: 当传入的角色标识是list类型时，是否开启严格模式，开启表示会校验列表中的每一个角色标识，所有的校验结果都需要为True才会通过
    :return: 根据角色校验当前用户接口权限依赖
    """
    return Depends(CheckRoleInterfaceAuth(role_key, is_strict))
