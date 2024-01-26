from fastapi import Depends
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from exceptions.exception import PermissionException


class CheckUserInterfaceAuth:
    """
    校验当前用户是否具有相应的接口权限
    """
    def __init__(self, perm_str: str = 'common'):
        self.perm_str = perm_str

    def __call__(self, current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
        user_auth_list = current_user.permissions
        user_auth_list.append('common')
        if '*:*:*' in user_auth_list or self.perm_str in user_auth_list:
            return True
        raise PermissionException(data="", message="该用户无此接口权限")
