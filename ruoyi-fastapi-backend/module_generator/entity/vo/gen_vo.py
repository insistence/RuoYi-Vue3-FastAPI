from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank

from common.constant import GenConstant
from utils.string_util import StringUtil


class GenTableBaseModel(BaseModel):
    """
    代码生成业务表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    table_id: int | None = Field(default=None, description='编号')
    table_name: str | None = Field(default=None, description='表名称')
    table_comment: str | None = Field(default=None, description='表描述')
    sub_table_name: str | None = Field(default=None, description='关联子表的表名')
    sub_table_fk_name: str | None = Field(default=None, description='子表关联的外键名')
    class_name: str | None = Field(default=None, description='实体类名称')
    tpl_category: str | None = Field(default=None, description='使用的模板（crud单表操作 tree树表操作）')
    tpl_web_type: str | None = Field(default=None, description='前端模板类型（element-ui模版 element-plus模版）')
    package_name: str | None = Field(default=None, description='生成包路径')
    module_name: str | None = Field(default=None, description='生成模块名')
    business_name: str | None = Field(default=None, description='生成业务名')
    function_name: str | None = Field(default=None, description='生成功能名')
    function_author: str | None = Field(default=None, description='生成功能作者')
    gen_type: Literal['0', '1'] | None = Field(default=None, description='生成代码方式（0zip压缩包 1自定义路径）')
    gen_path: str | None = Field(default=None, description='生成路径（不填默认项目路径）')
    options: str | None = Field(default=None, description='其它生成选项')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    remark: str | None = Field(default=None, description='备注')

    @NotBlank(field_name='table_name', message='表名称不能为空')
    def get_table_name(self) -> str | None:
        return self.table_name

    @NotBlank(field_name='table_comment', message='表描述不能为空')
    def get_table_comment(self) -> str | None:
        return self.table_comment

    @NotBlank(field_name='class_name', message='实体类名称不能为空')
    def get_class_name(self) -> str | None:
        return self.class_name

    @NotBlank(field_name='package_name', message='生成包路径不能为空')
    def get_package_name(self) -> str | None:
        return self.package_name

    @NotBlank(field_name='module_name', message='生成模块名不能为空')
    def get_module_name(self) -> str | None:
        return self.module_name

    @NotBlank(field_name='business_name', message='生成业务名不能为空')
    def get_business_name(self) -> str | None:
        return self.business_name

    @NotBlank(field_name='function_name', message='生成功能名不能为空')
    def get_function_name(self) -> str | None:
        return self.function_name

    @NotBlank(field_name='function_author', message='生成功能作者不能为空')
    def get_function_author(self) -> str | None:
        return self.function_author

    def validate_fields(self) -> None:
        self.get_table_name()
        self.get_table_comment()
        self.get_class_name()
        self.get_package_name()
        self.get_module_name()
        self.get_business_name()
        self.get_function_name()
        self.get_function_author()


class GenTableRowModel(GenTableBaseModel):
    """
    代码生成业务表行数据模型
    """

    columns: list['GenTableColumnBaseModel'] | None = Field(default=None, description='表列信息')


class GenTableDbRowModel(BaseModel):
    """
    代码生成业务表数据库行数据模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    table_name: str | None = Field(default=None, description='表名称')
    table_comment: str | None = Field(default=None, description='表描述')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class GenTableModel(GenTableBaseModel):
    """
    代码生成业务表模型
    """

    pk_column: Optional['GenTableColumnModel'] = Field(default=None, description='主键信息')
    sub_table: Optional['GenTableModel'] = Field(default=None, description='子表信息')
    columns: list['GenTableColumnModel'] | None = Field(default=None, description='表列信息')
    tree_code: str | None = Field(default=None, description='树编码字段')
    tree_parent_code: str | None = Field(default=None, description='树父编码字段')
    tree_name: str | None = Field(default=None, description='树名称字段')
    parent_menu_id: int | None = Field(default=None, description='上级菜单ID字段')
    parent_menu_name: str | None = Field(default=None, description='上级菜单名称字段')
    sub: bool | None = Field(default=None, description='是否为子表')
    tree: bool | None = Field(default=None, description='是否为树表')
    crud: bool | None = Field(default=None, description='是否为单表')

    @model_validator(mode='after')
    def check_some_is(self) -> 'GenTableModel':
        self.sub = bool(self.tpl_category and self.tpl_category == GenConstant.TPL_SUB)
        self.tree = bool(self.tpl_category and self.tpl_category == GenConstant.TPL_TREE)
        self.crud = bool(self.tpl_category and self.tpl_category == GenConstant.TPL_CRUD)
        return self


class EditGenTableModel(GenTableModel):
    """
    修改代码生成业务表模型
    """

    params: Optional['GenTableParamsModel'] = Field(default=None, description='业务表参数')


