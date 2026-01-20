from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import Network, NotBlank, Size


class DeptModel(BaseModel):
    """
    部门表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    dept_id: int | None = Field(default=None, description='部门id')
    parent_id: int | None = Field(default=None, description='父部门id')
    ancestors: str | None = Field(default=None, description='祖级列表')
    dept_name: str | None = Field(default=None, description='部门名称')
    order_num: int | None = Field(default=None, description='显示顺序')
    leader: str | None = Field(default=None, description='负责人')
    phone: str | None = Field(default=None, description='联系电话')
    email: str | None = Field(default=None, description='邮箱')
    status: Literal['0', '1'] | None = Field(default=None, description='部门状态（0正常 1停用）')
    del_flag: Literal['0', '2'] | None = Field(default=None, description='删除标志（0代表存在 2代表删除）')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')

    @NotBlank(field_name='dept_name', message='部门名称不能为空')
    @Size(field_name='dept_name', min_length=0, max_length=30, message='部门名称长度不能超过30个字符')
    def get_dept_name(self) -> str | None:
        return self.dept_name

    @NotBlank(field_name='order_num', message='显示顺序不能为空')
    def get_order_num(self) -> int | None:
        return self.order_num

    @Size(field_name='phone', min_length=0, max_length=11, message='联系电话长度不能超过11个字符')
    def get_phone(self) -> str | None:
        return self.phone

    @Network(field_name='email', field_type='EmailStr', message='邮箱格式不正确')
    @Size(field_name='email', min_length=0, max_length=50, message='邮箱长度不能超过50个字符')
    def get_email(self) -> str | None:
        return self.email

    def validate_fields(self) -> None:
        self.get_dept_name()
        self.get_order_num()
        self.get_phone()
        self.get_email()


class DeptQueryModel(DeptModel):
    """
    部门管理不分页查询模型
    """

    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class DeptTreeModel(BaseModel):
    """
    部门树模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    id: int = Field(description='部门id')
    label: str = Field(description='部门名称')
    parent_id: int = Field(description='父部门id')
    children: list['DeptTreeModel'] | None = Field(default=None, description='子部门树')


class DeleteDeptModel(BaseModel):
    """
    删除部门模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    dept_ids: str = Field(default=None, description='需要删除的部门id')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: str | None = Field(default=None, description='更新时间')
