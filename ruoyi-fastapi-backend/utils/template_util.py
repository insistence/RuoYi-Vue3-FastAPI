import json
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from typing import Dict, List, Set
from config.constant import GenConstant
from config.env import DataBaseConfig
from exceptions.exception import ServiceWarning
from module_generator.entity.vo.gen_vo import GenTableModel, GenTableColumnModel
from utils.common_util import CamelCaseUtil, SnakeCaseUtil
from utils.string_util import StringUtil


class TemplateInitializer:
    """
    模板引擎初始化类
    """

    @classmethod
    def init_jinja2(cls):
        """
        初始化 Jinja2 模板引擎

        :return: Jinja2 环境对象
        """
        try:
            template_dir = os.path.join(os.getcwd(), 'module_generator', 'templates')
            env = Environment(
                loader=FileSystemLoader(template_dir),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            env.filters.update(
                {
                    'camel_to_snake': SnakeCaseUtil.camel_to_snake,
                    'snake_to_camel': CamelCaseUtil.snake_to_camel,
                    'get_sqlalchemy_type': TemplateUtils.get_sqlalchemy_type,
                }
            )
            return env
        except Exception as e:
            raise RuntimeError(f'初始化Jinja2模板引擎失败: {e}')


class TemplateUtils:
    """
    模板工具类
    """

    # 项目路径
    FRONTEND_PROJECT_PATH = 'frontend'
    BACKEND_PROJECT_PATH = 'backend'
    DEFAULT_PARENT_MENU_ID = '3'

    @classmethod
    def prepare_context(cls, gen_table: GenTableModel):
        """
        准备模板变量

        :param gen_table: 生成表的配置信息
        :return: 模板上下文字典
        """
        if not gen_table.options:
            raise ServiceWarning(message='请先完善生成配置信息')
        class_name = gen_table.class_name
        module_name = gen_table.module_name
        business_name = gen_table.business_name
        package_name = gen_table.package_name
        tpl_category = gen_table.tpl_category
        function_name = gen_table.function_name

        context = {
            'tplCategory': tpl_category,
            'tableName': gen_table.table_name,
            'functionName': function_name if StringUtil.is_not_empty(function_name) else '【请填写功能名称】',
            'ClassName': class_name,
            'className': class_name.lower(),
            'moduleName': module_name,
            'BusinessName': business_name.capitalize(),
            'businessName': business_name,
            'basePackage': cls.get_package_prefix(package_name),
            'packageName': package_name,
            'author': gen_table.function_author,
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'pkColumn': gen_table.pk_column,
            'doImportList': cls.get_do_import_list(gen_table),
            'voImportList': cls.get_vo_import_list(gen_table),
            'permissionPrefix': cls.get_permission_prefix(module_name, business_name),
            'columns': gen_table.columns,
            'table': gen_table,
            'dicts': cls.get_dicts(gen_table),
            'dbType': DataBaseConfig.db_type,
        }

        # 设置菜单、树形结构、子表的上下文
        cls.set_menu_context(context, gen_table)
        if tpl_category == GenConstant.TPL_TREE:
            cls.set_tree_context(context, gen_table)
        if tpl_category == GenConstant.TPL_SUB:
            cls.set_sub_context(context, gen_table)

        return context

    @classmethod
    def set_menu_context(cls, context: Dict, gen_table: GenTableModel):
        """
        设置菜单上下文

        :param context: 模板上下文字典
        :param gen_table: 生成表的配置信息
        :return: 新的模板上下文字典
        """
        options = gen_table.options
        params_obj = json.loads(options)
        context['parentMenuId'] = cls.get_parent_menu_id(params_obj)

    @classmethod
    def set_tree_context(cls, context: Dict, gen_table: GenTableModel):
        """
        设置树形结构上下文

        :param context: 模板上下文字典
        :param gen_table: 生成表的配置信息
        :return: 新的模板上下文字典
        """
        options = gen_table.options
        params_obj = json.loads(options)
        context['treeCode'] = cls.get_tree_code(params_obj)
        context['treeParentCode'] = cls.get_tree_parent_code(params_obj)
        context['treeName'] = cls.get_tree_name(params_obj)
        context['expandColumn'] = cls.get_expand_column(gen_table)

    @classmethod
    def set_sub_context(cls, context: Dict, gen_table: GenTableModel):
        """
        设置子表上下文

        :param context: 模板上下文字典
        :param gen_table: 生成表的配置信息
        :return: 新的模板上下文字典
        """
        sub_table = gen_table.sub_table
        sub_table_name = gen_table.sub_table_name
        sub_table_fk_name = gen_table.sub_table_fk_name
        sub_class_name = sub_table.class_name
        sub_table_fk_class_name = StringUtil.convert_to_camel_case(sub_table_fk_name)
        context['subTable'] = sub_table
        context['subTableName'] = sub_table_name
        context['subTableFkName'] = sub_table_fk_name
        context['subTableFkClassName'] = sub_table_fk_class_name
        context['subTableFkclassName'] = sub_table_fk_class_name.lower()
        context['subClassName'] = sub_class_name
        context['subclassName'] = sub_class_name.lower()

    @classmethod
    def get_template_list(cls, tpl_category: str, tpl_web_type: str):
        """
        获取模板列表

        :param tpl_category: 生成模板类型
        :param tpl_web_type: 前端类型
        :return: 模板列表
        """
        use_web_type = 'vue'
        if tpl_web_type == 'element-plus':
            use_web_type = 'vue/v3'
        templates = [
            'python/controller.py.jinja2',
            'python/dao.py.jinja2',
            'python/do.py.jinja2',
            'python/service.py.jinja2',
            'python/vo.py.jinja2',
            'sql/sql.jinja2',
            'js/api.js.jinja2',
        ]
        if tpl_category == GenConstant.TPL_CRUD:
            templates.append(f'{use_web_type}/index.vue.jinja2')
        elif tpl_category == GenConstant.TPL_TREE:
            templates.append(f'{use_web_type}/index-tree.vue.jinja2')
        elif tpl_category == GenConstant.TPL_SUB:
            templates.append(f'{use_web_type}/index.vue.jinja2')
            # templates.append('python/sub-domain.python.jinja2')
        return templates

    @classmethod
    def get_file_name(cls, template: List[str], gen_table: GenTableModel):
        """
        根据模板生成文件名

        :param template: 模板列表
        :param gen_table: 生成表的配置信息
        :return: 模板生成文件名
        """
        package_name = gen_table.package_name
        module_name = gen_table.module_name
        business_name = gen_table.business_name

        vue_path = cls.FRONTEND_PROJECT_PATH
        python_path = f'{cls.BACKEND_PROJECT_PATH}/{package_name.replace(".", "/")}'

        if 'controller.py.jinja2' in template:
            return f'{python_path}/controller/{business_name}_controller.py'
        elif 'dao.py.jinja2' in template:
            return f'{python_path}/dao/{business_name}_dao.py'
        elif 'do.py.jinja2' in template:
            return f'{python_path}/entity/do/{business_name}_do.py'
        elif 'service.py.jinja2' in template:
            return f'{python_path}/service/{business_name}_service.py'
        elif 'vo.py.jinja2' in template:
            return f'{python_path}/entity/vo/{business_name}_vo.py'
        elif 'sql.jinja2' in template:
            return f'{cls.BACKEND_PROJECT_PATH}/sql/{business_name}_menu.sql'
        elif 'api.js.jinja2' in template:
            return f'{vue_path}/api/{module_name}/{business_name}.js'
        elif 'index.vue.jinja2' in template or 'index-tree.vue.jinja2' in template:
            return f'{vue_path}/views/{module_name}/{business_name}/index.vue'
        return ''

    @classmethod
    def get_package_prefix(cls, package_name: str):
        """
        获取包前缀

        :param package_name: 包名
        :return: 包前缀
        """
        return package_name[: package_name.rfind('.')]

    @classmethod
    def get_vo_import_list(cls, gen_table: GenTableModel):
        """
        获取vo模板导入包列表

        :param gen_table: 生成表的配置信息
        :return: 导入包列表
        """
        columns = gen_table.columns or []
        import_list = set()
        for column in columns:
            if column.python_type in GenConstant.TYPE_DATE:
                import_list.add(f'from datetime import {column.python_type}')
            elif column.python_type == GenConstant.TYPE_DECIMAL:
                import_list.add('from decimal import Decimal')
        if gen_table.sub:
            sub_columns = gen_table.sub_table.columns or []
            for sub_column in sub_columns:
                if sub_column.python_type in GenConstant.TYPE_DATE:
                    import_list.add(f'from datetime import {sub_column.python_type}')
                elif sub_column.python_type == GenConstant.TYPE_DECIMAL:
                    import_list.add('from decimal import Decimal')
        return cls.merge_same_imports(list(import_list), 'from datetime import')

    @classmethod
    def get_do_import_list(cls, gen_table: GenTableModel):
        """
        获取do模板导入包列表

        :param gen_table: 生成表的配置信息
        :return: 导入包列表
        """
        columns = gen_table.columns or []
        import_list = set()
        import_list.add('from sqlalchemy import Column')
        for column in columns:
            data_type = cls.get_db_type(column.column_type)
            if data_type in GenConstant.COLUMNTYPE_GEOMETRY:
                import_list.add('from geoalchemy2 import Geometry')
            import_list.add(
                f'from sqlalchemy import {StringUtil.get_mapping_value_by_key_ignore_case(GenConstant.DB_TO_SQLALCHEMY_TYPE_MAPPING, data_type)}'
            )
        if gen_table.sub:
            import_list.add('from sqlalchemy import ForeignKey')
            sub_columns = gen_table.sub_table.columns or []
            for sub_column in sub_columns:
                data_type = cls.get_db_type(sub_column.column_type)
                import_list.add(
                    f'from sqlalchemy import {StringUtil.get_mapping_value_by_key_ignore_case(GenConstant.DB_TO_SQLALCHEMY_TYPE_MAPPING, data_type)}'
                )
        return cls.merge_same_imports(list(import_list), 'from sqlalchemy import')

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
    def merge_same_imports(cls, imports: List[str], import_start: str) -> List[str]:
        """
        合并相同的导入语句

        :param imports: 导入语句列表
        :param import_start: 导入语句的起始字符串
        :return: 合并后的导入语句列表
        """
        merged_imports = []
        _imports = []
        for import_stmt in imports:
            if import_stmt.startswith(import_start):
                imported_items = import_stmt.split('import')[1].strip()
                _imports.extend(imported_items.split(', '))
            else:
                merged_imports.append(import_stmt)

        if _imports:
            merged_datetime_import = f'{import_start} {", ".join(_imports)}'
            merged_imports.append(merged_datetime_import)

        return merged_imports

    @classmethod
    def get_dicts(cls, gen_table: GenTableModel):
        """
        获取字典列表

        :param gen_table: 生成表的配置信息
        :return: 字典列表
        """
        columns = gen_table.columns or []
        dicts = set()
        cls.add_dicts(dicts, columns)
        if gen_table.sub_table is not None:
            cls.add_dicts(dicts, gen_table.sub_table.columns)
        return ', '.join(dicts)

    @classmethod
    def add_dicts(cls, dicts: Set[str], columns: List[GenTableColumnModel]):
        """
        添加字典列表

        :param dicts: 字典列表
        :param columns: 字段列表
        :return: 新的字典列表
        """
        for column in columns:
            if (
                not column.super_column
                and StringUtil.is_not_empty(column.dict_type)
                and StringUtil.equals_any_ignore_case(
                    column.html_type, [GenConstant.HTML_SELECT, GenConstant.HTML_RADIO, GenConstant.HTML_CHECKBOX]
                )
            ):
                dicts.add(f"'{column.dict_type}'")

    @classmethod
    def get_permission_prefix(cls, module_name: str, business_name: str):
        """
        获取权限前缀

        :param module_name: 模块名
        :param business_name: 业务名
        :return: 权限前缀
        """
        return f'{module_name}:{business_name}'

    @classmethod
    def get_parent_menu_id(cls, params_obj: Dict):
        """
        获取上级菜单ID

        :param params_obj: 菜单参数字典
        :return: 上级菜单ID
        """
        if params_obj and params_obj.get(GenConstant.PARENT_MENU_ID):
            return params_obj.get(GenConstant.PARENT_MENU_ID)
        return cls.DEFAULT_PARENT_MENU_ID

    @classmethod
    def get_tree_code(cls, params_obj: Dict):
        """
        获取树编码

        :param params_obj: 菜单参数字典
        :return: 树编码
        """
        if GenConstant.TREE_CODE in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_CODE))
        return ''

    @classmethod
    def get_tree_parent_code(cls, params_obj: Dict):
        """
        获取树父编码

        :param params_obj: 菜单参数字典
        :return: 树父编码
        """
        if GenConstant.TREE_PARENT_CODE in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_PARENT_CODE))
        return ''

    @classmethod
    def get_tree_name(cls, params_obj: Dict):
        """
        获取树名称

        :param params_obj: 菜单参数字典
        :return: 树名称
        """
        if GenConstant.TREE_NAME in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_NAME))
        return ''

    @classmethod
    def get_expand_column(cls, gen_table: GenTableModel):
        """
        获取展开列

        :param gen_table: 生成表的配置信息
        :return: 展开列
        """
        options = gen_table.options
        params_obj = json.loads(options)
        tree_name = params_obj.get(GenConstant.TREE_NAME)
        num = 0
        for column in gen_table.columns or []:
            if column.list:
                num += 1
                if column.column_name == tree_name:
                    break
        return num

    @classmethod
    def to_camel_case(cls, text: str) -> str:
        """
        将字符串转换为驼峰命名

        :param text: 待转换的字符串
        :return: 转换后的驼峰命名字符串
        """
        parts = text.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])

    @classmethod
    def get_sqlalchemy_type(cls, column_type: str):
        """
        获取SQLAlchemy类型

        :param column_type: 列类型
        :return: SQLAlchemy类型
        """
        if '(' in column_type:
            column_type_list = column_type.split('(')
            if column_type_list[0] in GenConstant.COLUMNTYPE_STR:
                sqlalchemy_type = (
                    StringUtil.get_mapping_value_by_key_ignore_case(
                        GenConstant.DB_TO_SQLALCHEMY_TYPE_MAPPING, column_type_list[0]
                    )
                    + '('
                    + column_type_list[1]
                )
            else:
                sqlalchemy_type = StringUtil.get_mapping_value_by_key_ignore_case(
                    GenConstant.DB_TO_SQLALCHEMY_TYPE_MAPPING, column_type_list[0]
                )
        else:
            sqlalchemy_type = StringUtil.get_mapping_value_by_key_ignore_case(
                GenConstant.DB_TO_SQLALCHEMY_TYPE_MAPPING, column_type
            )

        return sqlalchemy_type
