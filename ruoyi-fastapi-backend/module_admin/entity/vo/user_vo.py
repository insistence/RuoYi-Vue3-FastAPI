from pydantic import BaseModel, ConfigDict, model_validator
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.entity.vo.role_vo import RoleModel
from module_admin.entity.vo.dept_vo import DeptModel
from module_admin.entity.vo.post_vo import PostModel
from module_admin.annotation.pydantic_annotation import as_query, as_form


class TokenData(BaseModel):
    """
    token解析结果
    """
    user_id: Union[int, None] = None


class UserModel(BaseModel):
    """
    用户表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = None
    dept_id: Optional[int] = None
    user_name: Optional[str] = None
    nick_name: Optional[str] = None
    user_type: Optional[str] = None
    email: Optional[str] = None
    phonenumber: Optional[str] = None
    sex: Optional[str] = None
    avatar: Optional[str] = None
    password: Optional[str] = None
    status: Optional[str] = None
    del_flag: Optional[str] = None
    login_ip: Optional[str] = None
    login_date: Optional[datetime] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None
    admin: Optional[bool] = False

    @model_validator(mode='after')
    def check_admin(self) -> 'UserModel':
        if self.user_id == 1:
            self.admin = True
        else:
            self.admin = False
        return self


class UserRoleModel(BaseModel):
    """
    用户和角色关联表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = None
    role_id: Optional[int] = None


class UserPostModel(BaseModel):
    """
    用户与岗位关联表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = None
    post_id: Optional[int] = None


class UserInfoModel(UserModel):
    post_ids: Optional[Union[str, None]] = None
    role_ids: Optional[Union[str, None]] = None
    dept: Optional[Union[DeptModel, None]] = None
    role: Optional[List[Union[RoleModel, None]]] = []


class CurrentUserModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    permissions: List
    roles: List
    user: Union[UserInfoModel, None]


class UserDetailModel(BaseModel):
    """
    获取用户详情信息响应模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    data: Optional[Union[UserInfoModel, None]] = None
    post_ids: Optional[List] = None
    posts: List[Union[PostModel, None]]
    role_ids: Optional[List] = None
    roles: List[Union[RoleModel, None]]


class UserProfileModel(BaseModel):
    """
    获取个人信息响应模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    data: Union[UserInfoModel, None]
    post_group: Union[str, None]
    role_group: Union[str, None]


class UserQueryModel(UserModel):
    """
    用户管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class UserPageQueryModel(UserQueryModel):
    """
    用户管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class AddUserModel(UserModel):
    """
    新增用户模型
    """
    role_ids: Optional[List] = []
    post_ids: Optional[List] = []
    type: Optional[str] = None


class EditUserModel(AddUserModel):
    """
    编辑用户模型
    """
    role: Optional[List] = []


class ResetUserModel(UserModel):
    """
    重置用户密码模型
    """
    old_password: Optional[str] = None
    sms_code: Optional[str] = None
    session_id: Optional[str] = None


class DeleteUserModel(BaseModel):
    """
    删除用户模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    user_ids: str
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None


class UserRoleQueryModel(UserModel):
    """
    用户角色关联管理不分页查询模型
    """
    role_id: Optional[int] = None


@as_query
class UserRolePageQueryModel(UserRoleQueryModel):
    """
    用户角色关联管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class SelectedRoleModel(RoleModel):
    """
    是否选择角色模型
    """
    flag: Optional[bool] = False


class UserRoleResponseModel(BaseModel):
    """
    用户角色关联管理列表返回模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    roles: List[Union[SelectedRoleModel, None]] = []
    user: UserInfoModel


@as_query
class CrudUserRoleModel(BaseModel):
    """
    新增、删除用户关联角色及角色关联用户模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    user_id: Optional[int] = None
    user_ids: Optional[str] = None
    role_id: Optional[int] = None
    role_ids: Optional[str] = None
