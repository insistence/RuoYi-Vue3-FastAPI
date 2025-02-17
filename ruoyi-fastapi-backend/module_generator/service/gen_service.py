import io
import json
import os
import re
import zipfile
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from config.constant import GenConstant
from config.env import GenConfig
from exceptions.exception import ServiceException
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_generator.entity.vo.gen_vo import (
    DeleteGenTableModel,
    EditGenTableModel,
    GenTableColumnModel,
    GenTableModel,
    GenTablePageQueryModel,
)
from module_generator.dao.gen_dao import GenTableColumnDao, GenTableDao
from utils.common_util import CamelCaseUtil
from utils.gen_util import GenUtils
from utils.template_util import TemplateInitializer, TemplateUtils


class GenTableService:
    """
    代码生成业务表服务层
    """

    @classmethod
    async def get_gen_table_list_services(
        cls, query_db: AsyncSession, query_object: GenTablePageQueryModel, is_page: bool = False
    ):
        """
        获取代码生成业务表列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 代码生成业务列表信息对象
        """
        gen_table_list_result = await GenTableDao.get_gen_table_list(query_db, query_object, is_page)

        return gen_table_list_result

    @classmethod
    async def get_gen_db_table_list_services(
        cls, query_db: AsyncSession, query_object: GenTablePageQueryModel, is_page: bool = False
    ):
        """
        获取数据库列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 数据库列表信息对象
        """
        gen_db_table_list_result = await GenTableDao.get_gen_db_table_list(query_db, query_object, is_page)

        return gen_db_table_list_result

    @classmethod
    async def get_gen_db_table_list_by_name_services(cls, query_db: AsyncSession, table_names: List[str]):
        """
        根据表名称组获取数据库列表信息service

        :param query_db: orm对象
        :param table_names: 表名称组
        :return: 数据库列表信息对象
        """
        gen_db_table_list_result = await GenTableDao.get_gen_db_table_list_by_names(query_db, table_names)

        return [GenTableModel(**gen_table) for gen_table in CamelCaseUtil.transform_result(gen_db_table_list_result)]

    @classmethod
    async def import_gen_table_services(
        cls, query_db: AsyncSession, gen_table_list: List[GenTableModel], current_user: CurrentUserModel
    ):
        """
        导入表结构service

        :param query_db: orm对象
        :param gen_table_list: 导入表列表
        :param current_user: 当前用户信息对象
        :return: 导入结果
        """
        try:
            for table in gen_table_list:
                table_name = table.table_name
                GenUtils.init_table(table, current_user.user.user_name)
                add_gen_table = await GenTableDao.add_gen_table_dao(query_db, table)
                if add_gen_table:
                    table.table_id = add_gen_table.table_id
                    gen_table_columns = await GenTableColumnDao.get_gen_db_table_columns_by_name(query_db, table_name)
                    for column in [
                        GenTableColumnModel(**gen_table_column)
                        for gen_table_column in CamelCaseUtil.transform_result(gen_table_columns)
                    ]:
                        GenUtils.init_column_field(column, table)
                        await GenTableColumnDao.add_gen_table_column_dao(query_db, column)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='导入成功')
        except Exception as e:
            await query_db.rollback()
            raise ServiceException(message=f'导入失败, {str(e)}')

    @classmethod
    async def edit_gen_table_services(cls, query_db: AsyncSession, page_object: EditGenTableModel):
        """
        编辑业务表信息service

        :param query_db: orm对象
        :param page_object: 编辑业务表对象
        :return: 编辑业务表校验结果
        """
        edit_gen_table = page_object.model_dump(exclude_unset=True, by_alias=True)
        gen_table_info = await cls.get_gen_table_by_id_services(query_db, page_object.table_id)
        if gen_table_info.table_id:
            try:
                edit_gen_table['options'] = json.dumps(edit_gen_table.get('params'))
                await GenTableDao.edit_gen_table_dao(query_db, edit_gen_table)
                for gen_table_column in page_object.columns:
                    gen_table_column.update_by = page_object.update_by
                    gen_table_column.update_time = datetime.now()
                    await GenTableColumnDao.edit_gen_table_column_dao(
                        query_db, gen_table_column.model_dump(by_alias=True)
                    )
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='更新成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='业务表不存在')

    @classmethod
    async def delete_gen_table_services(cls, query_db: AsyncSession, page_object: DeleteGenTableModel):
        """
        删除业务表信息service

        :param query_db: orm对象
        :param page_object: 删除业务表对象
        :return: 删除业务表校验结果
        """
        if page_object.table_ids:
            table_id_list = page_object.table_ids.split(',')
            try:
                for table_id in table_id_list:
                    await GenTableDao.delete_gen_table_dao(query_db, GenTableModel(tableId=table_id))
                    await GenTableColumnDao.delete_gen_table_column_by_table_id_dao(
                        query_db, GenTableColumnModel(tableId=table_id)
                    )
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入业务表id为空')

    @classmethod
    async def get_gen_table_by_id_services(cls, query_db: AsyncSession, table_id: int):
        """
        获取需要生成的业务表详细信息service

        :param query_db: orm对象
        :param table_id: 需要生成的业务表id
        :return: 需要生成的业务表id对应的信息
        """
        gen_table = await GenTableDao.get_gen_table_by_id(query_db, table_id)
        result = await cls.set_table_from_options(GenTableModel(**CamelCaseUtil.transform_result(gen_table)))

        return result

    @classmethod
    async def get_gen_table_all_services(cls, query_db: AsyncSession):
        """
        获取所有业务表信息service

        :param query_db: orm对象
        :return: 所有业务表信息
        """
        gen_table_all = await GenTableDao.get_gen_table_all(query_db)
        result = [GenTableModel(**gen_table) for gen_table in CamelCaseUtil.transform_result(gen_table_all)]

        return result

    @classmethod
    async def create_table_services(cls, query_db: AsyncSession, sql: str, current_user: CurrentUserModel):
        """
        创建表结构service

        :param query_db: orm对象
        :param sql: 建表语句
        :param current_user: 当前用户信息对象
        :return: 创建表结构结果
        """
        if cls.__is_valid_create_table(sql):
            try:
                table_names = re.findall(r'create\s+table\s+(\w+)', sql, re.IGNORECASE)
                await GenTableDao.create_table_by_sql_dao(query_db, sql)
                gen_table_list = await cls.get_gen_db_table_list_by_name_services(query_db, table_names)
                await cls.import_gen_table_services(query_db, gen_table_list, current_user)

                return CrudResponseModel(is_success=True, message='创建表结构成功')
            except Exception as e:
                raise ServiceException(message=f'创建表结构异常，详细错误信息：{str(e)}')
        else:
            raise ServiceException(message='建表语句不合法')

    @classmethod
    def __is_valid_create_table(cls, sql: str):
        """
        校验sql语句是否为合法的建表语句

        :param sql: sql语句
        :return: 校验结果
        """
        create_table_pattern = r'^\s*CREATE\s+TABLE\s+'
        if not re.search(create_table_pattern, sql, re.IGNORECASE):
            return False
        forbidden_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE']
        for keyword in forbidden_keywords:
            if re.search(rf'\b{keyword}\b', sql, re.IGNORECASE):
                return False
        return True

    @classmethod
    async def preview_code_services(cls, query_db: AsyncSession, table_id: int):
        """
        预览代码service

        :param query_db: orm对象
        :param table_id: 业务表id
        :return: 预览数据列表
        """
        gen_table = GenTableModel(
            **CamelCaseUtil.transform_result(await GenTableDao.get_gen_table_by_id(query_db, table_id))
        )
        await cls.set_sub_table(query_db, gen_table)
        await cls.set_pk_column(gen_table)
        env = TemplateInitializer.init_jinja2()
        context = TemplateUtils.prepare_context(gen_table)
        template_list = TemplateUtils.get_template_list(gen_table.tpl_category, gen_table.tpl_web_type)
        preview_code_result = {}
        for template in template_list:
            render_content = env.get_template(template).render(**context)
            preview_code_result[template] = render_content
        return preview_code_result

    @classmethod
    async def generate_code_services(cls, query_db: AsyncSession, table_name: str):
        """
        生成代码至指定路径service

        :param query_db: orm对象
        :param table_name: 业务表名称
        :return: 生成代码结果
        """
        env = TemplateInitializer.init_jinja2()
        render_info = await cls.__get_gen_render_info(query_db, table_name)
        for template in render_info[0]:
            try:
                render_content = env.get_template(template).render(**render_info[2])
                gen_path = cls.__get_gen_path(render_info[3], template)
                os.makedirs(os.path.dirname(gen_path), exist_ok=True)
                with open(gen_path, 'w', encoding='utf-8') as f:
                    f.write(render_content)
            except Exception as e:
                raise ServiceException(
                    message=f'渲染模板失败，表名：{render_info[3].table_name}，详细错误信息：{str(e)}'
                )

        return CrudResponseModel(is_success=True, message='生成代码成功')

    @classmethod
    async def batch_gen_code_services(cls, query_db: AsyncSession, table_names: List[str]):
        """
        批量生成代码service

        :param query_db: orm对象
        :param table_names: 业务表名称组
        :return: 下载代码结果
        """
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for table_name in table_names:
                env = TemplateInitializer.init_jinja2()
                render_info = await cls.__get_gen_render_info(query_db, table_name)
                for template_file, output_file in zip(render_info[0], render_info[1]):
                    render_content = env.get_template(template_file).render(**render_info[2])
                    zip_file.writestr(output_file, render_content)

        zip_data = zip_buffer.getvalue()
        zip_buffer.close()
        return zip_data

    @classmethod
    async def __get_gen_render_info(cls, query_db: AsyncSession, table_name: str):
        """
        获取生成代码渲染模板相关信息

        :param query_db: orm对象
        :param table_name: 业务表名称
        :return: 生成代码渲染模板相关信息
        """
        gen_table = GenTableModel(
            **CamelCaseUtil.transform_result(await GenTableDao.get_gen_table_by_name(query_db, table_name))
        )
        await cls.set_sub_table(query_db, gen_table)
        await cls.set_pk_column(gen_table)
        context = TemplateUtils.prepare_context(gen_table)
        template_list = TemplateUtils.get_template_list(gen_table.tpl_category, gen_table.tpl_web_type)
        output_files = [TemplateUtils.get_file_name(template, gen_table) for template in template_list]

        return [template_list, output_files, context, gen_table]

    @classmethod
    def __get_gen_path(cls, gen_table: GenTableModel, template: str):
        """
        根据GenTableModel对象和模板名称生成路径

        :param gen_table: GenTableModel对象
        :param template: 模板名称
        :return: 生成的路径
        """
        gen_path = gen_table.gen_path
        if gen_path == '/':
            return os.path.join(os.getcwd(), GenConfig.GEN_PATH, TemplateUtils.get_file_name(template, gen_table))
        else:
            return os.path.join(gen_path, TemplateUtils.get_file_name(template, gen_table))

    @classmethod
    async def sync_db_services(cls, query_db: AsyncSession, table_name: str):
        """
        同步数据库service

        :param query_db: orm对象
        :param table_name: 业务表名称
        :return: 同步数据库结果
        """
        gen_table = await GenTableDao.get_gen_table_by_name(query_db, table_name)
        table = GenTableModel(**CamelCaseUtil.transform_result(gen_table))
        table_columns = table.columns
        table_column_map = {column.column_name: column for column in table_columns}
        query_db_table_columns = await GenTableColumnDao.get_gen_db_table_columns_by_name(query_db, table_name)
        db_table_columns = [
            GenTableColumnModel(**column) for column in CamelCaseUtil.transform_result(query_db_table_columns)
        ]
        if not db_table_columns:
            raise ServiceException('同步数据失败，原表结构不存在')
        db_table_column_names = [column.column_name for column in db_table_columns]
        try:
            for column in db_table_columns:
                GenUtils.init_column_field(column, table)
                if column.column_name in table_column_map:
                    prev_column = table_column_map[column.column_name]
                    column.column_id = prev_column.column_id
                    if column.list:
                        column.dict_type = prev_column.dict_type
                        column.query_type = prev_column.query_type
                    if (
                        prev_column.is_required != ''
                        and not column.pk
                        and (column.insert or column.edit)
                        and (column.usable_column or column.super_column)
                    ):
                        column.is_required = prev_column.is_required
                        column.html_type = prev_column.html_type
                    await GenTableColumnDao.edit_gen_table_column_dao(query_db, column.model_dump(by_alias=True))
                else:
                    await GenTableColumnDao.add_gen_table_column_dao(query_db, column)
            del_columns = [column for column in table_columns if column.column_name not in db_table_column_names]
            if del_columns:
                for column in del_columns:
                    await GenTableColumnDao.delete_gen_table_column_by_column_id_dao(query_db, column)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='同步成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def set_sub_table(cls, query_db: AsyncSession, gen_table: GenTableModel):
        """
        设置主子表信息

        :param query_db: orm对象
        :param gen_table: 业务表信息
        :return:
        """
        if gen_table.sub_table_name:
            sub_table = await GenTableDao.get_gen_table_by_name(query_db, gen_table.sub_table_name)
            gen_table.sub_table = GenTableModel(**CamelCaseUtil.transform_result(sub_table))

    @classmethod
    async def set_pk_column(cls, gen_table: GenTableModel):
        """
        设置主键列信息

        :param gen_table: 业务表信息
        :return:
        """
        for column in gen_table.columns:
            if column.pk:
                gen_table.pk_column = column
                break
        if gen_table.pk_column is None:
            gen_table.pk_column = gen_table.columns[0]
        if gen_table.tpl_category == GenConstant.TPL_SUB:
            for column in gen_table.sub_table.columns:
                if column.pk:
                    gen_table.sub_table.pk_column = column
                    break
            if gen_table.sub_table.columns is None:
                gen_table.sub_table.pk_column = gen_table.sub_table.columns[0]

    @classmethod
    async def set_table_from_options(cls, gen_table: GenTableModel):
        """
        设置代码生成其他选项值

        :param gen_table: 生成对象
        :return: 设置后的生成对象
        """
        params_obj = json.loads(gen_table.options) if gen_table.options else None
        if params_obj:
            gen_table.tree_code = params_obj.get(GenConstant.TREE_CODE)
            gen_table.tree_parent_code = params_obj.get(GenConstant.TREE_PARENT_CODE)
            gen_table.tree_name = params_obj.get(GenConstant.TREE_NAME)
            gen_table.parent_menu_id = params_obj.get(GenConstant.PARENT_MENU_ID)
            gen_table.parent_menu_name = params_obj.get(GenConstant.PARENT_MENU_NAME)

        return gen_table

    @classmethod
    async def validate_edit(cls, edit_gen_table: EditGenTableModel):
        """
        编辑保存参数校验

        :param edit_gen_table: 编辑业务表对象
        """
        if edit_gen_table.tpl_category == GenConstant.TPL_TREE:
            params_obj = edit_gen_table.params.model_dump(by_alias=True)

            if GenConstant.TREE_CODE not in params_obj:
                raise ServiceException(message='树编码字段不能为空')
            elif GenConstant.TREE_PARENT_CODE not in params_obj:
                raise ServiceException(message='树父编码字段不能为空')
            elif GenConstant.TREE_NAME not in params_obj:
                raise ServiceException(message='树名称字段不能为空')
            elif edit_gen_table.tpl_category == GenConstant.TPL_SUB:
                if not edit_gen_table.sub_table_name:
                    raise ServiceException(message='关联子表的表名不能为空')
                elif not edit_gen_table.sub_table_fk_name:
                    raise ServiceException(message='子表关联的外键名不能为空')


class GenTableColumnService:
    """
    代码生成业务表字段服务层
    """

    @classmethod
    async def get_gen_table_column_list_by_table_id_services(cls, query_db: AsyncSession, table_id: int):
        """
        获取业务表字段列表信息service

        :param query_db: orm对象
        :param table_id: 业务表格id
        :return: 业务表字段列表信息对象
        """
        gen_table_column_list_result = await GenTableColumnDao.get_gen_table_column_list_by_table_id(query_db, table_id)

        return [
            GenTableColumnModel(**gen_table_column)
            for gen_table_column in CamelCaseUtil.transform_result(gen_table_column_list_result)
        ]
