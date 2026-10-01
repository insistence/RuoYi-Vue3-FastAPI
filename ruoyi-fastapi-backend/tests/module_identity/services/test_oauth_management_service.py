from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
from config.env import OidcConfig
from module_identity.entity.do.oauth_audit_do import SysOAuthAuditLog
from module_identity.entity.do.oauth_client_do import (
    SysOAuthClient,
    SysOAuthClientSecret,
    SysOAuthClientUri,
)
from module_identity.entity.do.oauth_grant_do import SysOAuthGrant, SysOAuthRefreshToken, SysSsoSession
from module_identity.entity.do.oauth_resource_do import (
    SysOAuthClientResource,
    SysOAuthClientScope,
    SysOAuthResource,
    SysOAuthScope,
)
from module_identity.entity.vo.oauth_client_vo import (
    ClientCreateModel,
    ClientPageQueryModel,
    ClientStatusModel,
    ClientUpdateModel,
    ClientUriModel,
)
from module_identity.security.client_auth import verify_client_secret
from module_identity.service.oauth_management_service import (
    OAuthClientManagementError,
    OAuthClientManagementService,
    OAuthManagementBaseService,
)

_EXPECTED_PAGE_TOTAL = 3


@pytest_asyncio.fixture
async def management_session() -> AsyncSession:
    """创建只包含 OAuth 管理表的真实 SQLite 异步会话。"""
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    tables = [
        SysOAuthClient.__table__,
        SysOAuthResource.__table__,
        SysOAuthScope.__table__,
        SysOAuthClientSecret.__table__,
        SysOAuthClientUri.__table__,
        SysOAuthClientScope.__table__,
        SysOAuthClientResource.__table__,
        SysOAuthGrant.__table__,
        SysSsoSession.__table__,
        SysOAuthRefreshToken.__table__,
        SysOAuthAuditLog.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_definitions(session: AsyncSession) -> None:
    """写入用于绑定校验的启用 Resource 和 Scope。"""
    resource = SysOAuthResource(
        resource_id='resource-a',
        resource_name='Resource A',
        audience='urn:test:a',
        allowed_claims=['sub', 'email'],
        status='0',
        create_by='tester',
        update_by='tester',
    )
    session.add(resource)
    await session.flush()
    session.add_all(
        [
            SysOAuthScope(
                scope_code='openid',
                scope_name='OpenID',
                scope_type='identity',
                resource_pk=None,
                claims=['sub'],
                status='0',
                create_by='tester',
                update_by='tester',
            ),
            SysOAuthScope(
                scope_code='resource.read',
                scope_name='Read',
                scope_type='resource',
                resource_pk=resource.resource_pk,
                claims=['email'],
                status='0',
                create_by='tester',
                update_by='tester',
            ),
        ]
    )
    await session.flush()
    await session.commit()


def _confidential_payload(**changes: object) -> ClientCreateModel:
    """构造一个需要授权码、PKCE 和回调地址的机密 Client。"""
    values: dict[str, object] = {
        'client_name': '管理测试 Client',
        'client_type': 'confidential',
        'token_endpoint_auth_method': 'client_secret_basic',
        'grant_types': ['authorization_code', 'refresh_token'],
        'response_types': ['code'],
        'require_pkce': True,
        'scope_codes': ['openid', 'resource.read'],
        'pre_authorized_scope_codes': ['openid'],
        'resource_ids': ['resource-a'],
        'redirect_uris': ['https://client.example/callback'],
        'post_logout_redirect_uris': ['https://client.example/logout'],
        'cors_origins': ['https://client.example'],
    }
    values.update(changes)
    return ClientCreateModel.model_validate(values)


@pytest.mark.asyncio
async def test_after_commit_failure_does_not_rollback_committed_management_change() -> None:
    """提交后的运行时回调失败不得回滚已提交的管理事务。"""

    class _Db:
        commits = 0
        rollbacks = 0

        async def commit(self) -> None:
            self.commits += 1

        async def rollback(self) -> None:
            self.rollbacks += 1

    db = _Db()

    async def operation() -> str:
        return 'done'

    async def after_commit() -> None:
        raise RuntimeError('runtime refresh failed')

    with pytest.raises(RuntimeError, match='runtime refresh failed'):
        await OAuthManagementBaseService._transaction(db, operation, after_commit)
    assert db.commits == 1
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_create_detail_bindings_secret_and_cors_snapshot(management_session: AsyncSession) -> None:
    """创建应原子写入绑定，创建不自动发放 Secret，轮换时只返回一次明文。"""
    await _seed_definitions(management_session)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    detail = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(), actor='admin', now=now
    )
    secret = await OAuthClientManagementService.rotate_secret(
        management_session, detail.client_id, actor='admin', now=now
    )
    assert secret.client_secret.startswith('cs1.')
    assert detail.client_id.startswith('cli_')
    assert detail.scope_codes == ['openid', 'resource.read']
    assert detail.pre_authorized_scope_codes == ['openid']
    assert detail.resource_ids == ['resource-a']
    assert verify_client_secret(
        secret.client_secret, (await management_session.get(SysOAuthClientSecret, secret.secret_id)).secret_hash
    )
    assert secret.client_secret not in repr(detail)
    assert await OAuthClientManagementService.list_active_cors_origins(management_session) == (
        'https://client.example',
    )


