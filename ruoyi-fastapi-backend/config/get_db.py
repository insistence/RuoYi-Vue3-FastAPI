from collections.abc import AsyncGenerator
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from config.database import AsyncSessionLocal, Base, async_engine
from utils.log_util import logger


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    每一个请求处理完毕后会关闭当前连接，不同的请求使用不同的连接

    :return:
    """
    async with AsyncSessionLocal() as current_db:
        yield current_db


async def init_create_table(
    *,
    stage: Literal['platform', 'plugin_entities'] = 'platform',
    log_success_enabled: bool = True,
) -> None:
    """
    应用启动时初始化数据库元数据。

    :param stage: 建表阶段
    :param log_success_enabled: 是否输出阶段成功摘要
    :return: None
    """
    if log_success_enabled:
        message = '🔎 初始化平台数据库元数据...' if stage == 'platform' else '🔎 同步插件实体表...'
        logger.bind(database_init_stage=stage).info(message)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if log_success_enabled:
        message = '✅️ 平台数据库元数据初始化完成' if stage == 'platform' else '✅️ 插件实体表同步完成'
        logger.bind(database_init_stage=stage).info(message)


async def close_async_engine() -> None:
    """
    应用关闭时释放数据库连接池

    :return:
    """
    await async_engine.dispose()
