import hashlib

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.ext.asyncio import AsyncSession

from module_identity.entity.do.identity_subject_do import SysIdentitySubject
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.do.oauth_client_do import SysOAuthClient, SysOAuthClientSecret, SysOAuthClientUri
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken, SysSsoSession
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.do.oidc_key_do import SysOidcSigningKey

_HASH_HEX_LENGTH = 64


def test_all_identity_tables_are_registered() -> None:
    """断言统一认证第一阶段的全部表均注册到共享 MetaData。"""
    expected = {
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
    }
    actual = {
        model.__table__.name
        for model in (
            SysIdentitySubject,
            SysOAuthClient,
            SysOAuthClientSecret,
            SysOAuthClientUri,
            SysOAuthResource,
            SysOAuthScope,
            SysOAuthClientScope,
            SysOAuthClientResource,
            SysOAuthGrant,
            SysOAuthRefreshToken,
            SysSsoSession,
            SysOidcSigningKey,
            SysOAuthAuditLog,
        )
    }
    assert actual == expected


def test_identity_constraints_and_indexes_are_security_relevant() -> None:
    """断言主体、URI、Refresh Token 和密钥的唯一性/外键/索引存在。"""
    subject = SysIdentitySubject.__table__
    assert {'uk_identity_subject_user', 'uk_identity_subject_subject'} <= {
        constraint.name for constraint in subject.constraints if constraint.name
    }
    assert any(fk.name == 'fk_identity_subject_user' and fk.ondelete == 'RESTRICT' for fk in subject.foreign_keys)

    uri = SysOAuthClientUri.__table__
    assert 'uri_hash' in uri.c
    assert 'uk_oauth_client_uri_hash' in {constraint.name for constraint in uri.constraints if constraint.name}
    assert any(index.name == 'idx_oauth_client_uri_type' for index in uri.indexes)

    refresh = SysOAuthRefreshToken.__table__
    assert refresh.c.token_hash.type.length == _HASH_HEX_LENGTH
    assert SysSsoSession.__table__.c.session_secret_hash.type.length == _HASH_HEX_LENGTH
    assert SysSsoSession.__table__.c.user_agent_hash.type.length == _HASH_HEX_LENGTH
    assert 'uk_oauth_refresh_token_hash' in {constraint.name for constraint in refresh.constraints if constraint.name}
    assert any(index.name == 'idx_oauth_refresh_family' for index in refresh.indexes)

    key_constraints = [
        constraint for constraint in SysOidcSigningKey.__table__.constraints if isinstance(constraint, CheckConstraint)
    ]
    assert any(constraint.name == 'ck_oidc_signing_key_private_material' for constraint in key_constraints)


def test_client_update_by_is_not_datetime_updated_automatically() -> None:
    """断言更新者字段保持字符串语义，更新时间由 update_time 管理。"""
    assert SysOAuthClient.update_by.onupdate is None
    assert SysOAuthClient.update_time.onupdate is not None


def test_client_scope_relationships_have_only_named_composite_primary_keys() -> None:
    """断言关系表元数据与 migration 使用一致的复合主键。"""
    scope_table = SysOAuthClientScope.__table__
    resource_table = SysOAuthClientResource.__table__
    assert scope_table.primary_key.name == 'pk_oauth_client_scope'
    assert resource_table.primary_key.name == 'pk_oauth_client_resource'
    assert 'pk_oauth_client_scope' not in {index.name for index in scope_table.indexes}
    assert 'pk_oauth_client_resource' not in {index.name for index in resource_table.indexes}


@pytest.mark.asyncio
async def test_client_audit_defaults_are_empty_strings(data_session: AsyncSession) -> None:
    """断言 Client 审计字段落库默认值是真正空字符串。"""
    client = SysOAuthClient(
        client_pk=9201,
        client_id='default-client',
        client_name='Default Client',
        client_type='public',
        token_endpoint_auth_method='none',
        grant_types=['authorization_code'],
        response_types=['code'],
    )
    data_session.add(client)
    await data_session.flush()
    assert client.create_by == ''
    assert client.update_by == ''


def test_client_uri_derives_hash_for_cross_database_unique_index() -> None:
    """断言完整 URI 通过 SHA-256 派生固定长度摘要。"""
    uri = SysOAuthClientUri(client_pk=1, uri_type='redirect', uri='https://client.example/callback')
    assert uri.uri_hash == hashlib.sha256(uri.uri.encode('utf-8')).hexdigest()
