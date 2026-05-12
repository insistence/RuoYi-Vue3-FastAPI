from typing import Any

from cli.exit_codes import ARGUMENT_ERROR, DATABASE_ERROR, RUNTIME_ERROR

from .gateway import GenInfrastructureGateway
from .support import GenDomainSupport


class GenRuntimeService:
    """
    代码生成运行时服务。

    该服务作为代码生成运行时 facade，对外统一暴露业务表、数据库物理表、
    建表 SQL、代码预览、导出与数据库同步等入口。

    :param infrastructure_gateway: 代码生成基础设施网关
    :param domain_support: 代码生成领域支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: GenInfrastructureGateway | None = None,
        domain_support: GenDomainSupport | None = None,
    ) -> None:
        """
        初始化代码生成运行时服务。

        :param infrastructure_gateway: 代码生成基础设施网关
        :param domain_support: 代码生成领域支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or GenInfrastructureGateway()
        self.domain_support = domain_support or GenDomainSupport(self.infrastructure_gateway)

    async def import_tables(self, table_names: list[str], *, dry_run: bool = False) -> dict[str, Any]:
        """
        导入数据库表到代码生成业务表。

        :param table_names: 待导入表名列表
        :param dry_run: 是否仅演练执行
        :return: 导入结果
        """
        normalized_table_names = self.domain_support.normalize_table_names(table_names)
        if not normalized_table_names:
            return {'ok': False, 'message': '至少需要传入一个表名', 'exit_code': ARGUMENT_ERROR}

        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        service_exception = self.infrastructure_gateway.get_service_exception_class()
        try:
            async with async_session_local() as session:
                gen_table_list = await gen_table_service.get_gen_db_table_list_by_name_services(
                    session,
                    normalized_table_names,
                )
                matched_table_names = [gen_table.table_name for gen_table in gen_table_list if gen_table.table_name]
                missing_table_names = [
                    table_name for table_name in normalized_table_names if table_name not in matched_table_names
                ]

                if dry_run:
                    return {
                        'ok': True,
                        'message': '导入表结构演练完成，未执行实际写入',
                        'dryRun': True,
                        'requestedTables': normalized_table_names,
                        'matchedTables': matched_table_names,
                        'missingTables': missing_table_names,
                    }

                result = await gen_table_service.import_gen_table_services(
                    session,
                    gen_table_list,
                    self.domain_support.build_cli_current_user(),
                )
        except service_exception as exc:
            return {'ok': False, 'message': '导入表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '导入表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        return {
            'ok': bool(result.is_success),
            'message': result.message,
            'requestedTables': normalized_table_names,
        }

    async def list_gen_tables(
        self,
        *,
        table_name: str = '',
        table_comment: str = '',
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询代码生成业务表列表。

        :param table_name: 表名称过滤条件
        :param table_comment: 表描述过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 查询结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        try:
            gen_vo_module = self.infrastructure_gateway.get_gen_vo_module()
            query_model = gen_vo_module.GenTablePageQueryModel(
                tableName=table_name or None,
                tableComment=table_comment or None,
                pageNum=page_num,
                pageSize=page_size,
            )
            async with async_session_local() as session:
                result = await gen_table_service.get_gen_table_list_services(session, query_model, is_page=paged)
        except Exception as exc:
            return {
                'ok': False,
                'message': '读取代码生成业务表列表失败',
                'error': str(exc),
                'exit_code': DATABASE_ERROR,
            }

        filters = {
            'tableName': table_name,
            'tableComment': table_comment,
            'paged': paged,
            'pageNum': page_num,
            'pageSize': page_size,
        }
        return self.domain_support.build_list_payload(result, filters=filters, paged=paged)

    async def list_gen_db_tables(
        self,
        *,
        table_name: str = '',
        table_comment: str = '',
        paged: bool = False,
        page_num: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        查询数据库中可导入的物理表列表。

        :param table_name: 表名称过滤条件
        :param table_comment: 表描述过滤条件
        :param paged: 是否启用分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 查询结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        try:
            gen_vo_module = self.infrastructure_gateway.get_gen_vo_module()
            query_model = gen_vo_module.GenTablePageQueryModel(
                tableName=table_name or None,
                tableComment=table_comment or None,
                pageNum=page_num,
                pageSize=page_size,
            )
            async with async_session_local() as session:
                result = await gen_table_service.get_gen_db_table_list_services(session, query_model, is_page=paged)
        except Exception as exc:
            return {'ok': False, 'message': '读取数据库表列表失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        filters = {
            'tableName': table_name,
            'tableComment': table_comment,
            'paged': paged,
            'pageNum': page_num,
            'pageSize': page_size,
        }
        return self.domain_support.build_list_payload(result, filters=filters, paged=paged)

    async def create_tables(self, sql: str, sql_file: str, *, dry_run: bool = False) -> dict[str, Any]:
        """
        根据 SQL 创建表并导入代码生成业务表。

        :param sql: 直接传入的 SQL 文本
        :param sql_file: SQL 文件路径
        :param dry_run: 是否仅演练执行
        :return: 创建结果
        """
        try:
            sql_text = self.domain_support.resolve_sql_text(sql, sql_file)
            sql_statements, table_names = self.domain_support.parse_create_table_sql(sql_text)
        except ValueError as exc:
            return {'ok': False, 'message': '创建表结构失败', 'error': str(exc), 'exit_code': ARGUMENT_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '创建表结构失败', 'error': str(exc), 'exit_code': RUNTIME_ERROR}

        if dry_run:
            return {
                'ok': True,
                'message': '建表语句演练完成，未执行实际建表',
                'dryRun': True,
                'statementCount': len(sql_statements),
                'tableNames': table_names,
                'sql': sql_text,
            }

        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        service_exception = self.infrastructure_gateway.get_service_exception_class()
        try:
            async with async_session_local() as session:
                result = await gen_table_service.create_table_services(
                    session,
                    sql_text,
                    self.domain_support.build_cli_current_user(),
                )
        except service_exception as exc:
            return {'ok': False, 'message': '创建表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '创建表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        return {
            'ok': bool(result.is_success),
            'message': result.message,
            'tableNames': table_names,
        }

    async def preview_code(self, table_id: int) -> dict[str, Any]:
        """
        预览指定业务表的代码生成结果。

        :param table_id: 业务表 ID
        :return: 预览结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        service_exception = self.infrastructure_gateway.get_service_exception_class()
        try:
            async with async_session_local() as session:
                preview_payload = await gen_table_service.preview_code_services(session, table_id)
        except service_exception as exc:
            return {'ok': False, 'message': '预览代码失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '预览代码失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        return {
            'ok': True,
            'tableId': table_id,
            'templateCount': len(preview_payload),
            'preview': preview_payload,
        }

    async def get_gen_table_detail(self, table_id: int) -> dict[str, Any]:
        """
        读取单个代码生成业务表详情。

        :param table_id: 业务表 ID
        :return: 详情结果
        """
        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        gen_table_column_service = self.infrastructure_gateway.get_gen_table_column_service()
        try:
            async with async_session_local() as session:
                info = await gen_table_service.get_gen_table_by_id_services(session, table_id)
                if not getattr(info, 'table_id', None):
                    return {
                        'ok': False,
                        'message': f'代码生成业务表不存在：{table_id}',
                        'tableId': table_id,
                        'exit_code': RUNTIME_ERROR,
                    }
                rows = await gen_table_column_service.get_gen_table_column_list_by_table_id_services(session, table_id)
                tables = await gen_table_service.get_gen_table_all_services(session)
        except Exception as exc:
            return {
                'ok': False,
                'message': '读取代码生成业务表详情失败',
                'error': str(exc),
                'exit_code': DATABASE_ERROR,
            }

        detail_payload = {
            'info': self.domain_support.serialize_gen_item(info),
            'rows': self.domain_support.serialize_gen_items(rows),
            'tables': self.domain_support.serialize_gen_items(tables),
        }
        return {
            'ok': True,
            'tableId': table_id,
            'tableName': detail_payload['info'].get('tableName', ''),
            'columnCount': len(detail_payload['rows']),
            'tableCount': len(detail_payload['tables']),
            'detail': detail_payload,
        }

    async def export_code(
        self,
        table_names: list[str],
        *,
        mode: str = 'zip',
        output_file: str = '',
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        导出代码生成结果。

        :param table_names: 业务表名称列表
        :param mode: 导出模式，支持 `zip` 与 `local`
        :param output_file: zip 导出目标文件路径
        :param dry_run: 是否仅演练执行
        :return: 导出结果
        """
        normalized_table_names = self.domain_support.normalize_table_names(table_names)
        if not normalized_table_names:
            return {'ok': False, 'message': '至少需要传入一个表名', 'exit_code': ARGUMENT_ERROR}
        if mode not in {'zip', 'local'}:
            return {'ok': False, 'message': '导出模式仅支持 zip 或 local', 'exit_code': ARGUMENT_ERROR}

        gen_config = self.infrastructure_gateway.get_gen_config()
        if mode == 'local' and not gen_config.allow_overwrite:
            return {
                'ok': False,
                'message': '当前系统配置不允许生成文件覆盖到本地',
                'hint': '请检查 GenConfig.allow_overwrite 配置',
                'exit_code': RUNTIME_ERROR,
            }

        if dry_run:
            dry_run_payload: dict[str, Any] = {
                'ok': True,
                'message': '代码导出演练完成，未执行实际导出',
                'dryRun': True,
                'mode': mode,
                'tableNames': normalized_table_names,
            }
            if mode == 'zip':
                target_file = output_file.strip() or f'gen_code_{"_".join(normalized_table_names)}.zip'
                dry_run_payload['outputFile'] = self.domain_support.resolve_output_file_path(target_file)
            else:
                dry_run_payload['genPath'] = gen_config.GEN_PATH
            return dry_run_payload

        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        service_exception = self.infrastructure_gateway.get_service_exception_class()
        try:
            async with async_session_local() as session:
                if mode == 'zip':
                    zip_bytes = await gen_table_service.batch_gen_code_services(session, normalized_table_names)
                else:
                    messages = []
                    for table_name in normalized_table_names:
                        result = await gen_table_service.generate_code_services(session, table_name)
                        messages.append({'tableName': table_name, 'message': result.message, 'ok': result.is_success})
                    return {
                        'ok': True,
                        'message': '代码已生成到本地目录',
                        'mode': mode,
                        'tableNames': normalized_table_names,
                        'genPath': gen_config.GEN_PATH,
                        'results': messages,
                    }
        except service_exception as exc:
            return {'ok': False, 'message': '导出代码失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '导出代码失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        target_file = output_file.strip() or f'gen_code_{"_".join(normalized_table_names)}.zip'
        try:
            target_path = self.domain_support.write_export_zip(target_file, zip_bytes)
        except Exception as exc:
            return {'ok': False, 'message': '写出导出文件失败', 'error': str(exc), 'exit_code': RUNTIME_ERROR}

        return {
            'ok': True,
            'message': '代码压缩包导出完成',
            'mode': mode,
            'tableNames': normalized_table_names,
            'outputFile': target_path,
            'size': len(zip_bytes),
        }

    async def sync_gen_table_from_db(self, table_name: str) -> dict[str, Any]:
        """
        将指定代码生成业务表与数据库表结构进行同步。

        :param table_name: 业务表名称
        :return: 同步结果
        """
        normalized_table_name = table_name.strip()
        if not normalized_table_name:
            return {'ok': False, 'message': '表名不能为空', 'exit_code': ARGUMENT_ERROR}

        async_session_local = self.infrastructure_gateway.get_async_session_local()
        gen_table_service = self.infrastructure_gateway.get_gen_table_service()
        service_exception = self.infrastructure_gateway.get_service_exception_class()
        try:
            async with async_session_local() as session:
                result = await gen_table_service.sync_db_services(session, normalized_table_name)
        except service_exception as exc:
            return {'ok': False, 'message': '同步数据库表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}
        except Exception as exc:
            return {'ok': False, 'message': '同步数据库表结构失败', 'error': str(exc), 'exit_code': DATABASE_ERROR}

        return {
            'ok': bool(result.is_success),
            'message': result.message,
            'tableName': normalized_table_name,
        }


GEN_RUNTIME = GenRuntimeService()