class GenTableParamsModel(BaseModel):
    """
    代码生成业务表参数模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    tree_code: str | None = Field(default=None, description='树编码字段')
    tree_parent_code: str | None = Field(default=None, description='树父编码字段')
    tree_name: str | None = Field(default=None, description='树名称字段')
    parent_menu_id: int | None = Field(default=None, description='上级菜单ID字段')


class GenTableQueryModel(GenTableBaseModel):
    """
    代码生成业务表不分页查询模型
    """

    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class GenTablePageQueryModel(GenTableQueryModel):
    """
    代码生成业务表分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class GenTableDetailModel(BaseModel):
    """
    代码生成业务表详情模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    info: GenTableModel | None = Field(default=None, description='业务表信息')
    rows: list['GenTableColumnModel'] | None = Field(default=None, description='表列信息')
    tables: list['GenTableModel'] | None = Field(default=None, description='所有业务表信息')


class DeleteGenTableModel(BaseModel):
    """
    删除代码生成业务表模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    table_ids: str = Field(description='需要删除的代码生成业务表ID')


class GenTableColumnBaseModel(BaseModel):
    """
    代码生成业务表字段对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    column_id: int | None = Field(default=None, description='编号')
    table_id: int | None = Field(default=None, description='归属表编号')
    column_name: str | None = Field(default=None, description='列名称')
    column_comment: str | None = Field(default=None, description='列描述')
    column_type: str | None = Field(default=None, description='列类型')
    python_type: str | None = Field(default=None, description='PYTHON类型')
    python_field: str | None = Field(default=None, description='PYTHON字段名')
    is_pk: str | None = Field(default=None, description='是否主键（1是）')
    is_increment: str | None = Field(default=None, description='是否自增（1是）')
    is_required: str | None = Field(default=None, description='是否必填（1是）')
    is_unique: str | None = Field(default=None, description='是否唯一（1是）')
    is_insert: str | None = Field(default=None, description='是否为插入字段（1是）')
    is_edit: str | None = Field(default=None, description='是否编辑字段（1是）')
    is_list: str | None = Field(default=None, description='是否列表字段（1是）')
    is_query: str | None = Field(default=None, description='是否查询字段（1是）')
    query_type: str | None = Field(default=None, description='查询方式（等于、不等于、大于、小于、范围）')
    html_type: str | None = Field(
        default=None, description='显示类型（文本框、文本域、下拉框、复选框、单选框、日期控件）'
    )
    dict_type: str | None = Field(default=None, description='字典类型')
    sort: int | None = Field(default=None, description='排序')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')

    @NotBlank(field_name='python_field', message='Python属性不能为空')
    def get_python_field(self) -> str | None:
        return self.python_field

    def validate_fields(self) -> None:
        self.get_python_field()


class GenTableColumnModel(GenTableColumnBaseModel):
    """
    代码生成业务表字段模型
    """

    cap_python_field: str | None = Field(default=None, description='字段大写形式')
    pk: bool | None = Field(default=None, description='是否主键')
    increment: bool | None = Field(default=None, description='是否自增')
    required: bool | None = Field(default=None, description='是否必填')
    unique: bool | None = Field(default=None, description='是否唯一')
    insert: bool | None = Field(default=None, description='是否为插入字段')
    edit: bool | None = Field(default=None, description='是否编辑字段')
    list: bool | None = Field(default=None, description='是否列表字段')
    query: bool | None = Field(default=None, description='是否查询字段')
    super_column: bool | None = Field(default=None, description='是否为基类字段')
    usable_column: bool | None = Field(default=None, description='是否为基类字段白名单')

    @model_validator(mode='after')
    def check_some_is(self) -> 'GenTableModel':
        self.cap_python_field = self.python_field[0].upper() + self.python_field[1:] if self.python_field else None
        self.pk = self.is_pk and self.is_pk == '1'
        self.increment = bool(self.is_increment and self.is_increment == '1')
        self.required = bool(self.is_required and self.is_required == '1')
        self.unique = bool(self.is_unique and self.is_unique == '1')
        self.insert = bool(self.is_insert and self.is_insert == '1')
        self.edit = bool(self.is_edit and self.is_edit == '1')
        self.list = bool(self.is_list and self.is_list == '1')
        self.query = bool(self.is_query and self.is_query == '1')
        self.super_column = bool(
            StringUtil.equals_any_ignore_case(self.python_field, GenConstant.TREE_ENTITY + GenConstant.BASE_ENTITY)
        )
        self.usable_column = bool(
            StringUtil.equals_any_ignore_case(self.python_field, ['parentId', 'orderNum', 'remark'])
        )
        return self


class GenTableColumnQueryModel(GenTableColumnBaseModel):
    """
    代码生成业务表字段不分页查询模型
    """

    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class GenTableColumnPageQueryModel(GenTableColumnQueryModel):
    """
    代码生成业务表字段分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteGenTableColumnModel(BaseModel):
    """
    删除代码生成业务表字段模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    column_ids: str = Field(description='需要删除的代码生成业务表字段ID')
