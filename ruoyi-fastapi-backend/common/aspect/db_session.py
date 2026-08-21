from collections.abc import AsyncIterator
from functools import cache

from fastapi import Depends, params
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import DataSourceRegistry


class DBSessionProvider:
    """
    数据库会话依赖提供者
    """

    def __init__(self, source_name: str | None = None) -> None:
        self.source_name = source_name

    async def __call__(self) -> AsyncIterator[AsyncSession]:
        """
        创建指定数据源的数据库会话

        :return: 异步数据库会话
        """
        async with DataSourceRegistry.session(self.source_name) as session:
            yield session


@cache
def get_db_session_provider(source_name: str | None) -> DBSessionProvider:
    """
    获取指定数据源的数据库会话依赖提供者

    :param source_name: 数据源名称
    :return: 数据库会话依赖提供者
    """
    return DBSessionProvider(source_name)


def DBSessionDependency(source_name: str | None = None) -> params.Depends:  # noqa: N802
    """
    数据库会话依赖

    :param source_name: 数据源名称，为空时使用默认数据源
    :return: 数据库会话依赖
    """
    return Depends(get_db_session_provider(source_name))
