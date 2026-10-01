import pytest

from module_identity.redis_keys import OidcRedisKey
from utils.oidc_util import OidcUtil

_SHA256_HEX_LENGTH = 64


def test_oidc_keys_are_isolated_from_legacy_access_token_namespace() -> None:
    keys = [
        OidcRedisKey.interaction('interaction-id'),
        OidcRedisKey.authorization_code('code-id'),
        OidcRedisKey.sso_session('session-id'),
        OidcRedisKey.user_sessions(7),
        OidcRedisKey.revoked_jti('token-id'),
    ]

    assert all(key.startswith('oidc:') and not key.startswith('access_token:') for key in keys)


def test_sensitive_identifiers_use_independent_32_byte_pepper() -> None:
    pepper = 'independent-pepper-value-' + 'x' * 8
    digest = OidcUtil.hash_sensitive_identifier('user@example.com', pepper)

    assert len(digest) == _SHA256_HEX_LENGTH
    assert digest in OidcRedisKey.login_user_rate_limit(digest)
    assert digest in OidcRedisKey.sso_cookie(digest)

    with pytest.raises(ValueError):
        OidcUtil.hash_sensitive_identifier('user@example.com', 'short')
    with pytest.raises(TypeError):
        OidcUtil.hash_sensitive_identifier('user@example.com', 123)  # type: ignore[arg-type]


@pytest.mark.parametrize('value', ['../escape', 'space value', 'a' * 129])
def test_unsafe_key_components_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        OidcRedisKey.interaction(value)


def test_digest_components_must_be_sha256_hex() -> None:
    with pytest.raises(ValueError):
        OidcRedisKey.sso_cookie('not-a-digest')
    with pytest.raises(TypeError):
        OidcRedisKey.sso_cookie(123)  # type: ignore[arg-type]
