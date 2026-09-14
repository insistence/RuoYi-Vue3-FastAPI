"""在独立临时库验证身份迁移、刷新并发及原生备份恢复。"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy.ext.asyncio import async_sessionmaker

from config.database import create_async_db_engine, create_sync_db_engine
from config.env import DataSourceSettings, OidcConfig
from exceptions.exception import OAuthProtocolException
from module_admin.entity.do.user_do import SysUser
from module_identity.dao.oauth_token_dao import OAuthTokenDao
from module_identity.dao.sso_session_dao import SsoSessionDao
from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_client_do import SysOAuthClient
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken, SysSsoSession
from module_identity.entity.do.oauth_resource_do import SysOAuthClientScope, SysOAuthScope
from module_identity.security.opaque_token import parse_opaque_token
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.schema_service import IdentityMigrationRequired, IdentitySchemaService
from module_identity.service.token_service import RefreshTokenReuseDetected, TokenService
from scripts.verify_timezone_database import load_source
from utils.time_util import TimezoneUtil

if TYPE_CHECKING:
    from types import ModuleType

BACKEND = Path(__file__).resolve().parents[1]
PREFIX = 'ruoyi_oidc_verify_'
PEPPER = 'isolated-identity-verification-' + 'x' * 32
BUILTIN_SCOPE_COUNT = 7


def revision(filename: str) -> ModuleType:
    """
    加载指定的Alembic迁移模块

    :param filename: 迁移脚本文件名
    :return: 已加载的迁移模块
    """

    spec = importlib.util.spec_from_file_location(filename.removesuffix('.py'), BACKEND / 'alembic/versions' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_database(source: DataSourceSettings, created: list[str]) -> DataSourceSettings:
    """
    创建随机命名的隔离测试库并记录归属

    :param source: 具备建库权限的源连接配置
    :param created: 本次创建的测试库名称列表
    :return: 新建测试库的连接配置
    """

    name = PREFIX + uuid4().hex[:12]
    engine = create_sync_db_engine(config=source, echo=False)
    try:
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.exec_driver_sql(f'CREATE DATABASE {name}')
        created.append(name)
    finally:
        engine.dispose()
    return source.model_copy(update={'db_database': name, 'db_echo': False})


def cleanup(source: DataSourceSettings, created: list[str]) -> None:
    """
    删除本次创建且名称校验通过的隔离测试库

    :param source: 源数据库连接配置
    :param created: 本次创建的测试库名称列表
    :return: 无
    """

    engine = create_sync_db_engine(config=source, echo=False)
    try:
        for name in reversed(created):
            assert re.fullmatch(PREFIX + r'[0-9a-f]{12}', name) and name != source.db_database
            with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
                connection.exec_driver_sql(f'DROP DATABASE {name}')
    finally:
        engine.dispose()


def initialize_legacy(target: DataSourceSettings) -> None:
    """
    向已确认空的测试库导入原有业务表及种子数据

    :param target: 隔离测试库连接配置
    :return: 无
    """

    filename = 'ruoyi-fastapi.sql' if target.db_type == 'mysql' else 'ruoyi-fastapi-pg.sql'
    sql = (BACKEND / 'sql' / filename).read_text(encoding='utf-8').split('-- 统一认证中心相关表清理')[0]
    assert not re.search(r'(?im)^\s*(USE\s|(?:DROP|CREATE)\s+DATABASE\b)', sql)
    engine = create_sync_db_engine(config=target, echo=False)
    try:
        assert not sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
    kwargs = {
        'host': target.db_host,
        'port': target.db_port,
        'user': target.db_username,
        'password': target.db_password.get_secret_value(),
        'database': target.db_database,
    }
    if target.db_type == 'mysql':
        import pymysql  # noqa: PLC0415
        from pymysql.constants import CLIENT  # noqa: PLC0415

        connection = pymysql.connect(**kwargs, charset='utf8mb4', autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS)
    else:
        import psycopg2  # noqa: PLC0415

        connection = psycopg2.connect(**kwargs)
        connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            if target.db_type == 'mysql':
                while cursor.nextset():
                    pass
    finally:
        connection.close()


def apply_revision(connection: sa.Connection, filename: str, **options: str) -> None:
    """
    通过真实Alembic操作执行指定升级

    :param connection: 测试库连接
    :param filename: 迁移脚本文件名
    :param options: 传入迁移上下文的选项
    :return: 无
    """

    with Operations.context(MigrationContext.configure(connection, opts={'identity_options': options})):
        revision(filename).upgrade()


def native_snapshot(source: DataSourceSettings, output: Path, *, restore: bool = False) -> None:
    """
    使用数据库原生工具备份或恢复测试库

    密码仅通过子进程环境传递。

    :param source: 测试库连接配置
    :param output: 快照文件路径
    :param restore: 是否从快照恢复
    :return: 无
    """

    assert re.fullmatch(PREFIX + r'[0-9a-f]{12}', source.db_database)
    environment = dict(os.environ)
    if source.db_type == 'mysql':
        tool = shutil.which('mysqldump')
        if not tool:
            raise RuntimeError('mysqldump is required for restore verification')
        environment['MYSQL_PWD'] = source.db_password.get_secret_value()
        args = [
            str(Path(tool).with_name('mysql.exe')) if restore else tool,
            '--host=' + source.db_host,
            '--port=' + str(source.db_port),
            '--user=' + source.db_username,
            '--default-character-set=utf8mb4',
        ]
        if not restore:
            args.extend(['--single-transaction', '--set-gtid-purged=OFF', '--column-statistics=0', '--no-tablespaces'])
        args.append(source.db_database)
    else:
        executable = 'pg_restore.exe' if restore else 'pg_dump.exe'
        tool = shutil.which(executable) or str(Path('E:/PostgreSQL/bin') / executable)
        environment['PGPASSWORD'] = source.db_password.get_secret_value()
        args = [
            tool,
            '--host=' + source.db_host,
            '--port=' + str(source.db_port),
            '--username=' + source.db_username,
            '--no-owner',
            '--no-acl',
            '--dbname=' + source.db_database,
        ]
        if not restore:
            args.append('--format=custom')
    with output.open('rb' if restore else 'wb') as stream:
        result = subprocess.run(
            args,
            stdin=stream if restore else subprocess.DEVNULL,
            stdout=subprocess.PIPE if restore else stream,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=90,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    if result.returncode:
        raise RuntimeError(
            f'Native {"restore" if restore else "backup"} failed: ' + result.stderr.decode(errors='replace')[-1500:]
        )


def verify_migrations(target: DataSourceSettings, report: dict, snapshot: Path) -> dict:  # noqa: PLR0915
    """
    验证存量用户、UTC字段迁移及原生备份恢复

    :param target: 隔离测试库连接配置
    :param report: 原地补充验收结果的报告字典
    :param snapshot: 原生备份文件路径
    :return: 升级后用于对照的数据库快照
    """

    initial = '20260824_add_unified_authentication_center.py'
    utc = '20260912_identity_utc.py'
    engine = create_sync_db_engine(config=target, echo=False)
    try:
        with engine.begin() as connection:
            connection.execute(
                SysUser.__table__.insert().values(
                    user_id=9900,
                    user_name='deleted-identity-probe',
                    nick_name='Deleted',
                    del_flag='2',
                )
            )
            users_before = connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all()
            try:
                IdentitySchemaService.check(connection)
            except IdentityMigrationRequired:
                pass
            else:
                raise AssertionError('Missing identity migration was not detected')
            apply_revision(connection, initial)
            connection.execute(
                SysOAuthClient.__table__.insert().values(
                    client_pk=9910,
                    client_id='migration-consent-probe',
                    client_name='Migration consent probe',
                    client_type='public',
                    token_endpoint_auth_method='none',
                    grant_types=['authorization_code'],
                    response_types=['code'],
                    policy_version=1,
                )
            )
            legacy_grants = sa.Table('sys_oauth_grant', sa.MetaData(), autoload_with=connection)
            connection.execute(
                legacy_grants.insert().values(
                    grant_id='migration-consent-probe',
                    user_id=1,
                    subject_id='migration-probe',
                    client_pk=9910,
                    granted_scopes=['openid', 'offline_access'],
                    granted_resources=[],
                    client_policy_version=1,
                    status='active',
                    consented_at=TimezoneUtil.utc_now().replace(tzinfo=None),
                )
            )
            apply_revision(connection, '20260912_offline_consent.py')
            upgraded_grants = sa.Table('sys_oauth_grant', sa.MetaData(), autoload_with=connection)
            remembered = connection.scalar(
                sa.select(upgraded_grants.c.remembered_scopes).where(
                    upgraded_grants.c.grant_id == 'migration-consent-probe'
                )
            )
            assert remembered == ['openid', 'offline_access']
            report['legacy_remembered_consent_preserved'] = 'passed'
            IdentitySchemaService.check(connection)
            subjects = connection.execute(
                sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
            ).all()
            assert len(subjects) == len(users_before)
            assert connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all() == users_before
            assert connection.scalar(sa.text('SELECT COUNT(*) FROM sys_oauth_scope')) == BUILTIN_SCOPE_COUNT
            # 新建认证中心表无需指定历史数据时区
            apply_revision(connection, utc)
            assert (
                connection.execute(
                    sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
                ).all()
                == subjects
            )
            columns = {
                name: [c for c in sa.inspect(connection).get_columns(name) if isinstance(c['type'], sa.DateTime)]
                for name in IdentitySchemaService.TABLES
            }
            report['identity_time_columns'] = sum(map(len, columns.values()))
            # 仅在隔离测试库中复现旧版本地时间表结构
            for table, fields in columns.items():
                quote = connection.dialect.identifier_preparer.quote
                for column in fields:
                    name = quote(column['name'])
                    if target.db_type == 'postgresql':
                        connection.exec_driver_sql(
                            f'ALTER TABLE {quote(table)} ALTER COLUMN {name} TYPE TIMESTAMP WITHOUT TIME ZONE '
                            f"USING {name} AT TIME ZONE 'Asia/Shanghai'"
                        )
                    else:
                        connection.exec_driver_sql(
                            f'UPDATE {quote(table)} SET {name}=DATE_ADD({name}, INTERVAL 8 HOUR)'
                        )
                        nullable = 'NULL' if column['nullable'] else 'NOT NULL'
                        connection.exec_driver_sql(f'ALTER TABLE {quote(table)} MODIFY {name} DATETIME {nullable}')
            connection.execute(
                sa.text("UPDATE sys_identity_subject SET create_time='2026-09-12 10:20:30' WHERE user_id=1")
            )
        with engine.connect() as connection:
            try:
                apply_revision(connection, utc)
            except RuntimeError as exc:
                assert 'identity_legacy_timezone' in str(exc)
                connection.rollback()
            else:
                raise AssertionError('Legacy timezone was guessed')
        native_snapshot(target, snapshot)
        with engine.begin() as connection:
            apply_revision(connection, utc, identity_legacy_timezone='Asia/Shanghai')
            IdentitySchemaService.check(connection)
            actual = connection.scalar(sa.select(SysIdentitySubject.create_time).where(SysIdentitySubject.user_id == 1))
            assert actual == datetime(2026, 9, 12, 2, 20, 30, tzinfo=timezone.utc), actual
            assert connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all() == users_before
            assert (
                connection.execute(
                    sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
                ).all()
                == subjects
            )
            foreign_keys = sa.inspect(connection).get_foreign_keys('sys_oauth_refresh_token')
            assert {'parent_token_id', 'replaced_by_token_id'}.issubset(
                {field for key in foreign_keys for field in key['constrained_columns']}
            )
            report['refresh_foreign_keys'] = len(foreign_keys)
            report['version'] = connection.scalar(sa.text('SELECT version()'))
        report['fresh_and_legacy_migrations'] = 'passed'
        report['missing_timezone_rejected'] = 'passed'
        report['user_and_subject_preservation'] = 'passed'
        return {'users': users_before, 'subjects': subjects}
    finally:
        engine.dispose()


async def verify_refresh(target: DataSourceSettings, report: dict) -> None:  # noqa: PLR0915
    """
    通过真实行锁与事务验证刷新令牌轮换和离线撤销

    :param target: 隔离测试库连接配置
    :param report: 原地补充验收结果的报告字典
    :return: 无
    """

    OidcConfig.oidc_issuer = 'https://identity-verification.example'
    OidcConfig.oidc_public_base_url = OidcConfig.oidc_issuer
    OidcConfig.oidc_token_hash_pepper = PEPPER
    signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    engine = create_async_db_engine(config=target, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def seed(*, expired: bool = False) -> tuple[str, OAuthClientPrincipal, str]:
        """
        创建令牌轮换所需的客户端、会话和授权

        :param expired: 是否创建自然过期的SSO会话
        :return: 刷新令牌、客户端身份及会话标识
        """

        now = TimezoneUtil.utc_now()
        async with factory() as db:
            user = await db.get(SysUser, 1)
            subject = await db.scalar(sa.select(SysIdentitySubject).where(SysIdentitySubject.user_id == 1))
            client = SysOAuthClient(
                client_id='verify_' + uuid4().hex,
                client_name='Database verification',
                client_type='public',
                token_endpoint_auth_method='none',
                grant_types=['authorization_code', 'refresh_token'],
                response_types=['code'],
                policy_version=1,
                status='0',
            )
            db.add(client)
            await db.flush()
            scopes = (
                await db.scalars(
                    sa.select(SysOAuthScope).where(SysOAuthScope.scope_code.in_(['openid', 'offline_access']))
                )
            ).all()
            db.add_all([SysOAuthClientScope(client_pk=client.client_pk, scope_pk=s.scope_pk) for s in scopes])
            session = SysSsoSession(
                sid=str(uuid4()),
                session_secret_hash='a' * 64,
                user_id=1,
                subject_id=subject.subject_id,
                auth_version=1,
                auth_time=now - timedelta(hours=1),
                last_seen_at=now - timedelta(hours=1),
                idle_expires_at=now + timedelta(minutes=-30 if expired else 30),
                absolute_expires_at=now + timedelta(hours=-1 if expired else 8),
                acr='pwd',
                amr=['pwd'],
                status='expired' if expired else 'active',
            )
            grant = SysOAuthGrant(
                grant_id=str(uuid4()),
                user_id=1,
                subject_id=subject.subject_id,
                client_pk=client.client_pk,
                granted_scopes=['openid', 'offline_access'],
                granted_resources=[],
                client_policy_version=1,
                consented_at=now,
                status='active',
            )
            db.add_all([session, grant])
            await db.flush()
            token = await TokenService._create_refresh_token(
                db,
                client,
                grant,
                user,
                subject,
                session,
                ['openid', 'offline_access'],
                [],
                now,
                token_pepper=PEPPER,
            )
            await db.commit()
            return token, OAuthClientPrincipal(client.client_id, 'public', 'none'), session.sid

    async def rotate(token: str, principal: OAuthClientPrincipal) -> str:
        """
        在独立事务中轮换测试刷新令牌

        :param token: 当前刷新令牌
        :param principal: 客户端身份
        :return: 轮换后的刷新令牌
        """

        async with factory() as db:
            try:
                result = await TokenService.refresh_token(
                    db,
                    {'grant_type': 'refresh_token', 'client_id': principal.client_id, 'refresh_token': token},
                    principal,
                    signing_key=signing,
                    kid='verification-only',
                    token_pepper=PEPPER,
                )
                await db.commit()
                return result.refresh_token
            except RefreshTokenReuseDetected:
                await db.commit()
                raise
            except Exception:
                await db.rollback()
                raise

    try:
        for expired in (False, True):
            old, principal, sid = await seed(expired=expired)
            successor = await rotate(old, principal)
            async with factory() as db:
                row = await OAuthTokenDao.get_by_token_id(db, parse_opaque_token(old, 'rt1').token_id)
                new = await OAuthTokenDao.get_by_token_id(db, parse_opaque_token(successor, 'rt1').token_id)
                assert row.status == 'used' and row.replaced_by_token_id == new.token_id
                assert new.parent_token_id == row.token_id and new.absolute_expires_at == row.absolute_expires_at
                await SsoSessionDao.revoke(db, sid, reason='verification-explicit-logout')
                await db.commit()
            try:
                await rotate(successor, principal)
            except OAuthProtocolException as exc:
                assert exc.error == 'invalid_grant'
            else:
                raise AssertionError('Explicit logout did not block refresh')
        report['rotation_and_offline_expiry'] = 'passed'
        report['explicit_logout_stops_offline_refresh'] = 'passed'
        old, principal, _sid = await seed()
        with patch.object(TokenService, '_issue_access_token', AsyncMock(side_effect=RuntimeError('signer-failure'))):
            try:
                await rotate(old, principal)
            except RuntimeError as exc:
                assert str(exc) == 'signer-failure'
            else:
                raise AssertionError('Expected signer failure')
        async with factory() as db:
            row = await OAuthTokenDao.get_by_token_id(db, parse_opaque_token(old, 'rt1').token_id)
            count = await db.scalar(
                sa.select(sa.func.count())
                .select_from(SysOAuthRefreshToken)
                .where(SysOAuthRefreshToken.family_id == row.family_id)
            )
            assert row.status == 'active' and row.replaced_by_token_id is None and count == 1
        report['signing_failure_transaction_rollback'] = 'passed'
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                rotate(old, principal),
                rotate(old, principal),
                return_exceptions=True,
            ),
            timeout=30,
        )
        assert sum(isinstance(value, str) for value in outcomes) == 1, [type(value).__name__ for value in outcomes]
        assert sum(isinstance(value, RefreshTokenReuseDetected) for value in outcomes) == 1, [
            type(value).__name__ for value in outcomes
        ]
        async with factory() as db:
            row = await OAuthTokenDao.get_by_token_id(db, parse_opaque_token(old, 'rt1').token_id)
            states = (
                await db.scalars(
                    sa.select(SysOAuthRefreshToken.status).where(SysOAuthRefreshToken.family_id == row.family_id)
                )
            ).all()
            assert sorted(states) == ['reuse_detected', 'revoked'], states
        report['concurrent_rotation_and_replay_commit'] = 'passed'
    finally:
        await engine.dispose()


def main() -> None:  # noqa: PLR0915
    """
    执行数据库验收并输出不包含凭据的报告

    :return: 无
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', default=str(BACKEND / '.env.dev'))
    parser.add_argument('--source')
    parser.add_argument('--config')
    parser.add_argument('--report', required=True)
    parser.add_argument('--keep', action='store_true', help='保留本次临时库，用于后续隔离浏览器验收')
    args = parser.parse_args()
    source = load_source(args)
    created: list[str] = []
    report = {'dialect': source.db_type, 'status': 'running', 'started_at': TimezoneUtil.utc_now().isoformat()}
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        target = create_database(source, created)
        report['database'] = target.db_database
        initialize_legacy(target)
        snapshot = output.with_suffix('.snapshot')
        before = verify_migrations(target, report, snapshot)
        asyncio.run(verify_refresh(target, report))
        restored = create_database(source, created)
        native_snapshot(restored, snapshot, restore=True)
        engine = create_sync_db_engine(config=restored, echo=False)
        try:
            with engine.connect() as connection:
                assert connection.execute(sa.text('SELECT * FROM sys_user ORDER BY user_id')).all() == before['users']
                assert (
                    connection.execute(
                        sa.text('SELECT user_id, subject_id FROM sys_identity_subject ORDER BY user_id')
                    ).all()
                    == before['subjects']
                )
                actual = connection.scalar(sa.text('SELECT create_time FROM sys_identity_subject WHERE user_id=1'))
                assert actual == datetime(2026, 9, 12, 10, 20, 30)
        finally:
            engine.dispose()
        report['native_backup_restore'] = 'passed'
        report['restored_database'] = restored.db_database
        report['status'] = 'passed'
    except Exception as exc:
        message = str(exc)
        secret = source.db_password.get_secret_value()
        if secret:
            message = message.replace(secret, '[redacted]')
        report['error'] = type(exc).__name__ + ': ' + message[:1800]
        report['status'] = 'failed'
    finally:
        if not args.keep:
            cleanup(source, created)
        report['created_databases'] = created
        report['temporary_databases_retained'] = args.keep
        report['completed_at'] = TimezoneUtil.utc_now().isoformat()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
