from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from sqlalchemy import Row, bindparam, delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlglot.expressions import Expression

from common.vo import PageModel
from config.env import DataBaseConfig, DataSourceSettings
from module_generator.entity.do.gen_do import GenTable, GenTableColumn
from module_generator.entity.vo.gen_vo import (
    GenTableBaseModel,
    GenTableColumnBaseModel,
    GenTableColumnModel,
    GenTableModel,
    GenTablePageQueryModel,
)
from utils.page_util import PageUtil


@dataclass(frozen=True, slots=True)
class DatabaseMetadataAdapter:
    """代码生成器使用的数据库元数据查询。"""

    table_list_query: str
    tables_by_name_query: str
    columns_query: str
    created_after_filter: str
    created_before_filter: str


_METADATA_ADAPTERS = {
    'mysql': DatabaseMetadataAdapter(
        table_list_query=r"""
            table_name as table_name,
            table_comment as table_comment,
            create_time as create_time,
            update_time as update_time
        from
            information_schema.tables
        where
            table_schema = (select database())
            and table_name not like 'apscheduler\_%'
            and table_name not like 'gen\_%'
        """,
        tables_by_name_query=r"""
        select
            table_name as table_name,
            table_comment as table_comment,
            create_time as create_time,
            update_time as update_time
        from
            information_schema.tables
        where
            table_name not like 'qrtz\_%'
            and table_name not like 'gen\_%'
            and table_schema = (select database())
            and table_name in :table_names
        """,
        columns_query="""
        select
            column_name as column_name,
            case when is_nullable = 'no' and column_key != 'PRI' then '1' else '0' end as is_required,
            case when column_key = 'PRI' then '1' else '0' end as is_pk,
            ordinal_position as sort,
            column_comment as column_comment,
            case when extra = 'auto_increment' then '1' else '0' end as is_increment,
            column_type as column_type
        from
            information_schema.columns
        where
            table_schema = (select database())
            and table_name = :table_name
        order by
            ordinal_position
        """,
        created_after_filter=" and date_format(create_time, '%Y%m%d') >= date_format(:begin_time, '%Y%m%d')",
        created_before_filter=" and date_format(create_time, '%Y%m%d') <= date_format(:end_time, '%Y%m%d')",
    ),
    'postgresql': DatabaseMetadataAdapter(
        table_list_query="""
            table_name as table_name,
            table_comment as table_comment,
            create_time as create_time,
            update_time as update_time
        from
            list_table
        where
            table_name not like 'apscheduler_%'
            and table_name not like 'gen_%'
        """,
        tables_by_name_query="""
        select
            table_name as table_name,
            table_comment as table_comment,
            create_time as create_time,
            update_time as update_time
        from
            list_table
        where
            table_name not like 'qrtz_%'
            and table_name not like 'gen_%'
            and table_name in :table_names
        """,
        columns_query="""
        select
            column_name, is_required, is_pk, sort, column_comment, is_increment, column_type
        from
            list_column
        where
            table_name = :table_name
        """,
        created_after_filter=" and create_time::date >= to_date(:begin_time, 'yyyy-MM-dd')",
        created_before_filter=" and create_time::date <= to_date(:end_time, 'yyyy-MM-dd')",
    ),
}


def _get_database_metadata_adapter(db_type: str) -> DatabaseMetadataAdapter:
    """
    根据数据库类型获取元数据查询适配器

    :param db_type: 数据库类型
    :return: 元数据查询适配器
    """
    try:
        return _METADATA_ADAPTERS[db_type]
    except KeyError as exc:
        raise ValueError(f'不支持的数据库类型：{db_type!r}') from exc