@pytest.mark.asyncio
async def test_update_replaces_bindings_and_increments_policy(management_session: AsyncSession) -> None:
    """更新策略应锁定 Client、替换旧绑定并单调增加 policy_version。"""
    await _seed_definitions(management_session)
    detail = await OAuthClientManagementService.create_client(management_session, _confidential_payload(), actor='a')
    update_values = _confidential_payload(
        client_name='更新后的 Client',
        pre_authorized_scope_codes=['openid', 'resource.read'],
        cors_origins=['https://new-client.example'],
    ).model_dump()
    update_values['client_id'] = detail.client_id
    update = ClientUpdateModel.model_validate(update_values)
    changed = await OAuthClientManagementService.update_client(management_session, update, actor='b')
    assert changed.client_name == '更新后的 Client'
    assert changed.policy_version == detail.policy_version + 1
    assert changed.cors_origins == ['https://new-client.example']
    assert (
        (await management_session.execute(select(SysOAuthClientUri).where(SysOAuthClientUri.client_pk == 1)))
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_status_soft_disable_and_secret_revoke_are_safe(management_session: AsyncSession) -> None:
    """状态变更、跨 Client 撤销和重复撤销都不泄漏 Secret。"""
    await _seed_definitions(management_session)
    first = await OAuthClientManagementService.create_client(management_session, _confidential_payload(), actor='a')
    second = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(client_name='第二个'), actor='a'
    )
    first_secret = await OAuthClientManagementService.rotate_secret(management_session, first.client_id, actor='a')
    second_secret = await OAuthClientManagementService.rotate_secret(management_session, second.client_id, actor='a')
    with pytest.raises(OAuthClientManagementError, match='不属于当前客户端'):
        await OAuthClientManagementService.revoke_secret(
            management_session, first.client_id, second_secret.secret_id, actor='admin'
        )
    assert await OAuthClientManagementService.revoke_secret(
        management_session, first.client_id, first_secret.secret_id, actor='admin'
    )
    assert not await OAuthClientManagementService.revoke_secret(
        management_session, first.client_id, first_secret.secret_id, actor='admin'
    )
    second_row = (
        await management_session.execute(select(SysOAuthClient).where(SysOAuthClient.client_id == second.client_id))
    ).scalar_one()
    management_session.add(
        SysOAuthGrant(
            grant_id='grant-disable',
            user_id=7,
            subject_id='subject-disable',
            client_pk=second_row.client_pk,
            granted_scopes=[],
            granted_resources=[],
            client_policy_version=second.policy_version,
            status='active',
        )
    )
    management_session.add(
        SysSsoSession(
            sid='sid-disable',
            session_secret_hash='a' * 64,
            user_id=7,
            subject_id='subject-disable',
            auth_version=1,
            auth_time=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            idle_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            absolute_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            acr='urn:test',
            amr=['pwd'],
            status='active',
        )
    )
    management_session.add(
        SysOAuthRefreshToken(
            token_id='refresh-disable',
            token_hash='b' * 64,
            family_id='family-disable',
            grant_id='grant-disable',
            user_id=7,
            subject_id='subject-disable',
            auth_version=1,
            client_pk=second_row.client_pk,
            sid='sid-disable',
            scopes=[],
            resources=[],
            status='active',
            issued_at=datetime.now(timezone.utc),
            idle_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            absolute_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
    )
    await management_session.flush()
    disabled = await OAuthClientManagementService.change_client_status(
        management_session, ClientStatusModel(client_id=second.client_id, status='1'), actor='admin'
    )
    assert disabled.status == '1'
    assert (await management_session.get(SysOAuthGrant, 'grant-disable')).status == 'revoked'
    assert (await management_session.get(SysOAuthRefreshToken, 'refresh-disable')).status == 'revoked'
    assert (await management_session.get(SysSsoSession, 'sid-disable')).status == 'active'
    disabled_again = await OAuthClientManagementService.change_client_status(
        management_session, ClientStatusModel(client_id=second.client_id, status='1'), actor='admin'
    )
    assert disabled_again.status == '1'


@pytest.mark.asyncio
async def test_client_ttl_limits_and_scope_default_are_fail_closed(
    management_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Client TTL 受平台上限约束，允许 Scope 不会被误标为默认 Scope。"""
    await _seed_definitions(management_session)
    monkeypatch.setattr(OidcConfig, 'oidc_max_access_token_ttl_seconds', 60)
    monkeypatch.setattr(OidcConfig, 'oidc_access_token_ttl_seconds', 30)
    monkeypatch.setattr(OidcConfig, 'oidc_refresh_token_idle_seconds', 100)
    monkeypatch.setattr(OidcConfig, 'oidc_refresh_token_absolute_seconds', 200)
    with pytest.raises(OAuthClientManagementError, match='访问令牌有效期'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(access_token_ttl_seconds=61),
            actor='admin',
        )
    with pytest.raises(OAuthClientManagementError, match='闲置有效期超过平台上限'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(refresh_token_idle_seconds=150, refresh_token_absolute_seconds=200),
            actor='admin',
        )
    with pytest.raises(OAuthClientManagementError, match='闲置有效期不能超过绝对有效期'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(refresh_token_idle_seconds=100, refresh_token_absolute_seconds=50),
            actor='admin',
        )
    with pytest.raises(OAuthClientManagementError, match='绝对有效期超过平台上限'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(refresh_token_idle_seconds=100, refresh_token_absolute_seconds=201),
            actor='admin',
        )
    await OAuthClientManagementService.create_client(management_session, _confidential_payload(), actor='admin')
    defaults = (
        (await management_session.execute(select(SysOAuthClientScope).where(SysOAuthClientScope.client_pk == 1)))
        .scalars()
        .all()
    )
    assert defaults and all(row.is_default == 0 for row in defaults)


@pytest.mark.asyncio
async def test_client_count_matches_filter_and_ignores_pagination(management_session: AsyncSession) -> None:
    """Client 分页的 total 必须是过滤后的全量数量，而不是当前页数量。"""
    await _seed_definitions(management_session)
    for index in range(3):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(client_name=f'分页计数 Client {index}'),
            actor='admin',
        )
    query = ClientPageQueryModel(client_name='分页计数', page_num=2, page_size=2)
    rows = await OAuthClientManagementService.list_clients(management_session, query)
    total = await OAuthClientManagementService.count_clients(management_session, query)
    assert len(rows) == 1
    assert total == _EXPECTED_PAGE_TOTAL


@pytest.mark.asyncio
async def test_secret_rotation_bounds_old_active_secret(management_session: AsyncSession) -> None:
    """轮换应将旧 Active Secret 置为 retiring 并设置明确退役窗口。"""
    await _seed_definitions(management_session)
    detail = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(), actor='admin'
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = await OAuthClientManagementService.rotate_secret(
        management_session, detail.client_id, actor='admin', now=now, retirement_seconds=120
    )
    future = now + timedelta(days=2)
    second = await OAuthClientManagementService.rotate_secret(
        management_session,
        detail.client_id,
        actor='admin',
        now=now,
        not_before=future,
        retirement_seconds=120,
    )
    old = await management_session.get(SysOAuthClientSecret, first.secret_id)
    assert old is not None and old.status == 'retiring'
    assert old.expires_at == future + timedelta(seconds=120)
    new = await management_session.get(SysOAuthClientSecret, second.secret_id)
    assert new is not None
    assert new.create_time == now
    assert new.not_before == future
    assert second.secret_hint == f'...{second.client_secret[-6:]}'
    secret_tail = second.client_secret[-6:]
    assert second.secret_hint.startswith('...')
    assert len(second.secret_hint) <= len('...') + len(secret_tail)


@pytest.mark.asyncio
async def test_secret_rotation_respects_original_expiry_and_rejects_a_gap(
    management_session: AsyncSession,
) -> None:
    """轮换不延长原过期时间，远期过期会被截断，排期断档则原子拒绝。"""
    await _seed_definitions(management_session)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    early_client = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(client_name='原过期较早'), actor='admin'
    )
    early_secret = await OAuthClientManagementService.rotate_secret(
        management_session,
        early_client.client_id,
        actor='admin',
        now=now,
        expires_at=now + timedelta(seconds=60),
    )
    await OAuthClientManagementService.rotate_secret(
        management_session,
        early_client.client_id,
        actor='admin',
        now=now,
        not_before=now + timedelta(seconds=30),
        retirement_seconds=120,
    )
    early_old = await management_session.get(SysOAuthClientSecret, early_secret.secret_id)
    assert early_old is not None and early_old.status == 'retiring'
    assert early_old.expires_at == now + timedelta(seconds=60)

    far_client = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(client_name='原过期较远'), actor='admin'
    )
    far_secret = await OAuthClientManagementService.rotate_secret(
        management_session,
        far_client.client_id,
        actor='admin',
        now=now,
        expires_at=now + timedelta(seconds=1000),
    )
    await OAuthClientManagementService.rotate_secret(
        management_session, far_client.client_id, actor='admin', now=now, retirement_seconds=120
    )
    far_old = await management_session.get(SysOAuthClientSecret, far_secret.secret_id)
    assert far_old is not None and far_old.status == 'retiring'
    assert far_old.expires_at == now + timedelta(seconds=120)

    reject_client = await OAuthClientManagementService.create_client(
        management_session, _confidential_payload(client_name='排期断档'), actor='admin'
    )
    reject_secret = await OAuthClientManagementService.rotate_secret(
        management_session,
        reject_client.client_id,
        actor='admin',
        now=now,
        expires_at=now + timedelta(seconds=60),
    )
    with pytest.raises(OAuthClientManagementError, match='新旧密钥的重叠有效期'):
        await OAuthClientManagementService.rotate_secret(
            management_session,
            reject_client.client_id,
            actor='admin',
            now=now,
            not_before=now + timedelta(seconds=60),
            retirement_seconds=120,
        )
    reject_old = await management_session.get(SysOAuthClientSecret, reject_secret.secret_id)
    assert reject_old is not None and reject_old.status == 'active'
    assert reject_old.expires_at == now + timedelta(seconds=60)
    reject_rows = (
        (
            await management_session.execute(
                select(SysOAuthClientSecret).where(SysOAuthClientSecret.client_pk == reject_old.client_pk)
            )
        )
        .scalars()
        .all()
    )
    assert len(reject_rows) == 1


@pytest.mark.asyncio
async def test_uri_add_and_soft_remove_increment_policy(management_session: AsyncSession) -> None:
    """URI 增删应锁定 Client、递增版本且保留停用历史行。"""
    await _seed_definitions(management_session)
    detail = await OAuthClientManagementService.create_client(management_session, _confidential_payload(), actor='a')
    uri_id = await OAuthClientManagementService.add_uri(
        management_session,
        detail.client_id,
        ClientUriModel(uri_type='redirect', uri='https://client.example/second-callback'),
        actor='a',
    )
    added = await OAuthClientManagementService.detail(management_session, detail.client_id)
    assert added.policy_version == detail.policy_version + 1
    assert 'https://client.example/second-callback' in added.redirect_uris
    assert await OAuthClientManagementService.remove_uri(management_session, detail.client_id, uri_id, actor='a')
    removed = await OAuthClientManagementService.detail(management_session, detail.client_id)
    assert removed.policy_version == added.policy_version + 1
    assert 'https://client.example/second-callback' not in removed.redirect_uris
    historical = await management_session.get(SysOAuthClientUri, uri_id)
    assert historical is not None and historical.status == '1'


@pytest.mark.asyncio
async def test_public_client_has_no_secret_and_uri_policy_is_fail_closed(management_session: AsyncSession) -> None:
    """Public Client 禁止轮换密钥，危险 URI 和错误绑定均在服务边界拒绝。"""
    public = ClientCreateModel.model_validate(
        {
            'client_name': '公共 Client',
            'client_type': 'public',
            'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code'],
            'response_types': ['code'],
            'scope_codes': [],
            'redirect_uris': ['https://public.example/callback'],
        }
    )
    detail = await OAuthClientManagementService.create_client(management_session, public, actor='admin')
    with pytest.raises(OAuthClientManagementError, match='公开客户端'):
        await OAuthClientManagementService.rotate_secret(management_session, detail.client_id, actor='admin')
    await _seed_definitions(management_session)
    with pytest.raises(OAuthClientManagementError, match='保留参数'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(redirect_uris=['https://client.example/callback?state=bad']),
            actor='admin',
        )
    with pytest.raises(OAuthClientManagementError, match='资源权限'):
        await OAuthClientManagementService.create_client(
            management_session,
            _confidential_payload(resource_ids=[]),
            actor='admin',
        )


@pytest.mark.asyncio
async def test_create_failure_can_be_rolled_back_by_caller(management_session: AsyncSession) -> None:
    """公共写入口提交事务，调用方后续回滚不会撤销已提交变更。"""
    await _seed_definitions(management_session)
    await OAuthClientManagementService.create_client(management_session, _confidential_payload(), actor='admin')
    await management_session.rollback()
    result = await management_session.execute(select(SysOAuthClient))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_role_allowlist_is_persisted_and_changes_client_policy(management_session: AsyncSession) -> None:
    """仅发布白名单中的角色，修改白名单后旧策略授权失效。"""
    await _seed_definitions(management_session)
    management_session.add(
        SysOAuthScope(
            scope_code='roles',
            scope_name='Roles',
            scope_type='identity',
            claims=['roles'],
            status='0',
            create_by='tester',
            update_by='tester',
        )
    )
    await management_session.commit()
    payload = _confidential_payload(
        scope_codes=['openid', 'roles'],
        resource_ids=[],
        allowed_role_keys=['analyst'],
    )
    created = await OAuthClientManagementService.create_client(management_session, payload, actor='admin')
    assert created.allowed_role_keys == ['analyst']
    values = payload.model_dump()
    values.update(client_id=created.client_id, allowed_role_keys=['reader'])
    changed = await OAuthClientManagementService.update_client(
        management_session,
        ClientUpdateModel.model_validate(values),
        actor='admin',
    )
    assert changed.policy_version == created.policy_version + 1
    loaded = await OAuthClientManagementService.detail(management_session, created.client_id)
    assert loaded.allowed_role_keys == ['reader']
    filters = (
        (
            await management_session.execute(
                select(SysOAuthClientScope.claim_filter)
                .join(SysOAuthScope, SysOAuthScope.scope_pk == SysOAuthClientScope.scope_pk)
                .where(SysOAuthScope.scope_code == 'roles')
            )
        )
        .scalars()
        .all()
    )
    assert filters == [{'claims': ['roles'], 'allowed_role_keys': ['reader']}]
    values['allowed_role_keys'] = []
    cleared = await OAuthClientManagementService.update_client(
        management_session,
        ClientUpdateModel.model_validate(values),
        actor='admin',
    )
    assert cleared.allowed_role_keys == []
    assert cleared.policy_version == changed.policy_version + 1
