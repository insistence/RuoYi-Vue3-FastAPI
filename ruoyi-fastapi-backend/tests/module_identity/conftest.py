import json
import os
from unittest.mock import AsyncMock

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

import pytest
import pytest_asyncio
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from config.database import Base
from module_admin.entity.do.user_do import SysUser as _sys_user_model  # noqa: N813, F401
from module_identity.dao.oauth_client_dao import OAuthClientDao
from module_identity.entity.do import (
    identity_subject_do as _identity_subject_models,  # noqa: F401
)
from module_identity.entity.do import oauth_audit_do as _oauth_audit_models  # noqa: F401
from module_identity.entity.do import oauth_client_do as _oauth_client_models  # noqa: F401
from module_identity.entity.do import oauth_grant_do as _oauth_grant_models  # noqa: F401
from module_identity.entity.do import oauth_resource_do as _oauth_resource_models  # noqa: F401
from module_identity.entity.do import oidc_key_do as _oidc_key_models  # noqa: F401
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_resource_do import SysOAuthScope


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


@pytest.fixture
def interaction_page_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SysOAuthClient, list[SysOAuthScope]]:
    """提供当前已登记的页面元数据，管理备注必须保持私有。"""
    client = SysOAuthClient(
        client_pk=1001,
        client_id='portal-client',
        client_name='示例门户',
        policy_uri='https://portal.example/privacy',
        remark='private-client-note',
    )
    scopes = [
        SysOAuthScope(
            scope_pk=1,
            scope_code='openid',
            scope_name='确认身份',
            consent_required=0,
            sensitive=0,
            remark='private-scope-note',
        ),
        SysOAuthScope(
            scope_pk=2,
            scope_code='profile',
            scope_name='基本资料',
            consent_required=1,
            sensitive=1,
            remark='private-scope-note',
        ),
    ]
    monkeypatch.setattr(OAuthClientDao, 'get_by_pk', AsyncMock(return_value=client))
    monkeypatch.setattr(OAuthClientDao, 'list_scopes', AsyncMock(return_value=scopes))
    return client, scopes
