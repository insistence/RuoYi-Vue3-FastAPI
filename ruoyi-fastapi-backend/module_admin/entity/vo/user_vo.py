import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import Network, NotBlank, Size, Xss
from typing import List, Literal, Optional, Union
from exceptions.exception import ModelValidatorException
from module_admin.annotation.pydantic_annotation import as_query
from module_admin.entity.vo.dept_vo import DeptModel
from module_admin.entity.vo.post_vo import PostModel
from module_admin.entity.vo.role_vo import RoleModel


class TokenData(BaseModel):
    """
    token解析结果
    """

    user_id: Union[int, None] = Field(default=None, description='用户ID')


class UserModel(BaseModel):
    """
    用户表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = Field(default=None, description='用户ID')
    dept_id: Optional[int] = Field(default=None, description='部门ID')
    user_name: Optional[str] = Field(default=None, description='用户账号')
    nick_name: Optional[str] = Field(default=None, description='用户昵称')
    user_type: Optional[str] = Field(default=None, description='用户类型（00系统用户）')
    email: Optional[str] = Field(default=None, description='用户邮箱')
    phonenumber: Optional[str] = Field(default=None, description='手机号码')
    sex: Optional[Literal['0', '1', '2']] = Field(default=None, description='用户性别（0男 1女 2未知）')
    avatar: Optional[str] = Field(default=None, description='头像地址')
    password: Optional[str] = Field(default=None, description='密码')
    status: Optional[Literal['0', '1']] = Field(default=None, description='帐号状态（0正常 1停用）')
    del_flag: Optional[Literal['0', '2']] = Field(default=None, description='删除标志（0代表存在 2代表删除）')
    login_ip: Optional[str] = Field(default=None, description='最后登录IP')
    login_date: Optional[datetime] = Field(default=None, description='最后登录时间')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')
    admin: Optional[bool] = Field(default=False, description='是否为admin')

    @model_validator(mode='after')
    def check_password(self) -> 'UserModel':
        pattern = r"""^[^<>"'|\\]+$"""
        if self.password is None or re.match(pattern, self.password):
            return self
        else:
            raise ModelValidatorException(message='密码不能包含非法字符：< > " \' \\ |')

    @model_validator(mode='after')
    def check_admin(self) -> 'UserModel':
        if self.user_id == 1:
            self.admin = True
        else:
            self.admin = False
        return self

    @Xss(field_name='user_name', message='用户账号不能包含脚本字符')
    @NotBlank(field_name='user_name', message='用户账号不能为空')
    @Size(field_name='user_name', min_length=0, max_length=30, message='用户账号长度不能超过30个字符')
    def get_user_name(self):
        return self.user_name

    @Xss(field_name='nick_name', message='用户昵称不能包含脚本字符')
    @Size(field_name='nick_name', min_length=0, max_length=30, message='用户昵称长度不能超过30个字符')
    def get_nick_name(self):
        return self.nick_name

    @Network(field_name='email', field_type='EmailStr', message='邮箱格式不正确')
    @Size(field_name='email', min_length=0, max_length=50, message='邮箱长度不能超过50个字符')
    def get_email(self):
        return self.email

    @Size(field_name='phonenumber', min_length=0, max_length=11, message='手机号码长度不能超过11个字符')
    def get_phonenumber(self):
        return self.phonenumber

    def validate_fields(self):
        self.get_user_name()
        self.get_nick_name()
        self.get_email()
        self.get_phonenumber()


class UserRoleModel(BaseModel):
    """
    用户和角色关联表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = Field(default=None, description='用户ID')
    role_id: Optional[int] = Field(default=None, description='角色ID')


class UserPostModel(BaseModel):
    """
    用户与岗位关联表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    user_id: Optional[int] = Field(default=None, description='用户ID')
    post_id: Optional[int] = Field(default=None, description='岗位ID')


class UserInfoModel(UserModel):
    post_ids: Optional[Union[str, None]] = Field(default=None, description='岗位ID信息')
    role_ids: Optional[Union[str, None]] = Field(default=None, description='角色ID信息')
    dept: Optional[Union[DeptModel, None]] = Field(default=None, description='部门信息')
    role: Optional[List[Union[RoleModel, None]]] = Field(default=[], description='角色信息')


class CurrentUserModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    permissions: List = Field(description='权限信息')
    roles: List = Field(description='角色信息')
    user: Union[UserInfoModel, None] = Field(description='用户信息')


class UserDetailModel(BaseModel):
    """
    获取用户详情信息响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    data: Optional[Union[UserInfoModel, None]] = Field(default=None, description='用户信息')
    post_ids: Optional[List] = Field(default=None, description='岗位ID信息')
    posts: List[Union[PostModel, None]] = Field(description='岗位信息')
    role_ids: Optional[List] = Field(default=None, description='角色ID信息')
    roles: List[Union[RoleModel, None]] = Field(description='角色信息')


class UserProfileModel(BaseModel):
    """
    获取个人信息响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    data: Union[UserInfoModel, None] = Field(description='用户信息')
    post_group: Union[str, None] = Field(description='岗位信息')
    role_group: Union[str, None] = Field(description='角色信息')


class UserQueryModel(UserModel):
    """
    用户管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class UserPageQueryModel(UserQueryModel):
    """
    用户管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class AddUserModel(UserModel):
    """
    新增用户模型
    """

    role_ids: Optional[List] = Field(default=[], description='角色ID信息')
    post_ids: Optional[List] = Field(default=[], description='岗位ID信息')
    type: Optional[str] = Field(default=None, description='操作类型')


class EditUserModel(AddUserModel):
    """
    编辑用户模型
    """

    role: Optional[List] = Field(default=[], description='角色信息')


class ResetPasswordModel(BaseModel):
    """
    重置密码模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    old_password: Optional[str] = Field(default=None, description='旧密码')
    new_password: Optional[str] = Field(default=None, description='新密码')

    @model_validator(mode='after')
    def check_new_password(self) -> 'ResetPasswordModel':
        pattern = r"""^[^<>"'|\\]+$"""
        if self.new_password is None or re.match(pattern, self.new_password):
            return self
        else:
            raise ModelValidatorException(message='密码不能包含非法字符：< > " \' \\ |')


class ResetUserModel(UserModel):
    """
    重置用户密码模型
    """

    old_password: Optional[str] = Field(default=None, description='旧密码')
    sms_code: Optional[str] = Field(default=None, description='验证码')
    session_id: Optional[str] = Field(default=None, description='会话id')


class DeleteUserModel(BaseModel):
    """
    删除用户模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    user_ids: str = Field(description='需要删除的用户ID')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')


class UserRoleQueryModel(UserModel):
    """
    用户角色关联管理不分页查询模型
    """

    role_id: Optional[int] = Field(default=None, description='角色ID')


@as_query
class UserRolePageQueryModel(UserRoleQueryModel):
    """
    用户角色关联管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class SelectedRoleModel(RoleModel):
    """
    是否选择角色模型
    """

    flag: Optional[bool] = Field(default=False, description='选择标识')


class UserRoleResponseModel(BaseModel):
    """
    用户角色关联管理列表返回模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    roles: List[Union[SelectedRoleModel, None]] = Field(default=[], description='角色信息')
    user: UserInfoModel = Field(description='用户信息')


@as_query
class CrudUserRoleModel(BaseModel):
    """
    新增、删除用户关联角色及角色关联用户模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    user_id: Optional[int] = Field(default=None, description='用户ID')
    user_ids: Optional[str] = Field(default=None, description='用户ID信息')
    role_id: Optional[int] = Field(default=None, description='角色ID')
    role_ids: Optional[str] = Field(default=None, description='角色ID信息')
