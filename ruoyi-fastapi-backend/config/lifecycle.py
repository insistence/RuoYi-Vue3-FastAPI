from typing import Literal

from config.database import Base, DataSourceRegistry
from utils.log_util import logger


async def init_create_table(
    *,
    stage: Literal['platform', 'plugin_entities'] = 'platform',
    log_success_enabled: bool = True,
) -> None:
    """
    在默认数据源中初始化平台数据库元数据

    :param stage: 建表阶段
    :param log_success_enabled: 是否输出阶段成功摘要
    :return: None
    """
    if log_success_enabled:
        message = '🔎 初始化平台数据库元数据...' if stage == 'platform' else '🔎 同步插件实体表...'
        logger.bind(database_init_stage=stage).info(message)
    async with DataSourceRegistry.connection() as connection:
        # 签名制品的数据结构只能由维护迁移准备，普通 worker 不隐式补建其表。
        artifact_tables = [table for table in Base.metadata.tables.values() if table.info.get('plugin_artifact')]
        if artifact_tables:
            tables = [table for table in Base.metadata.tables.values() if not table.info.get('plugin_artifact')]
            await connection.run_sync(Base.metadata.create_all, tables=tables)
        else:
            await connection.run_sync(Base.metadata.create_all)
    if log_success_enabled:
        message = '✅️ 平台数据库元数据初始化完成' if stage == 'platform' else '✅️ 插件实体表同步完成'
        logger.bind(database_init_stage=stage).info(message)
