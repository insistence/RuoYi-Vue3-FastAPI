import pytest
from pydantic import ValidationError

from config.env import OidcSettings


def _enabled_values() -> dict[str, object]:
    return {
        '_env_file': None,
        'oidc_enabled': True,
        'oidc_issuer': 'https://auth.example.com',
        'oidc_public_base_url': 'https://auth.example.com',
        'oidc_token_hash_pepper': 'p' * 32,
        'oidc_active_kid': '2026-primary',
        'oidc_signing_private_key_path': '/secure/oidc-private.pem',
        'oidc_interaction_login_url': 'https://auth.example.com/auth-center/login',
        'oidc_interaction_consent_url': 'https://auth.example.com/auth-center/consent',
        'oidc_interaction_error_url': 'https://auth.example.com/auth-center/error',
    }


def test_oidc_disabled_does_not_require_runtime_secrets() -> None:
    settings = OidcSettings(_env_file=None, oidc_enabled=False, oidc_issuer='', oidc_public_base_url='')

    assert settings.oidc_enabled is False


def test_oidc_enabled_accepts_secure_defaults() -> None:
    settings = OidcSettings(**_enabled_values())

    assert settings.oidc_require_pkce is True
    assert settings.oidc_legacy_auth_isolation_enabled is True
    assert settings.oidc_sso_cookie_name.startswith('__Host-')


@pytest.mark.parametrize(
    'overrides',
    [
        {'oidc_require_pkce': False},
        {'oidc_legacy_auth_isolation_enabled': False},
        {'oidc_token_hash_pepper': 'short'},
        {'oidc_issuer': 'https://auth.example.com/realm'},
        {'oidc_sso_cookie_name': 'ruoyi-sso'},
        {'oidc_interaction_login_url': 'https://ui.example.com/login'},
    ],
)
def test_oidc_enabled_rejects_unsafe_configuration(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        OidcSettings(**(_enabled_values() | overrides))


def test_oidc_cors_origin_rejects_userinfo_and_non_local_http(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        OidcSettings(**(_enabled_values() | {'oidc_cors_allowed_origins': 'https://user:pass@client.example'}))

    monkeypatch.setenv('APP_ENV', 'prod')
    with pytest.raises(ValidationError):
        OidcSettings(**(_enabled_values() | {'oidc_cors_allowed_origins': 'http://client.example'}))

    monkeypatch.setenv('APP_ENV', 'dev')
    with pytest.raises(ValidationError):
        OidcSettings(**(_enabled_values() | {'oidc_cors_allowed_origins': 'http://client.example'}))
    settings = OidcSettings(**(_enabled_values() | {'oidc_cors_allowed_origins': 'http://localhost:5173'}))
    assert settings.cors_origin_list == ('http://localhost:5173',)


def test_oidc_pepper_cannot_reuse_signing_key_encryption_key() -> None:
    values = _enabled_values()
    values['oidc_signing_key_encryption_key'] = values['oidc_token_hash_pepper']

    with pytest.raises(ValidationError):
        OidcSettings(**values)
