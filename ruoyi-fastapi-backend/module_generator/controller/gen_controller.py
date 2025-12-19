from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import RoleInterfaceAuthDependency, UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from config.env import GenConfig
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_generator.entity.vo.gen_vo import (
    DeleteGenTableModel,
    EditGenTableModel,
    GenTableDbRowModel,
    GenTableDetailModel,
    GenTablePageQueryModel,
    GenTableRowModel,
)
from module_generator.service.gen_service import GenTableColumnService, GenTableService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.response_util import ResponseUtil

gen_controller = APIRouterPro(prefix='/tool/gen', order_num=17, tags=['代码生成'], dependencies=[PreAuthDependency()])


@gen_controller.get(
    '/list',
    summary='获取代码生成表分页列表接口',
    description='用于获取代码生成表分页列表',
    response_model=PageResponseModel[GenTableRowModel],
    dependencies=[UserInterfaceAuthDependency('tool:gen:list')],
)
async def get_gen_table_list(
    request: Request,
    gen_page_query: Annotated[GenTablePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    gen_page_query_result = await GenTableService.get_gen_table_list_services(query_db, gen_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=gen_page_query_result)


@gen_controller.get(
    '/db/list',
    summary='获取数据库表分页列表接口',
    description='用于获取数据库表分页列表',
    response_model=PageResponseModel[GenTableDbRowModel],
    dependencies=[UserInterfaceAuthDependency('tool:gen:list')],
)
async def get_gen_db_table_list(
    request: Request,
    gen_page_query: Annotated[GenTablePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 获取分页数据
    gen_page_query_result = await GenTableService.get_gen_db_table_list_services(query_db, gen_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=gen_page_query_result)


@gen_controller.post(
    '/importTable',
    summary='导入数据库表接口',
    description='用于导入数据库表',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('tool:gen:import')],
)
@Log(title='代码生成', business_type=BusinessType.IMPORT)
async def import_gen_table(
    request: Request,
    tables: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    table_names = tables.split(',') if tables else []
    add_gen_table_list = await GenTableService.get_gen_db_table_list_by_name_services(query_db, table_names)
    add_gen_table_result = await GenTableService.import_gen_table_services(query_db, add_gen_table_list, current_user)
    logger.info(add_gen_table_result.message)

    return ResponseUtil.success(msg=add_gen_table_result.message)


@gen_controller.put(
    '',
    summary='编辑代码生成表接口',
    description='用于编辑代码生成表',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('tool:gen:edit')],
)
@ValidateFields(validate_model='edit_gen_table')
@Log(title='代码生成', business_type=BusinessType.UPDATE)
async def edit_gen_table(
    request: Request,
    edit_gen_table: EditGenTableModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_gen_table.update_by = current_user.user.user_name
    edit_gen_table.update_time = datetime.now()
    await GenTableService.validate_edit(edit_gen_table)
    edit_gen_result = await GenTableService.edit_gen_table_services(query_db, edit_gen_table)
    logger.info(edit_gen_result.message)

    return ResponseUtil.success(msg=edit_gen_result.message)


@gen_controller.delete(
    '/{table_ids}',
    summary='删除代码生成表接口',
    description='用于删除代码生成表',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('tool:gen:remove')],
)
@Log(title='代码生成', business_type=BusinessType.DELETE)
async def delete_gen_table(
    request: Request,
    table_ids: Annotated[str, Path(description='需要删除的代码生成业务表ID')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    delete_gen_table = DeleteGenTableModel(tableIds=table_ids)
    delete_gen_table_result = await GenTableService.delete_gen_table_services(query_db, delete_gen_table)
    logger.info(delete_gen_table_result.message)

    return ResponseUtil.success(msg=delete_gen_table_result.message)


@gen_controller.post(
    '/createTable',
    summary='创建数据库表接口',
    description='用于创建数据库表',
    response_model=ResponseBaseModel,
    dependencies=[RoleInterfaceAuthDependency('admin')],
)
@Log(title='创建表', business_type=BusinessType.OTHER)
async def create_table(
    request: Request,
    sql: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    create_table_result = await GenTableService.create_table_services(query_db, sql, current_user)
    logger.info(create_table_result.message)

    return ResponseUtil.success(msg=create_table_result.message)


@gen_controller.get(
    '/batchGenCode',
    summary='生成代码文件接口',
    description='用于生成代码文件',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回生成的代码文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('tool:gen:code')],
)
@Log(title='代码生成', business_type=BusinessType.GENCODE)
async def batch_gen_code(
    request: Request,
    tables: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    table_names = tables.split(',') if tables else []
    batch_gen_code_result = await GenTableService.batch_gen_code_services(query_db, table_names)
    logger.info('生成代码成功')

    return ResponseUtil.streaming(data=bytes2file_response(batch_gen_code_result))


@gen_controller.get(
    '/genCode/{table_name}',
    summary='生成代码文件到本地接口',
    description='用于生成代码文件到本地',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('tool:gen:code')],
)
@Log(title='代码生成', business_type=BusinessType.GENCODE)
async def gen_code_local(
    request: Request,
    table_name: Annotated[str, Path(description='表名称')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not GenConfig.allow_overwrite:
        logger.error('【系统预设】不允许生成文件覆盖到本地')
        return ResponseUtil.error('【系统预设】不允许生成文件覆盖到本地')
    gen_code_local_result = await GenTableService.generate_code_services(query_db, table_name)
    logger.info(gen_code_local_result.message)

    return ResponseUtil.success(msg=gen_code_local_result.message)


@gen_controller.get(
    '/{table_id}',
    summary='获取代码生成表详情接口',
    description='用于获取指定代码生成表的详细信息',
    response_model=DataResponseModel[GenTableDetailModel],
    dependencies=[UserInterfaceAuthDependency('tool:gen:query')],
)
async def query_detail_gen_table(
    request: Request,
    table_id: Annotated[int, Path(description='表编号')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    gen_table = await GenTableService.get_gen_table_by_id_services(query_db, table_id)
    gen_tables = await GenTableService.get_gen_table_all_services(query_db)
    gen_columns = await GenTableColumnService.get_gen_table_column_list_by_table_id_services(query_db, table_id)
    gen_table_detail_result = {'info': gen_table, 'rows': gen_columns, 'tables': gen_tables}
    logger.info(f'获取table_id为{table_id}的信息成功')

    return ResponseUtil.success(data=gen_table_detail_result)


@gen_controller.get(
    '/preview/{table_id}',
    summary='预览生成的代码接口',
    description='用于预览指定代码生成表生成的代码',
    response_model=DataResponseModel[dict[str, str]],
    dependencies=[UserInterfaceAuthDependency('tool:gen:preview')],
)
async def preview_code(
    request: Request,
    table_id: Annotated[int, Path(description='表编号')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    preview_code_result = await GenTableService.preview_code_services(query_db, table_id)
    logger.info('获取预览代码成功')

    return ResponseUtil.success(data=preview_code_result)


@gen_controller.get(
    '/synchDb/{table_name}',
    summary='同步数据库接口',
    description='用于同步指定数据库信息到指定代码生成表',
    response_model=DataResponseModel[str],
    dependencies=[UserInterfaceAuthDependency('tool:gen:edit')],
)
@Log(title='代码生成', business_type=BusinessType.UPDATE)
async def sync_db(
    request: Request,
    table_name: Annotated[str, Path(description='表名称')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    sync_db_result = await GenTableService.sync_db_services(query_db, table_name)
    logger.info(sync_db_result.message)

    return ResponseUtil.success(data=sync_db_result.message)
