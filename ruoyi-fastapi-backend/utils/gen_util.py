import re
from datetime import datetime
from typing import List
from config.constant import GenConstant
from config.env import GenConfig
from module_generator.entity.vo.gen_vo import GenTableColumnModel, GenTableModel
from utils.string_util import StringUtil


class GenUtils:
    """代码生成器工具类"""

    @classmethod
    def init_table(cls, gen_table: GenTableModel, oper_name: str) -> None:
        """
        初始化表信息

        param gen_table: 业务表对象
        param oper_name: 操作人
        :return:
        """
        gen_table.class_name = cls.convert_class_name(gen_table.table_name)
        gen_table.package_name = GenConfig.package_name
        gen_table.module_name = cls.get_module_name(GenConfig.package_name)
        gen_table.business_name = cls.get_business_name(gen_table.table_name)
        gen_table.function_name = cls.replace_text(gen_table.table_comment)
        gen_table.function_author = GenConfig.author
        gen_table.create_by = oper_name
        gen_table.create_time = datetime.now()
        gen_table.update_by = oper_name
        gen_table.update_time = datetime.now()

    @classmethod
    def init_column_field(cls, column: GenTableColumnModel, table: GenTableModel) -> None:
        """
        初始化列属性字段

        param column: 业务表字段对象
        param table: 业务表对象
        :return:
        """
        data_type = cls.get_db_type(column.column_type)
        column_name = column.column_name
        column.table_id = table.table_id
        column.create_by = table.create_by
        # 设置Python字段名
        column.python_field = cls.to_camel_case(column_name)
        # 设置默认类型
        column.python_type = StringUtil.get_mapping_value_by_key_ignore_case(
            GenConstant.DB_TO_PYTHON_TYPE_MAPPING, data_type
        )
        column.query_type = GenConstant.QUERY_EQ

        if cls.arrays_contains(GenConstant.COLUMNTYPE_STR, data_type) or cls.arrays_contains(
            GenConstant.COLUMNTYPE_TEXT, data_type
        ):
            # 字符串长度超过500设置为文本域
            column_length = cls.get_column_length(column.column_type)
            html_type = (
                GenConstant.HTML_TEXTAREA
                if column_length >= 500 or cls.arrays_contains(GenConstant.COLUMNTYPE_TEXT, data_type)
                else GenConstant.HTML_INPUT
            )
            column.html_type = html_type
        elif cls.arrays_contains(GenConstant.COLUMNTYPE_TIME, data_type):
            column.html_type = GenConstant.HTML_DATETIME
        elif cls.arrays_contains(GenConstant.COLUMNTYPE_NUMBER, data_type):
            column.html_type = GenConstant.HTML_INPUT

        # 插入字段（默认所有字段都需要插入）
        column.is_insert = GenConstant.REQUIRE

        # 编辑字段
        if not cls.arrays_contains(GenConstant.COLUMNNAME_NOT_EDIT, column_name) and not column.pk:
            column.is_edit = GenConstant.REQUIRE
        # 列表字段
        if not cls.arrays_contains(GenConstant.COLUMNNAME_NOT_LIST, column_name) and not column.pk:
            column.is_list = GenConstant.REQUIRE
        # 查询字段
        if not cls.arrays_contains(GenConstant.COLUMNNAME_NOT_QUERY, column_name) and not column.pk:
            column.is_query = GenConstant.REQUIRE

        # 查询字段类型
        if column_name.lower().endswith('name'):
            column.query_type = GenConstant.QUERY_LIKE
        # 状态字段设置单选框
        if column_name.lower().endswith('status'):
            column.html_type = GenConstant.HTML_RADIO
        # 类型&性别字段设置下拉框
        elif column_name.lower().endswith('type') or column_name.lower().endswith('sex'):
            column.html_type = GenConstant.HTML_SELECT
        # 图片字段设置图片上传控件
        elif column_name.lower().endswith('image'):
            column.html_type = GenConstant.HTML_IMAGE_UPLOAD
        # 文件字段设置文件上传控件
        elif column_name.lower().endswith('file'):
            column.html_type = GenConstant.HTML_FILE_UPLOAD
        # 内容字段设置富文本控件
        elif column_name.lower().endswith('content'):
            column.html_type = GenConstant.HTML_EDITOR
        
        column.create_by = table.create_by
        column.create_time = datetime.now()
        column.update_by = table.update_by
        column.update_time = datetime.now()

    @classmethod
    def arrays_contains(cls, arr: List[str], target_value: str) -> bool:
        """
        校验数组是否包含指定值

        param arr: 数组
        param target_value: 需要校验的值
        :return: 校验结果
        """
        return target_value in arr

    @classmethod
    def get_module_name(cls, package_name: str) -> str:
        """
        获取模块名

        param package_name: 包名
        :return: 模块名
        """
        return package_name.split('.')[-1]

    @classmethod
    def get_business_name(cls, table_name: str) -> str:
        """
        获取业务名

        param table_name: 业务表名
        :return: 业务名
        """
        return table_name.split('_')[-1]

    @classmethod
    def convert_class_name(cls, table_name: str) -> str:
        """
        表名转换成Python类名

        param table_name: 业务表名
        :return: Python类名
        """
        auto_remove_pre = GenConfig.auto_remove_pre
        table_prefix = GenConfig.table_prefix
        if auto_remove_pre and table_prefix:
            search_list = table_prefix.split(',')
            table_name = cls.replace_first(table_name, search_list)
        return StringUtil.convert_to_camel_case(table_name)

    @classmethod
    def replace_first(cls, replacement: str, search_list: List[str]) -> str:
        """
        批量替换前缀

        param replacement: 需要被替换的字符串
        param search_list: 可替换的字符串列表
        :return: 替换后的字符串
        """
        for search_string in search_list:
            if replacement.startswith(search_string):
                return replacement.replace(search_string, '', 1)
        return replacement

    @classmethod
    def replace_text(cls, text: str) -> str:
        """
        关键字替换

        param text: 需要被替换的字符串
        :return: 替换后的字符串
        """
        return re.sub(r'(?:表|若依)', '', text)

    @classmethod
    def get_db_type(cls, column_type: str) -> str:
        """
        获取数据库类型字段

        param column_type: 字段类型
        :return: 数据库类型
        """
        if '(' in column_type:
            return column_type.split('(')[0]
        return column_type

    @classmethod
    def get_column_length(cls, column_type: str) -> int:
        """
        获取字段长度

        param column_type: 字段类型
        :return: 字段长度
        """
        if '(' in column_type:
            length = len(column_type.split('(')[1].split(')')[0])
            return length
        return 0

    @classmethod
    def split_column_type(cls, column_type: str) -> List[str]:
        """
        拆分列类型

        param column_type: 字段类型
        :return: 拆分结果
        """
        if '(' in column_type and ')' in column_type:
            return column_type.split('(')[1].split(')')[0].split(',')
        return []

    @classmethod
    def to_camel_case(cls, text: str) -> str:
        """
        将字符串转换为驼峰命名

        param text: 需要转换的字符串
        :return: 驼峰命名
        """
        parts = text.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])
