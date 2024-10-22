from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size
from typing import List, Literal, Optional, Union
from module_admin.annotation.pydantic_annotation import as_query


class RoleModel(BaseModel):
    """
    角色表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = Field(default=None, description='角色ID')
    role_name: Optional[str] = Field(default=None, description='角色名称')
    role_key: Optional[str] = Field(default=None, description='角色权限字符串')
    role_sort: Optional[int] = Field(default=None, description='显示顺序')
    data_scope: Optional[Literal['1', '2', '3', '4', '5']] = Field(
        default=None,
        description='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限 5：仅本人数据权限）',
    )
    menu_check_strictly: Optional[Union[int, bool]] = Field(default=None, description='菜单树选择项是否关联显示')
    dept_check_strictly: Optional[Union[int, bool]] = Field(default=None, description='部门树选择项是否关联显示')
    status: Optional[Literal['0', '1']] = Field(default=None, description='角色状态（0正常 1停用）')
    del_flag: Optional[Literal['0', '2']] = Field(default=None, description='删除标志（0代表存在 2代表删除）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')
    admin: Optional[bool] = Field(default=False, description='是否为admin')

    @field_validator('menu_check_strictly', 'dept_check_strictly')
    @classmethod
    def check_filed_mapping(cls, v: Union[int, bool]) -> Union[int, bool]:
        if v == 1:
            v = True
        elif v == 0:
            v = False
        elif v is True:
            v = 1
        elif v is False:
            v = 0
        return v

    @model_validator(mode='after')
    def check_admin(self) -> 'RoleModel':
        if self.role_id == 1:
            self.admin = True
        else:
            self.admin = False
        return self

    @NotBlank(field_name='role_name', message='角色名称不能为空')
    @Size(field_name='role_name', min_length=0, max_length=30, message='角色名称长度不能超过30个字符')
    def get_role_name(self):
        return self.role_name

    @NotBlank(field_name='role_key', message='权限字符不能为空')
    @Size(field_name='role_key', min_length=0, max_length=100, message='权限字符长度不能超过100个字符')
    def get_role_key(self):
        return self.role_key

    @NotBlank(field_name='role_sort', message='显示顺序不能为空')
    def get_role_sort(self):
        return self.role_sort

    def validate_fields(self):
        self.get_role_name()
        self.get_role_key()
        self.get_role_sort()


class RoleMenuModel(BaseModel):
    """
    角色和菜单关联表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = Field(default=None, description='角色ID')
    menu_id: Optional[int] = Field(default=None, description='菜单ID')


class RoleDeptModel(BaseModel):
    """
    角色和部门关联表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = Field(default=None, description='角色ID')
    dept_id: Optional[int] = Field(default=None, description='部门ID')


class RoleQueryModel(RoleModel):
    """
    角色管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class RolePageQueryModel(RoleQueryModel):
    """
    角色管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class RoleMenuQueryModel(BaseModel):
    """
    角色菜单查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    menus: List = Field(default=[], description='菜单信息')
    checked_keys: List[int] = Field(default=[], description='已选择的菜单ID信息')


class RoleDeptQueryModel(BaseModel):
    """
    角色部门查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    depts: List = Field(default=[], description='部门信息')
    checked_keys: List[int] = Field(default=[], description='已选择的部门ID信息')


class AddRoleModel(RoleModel):
    """
    新增角色模型
    """

    dept_ids: List = Field(default=[], description='部门ID信息')
    menu_ids: List = Field(default=[], description='菜单ID信息')
    type: Optional[str] = Field(default=None, description='操作类型')


class DeleteRoleModel(BaseModel):
    """
    删除角色模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    role_ids: str = Field(description='需要删除的菜单ID')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