class GenTableDao:
    """
    代码生成业务表模块数据库操作层
    """

    @classmethod
    async def get_gen_table_by_id(cls, db: AsyncSession, table_id: int) -> GenTable | None:
        """
        根据业务表id获取需要生成的业务表信息

        :param db: orm对象
        :param table_id: 业务表id
        :return: 需要生成的业务表信息对象
        """
        gen_table_info = (
            (
                await db.execute(
                    select(GenTable).options(selectinload(GenTable.columns)).where(GenTable.table_id == table_id)
                )
            )
            .scalars()
            .first()
        )

        return gen_table_info

    @classmethod
    async def get_gen_table_by_name(cls, db: AsyncSession, table_name: str, source_name: str) -> GenTable | None:
        """
        根据业务表名称获取需要生成的业务表信息

        :param db: orm对象
        :param table_name: 业务表名称
        :param source_name: 数据源名称
        :return: 需要生成的业务表信息对象
        """
        gen_table_info = (
            (
                await db.execute(
                    select(GenTable)
                    .options(selectinload(GenTable.columns))
                    .where(
                        GenTable.table_name == table_name,
                        GenTable.data_source_name == source_name,
                    )
                )
            )
            .scalars()
            .first()
        )

        return gen_table_info

    @classmethod
    async def get_gen_table_all(cls, db: AsyncSession, source_name: str | None = None) -> Sequence[GenTable]:
        """
        获取所有业务表信息

        :param db: orm对象
        :param source_name: 数据源名称
        :return: 所有业务表信息
        """
        query = select(GenTable).options(selectinload(GenTable.columns))
        if source_name:
            query = query.where(GenTable.data_source_name == source_name)
        gen_table_all = (await db.execute(query)).scalars().all()

        return gen_table_all

    @classmethod
    async def create_table_by_sql_dao(
        cls, db: AsyncSession, sql_statements: list[Expression], *, source_config: DataSourceSettings
    ) -> None:
        """
        根据sql语句创建表结构

        :param db: orm对象
        :param sql_statements: sql语句的ast列表
        :param source_config: 目标数据源配置
        :return:
        """
        for sql_statement in sql_statements:
            sql = sql_statement.sql(dialect=source_config.sqlglot_parse_dialect)
            await db.execute(text(sql))

    @classmethod
    async def get_gen_table_list(
        cls, db: AsyncSession, query_object: GenTablePageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取代码生成业务表列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 代码生成业务表列表信息对象
        """
        query = (
            select(GenTable)
            .options(selectinload(GenTable.columns))
            .where(
                func.lower(GenTable.table_name).like(f'%{query_object.table_name.lower()}%')
                if query_object.table_name
                else True,
                func.lower(GenTable.table_comment).like(f'%{query_object.table_comment.lower()}%')
                if query_object.table_comment
                else True,
                GenTable.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
                GenTable.data_source_name == query_object.data_source_name if query_object.data_source_name else True,
            )
            .distinct()
        )
        gen_table_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return gen_table_list

    @classmethod
    async def get_gen_table_names(cls, db: AsyncSession, source_name: str | None = None) -> set[str]:
        """
        获取控制库中指定数据源已导入的业务表名称

        :param db: orm对象
        :param source_name: 数据源名称
        :return: 已导入的业务表名称集合
        """
        query = select(GenTable.table_name)
        if source_name:
            query = query.where(GenTable.data_source_name == source_name)
        return {name for name in (await db.execute(query)).scalars().all() if name}

    @classmethod
    async def get_gen_db_table_list(
        cls,
        db: AsyncSession,
        query_object: GenTablePageQueryModel,
        is_page: bool = False,
        *,
        excluded_table_names: set[str] | None = None,
        source_config: DataSourceSettings | None = None,
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取数据库列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :param excluded_table_names: 需要排除的已导入表名称集合
        :param source_config: 目标数据源配置
        :return: 数据库列表信息对象
        """
        source_config = source_config or DataBaseConfig.default_source
        metadata = _get_database_metadata_adapter(source_config.db_type)
        query_params: dict[str, Any] = {}
        query_sql = metadata.table_list_query
        if excluded_table_names:
            query_sql += ' and table_name not in :excluded_table_names'
            query_params['excluded_table_names'] = tuple(excluded_table_names)
        if query_object.table_name:
            query_sql += " and lower(table_name) like lower(concat('%', :table_name, '%'))"
            query_params['table_name'] = query_object.table_name
        if query_object.table_comment:
            query_sql += " and lower(table_comment) like lower(concat('%', :table_comment, '%'))"
            query_params['table_comment'] = query_object.table_comment
        if query_object.begin_time:
            query_sql += metadata.created_after_filter
            query_params['begin_time'] = query_object.begin_time
        if query_object.end_time:
            query_sql += metadata.created_before_filter
            query_params['end_time'] = query_object.end_time
        query_sql += ' order by create_time desc'
        statement = text(query_sql)
        if excluded_table_names:
            statement = statement.bindparams(bindparam('excluded_table_names', expanding=True))
        query = select(statement.bindparams(**query_params))
        gen_db_table_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            db, query, query_object.page_num, query_object.page_size, is_page
        )

        return gen_db_table_list

    @classmethod
    async def get_gen_db_table_list_by_names(
        cls, db: AsyncSession, table_names: list[str], source_config: DataSourceSettings | None = None
    ) -> Sequence[Row]:
        """
        根据业务表名称组获取数据库列表信息

        :param db: orm对象
        :param table_names: 业务表名称组
        :param source_config: 目标数据源配置
        :return: 数据库列表信息对象
        """
        source_config = source_config or DataBaseConfig.default_source
        query_sql = _get_database_metadata_adapter(source_config.db_type).tables_by_name_query
        query = text(query_sql).bindparams(bindparam('table_names', value=table_names, expanding=True))
        gen_db_table_list = (await db.execute(query)).fetchall()

        return gen_db_table_list

    @classmethod
    async def add_gen_table_dao(cls, db: AsyncSession, gen_table: GenTableModel) -> GenTable:
        """
        新增业务表数据库操作

        :param db: orm对象
        :param gen_table: 业务表对象
        :return:
        """
        db_gen_table = GenTable(**GenTableBaseModel(**gen_table.model_dump(by_alias=True)).model_dump())
        db.add(db_gen_table)
        await db.flush()

        return db_gen_table

    @classmethod
    async def edit_gen_table_dao(cls, db: AsyncSession, gen_table: dict) -> None:
        """
        编辑业务表数据库操作

        :param db: orm对象
        :param gen_table: 需要更新的业务表字典
        :return:
        """
        await db.execute(update(GenTable), [GenTableBaseModel(**gen_table).model_dump()])

    @classmethod
    async def delete_gen_table_dao(cls, db: AsyncSession, gen_table: GenTableModel) -> None:
        """
        删除业务表数据库操作

        :param db: orm对象
        :param gen_table: 业务表对象
        :return:
        """
        await db.execute(delete(GenTable).where(GenTable.table_id.in_([gen_table.table_id])))


