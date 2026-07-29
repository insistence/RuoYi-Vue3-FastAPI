from unittest.mock import patch

import pytest

from config.env import JwtSettings


def test_empty_jwt_secret_key_is_generated(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验空Jwt密钥会自动生成32字节随机值。"""
    monkeypatch.setenv('JWT_SECRET_KEY', '')

    with patch('config.env.secrets.token_hex', return_value='a' * 64) as token_hex:
        settings = JwtSettings()

    token_hex.assert_called_once_with(32)
    assert settings.jwt_secret_key == 'a' * 64


def test_missing_jwt_secret_key_is_generated(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验未配置Jwt密钥时也会使用安全随机默认值。"""
    monkeypatch.delenv('JWT_SECRET_KEY', raising=False)

    with patch('config.env.secrets.token_hex', return_value='b' * 64) as token_hex:
        settings = JwtSettings()

    token_hex.assert_called_once_with(32)
    assert settings.jwt_secret_key == 'b' * 64


def test_configured_jwt_secret_key_is_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验显式配置的Jwt密钥不会被随机值覆盖。"""
    configured_secret = 'configured-jwt-secret'
    monkeypatch.setenv('JWT_SECRET_KEY', configured_secret)

    with patch('config.env.secrets.token_hex') as token_hex:
        settings = JwtSettings()

    token_hex.assert_not_called()
    assert settings.jwt_secret_key == configured_secret
