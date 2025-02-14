import json
import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from typing import Dict, List, Set
from config.constant import GenConstant
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
            'importList': cls.get_import_list(gen_table),
            'permissionPrefix': cls.get_permission_prefix(module_name, business_name),
            'columns': gen_table.columns,
            'table': gen_table,
            'dicts': cls.get_dicts(gen_table),
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
        """设置菜单上下文"""
        options = gen_table.options
        params_obj = json.loads(options)
        context['parentMenuId'] = cls.get_parent_menu_id(params_obj)

    @classmethod
    def set_tree_context(cls, context: Dict, gen_table: GenTableModel):
        """设置树形结构上下文"""
        options = gen_table.options
        params_obj = json.loads(options)
        context['treeCode'] = cls.get_tree_code(params_obj)
        context['treeParentCode'] = cls.get_tree_parent_code(params_obj)
        context['treeName'] = cls.get_tree_name(params_obj)
        context['expandColumn'] = cls.get_expand_column(gen_table)

    @classmethod
    def set_sub_context(cls, context: Dict, gen_table: GenTableModel):
        """设置子表上下文"""
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
        context['subImportList'] = cls.get_import_list(sub_table)

    @classmethod
    def get_template_list(cls, tpl_category, tpl_web_type):
        """获取模板列表"""
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
    def get_file_name(cls, template, gen_table: GenTableModel):
        """根据模板生成文件名"""
        package_name = gen_table.package_name
        module_name = gen_table.module_name
        business_name = gen_table.business_name

        vue_path = cls.FRONTEND_PROJECT_PATH
        python_path = f"{cls.BACKEND_PROJECT_PATH}/{package_name.replace('.', '/')}"

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
        elif 'index.vue.jinja2' in template or 'index-tree.vue.j2' in template:
            return f'{vue_path}/views/{module_name}/{business_name}/index.vue'
        return ''

    @classmethod
    def get_package_prefix(cls, package_name: str):
        """获取包前缀"""
        return package_name[: package_name.rfind('.')]

    @classmethod
    def get_import_list(cls, gen_table: GenTableModel):
        """获取导入包列表"""
        columns = gen_table.columns or []
        sub_gen_table = gen_table.sub_table
        import_list = set()
        if sub_gen_table is not None:
            import_list.add('python.util.List')
        for column in columns:
            if not column.super_column and column.python_type in GenConstant.TYPE_DATE:
                import_list.add(f'from datetime import {column.python_type}')
            elif not column.super_column and column.python_type == GenConstant.TYPE_DECIMAL:
                import_list.add('from decimal import Decimal')
        return list(import_list)

    @classmethod
    def get_dicts(cls, gen_table: GenTableModel):
        """获取字典列表"""
        columns = gen_table.columns or []
        dicts = set()
        cls.add_dicts(dicts, columns)
        if gen_table.sub_table is not None:
            cls.add_dicts(dicts, gen_table.sub_table.columns)
        return ', '.join(dicts)

    @classmethod
    def add_dicts(cls, dicts: Set[str], columns: List[GenTableColumnModel]):
        """添加字典列表"""
        for column in columns:
            if (
                column.super_column
                and StringUtil.is_not_empty(column.dict_type)
                and StringUtil.equals_any_ignore_case(
                    column.html_type, [GenConstant.HTML_SELECT, GenConstant.HTML_RADIO, GenConstant.HTML_CHECKBOX]
                )
            ):
                dicts.add(f"'{column.dict_type}'")

    @classmethod
    def get_permission_prefix(cls, module_name: str, business_name: str):
        """获取权限前缀"""
        return f'{module_name}:{business_name}'

    @classmethod
    def get_parent_menu_id(cls, params_obj):
        """获取上级菜单ID"""
        if params_obj and params_obj.get(GenConstant.PARENT_MENU_ID):
            return params_obj.get(GenConstant.PARENT_MENU_ID)
        return cls.DEFAULT_PARENT_MENU_ID

    @classmethod
    def get_tree_code(cls, params_obj: Dict):
        """获取树编码"""
        if GenConstant.TREE_CODE in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_CODE))
        return ''

    @classmethod
    def get_tree_parent_code(cls, params_obj: Dict):
        """获取树父编码"""
        if GenConstant.TREE_PARENT_CODE in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_PARENT_CODE))
        return ''

    @classmethod
    def get_tree_name(cls, params_obj: Dict):
        """获取树名称"""
        if GenConstant.TREE_NAME in params_obj:
            return cls.to_camel_case(params_obj.get(GenConstant.TREE_NAME))
        return ''

    @classmethod
    def get_expand_column(cls, gen_table: GenTableModel):
        """获取展开列"""
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
        """将字符串转换为驼峰命名"""
        parts = text.split('_')
        return parts[0] + ''.join(word.capitalize() for word in parts[1:])

    @classmethod
    def get_sqlalchemy_type(cls, column_type: str):
        if '(' in column_type:
            column_type_list = column_type.split('(')
            sqlalchemy_type = (
                StringUtil.get_mapping_value_by_key_ignore_case(
                    GenConstant.MYSQL_TO_SQLALCHEMY_TYPE_MAPPING, column_type_list[0]
                )
                + '('
                + column_type_list[1]
            )
        else:
            sqlalchemy_type = StringUtil.get_mapping_value_by_key_ignore_case(
                GenConstant.MYSQL_TO_SQLALCHEMY_TYPE_MAPPING, column_type
            )

        return sqlalchemy_type
