"""三类 JWT Profile 的类型、算法、Issuer 与 Audience 隔离测试。"""

import math
from datetime import datetime, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from module_identity.security.jwt_profile import (
    BACKCHANNEL_LOGOUT_EVENT,
    JwtProfileError,
    decode_access_token,
    decode_id_token,
    decode_logout_token,
    encode_access_token,
    encode_id_token,
    encode_logout_token,
)


@pytest.fixture()
def key_pair() -> tuple[object, object]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def test_access_profile_requires_at_jwt_and_checks_audience(key_pair: tuple[object, object]) -> None:
    private, public = key_pair
    now = _now()
    claims = {
        'iss': 'https://issuer.example',
        'sub': 'subject',
        'aud': ['resource-a'],
        'exp': now + 60,
        'iat': now,
        'nbf': now,
        'jti': 'token-id',
        'client_id': 'client',
        'scope': 'openid',
        'gty': 'authorization_code',
        'sid': 'session-id',
        'ver': 1,
        'auth_time': now,
        'acr': 'pwd',
        'amr': ['pwd'],
    }
    token = encode_access_token(claims, signing_key=private, kid='key-1')
    assert (
        decode_access_token(token, verification_key=public, issuer=claims['iss'], audience='resource-a')['sub']
        == 'subject'
    )
    with pytest.raises(JwtProfileError):
        decode_access_token(token, verification_key=public, issuer=claims['iss'], audience='resource-b')
    with pytest.raises(JwtProfileError):
        decode_access_token(token, verification_key=public, issuer='https://other.example', audience='resource-a')


def test_id_token_cannot_be_used_as_access_token_and_leeway_is_forwarded(key_pair: tuple[object, object]) -> None:
    private, public = key_pair
    now = _now()
    claims = {
        'iss': 'https://issuer.example',
        'sub': 'subject',
        'aud': 'client',
        'exp': now - 61,
        'iat': now - 60,
        'auth_time': now - 60,
        'nonce': 'opaque-nonce',
        'sid': 'sid',
        'acr': 'pwd',
        'amr': ['pwd'],
    }
    id_token = encode_id_token(claims, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        decode_access_token(id_token, verification_key=public, issuer=claims['iss'], audience='client')
    assert (
        decode_id_token(id_token, verification_key=public, issuer=claims['iss'], audience='client', clock_skew=120)[
            'sub'
        ]
        == 'subject'
    )
    with pytest.raises(JwtProfileError):
        encode_id_token({key: value for key, value in claims.items() if key != 'nonce'}, private, 'key-1')


def test_wrong_algorithm_kid_and_numeric_types_are_rejected(key_pair: tuple[object, object]) -> None:
    private, public = key_pair
    now = _now()
    claims = {
        'iss': 'https://issuer.example',
        'sub': 's',
        'aud': 'r',
        'exp': now + 60,
        'iat': now,
        'nbf': now,
        'jti': 'j',
        'client_id': 'c',
        'scope': 'openid',
        'gty': 'authorization_code',
        'sid': 'session-id',
        'ver': 1,
        'auth_time': now,
        'acr': 'pwd',
        'amr': ['pwd'],
    }
    with pytest.raises(JwtProfileError):
        encode_access_token({**claims, 'exp': True}, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        encode_access_token({**claims, 'exp': math.nan}, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        encode_access_token({**claims, 'aud': []}, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        encode_access_token({**claims, 'aud': ['r', 'r']}, signing_key=private, kid='key-1')
    token = encode_access_token(claims, signing_key=private, kid='key-1')
    header = jwt.get_unverified_header(token)
    assert header['typ'] == 'at+jwt' and header['alg'] == 'RS256'
    with pytest.raises(JwtProfileError):
        decode_access_token(token, issuer=claims['iss'], audience='r', verification_keys={'other': public})
    unsafe_header = jwt.encode(
        claims,
        private,
        algorithm='RS256',
        headers={'kid': 'key-1', 'typ': 'at+jwt', 'jku': 'https://attacker.example/jwks'},
    )
    with pytest.raises(JwtProfileError):
        decode_access_token(unsafe_header, verification_key=public, issuer=claims['iss'], audience='r')


def test_signed_non_finite_numeric_date_is_rejected(key_pair: tuple[object, object]) -> None:
    private, public = key_pair
    now = _now()
    claims = {
        'iss': 'https://issuer.example',
        'sub': 's',
        'aud': 'r',
        'exp': math.nan,
        'iat': now,
        'jti': 'j',
        'client_id': 'c',
        'scope': 'openid',
    }
    token = jwt.encode(claims, private, algorithm='RS256', headers={'kid': 'key-1', 'typ': 'at+jwt'})
    with pytest.raises(JwtProfileError):
        decode_access_token(token, verification_key=public, issuer=claims['iss'], audience='r')


def test_access_profile_requires_gty_and_rejects_machine_user_field_confusion(
    key_pair: tuple[object, object],
) -> None:
    """Access Profile 强制 gty，并隔离机器与用户绑定字段。"""
    private, public = key_pair
    now = _now()
    base = {
        'iss': 'https://issuer.example',
        'aud': 'r',
        'exp': now + 60,
        'iat': now,
        'nbf': now,
        'jti': 'j',
        'client_id': 'c',
        'scope': 'scope',
    }
    with pytest.raises(JwtProfileError):
        encode_access_token({**base, 'sub': 'client:c', 'gty': 'client_credentials', 'sid': 'sid'}, private, 'key-1')
    machine = encode_access_token({**base, 'sub': 'client:c', 'gty': 'client_credentials'}, private, 'key-1')
    assert decode_access_token(machine, verification_key=public, issuer=base['iss'], audience='r')['gty'] == (
        'client_credentials'
    )
    user = encode_access_token(
        {
            **base,
            'sub': 'subject',
            'gty': 'authorization_code',
            'sid': 'sid',
            'ver': 1,
            'auth_time': now,
            'acr': 'pwd',
            'amr': ['pwd'],
        },
        private,
        'key-1',
    )
    assert decode_access_token(user, verification_key=public, issuer=base['iss'], audience='r')['gty'] == (
        'authorization_code'
    )


def test_logout_profile_requires_event_and_non_empty_sid_or_sub(key_pair: tuple[object, object]) -> None:
    private, public = key_pair
    now = _now()
    claims = {
        'iss': 'https://issuer.example',
        'aud': 'client',
        'iat': now,
        'jti': 'logout-id',
        'sid': 'sid',
        'events': {BACKCHANNEL_LOGOUT_EVENT: {}},
    }
    token = encode_logout_token(claims, signing_key=private, kid='key-1')
    assert decode_logout_token(token, verification_key=public, issuer=claims['iss'], audience='client')['sid'] == 'sid'
    with pytest.raises(JwtProfileError):
        encode_logout_token({**claims, 'sid': ''}, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        encode_logout_token({**claims, 'nonce': 'must-not-exist'}, signing_key=private, kid='key-1')
    with pytest.raises(JwtProfileError):
        encode_logout_token(
            {key: value for key, value in claims.items() if key != 'iat'}, signing_key=private, kid='key-1'
        )
    with pytest.raises(JwtProfileError):
        encode_logout_token({**claims, 'aud': []}, signing_key=private, kid='key-1')
