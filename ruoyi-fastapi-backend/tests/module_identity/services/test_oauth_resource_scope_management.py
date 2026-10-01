from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
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
from module_identity.entity.vo.oauth_client_vo import ClientCreateModel, ClientUpdateModel, ClientUriModel
from module_identity.entity.vo.oauth_resource_vo import (
    ResourceCreateModel,
    ResourcePageQueryModel,
    ResourceStatusModel,
    ResourceUpdateModel,
    ScopeModel,
    ScopePageQueryModel,
    ScopeStatusModel,
)
from module_identity.entity.vo.oidc_key_vo import OidcKeyRotateModel
from module_identity.service.oauth_management_service import (
    OAuthClientManagementError,
    OAuthClientManagementService,
    OAuthResourceManagementService,
)

_FIRST_POLICY_CHANGE = 2
_SECOND_POLICY_CHANGE = 3
_EXPECTED_PAGE_TOTAL = 3


@pytest_asyncio.fixture
async def resource_session() -> AsyncSession:
    """创建只包含 Resource/Scope/Client 管理表的真实 SQLite 会话。"""
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


def _resource_payload(**changes: object) -> ResourceCreateModel:
    """构造一个合法 Resource DTO。"""
    values: dict[str, object] = {
        'resource_id': 'orders-api',
        'resource_name': '订单 API',
        'audience': 'https://orders-api.example/api',
        'allowed_claims': ['sub', 'scope'],
    }
    values.update(changes)
    return ResourceCreateModel.model_validate(values)


@pytest.mark.parametrize('value', ['bad/id', 'bad,code', 'bad%20code', 'bad code', '\\x00bad'])
def test_management_identifiers_are_safe_path_segments(value: str) -> None:
    """Resource、Scope 和 Key 标识拒绝路径分隔符、CSV 分隔符和控制字符。"""
    with pytest.raises(ValueError):
        ResourceCreateModel(resource_id=value, resource_name='x', audience='https://x.example')
    with pytest.raises(ValueError):
        ScopeModel(scope_code=value, scope_name='x', scope_type='identity')
    with pytest.raises(ValueError):
        OidcKeyRotateModel(kid=value, publish_at=datetime.now(timezone.utc))


def _client_payload(resource_id: str = 'orders-api', scope_code: str | None = None) -> ClientCreateModel:
    """构造授权码机密 Client。"""
    return ClientCreateModel.model_validate(
        {
            'client_name': 'Resource 管理测试 Client',
            'client_type': 'confidential',
            'token_endpoint_auth_method': 'client_secret_basic',
            'grant_types': ['authorization_code'],
            'response_types': ['code'],
            'scope_codes': [scope_code] if scope_code else [],
            'resource_ids': [resource_id],
            'redirect_uris': ['https://client.example/callback'],
        }
    )


async def _create_resource(session: AsyncSession, resource_id: str = 'orders-api') -> object:
    """创建一个基础启用 Resource。"""
    return await OAuthResourceManagementService.create_resource(
        session,
        _resource_payload(resource_id=resource_id, audience=f'https://{resource_id}.example/api'),
        actor='admin',
    )


