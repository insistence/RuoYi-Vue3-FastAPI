"""
统一认证中心启动前的只读数据库升级检查
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from config.database import DataSourceRegistry


class IdentityMigrationRequired(RuntimeError):
    """
    统一认证中心数据库尚未完成升级异常
    """


class IdentitySchemaService:
    """
    统一认证中心数据库结构校验服务层
    """

    _UTC_PRECISION = 3
    TABLES = (
        'sys_identity_subject',
        'sys_oauth_client',
        'sys_oauth_client_secret',
        'sys_oauth_client_uri',
        'sys_oauth_resource',
        'sys_oauth_scope',
        'sys_oauth_client_scope',
        'sys_oauth_client_resource',
        'sys_oauth_grant',
        'sys_oauth_refresh_token',
        'sys_sso_session',
        'sys_oidc_signing_key',
        'sys_oauth_audit_log',
        'sys_oauth_audit_archive',
    )

    @classmethod
    def check(cls, connection: Connection) -> None:
        """
        检查存量数据库的认证中心表、UTC字段及主体回填情况

        在自动建表前执行只读检查，避免自动建表掩盖缺失的数据迁移。

        :param connection: 数据库同步连接
        :return: 无
        :raises IdentityMigrationRequired: 数据库缺少必要的结构或数据迁移
        """

        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if 'sys_user' not in tables:
            return
        missing = set(cls.TABLES) - tables
        if missing:
            raise IdentityMigrationRequired(
                'Identity database upgrade required before startup; missing tables: '
                + ', '.join(sorted(missing))
                + '. See docs/unified_authentication_operations.md.'
            )
        consent_columns = {column['name'] for column in inspector.get_columns('sys_oauth_grant')}
        if not {'remembered_scopes', 'remembered_resources'}.issubset(consent_columns):
            raise IdentityMigrationRequired(
                'Identity consent preference migration required before startup; run alembic upgrade head.'
            )
        for table in cls.TABLES:
            for column in inspector.get_columns(table):
                data_type = column['type']
                if connection.dialect.name == 'postgresql':
                    legacy = data_type.__class__.__name__ == 'TIMESTAMP' and not data_type.timezone
                elif connection.dialect.name == 'mysql':
                    legacy = (
                        data_type.__class__.__name__ in {'DATETIME', 'TIMESTAMP'}
                        and (data_type.fsp or 0) < cls._UTC_PRECISION
                    )
                else:
                    legacy = False
                if legacy:
                    raise IdentityMigrationRequired(
                        f'Identity UTC migration required for {table}.{column["name"]}; '
                        'specify the original timezone. See docs/unified_authentication_operations.md.'
                    )
        missing_subject = connection.execute(
            text(
                'SELECT u.user_id FROM sys_user u LEFT JOIN sys_identity_subject i ON i.user_id = u.user_id '
                'WHERE i.identity_id IS NULL LIMIT 1'
            )
        ).first()
        if missing_subject is not None:
            raise IdentityMigrationRequired(
                'Identity Subject backfill is incomplete, including when OIDC is disabled. '
                'Run the documented upgrade/repair before startup.'
            )

    @classmethod
    async def validate_before_start(cls) -> None:
        """
        启动前校验认证中心数据库升级状态

        OIDC关闭时也检查稳定主体是否完成回填。

        :return: 无
        :raises IdentityMigrationRequired: 数据库尚未完成认证中心升级
        """

        async with DataSourceRegistry.session() as db:
            connection = await db.connection()
            await connection.run_sync(cls.check)
