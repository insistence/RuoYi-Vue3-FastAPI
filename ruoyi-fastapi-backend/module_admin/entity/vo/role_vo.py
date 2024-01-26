from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class RoleModel(BaseModel):
    """
    角色表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = None
    role_name: Optional[str] = None
    role_key: Optional[str] = None
    role_sort: Optional[int] = None
    data_scope: Optional[str] = None
    menu_check_strictly: Optional[Union[int, bool]] = None
    dept_check_strictly: Optional[Union[int, bool]] = None
    status: Optional[str] = None
    del_flag: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None
    admin: Optional[bool] = False

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


class RoleMenuModel(BaseModel):
    """
    角色和菜单关联表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = None
    menu_id: Optional[int] = None


class RoleDeptModel(BaseModel):
    """
    角色和部门关联表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    role_id: Optional[int] = None
    dept_id: Optional[int] = None


class RoleQueryModel(RoleModel):
    """
    角色管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class RolePageQueryModel(RoleQueryModel):
    """
    角色管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class RoleMenuQueryModel(BaseModel):
    """
    角色菜单查询模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    menus: List = []
    checked_keys: List[int] = []


class RoleDeptQueryModel(BaseModel):
    """
    角色部门查询模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    depts: List = []
    checked_keys: List[int] = []


class AddRoleModel(RoleModel):
    """
    新增角色模型
    """
    dept_ids: List = []
    menu_ids: List = []
    type: Optional[str] = None


class DeleteRoleModel(BaseModel):
    """
    删除角色模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    role_ids: str
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