class GenTableColumnDao:
    """
    代码生成业务表字段模块数据库操作层
    """

    @classmethod
    async def get_gen_table_column_list_by_table_id(cls, db: AsyncSession, table_id: int) -> GenTableColumn:
        """
        根据业务表id获取需要生成的业务表字段列表信息

        :param db: orm对象
        :param table_id: 业务表id
        :return: 需要生成的业务表字段列表信息对象
        """
        gen_table_column_list = (
            (
                await db.execute(
                    select(GenTableColumn).where(GenTableColumn.table_id == table_id).order_by(GenTableColumn.sort)
                )
            )
            .scalars()
            .all()
        )

        return gen_table_column_list

    @classmethod
    async def get_gen_db_table_columns_by_name(
        cls, db: AsyncSession, table_name: str, source_config: DataSourceSettings | None = None
    ) -> Sequence[Row]:
        """
        根据业务表名称获取业务表字段列表信息

        :param db: orm对象
        :param table_name: 业务表名称
        :param source_config: 目标数据源配置
        :return: 业务表字段列表信息对象
        """
        source_config = source_config or DataBaseConfig.default_source
        query_sql = _get_database_metadata_adapter(source_config.db_type).columns_query
        query = text(query_sql).bindparams(table_name=table_name)
        gen_db_table_columns = (await db.execute(query)).fetchall()

        return gen_db_table_columns

    @classmethod
    async def add_gen_table_column_dao(cls, db: AsyncSession, gen_table_column: GenTableColumnModel) -> GenTableColumn:
        """
        新增业务表字段数据库操作

        :param db: orm对象
        :param gen_table_column: 岗位对象
        :return:
        """
        db_gen_table_column = GenTableColumn(
            **GenTableColumnBaseModel(**gen_table_column.model_dump(by_alias=True)).model_dump()
        )
        db.add(db_gen_table_column)
        await db.flush()

        return db_gen_table_column

    @classmethod
    async def edit_gen_table_column_dao(cls, db: AsyncSession, gen_table_column: dict) -> None:
        """
        编辑业务表字段数据库操作

        :param db: orm对象
        :param gen_table_column: 需要更新的业务表字段字典
        :return:
        """
        await db.execute(update(GenTableColumn), [GenTableColumnBaseModel(**gen_table_column).model_dump()])

    @classmethod
    async def delete_gen_table_column_by_table_id_dao(
        cls, db: AsyncSession, gen_table_column: GenTableColumnModel
    ) -> None:
        """
        通过业务表id删除业务表字段数据库操作

        :param db: orm对象
        :param gen_table_column: 业务表字段对象
        :return:
        """
        await db.execute(delete(GenTableColumn).where(GenTableColumn.table_id.in_([gen_table_column.table_id])))

    @classmethod
    async def delete_gen_table_column_by_column_id_dao(
        cls, db: AsyncSession, gen_table_column: GenTableColumnModel
    ) -> None:
        """
        通过业务字段id删除业务表字段数据库操作

        :param db: orm对象
        :param post: 业务表字段对象
        :return:
        """
        await db.execute(delete(GenTableColumn).where(GenTableColumn.column_id.in_([gen_table_column.column_id])))
