import pytest

from config.env import AppConfig, TransportCryptoConfig
from middlewares.transport_crypto_middleware import TransportCryptoMiddleware


def test_standard_oidc_paths_are_always_excluded_from_transport_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_exclude_paths', '')

    assert all(
        TransportCryptoMiddleware._is_excluded_path(path) for path in TransportCryptoMiddleware._STANDARD_OIDC_PATHS
    )


def test_interaction_api_is_not_implicitly_excluded() -> None:
    assert not TransportCryptoMiddleware._is_excluded_path('/auth/interaction/interaction-id/login')


def test_app_root_path_is_removed_before_oidc_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AppConfig, 'app_root_path', '/dev-api')

    normalized_path = TransportCryptoMiddleware._normalize_path('/dev-api/oauth2/token')

    assert normalized_path == '/oauth2/token'
    assert TransportCryptoMiddleware._is_excluded_path(normalized_path)