@pytest.mark.asyncio
async def test_resource_crud_introspection_policy_and_invalidation_snapshot(resource_session: AsyncSession) -> None:
    """Resource 更新应校验 introspection Client、递增绑定 Client 策略并提供撤销目标接口。"""
    await _create_resource(resource_session)
    client = await OAuthClientManagementService.create_client(resource_session, _client_payload(), actor='admin')
    update_values = _resource_payload(
        allowed_claims=['sub', 'email'], introspection_client_id=client.client_id
    ).model_dump()
    update_values['status'] = '0'
    updated = await OAuthResourceManagementService.update_resource(
        resource_session,
        ResourceUpdateModel.model_validate(update_values),
        actor='admin',
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert updated.introspection_client_id == client.client_id
    assert updated.allowed_claims == ['sub', 'email']
    stored_client = await resource_session.get(SysOAuthClient, 1)
    assert stored_client is not None and stored_client.policy_version == _FIRST_POLICY_CHANGE
    resource_session.add(
        SysOAuthGrant(
            grant_id='grant-1',
            user_id=7,
            subject_id='subject-1',
            client_pk=stored_client.client_pk,
            granted_scopes=[],
            granted_resources=['orders-api'],
            client_policy_version=stored_client.policy_version,
            status='active',
        )
    )
    await resource_session.flush()
    targets = await OAuthResourceManagementService.collect_resource_invalidation_targets(resource_session, 'orders-api')
    assert targets.client_ids == (client.client_id,)
    assert targets.grant_ids == ('grant-1',)
    assert targets.refresh_token_ids == ()
    disabled = await OAuthResourceManagementService.change_resource_status(
        resource_session, ResourceStatusModel(resource_id='orders-api', status='1'), actor='admin'
    )
    assert disabled.status == '1'
    assert (await resource_session.get(SysOAuthClient, 1)).policy_version == _SECOND_POLICY_CHANGE


@pytest.mark.asyncio
async def test_resource_audience_and_introspection_validation_is_fail_closed(resource_session: AsyncSession) -> None:
    """Resource audience 必须绝对 HTTPS，introspection Client 必须 active confidential。"""
    for audience in (
        'http://orders.example/api',
        'https://user:pass@orders.example/api',
        'https://orders.example/api#fragment',
        'https:///missing-host',
    ):
        with pytest.raises(OAuthClientManagementError):
            await OAuthResourceManagementService.create_resource(
                resource_session, _resource_payload(audience=audience), actor='a'
            )
    await _create_resource(resource_session)
    public = await OAuthClientManagementService.create_client(
        resource_session,
        ClientCreateModel.model_validate(
            {
                'client_name': 'Public',
                'client_type': 'public',
                'token_endpoint_auth_method': 'none',
                'grant_types': ['authorization_code'],
                'response_types': ['code'],
                'redirect_uris': ['https://public.example/callback'],
            }
        ),
        actor='a',
    )
    with pytest.raises(OAuthClientManagementError, match='机密客户端'):
        await OAuthResourceManagementService.update_resource(
            resource_session,
            ResourceUpdateModel.model_validate(
                _resource_payload(introspection_client_id=public.client_id).model_dump()
            ),
            actor='a',
        )


@pytest.mark.asyncio
async def test_scope_binding_claim_whitelist_and_builtin_openid(resource_session: AsyncSession) -> None:
    """Scope 的 Resource 归属、Claim 白名单和内置 openid 保护必须 fail-closed。"""
    await _create_resource(resource_session)
    scope = await OAuthResourceManagementService.create_scope(
        resource_session,
        ScopeModel(
            scope_code='orders.read',
            scope_name='读取订单',
            scope_type='resource',
            resource_id='orders-api',
            claims=['sub', 'scope'],
        ),
        actor='admin',
    )
    client = await OAuthClientManagementService.create_client(
        resource_session, _client_payload(scope_code='orders.read'), actor='admin'
    )
    changed = await OAuthResourceManagementService.update_scope(
        resource_session,
        ScopeModel(
            scope_code='orders.read',
            scope_name='读取订单',
            scope_type='resource',
            resource_id='orders-api',
            claims=['sub'],
        ),
        actor='admin',
    )
    assert changed.claims == ['sub']
    assert (await resource_session.get(SysOAuthClient, 1)).policy_version == _FIRST_POLICY_CHANGE
    with pytest.raises(OAuthClientManagementError, match='不允许发布的声明'):
        await OAuthResourceManagementService.create_scope(
            resource_session,
            ScopeModel(scope_code='bad', scope_name='Bad', scope_type='identity', claims=['user_id']),
            actor='admin',
        )
    await OAuthResourceManagementService.create_scope(
        resource_session,
        ScopeModel(scope_code='openid', scope_name='OpenID', scope_type='identity', claims=['sub']),
        actor='admin',
    )
    with pytest.raises(OAuthClientManagementError, match='不能停用'):
        await OAuthResourceManagementService.change_scope_status(
            resource_session, ScopeStatusModel(scope_code='openid', status='1'), actor='admin'
        )
    with pytest.raises(OAuthClientManagementError, match='不能停用或更改归属'):
        await OAuthResourceManagementService.update_scope(
            resource_session,
            ScopeModel(
                scope_code='openid',
                scope_name='OpenID',
                scope_type='resource',
                resource_id='orders-api',
                claims=['sub'],
            ),
            actor='admin',
        )
    assert scope.scope_code == 'orders.read' and client.client_id


@pytest.mark.asyncio
async def test_display_only_client_resource_scope_updates_do_not_bump_policy_version(
    resource_session: AsyncSession,
) -> None:
    """仅修改展示字段时，不应使绑定凭据的策略版本失效。"""
    await _create_resource(resource_session)
    await OAuthResourceManagementService.create_scope(
        resource_session,
        ScopeModel(
            scope_code='orders.read',
            scope_name='读取订单',
            scope_type='resource',
            resource_id='orders-api',
            claims=['sub'],
        ),
        actor='admin',
    )
    client = await OAuthClientManagementService.create_client(
        resource_session, _client_payload(scope_code='orders.read'), actor='admin'
    )
    assert client.policy_version == 1

    client_update = ClientUpdateModel.model_validate(
        {
            **_client_payload(scope_code='orders.read').model_dump(),
            'client_id': client.client_id,
            'client_name': '新的展示名称',
            'logo_uri': 'https://client.example/logo.svg',
            'policy_uri': 'https://client.example/policy',
            'tos_uri': 'https://client.example/terms',
            'remark': '展示备注',
        }
    )
    changed_client = await OAuthClientManagementService.update_client(resource_session, client_update, actor='admin')
    assert changed_client.policy_version == 1

    changed_resource = await OAuthResourceManagementService.update_resource(
        resource_session,
        ResourceUpdateModel(
            **_resource_payload(resource_name='新的 Resource 展示名', remark='展示备注').model_dump(),
            status='0',
        ),
        actor='admin',
    )
    assert changed_resource.resource_name == '新的 Resource 展示名'
    assert (await resource_session.get(SysOAuthClient, 1)).policy_version == 1

    changed_scope = await OAuthResourceManagementService.update_scope(
        resource_session,
        ScopeModel(
            scope_code='orders.read',
            scope_name='新的 Scope 展示名',
            scope_type='resource',
            resource_id='orders-api',
            claims=['sub'],
            remark='展示备注',
        ),
        actor='admin',
    )
    assert changed_scope.scope_name == '新的 Scope 展示名'
    assert (await resource_session.get(SysOAuthClient, 1)).policy_version == 1


@pytest.mark.asyncio
async def test_scope_requires_active_resource(resource_session: AsyncSession) -> None:
    """Resource Scope 不得绑定未知或停用 Resource。"""
    await _create_resource(resource_session)
    await OAuthResourceManagementService.change_resource_status(
        resource_session, ResourceStatusModel(resource_id='orders-api', status='1'), actor='admin'
    )
    with pytest.raises(OAuthClientManagementError, match='已停用'):
        await OAuthResourceManagementService.create_scope(
            resource_session,
            ScopeModel(scope_code='orders.read', scope_name='读取', scope_type='resource', resource_id='orders-api'),
            actor='admin',
        )


@pytest.mark.asyncio
async def test_resource_scope_count_matches_filter_and_ignores_pagination(resource_session: AsyncSession) -> None:
    """Resource/Scope 分页的 total 必须是过滤后的全量数量。"""
    await _create_resource(resource_session)
    for index in range(2):
        await _create_resource(resource_session, resource_id=f'orders-api-{index}')
    resource_query = ResourcePageQueryModel(resource_name='订单', page_num=2, page_size=1)
    resource_rows = await OAuthResourceManagementService.list_resources(resource_session, resource_query)
    resource_total = await OAuthResourceManagementService.count_resources(resource_session, resource_query)
    assert len(resource_rows) == 1
    assert resource_total == _EXPECTED_PAGE_TOTAL

    for index in range(3):
        await OAuthResourceManagementService.create_scope(
            resource_session,
            ScopeModel(
                scope_code=f'orders.read.{index}',
                scope_name=f'读取订单 {index}',
                scope_type='resource',
                resource_id='orders-api',
                claims=['sub'],
            ),
            actor='admin',
        )
    scope_query = ScopePageQueryModel(scope_name='读取订单', page_num=2, page_size=1)
    scope_rows = await OAuthResourceManagementService.list_scopes(resource_session, scope_query)
    scope_total = await OAuthResourceManagementService.count_scopes(resource_session, scope_query)
    assert len(scope_rows) == 1
    assert scope_total == _EXPECTED_PAGE_TOTAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'uri',
    [
        'http://localhost/backchannel',
        'https://127.0.0.1/backchannel',
        'https://[::1]/backchannel',
        'https://10.0.0.1/backchannel',
        'https://169.254.1.1/backchannel',
        'https://[ff02::1]/backchannel',
        'https://0.0.0.0/backchannel',
    ],
)
async def test_backchannel_registration_has_first_layer_ssrf_boundary(resource_session: AsyncSession, uri: str) -> None:
    """Backchannel 注册期拒绝非 HTTPS 和特殊 IP，运行时仍会再次解析校验。"""
    await _create_resource(resource_session)
    client = await OAuthClientManagementService.create_client(resource_session, _client_payload(), actor='admin')
    with pytest.raises(OAuthClientManagementError):
        await OAuthClientManagementService.add_uri(
            resource_session,
            client.client_id,
            ClientUriModel(uri_type='backchannel_logout', uri=uri),
            actor='admin',
        )


@pytest.mark.asyncio
async def test_backchannel_registration_rechecks_dns_target(
    resource_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backchannel 注册必须执行与发送端一致的 DNS 公网重解析。"""
    await _create_resource(resource_session)
    client = await OAuthClientManagementService.create_client(resource_session, _client_payload(), actor='admin')
    monkeypatch.setattr(
        'module_identity.security.uri_validator.socket.getaddrinfo',
        lambda *_args, **_kwargs: [(2, 1, 6, '', ('169.254.169.254', 443))],
    )
    with pytest.raises(OAuthClientManagementError):
        await OAuthClientManagementService.add_uri(
            resource_session,
            client.client_id,
            ClientUriModel(uri_type='backchannel_logout', uri='https://client.example/logout'),
            actor='admin',
        )
