import copy
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.identity_demo_backchannel import apply_logout, verify_logout_token


@pytest.fixture()
def signed_event() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """构造使用真实 RSA 签名的短时退出事件。"""

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public.update(kid='key-1', alg='RS256', use='sig')
    now = int(time.time())
    claims = {
        'iss': 'https://issuer.example',
        'aud': 'client',
        'iat': now,
        'exp': now + 120,
        'jti': 'event-1',
        'sid': 'sid-1',
        'events': {'http://schemas.openid.net/event/backchannel-logout': {}},
    }
    return private, {'keys': [public]}, claims


@pytest.mark.parametrize(
    'changes',
    [
        {'iss': 'https://other.example'},
        {'aud': 'other'},
        {'exp': 0},
        {'exp': True},
        {'nonce': 'not-allowed'},
        {'events': {}},
        {'events': {'http://schemas.openid.net/event/backchannel-logout': []}},
        {'sid': ''},
        {'jti': ''},
        {'iat': int(time.time()) + 3600},
    ],
)
def test_receiver_rejects_invalid_signed_claims(signed_event: tuple[Any, ...], changes: dict[str, Any]) -> None:
    """即使签名有效也必须拒绝错误的令牌用途、主体与时效。"""

    private, jwks, claims = signed_event
    token = jwt.encode({**claims, **changes}, private, algorithm='RS256', headers={'kid': 'key-1', 'typ': 'logout+jwt'})
    with pytest.raises(ValueError, match='退出通知校验失败'):
        verify_logout_token(token, 'client', 'https://issuer.example', jwks)


def test_receiver_verifies_signature_and_isolates_sid_client_and_issuer(signed_event: tuple[Any, ...]) -> None:
    """真实验签后只清理目标会话，同一事件不会再次清理重新建立的状态。"""

    private, jwks, claims = signed_event
    token = jwt.encode(claims, private, algorithm='RS256', headers={'kid': 'key-1', 'typ': 'logout+jwt'})
    verified = verify_logout_token(token, 'client', claims['iss'], jwks)
    identity = {'iss': claims['iss'], 'sid': 'sid-1', 'sub': 'user-1'}
    value = {'identity': identity}
    sessions = {
        'target': {'apps': {'client': copy.deepcopy(value), 'other': copy.deepcopy(value)}},
        'device': {'apps': {'client': {'identity': {**identity, 'sid': 'sid-2'}}}},
        'issuer': {'apps': {'client': {'identity': {**identity, 'iss': 'https://other.example'}}}},
    }
    seen = {}
    assert apply_logout(verified, 'client', sessions, seen) == {'cleared_sessions': 1, 'duplicate': False}
    assert 'client' not in sessions['target']['apps']
    assert 'other' in sessions['target']['apps']
    assert 'client' in sessions['device']['apps'] and 'client' in sessions['issuer']['apps']
    sessions['target']['apps']['client'] = copy.deepcopy(value)
    assert apply_logout(verified, 'client', sessions, seen) == {'cleared_sessions': 0, 'duplicate': True}
    assert 'client' in sessions['target']['apps']
    forged_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(claims, forged_key, algorithm='RS256', headers={'kid': 'key-1', 'typ': 'logout+jwt'})
    with pytest.raises(ValueError):
        verify_logout_token(forged, 'client', claims['iss'], jwks)
