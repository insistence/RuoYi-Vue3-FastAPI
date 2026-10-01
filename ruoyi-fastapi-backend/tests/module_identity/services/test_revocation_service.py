from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config.env import OidcConfig
from module_identity.security.opaque_token import generate_refresh_token, token_digest
from module_identity.security.principal import OAuthClientPrincipal
from module_identity.service.infrastructure_service import AfterCommitCoordinator
from module_identity.service.token_protocol_service import RevocationService
from tests.module_identity.support.redis_fakes import FakeRedis

_PEPPER = 'revocation-test-pepper-' + 'x' * 32


def _config() -> SimpleNamespace:
    """构造撤销所需的最小配置。"""

    return SimpleNamespace(
        oidc_issuer='https://auth.example.com',
        oidc_allowed_clock_skew_seconds=60,
        oidc_token_hash_pepper=_PEPPER,
    )


@pytest.fixture(autouse=True)
def _configure_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    """将全局 OIDC 配置固定为本文件测试所需的协议值。"""

    monkeypatch.setattr(OidcConfig, 'oidc_issuer', 'https://auth.example.com')
    monkeypatch.setattr(OidcConfig, 'oidc_allowed_clock_skew_seconds', 60)
    monkeypatch.setattr(OidcConfig, 'oidc_token_hash_pepper', _PEPPER)


def _client(client_type: str = 'public') -> SimpleNamespace:
    """构造启用的撤销 Client。"""

    return SimpleNamespace(
        client_pk=10,
        client_id='client-a',
        client_type=client_type,
        status='0',
        token_endpoint_auth_method='client_secret_basic' if client_type == 'confidential' else 'none',
    )


@pytest.mark.asyncio
async def test_public_client_can_revoke_only_its_own_refresh_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public Client 只能撤销自己签发的 Refresh Token Family。"""

    monkeypatch.setattr('module_identity.service.token_protocol_service.AuditService.record', AsyncMock())
    client = _client()
    token = generate_refresh_token('token-0001')
    row = SimpleNamespace(
        client_pk=10,
        family_id='family-1',
        status='active',
        token_hash=token_digest(token, _PEPPER),
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )
    get_by_token_id = AsyncMock(return_value=row)
    revoke_family = AsyncMock()
    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthTokenDao.get_by_token_id', get_by_token_id)
    monkeypatch.setattr('module_identity.service.token_protocol_service.OAuthTokenDao.revoke_family', revoke_family)
    db = object()

    await RevocationService.revoke(
        db,
        FakeRedis(),
        token,
        OAuthClientPrincipal('client-a', 'public', 'none'),
    )

    get_by_token_id.assert_awaited_once_with(db, 'token-0001', for_update=True)
    revoke_family.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('client_type', 'db_method', 'principal_type', 'principal_method', 'expected'),
    [
        ('public', 'none', 'public', 'none', True),
        ('confidential', 'client_secret_basic', 'confidential', 'client_secret_basic', True),
        ('public', 'client_secret_basic', 'public', 'none', False),
        ('public', 'none', 'public', 'client_secret_basic', False),
        ('confidential', 'none', 'confidential', 'client_secret_basic', False),
        ('confidential', 'client_secret_basic', 'confidential', 'client_secret_post', False),
    ],
)
async def test_revocation_auth_method_pair_is_exact(
    monkeypatch: pytest.MonkeyPatch,
    client_type: str,
    db_method: str,
    principal_type: str,
    principal_method: str,
    expected: bool,
) -> None:
    """Revocation 对 Public/none 与 Confidential/Basic 组合逐项 fail closed。"""

    client = _client(client_type)
    client.token_endpoint_auth_method = db_method
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )

    result = await RevocationService._resolve_caller(
        object(), OAuthClientPrincipal('client-a', principal_type, principal_method)
    )

    assert (result is not None) is expected


@pytest.mark.asyncio
async def test_unknown_refresh_is_idempotent_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知或错误 Secret 不得暴露存在性，且 RFC7009 仍返回成功。"""

    client = _client()
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthTokenDao.get_by_token_id', AsyncMock(return_value=None)
    )

    result = await RevocationService.revoke(
        object(),
        FakeRedis(),
        generate_refresh_token('token-0002'),
        OAuthClientPrincipal('client-a', 'public', 'none'),
    )

    assert result is None


@pytest.mark.asyncio
async def test_access_revocation_is_written_only_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Access JTI 撤销必须在数据库提交成功后写入 Redis。"""

    client = _client('confidential')
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject',
            'client_id': 'client-a',
            'aud': ['https://api.example'],
            'scope': 'api.read',
            'iat': 100,
            'exp': 500,
            'jti': 'access-jti',
        },
    )
    redis = FakeRedis()
    coordinator = AfterCommitCoordinator()
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    now = datetime.fromtimestamp(200, timezone.utc)

    await RevocationService.revoke(
        db,
        redis,
        'signed-access',
        OAuthClientPrincipal('client-a', 'confidential', 'client_secret_basic'),
        coordinator=coordinator,
        now=now,
    )
    assert await redis.get('oidc:revoked_jti:access-jti') is None
    await coordinator.commit(db)
    assert await redis.get('oidc:revoked_jti:access-jti') == '1'


@pytest.mark.asyncio
async def test_public_client_can_revoke_its_own_access_after_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public Client 可撤销自己通过 PKCE 获得的 Access JWT。"""

    client = _client('public')
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject',
            'client_id': 'client-a',
            'aud': ['https://api.example'],
            'scope': 'api.read',
            'gty': 'authorization_code',
            'iat': 100,
            'exp': 500,
            'jti': 'public-access-jti',
        },
    )
    redis = FakeRedis()
    coordinator = AfterCommitCoordinator()
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    await RevocationService.revoke(
        db,
        redis,
        'signed-public-access',
        OAuthClientPrincipal('client-a', 'public', 'none'),
        coordinator=coordinator,
        now=datetime.fromtimestamp(200, timezone.utc),
    )
    await coordinator.commit(db)

    assert await redis.get('oidc:revoked_jti:public-access-jti') == '1'


@pytest.mark.asyncio
async def test_public_client_cannot_revoke_other_client_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public Client 不能撤销其他业务 Client 的 Access JWT。"""

    client = _client('public')
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.OAuthClientDao.get_by_client_id', _client_lookup(client)
    )
    monkeypatch.setattr(
        'module_identity.service.token_protocol_service.decode_access_token',
        lambda *_args, **_kwargs: {
            'iss': 'https://auth.example.com',
            'sub': 'subject',
            'client_id': 'client-b',
            'aud': ['https://api.example'],
            'scope': 'api.read',
            'gty': 'authorization_code',
            'iat': 100,
            'exp': 500,
            'jti': 'foreign-access-jti',
        },
    )
    redis = FakeRedis()
    await RevocationService.revoke(
        object(), redis, 'foreign-access', OAuthClientPrincipal('client-a', 'public', 'none')
    )

    assert not redis.values


def _client_lookup(client: SimpleNamespace) -> object:
    """返回指定 Client 的异步 DAO 查询桩。"""

    async def lookup(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return client

    return lookup
