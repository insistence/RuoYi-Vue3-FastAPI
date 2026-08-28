"""OIDC 公钥 DTO 防私钥泄漏测试。"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from module_identity.entity.vo.oidc_key_vo import OidcKeyRotateModel, OidcKeyViewModel


def test_public_jwk_rejects_private_rsa_parameters() -> None:
    with pytest.raises(ValidationError):
        OidcKeyViewModel(
            kid='key-1',
            status='active',
            publishAt='2026-01-01T00:00:00Z',
            publicJwk={
                'kty': 'RSA',
                'use': 'sig',
                'kid': 'key-1',
                'alg': 'RS256',
                'n': 'n',
                'e': 'AQAB',
                'd': 'private',
            },
        )


def test_rotation_request_rejects_timezone_offset() -> None:
    """管理端轮换时间必须遵循项目的本地无时区契约。"""
    with pytest.raises(ValidationError, match='must not include a timezone offset'):
        OidcKeyRotateModel(
            kid='key-1',
            publishAt=datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc),
        )
