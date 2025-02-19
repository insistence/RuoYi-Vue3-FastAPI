from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank
from typing import List, Literal, Optional
from config.constant import GenConstant
from module_admin.annotation.pydantic_annotation import as_query
from utils.string_util import StringUtil


class GenTableBaseModel(BaseModel):
    """
    代码生成业务表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    table_id: Optional[int] = Field(default=None, description='编号')
    table_name: Optional[str] = Field(default=None, description='表名称')
    table_comment: Optional[str] = Field(default=None, description='表描述')
    sub_table_name: Optional[str] = Field(default=None, description='关联子表的表名')
    sub_table_fk_name: Optional[str] = Field(default=None, description='子表关联的外键名')
    class_name: Optional[str] = Field(default=None, description='实体类名称')
    tpl_category: Optional[str] = Field(default=None, description='使用的模板（crud单表操作 tree树表操作）')
    tpl_web_type: Optional[str] = Field(default=None, description='前端模板类型（element-ui模版 element-plus模版）')
    package_name: Optional[str] = Field(default=None, description='生成包路径')
    module_name: Optional[str] = Field(default=None, description='生成模块名')
    business_name: Optional[str] = Field(default=None, description='生成业务名')
    function_name: Optional[str] = Field(default=None, description='生成功能名')
    function_author: Optional[str] = Field(default=None, description='生成功能作者')
    gen_type: Optional[Literal['0', '1']] = Field(default=None, description='生成代码方式（0zip压缩包 1自定义路径）')
    gen_path: Optional[str] = Field(default=None, description='生成路径（不填默认项目路径）')
    options: Optional[str] = Field(default=None, description='其它生成选项')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注')

    @NotBlank(field_name='table_name', message='表名称不能为空')
    def get_table_name(self):
        return self.table_name

    @NotBlank(field_name='table_comment', message='表描述不能为空')
    def get_table_comment(self):
        return self.table_comment

    @NotBlank(field_name='class_name', message='实体类名称不能为空')
    def get_class_name(self):
        return self.class_name

    @NotBlank(field_name='package_name', message='生成包路径不能为空')
    def get_package_name(self):
        return self.package_name

    @NotBlank(field_name='module_name', message='生成模块名不能为空')
    def get_module_name(self):
        return self.module_name

    @NotBlank(field_name='business_name', message='生成业务名不能为空')
    def get_business_name(self):
        return self.business_name

    @NotBlank(field_name='function_name', message='生成功能名不能为空')
    def get_function_name(self):
        return self.function_name

    @NotBlank(field_name='function_author', message='生成功能作者不能为空')
    def get_function_author(self):
        return self.function_author

    def validate_fields(self):
        self.get_table_name()
        self.get_table_comment()
        self.get_class_name()
        self.get_package_name()
        self.get_module_name()
        self.get_business_name()
        self.get_function_name()
        self.get_function_author()


class GenTableModel(GenTableBaseModel):
    """
    代码生成业务表模型
    """

    pk_column: Optional['GenTableColumnModel'] = Field(default=None, description='主键信息')
    sub_table: Optional['GenTableModel'] = Field(default=None, description='子表信息')
    columns: Optional[List['GenTableColumnModel']] = Field(default=None, description='表列信息')
    tree_code: Optional[str] = Field(default=None, description='树编码字段')
    tree_parent_code: Optional[str] = Field(default=None, description='树父编码字段')
    tree_name: Optional[str] = Field(default=None, description='树名称字段')
    parent_menu_id: Optional[int] = Field(default=None, description='上级菜单ID字段')
    parent_menu_name: Optional[str] = Field(default=None, description='上级菜单名称字段')
    sub: Optional[bool] = Field(default=None, description='是否为子表')
    tree: Optional[bool] = Field(default=None, description='是否为树表')
    crud: Optional[bool] = Field(default=None, description='是否为单表')

    @model_validator(mode='after')
    def check_some_is(self) -> 'GenTableModel':
        self.sub = True if self.tpl_category and self.tpl_category == GenConstant.TPL_SUB else False
        self.tree = True if self.tpl_category and self.tpl_category == GenConstant.TPL_TREE else False
        self.crud = True if self.tpl_category and self.tpl_category == GenConstant.TPL_CRUD else False
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

    tree_code: Optional[str] = Field(default=None, description='树编码字段')
    tree_parent_code: Optional[str] = Field(default=None, description='树父编码字段')
    tree_name: Optional[str] = Field(default=None, description='树名称字段')
    parent_menu_id: Optional[int] = Field(default=None, description='上级菜单ID字段')


class GenTableQueryModel(GenTableBaseModel):
    """
    代码生成业务表不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class GenTablePageQueryModel(GenTableQueryModel):
    """
    代码生成业务表分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


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

    column_id: Optional[int] = Field(default=None, description='编号')
    table_id: Optional[int] = Field(default=None, description='归属表编号')
    column_name: Optional[str] = Field(default=None, description='列名称')
    column_comment: Optional[str] = Field(default=None, description='列描述')
    column_type: Optional[str] = Field(default=None, description='列类型')
    python_type: Optional[str] = Field(default=None, description='PYTHON类型')
    python_field: Optional[str] = Field(default=None, description='PYTHON字段名')
    is_pk: Optional[str] = Field(default=None, description='是否主键（1是）')
    is_increment: Optional[str] = Field(default=None, description='是否自增（1是）')
    is_required: Optional[str] = Field(default=None, description='是否必填（1是）')
    is_unique: Optional[str] = Field(default=None, description='是否唯一（1是）')
    is_insert: Optional[str] = Field(default=None, description='是否为插入字段（1是）')
    is_edit: Optional[str] = Field(default=None, description='是否编辑字段（1是）')
    is_list: Optional[str] = Field(default=None, description='是否列表字段（1是）')
    is_query: Optional[str] = Field(default=None, description='是否查询字段（1是）')
    query_type: Optional[str] = Field(default=None, description='查询方式（等于、不等于、大于、小于、范围）')
    html_type: Optional[str] = Field(
        default=None, description='显示类型（文本框、文本域、下拉框、复选框、单选框、日期控件）'
    )
    dict_type: Optional[str] = Field(default=None, description='字典类型')
    sort: Optional[int] = Field(default=None, description='排序')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')

    @NotBlank(field_name='python_field', message='Python属性不能为空')
    def get_python_field(self):
        return self.python_field

    def validate_fields(self):
        self.get_python_field()


class GenTableColumnModel(GenTableColumnBaseModel):
    """
    代码生成业务表字段模型
    """

    cap_python_field: Optional[str] = Field(default=None, description='字段大写形式')
    pk: Optional[bool] = Field(default=None, description='是否主键')
    increment: Optional[bool] = Field(default=None, description='是否自增')
    required: Optional[bool] = Field(default=None, description='是否必填')
    unique: Optional[bool] = Field(default=None, description='是否唯一')
    insert: Optional[bool] = Field(default=None, description='是否为插入字段')
    edit: Optional[bool] = Field(default=None, description='是否编辑字段')
    list: Optional[bool] = Field(default=None, description='是否列表字段')
    query: Optional[bool] = Field(default=None, description='是否查询字段')
    super_column: Optional[bool] = Field(default=None, description='是否为基类字段')
    usable_column: Optional[bool] = Field(default=None, description='是否为基类字段白名单')

    @model_validator(mode='after')
    def check_some_is(self) -> 'GenTableModel':
        self.cap_python_field = self.python_field[0].upper() + self.python_field[1:] if self.python_field else None
        self.pk = True if self.is_pk and self.is_pk == '1' else False
        self.increment = True if self.is_increment and self.is_increment == '1' else False
        self.required = True if self.is_required and self.is_required == '1' else False
        self.unique = True if self.is_unique and self.is_unique == '1' else False
        self.insert = True if self.is_insert and self.is_insert == '1' else False
        self.edit = True if self.is_edit and self.is_edit == '1' else False
        self.list = True if self.is_list and self.is_list == '1' else False
        self.query = True if self.is_query and self.is_query == '1' else False
        self.super_column = (
            True
            if StringUtil.equals_any_ignore_case(self.python_field, GenConstant.TREE_ENTITY + GenConstant.BASE_ENTITY)
            else False
        )
        self.usable_column = (
            True if StringUtil.equals_any_ignore_case(self.python_field, ['parentId', 'orderNum', 'remark']) else False
        )
        return self


class GenTableColumnQueryModel(GenTableColumnBaseModel):
    """
    代码生成业务表字段不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
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
