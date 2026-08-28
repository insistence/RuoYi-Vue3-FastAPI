"""统一认证数据层测试的最小数据库环境。"""

import json
import os

os.environ.setdefault(
    'DB_SOURCES',
    json.dumps(
        {
            'primary': {
                'db_type': 'mysql',
                'db_host': 'localhost',
                'db_port': 3306,
                'db_username': 'test',
                'db_password': 'test',
                'db_database': 'test',
            }
        }
    ),
)
os.environ.setdefault('DB_DEFAULT_SOURCE', 'primary')

import pytest_asyncio
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from config.database import Base
from module_admin.entity.do.user_do import SysUser as _sys_user_model  # noqa: N813, F401
from module_identity.entity.do import (
    identity_subject_do as _identity_subject_models,  # noqa: F401
)
from module_identity.entity.do import oauth_audit_do as _oauth_audit_models  # noqa: F401
from module_identity.entity.do import oauth_client_do as _oauth_client_models  # noqa: F401
from module_identity.entity.do import oauth_grant_do as _oauth_grant_models  # noqa: F401
from module_identity.entity.do import oauth_resource_do as _oauth_resource_models  # noqa: F401
from module_identity.entity.do import oidc_key_do as _oidc_key_models  # noqa: F401


@compiles(TINYINT, 'sqlite')
def _compile_mysql_tinyint_for_sqlite(_type: TINYINT, _compiler: object, **_kwargs: object) -> str:
    """让现有 MySQL 布尔列可在认证模块的 SQLite 测试库中建表。"""
    return 'SMALLINT'


@pytest_asyncio.fixture
async def data_session() -> AsyncSession:
    """创建只包含认证模块表的独立内存 SQLite 异步会话。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    identity_tables = [
        table
        for table_name, table in Base.metadata.tables.items()
        if table_name == 'sys_user' or table_name.startswith(('sys_identity_', 'sys_oauth_', 'sys_oidc_', 'sys_sso_'))
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(sync_connection, tables=identity_tables)
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
