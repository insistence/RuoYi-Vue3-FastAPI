from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic_validation_decorator import ValidateFields
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.interface_auth import CheckRoleInterfaceAuth, CheckUserInterfaceAuth
from common.enums import BusinessType
from config.env import GenConfig
from config.get_db import get_db
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.login_service import LoginService
from module_generator.entity.vo.gen_vo import DeleteGenTableModel, EditGenTableModel, GenTablePageQueryModel
from module_generator.service.gen_service import GenTableColumnService, GenTableService
from utils.common_util import bytes2file_response
from utils.log_util import logger
from utils.page_util import PageResponseModel
from utils.response_util import ResponseUtil

gen_controller = APIRouter(prefix='/tool/gen', dependencies=[Depends(LoginService.get_current_user)])


@gen_controller.get(
    '/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:list'))]
)
async def get_gen_table_list(
    request: Request,
    gen_page_query: Annotated[GenTablePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取分页数据
    gen_page_query_result = await GenTableService.get_gen_table_list_services(query_db, gen_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=gen_page_query_result)


@gen_controller.get(
    '/db/list', response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:list'))]
)
async def get_gen_db_table_list(
    request: Request,
    gen_page_query: Annotated[GenTablePageQueryModel, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # 获取分页数据
    gen_page_query_result = await GenTableService.get_gen_db_table_list_services(query_db, gen_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=gen_page_query_result)


@gen_controller.post('/importTable', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:import'))])
@Log(title='代码生成', business_type=BusinessType.IMPORT)
async def import_gen_table(
    request: Request,
    tables: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    table_names = tables.split(',') if tables else []
    add_gen_table_list = await GenTableService.get_gen_db_table_list_by_name_services(query_db, table_names)
    add_gen_table_result = await GenTableService.import_gen_table_services(query_db, add_gen_table_list, current_user)
    logger.info(add_gen_table_result.message)

    return ResponseUtil.success(msg=add_gen_table_result.message)


@gen_controller.put('', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:edit'))])
@ValidateFields(validate_model='edit_gen_table')
@Log(title='代码生成', business_type=BusinessType.UPDATE)
async def edit_gen_table(
    request: Request,
    edit_gen_table: EditGenTableModel,
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    edit_gen_table.update_by = current_user.user.user_name
    edit_gen_table.update_time = datetime.now()
    await GenTableService.validate_edit(edit_gen_table)
    edit_gen_result = await GenTableService.edit_gen_table_services(query_db, edit_gen_table)
    logger.info(edit_gen_result.message)

    return ResponseUtil.success(msg=edit_gen_result.message)


@gen_controller.delete('/{table_ids}', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:remove'))])
@Log(title='代码生成', business_type=BusinessType.DELETE)
async def delete_gen_table(
    request: Request,
    table_ids: Annotated[str, Path(description='需要删除的代码生成业务表ID')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    delete_gen_table = DeleteGenTableModel(tableIds=table_ids)
    delete_gen_table_result = await GenTableService.delete_gen_table_services(query_db, delete_gen_table)
    logger.info(delete_gen_table_result.message)

    return ResponseUtil.success(msg=delete_gen_table_result.message)


@gen_controller.post('/createTable', dependencies=[Depends(CheckRoleInterfaceAuth('admin'))])
@Log(title='创建表', business_type=BusinessType.OTHER)
async def create_table(
    request: Request,
    sql: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUserModel, Depends(LoginService.get_current_user)],
) -> Response:
    create_table_result = await GenTableService.create_table_services(query_db, sql, current_user)
    logger.info(create_table_result.message)

    return ResponseUtil.success(msg=create_table_result.message)


@gen_controller.get('/batchGenCode', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:code'))])
@Log(title='代码生成', business_type=BusinessType.GENCODE)
async def batch_gen_code(
    request: Request,
    tables: Annotated[str, Query()],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    table_names = tables.split(',') if tables else []
    batch_gen_code_result = await GenTableService.batch_gen_code_services(query_db, table_names)
    logger.info('生成代码成功')

    return ResponseUtil.streaming(data=bytes2file_response(batch_gen_code_result))


@gen_controller.get('/genCode/{table_name}', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:code'))])
@Log(title='代码生成', business_type=BusinessType.GENCODE)
async def gen_code_local(
    request: Request,
    table_name: Annotated[str, Path(description='表名称')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    if not GenConfig.allow_overwrite:
        logger.error('【系统预设】不允许生成文件覆盖到本地')
        return ResponseUtil.error('【系统预设】不允许生成文件覆盖到本地')
    gen_code_local_result = await GenTableService.generate_code_services(query_db, table_name)
    logger.info(gen_code_local_result.message)

    return ResponseUtil.success(msg=gen_code_local_result.message)


@gen_controller.get('/{table_id}', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:query'))])
async def query_detail_gen_table(
    request: Request,
    table_id: Annotated[int, Path(description='表编号')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    gen_table = await GenTableService.get_gen_table_by_id_services(query_db, table_id)
    gen_tables = await GenTableService.get_gen_table_all_services(query_db)
    gen_columns = await GenTableColumnService.get_gen_table_column_list_by_table_id_services(query_db, table_id)
    gen_table_detail_result = {'info': gen_table, 'rows': gen_columns, 'tables': gen_tables}
    logger.info(f'获取table_id为{table_id}的信息成功')

    return ResponseUtil.success(data=gen_table_detail_result)


@gen_controller.get('/preview/{table_id}', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:preview'))])
async def preview_code(
    request: Request,
    table_id: Annotated[int, Path(description='表编号')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    preview_code_result = await GenTableService.preview_code_services(query_db, table_id)
    logger.info('获取预览代码成功')

    return ResponseUtil.success(data=preview_code_result)


@gen_controller.get('/synchDb/{table_name}', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:edit'))])
@Log(title='代码生成', business_type=BusinessType.UPDATE)
async def sync_db(
    request: Request,
    table_name: Annotated[str, Path(description='表名称')],
    query_db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    sync_db_result = await GenTableService.sync_db_services(query_db, table_name)
    logger.info(sync_db_result.message)

    return ResponseUtil.success(data=sync_db_result.message)
