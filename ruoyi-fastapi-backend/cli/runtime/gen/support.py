from pathlib import Path
from typing import Any

from cli.runtime.base import RUNTIME_OPERATOR, RuntimeOperatorService

from .gateway import GenInfrastructureGateway


class GenDomainSupport:
    """
    代码生成领域支持对象。

    该对象负责 CLI 当前用户构建、表名规整、记录序列化、SQL 解析
    以及导出路径处理，避免主运行时服务继续承载过多局部规则。

    :param infrastructure_gateway: 代码生成基础设施网关
    """

    def __init__(
        self,
        infrastructure_gateway: GenInfrastructureGateway,
        operator_service: RuntimeOperatorService = RUNTIME_OPERATOR,
    ) -> None:
        """
        初始化代码生成领域支持对象。

        :param infrastructure_gateway: 代码生成基础设施网关
        :param operator_service: 运行时操作者解析服务
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway
        self.operator_service = operator_service

    def build_cli_current_user(self) -> Any:
        """
        构建 CLI 场景使用的最小当前用户模型。

        :return: CLI 当前用户模型
        """
        operator = self.operator_service.resolve_operator()
        user_vo_module = self.infrastructure_gateway.get_user_vo_module()
        return user_vo_module.CurrentUserModel(
            permissions=[],
            roles=['admin'],
            user=user_vo_module.UserInfoModel(
                user_id=1,
                user_name=operator,
                nick_name=operator,
                user_type='00',
                status='0',
                del_flag='0',
            ),
        )

    @staticmethod
    def normalize_table_names(table_names: list[str]) -> list[str]:
        """
        规范化表名列表。

        :param table_names: 原始表名列表
        :return: 规范化后的表名列表
        """
        return [table_name.strip() for table_name in table_names if table_name.strip()]

    @staticmethod
    def serialize_gen_item(item: Any) -> dict[str, Any]:
        """
        序列化单个代码生成表记录。

        :param item: 原始记录对象
        :return: 可输出的字典
        """
        if hasattr(item, 'model_dump'):
            return dict(item.model_dump(by_alias=True, exclude_none=True))
        return dict(item)

    def serialize_gen_items(self, items: list[Any]) -> list[dict[str, Any]]:
        """
        序列化代码生成表记录列表。

        :param items: 原始记录列表
        :return: 序列化后的字典列表
        """
        return [self.serialize_gen_item(item) for item in items]

    def parse_create_table_sql(self, sql: str) -> tuple[list[Any], list[str]]:
        """
        解析建表 SQL 并提取建表语句信息。

        :param sql: 原始 SQL 文本
        :return: SQL AST 列表与建表表名列表
        :raises ValueError: SQL 非法时抛出异常
        """
        sqlglot_module = self.infrastructure_gateway.get_sqlglot_module()
        expressions_module = self.infrastructure_gateway.get_sqlglot_expressions_module()
        database_config = self.infrastructure_gateway.get_database_config()
        sql_statements = sqlglot_module.parse(sql, dialect=database_config.sqlglot_parse_dialect)
        has_create = any(isinstance(sql_statement, expressions_module.Create) for sql_statement in sql_statements)
        has_forbidden_keyword = any(
            isinstance(
                sql_statement,
                (
                    expressions_module.Add,
                    expressions_module.Alter,
                    expressions_module.Delete,
                    expressions_module.Drop,
                    expressions_module.Insert,
                    expressions_module.TruncateTable,
                    expressions_module.Update,
                ),
            )
            for sql_statement in sql_statements
        )
        if not has_create or has_forbidden_keyword:
            raise ValueError('建表语句不合法，仅允许 CREATE TABLE 语句')

        table_names = [
            sql_statement.find(expressions_module.Table).name
            for sql_statement in sql_statements
            if isinstance(sql_statement, expressions_module.Create)
        ]
        if not table_names:
            raise ValueError('未解析到建表表名')
        return sql_statements, table_names

    @staticmethod
    def resolve_sql_text(sql: str, sql_file: str) -> str:
        """
        解析命令输入中的 SQL 文本。

        :param sql: 直接传入的 SQL 文本
        :param sql_file: SQL 文件路径
        :return: 最终 SQL 文本
        :raises ValueError: 参数非法时抛出异常
        """
        if bool(sql.strip()) == bool(sql_file.strip()):
            raise ValueError('必须且只能传入 --sql 或 --sql-file 其中一种方式')
        if sql.strip():
            return sql.strip()

        sql_path = Path(sql_file).expanduser().resolve()
        if not sql_path.is_file():
            raise ValueError(f'SQL 文件不存在：{sql_path}')
        return sql_path.read_text(encoding='utf-8').strip()

    @staticmethod
    def resolve_output_file_path(target_file: str) -> str:
        """
        解析导出文件绝对路径。

        :param target_file: 原始导出文件路径
        :return: 绝对路径字符串
        """
        return str(Path(target_file).expanduser().resolve())

    @staticmethod
    def write_export_zip(target_file: str, zip_bytes: bytes) -> str:
        """
        将导出的 zip 数据写入目标文件。

        :param target_file: 目标文件路径
        :param zip_bytes: zip 二进制内容
        :return: 实际写入的绝对路径
        """
        target_path = Path(target_file).expanduser().resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(zip_bytes)
        return str(target_path)

    def build_list_payload(
        self,
        result: Any,
        *,
        filters: dict[str, Any],
        paged: bool,
    ) -> dict[str, Any]:
        """
        统一构建代码生成列表返回结构。

        :param result: 原始结果对象
        :param filters: 查询过滤条件
        :param paged: 是否分页
        :return: 可输出结果
        """
        if paged and isinstance(result, self.infrastructure_gateway.get_page_model()):
            page_payload = result.model_dump(by_alias=True)
            page_payload['rows'] = self.serialize_gen_items(page_payload.get('rows', []))
            return {'ok': True, 'filters': filters, 'page': page_payload}

        items = self.serialize_gen_items(result)
        return {'ok': True, 'filters': filters, 'count': len(items), 'items': items}
