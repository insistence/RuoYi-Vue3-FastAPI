import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import rsa

from utils.oidc_util import OidcUtil

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_V1_CIPHERTEXT = 'v1.AAECAwQFBgcICQoLh36B9Tc6XrrXlTTTKJydxYN2UsldJqzgWxIn_pyIfSbMrPlmPXHJz6_NAJpbzQ=='
_V2_CIPHERTEXT = (
    'v2.c2FsdAABAgMEBQYHCAkKCwwNDg8AAQIDBAUGBwgJCgvFPMVj6MHgGRqLTZd7zlLGG0F_YMv1J22s0Nx84W-t468Xts0APDbdZpj8hlwN'
)


def test_query_replacement_preserves_unrelated_duplicates_blank_values_and_fragment() -> None:
    location = OidcUtil.replace_query_parameters(
        'https://rp.example/cb?keep=one&keep=two&empty=&state=old&error=old#part',
        [('code', 'a+/='), ('state', '中文 +&')],
        {'code', 'state', 'error'},
    )
    assert location == (
        'https://rp.example/cb?keep=one&keep=two&empty=&code=a%2B%2F%3D&state=%E4%B8%AD%E6%96%87+%2B%26#part'
    )


def test_logout_state_distinguishes_missing_and_empty_state() -> None:
    uri = 'https://rp.example/cb?state=old&keep=1&state=older'
    assert OidcUtil.append_state(uri, None) == uri
    assert OidcUtil.append_state(uri, '') == 'https://rp.example/cb?keep=1&state='


def test_interaction_csrf_is_only_in_fragment() -> None:
    assert OidcUtil.interaction_url('https://id.example/login?lang=zh#old', 'i-1', 's+/=') == (
        'https://id.example/login?lang=zh&interaction=i-1#csrf=s+/='
    )


@pytest.mark.parametrize(('validate_all_first', 'message'), [(False, '参数重复'), (True, '参数无效')])
def test_batch_validation_preserves_each_callers_error_precedence(validate_all_first: bool, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OidcUtil.split_batch('one,one,bad/path', 'ids', max_size=100, validate_all_first=validate_all_first)


@pytest.mark.parametrize('value', ['one,,two', 'one,%2Ftwo', 'one,t wo', 'one,t\\wo'])
def test_batch_rejects_ambiguous_path_identifiers(value: str) -> None:
    with pytest.raises(ValueError, match='参数无效'):
        OidcUtil.split_batch(value, 'ids', max_size=100)


def test_json_keeps_unicode_and_key_order_without_accepting_duplicate_input_keys() -> None:
    assert OidcUtil.serialize_json({'z': [1], 'a': '中文'}, error_message='载荷无效') == '{"a":"中文","z":[1]}'
    with pytest.raises(ValueError, match='重复字段'):
        json.loads('{"nested":{"scope":"openid","scope":"admin"}}', object_pairs_hook=OidcUtil.json_object_pairs)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), object()])
def test_cache_json_rejects_nonfinite_numbers_and_nonserializable_objects(value: object) -> None:
    with pytest.raises(ValueError, match='载荷无效'):
        OidcUtil.serialize_json({'value': value}, error_message='载荷无效')


def test_digest_vectors_preserve_existing_wire_and_browser_binding_formats() -> None:
    assert OidcUtil.sha256_digest('abc') == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    assert OidcUtil.hmac_sha256('Hi There', b'\x0b' * 20) == (
        'b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7'
    )
    assert OidcUtil.access_token_hash('SlAV32hkKG') == 'rXH7QWVTZnXYCou_6Vdpfg'
    # 现有退出凭据使用字面量反斜杠加零，不能在重构中替换为 NUL。
    assert OidcUtil.logout_confirmation_digest('ss1.cookie', 'browser-nonce', b'p' * 32) == (
        '55d146629427f15316caa1355ccfbe3d6446b2b6b4e26787750270f890e21d2d'
    )


@pytest.mark.parametrize('ciphertext', [_V1_CIPHERTEXT, _V2_CIPHERTEXT], ids=['legacy-v1', 'salted-v2'])
def test_decrypt_accepts_persisted_private_key_formats(ciphertext: str) -> None:
    assert OidcUtil.decrypt_signing_private_key(ciphertext, b'm' * 32) == b'private-key-regression-fixture'


def test_encrypt_preserves_v2_envelope_and_rejects_wrong_decryption_key() -> None:
    ciphertext = OidcUtil.encrypt_signing_private_key(
        b'private-key-regression-fixture', b'm' * 32, salt=bytes(range(16)), nonce=bytes(range(12))
    )
    assert ciphertext == _V2_CIPHERTEXT
    with pytest.raises(InvalidTag):
        OidcUtil.decrypt_signing_private_key(ciphertext, b'x' * 32)


@pytest.fixture(scope='module')
def public_jwk() -> dict[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return OidcUtil.rsa_public_jwk(key.public_key(), 'k1')


def test_public_jwk_strips_private_fields_without_mutating_input(public_jwk: dict[str, str]) -> None:
    record = SimpleNamespace(kid='k1', public_jwk={**public_jwk, 'd': 'private-material'})
    actual = OidcUtil.normalize_public_jwk(record, min_rsa_bits=2048, min_exponent=3, max_exponent=2**32)
    assert actual == public_jwk
    assert record.public_jwk['d'] == 'private-material'
    record.kid = 'another-key'
    with pytest.raises(ValueError, match='不匹配'):
        OidcUtil.normalize_public_jwk(record, min_rsa_bits=2048, min_exponent=3, max_exponent=2**32)


@pytest.mark.parametrize(('field', 'value'), [('n', 'AQ'), ('e', 'Ag'), ('e', 'AQAB=')])
def test_public_jwk_rejects_weak_or_noncanonical_parameters(public_jwk: dict[str, str], field: str, value: str) -> None:
    with pytest.raises(ValueError):
        OidcUtil.normalize_public_jwk(
            {**public_jwk, field: value}, min_rsa_bits=2048, min_exponent=3, max_exponent=2**32
        )


@pytest.mark.parametrize(
    'uri',
    [
        'http://rp.example/logout',
        'https://user:pass@rp.example/logout',
        'https://rp.example/logout?q=x',
        'https://rp.example/logout#part',
        'https://127.0.0.1/logout',
        'https://[::1]/logout',
        'https://rp.example:bad/logout',
    ],
)
def test_backchannel_parser_rejects_unsafe_structures_and_literal_private_ips(uri: str) -> None:
    assert OidcUtil.parse_backchannel_uri(uri) is None


def test_uri_helpers_preserve_different_registration_policies() -> None:
    localhost = 'http://localhost:5173/callback'
    assert OidcUtil.validate_registered_uri('redirect', localhost) == localhost
    assert OidcUtil.is_safe_post_logout_uri(localhost)
    with pytest.raises(ValueError, match='HTTPS'):
        OidcUtil.validate_resource_audience(localhost, max_length=500)
    assert OidcUtil.parse_backchannel_uri('https://rp.example:8443/logout') == ('rp.example', 8443)


@pytest.mark.parametrize(
    'modules',
    [
        ['utils.oidc_util', 'exceptions.exception', 'utils.time_util'],
        ['exceptions.exception', 'utils.time_util', 'utils.oidc_util'],
        ['utils.time_util', 'utils.oidc_util', 'exceptions.exception'],
    ],
)
def test_utilities_and_exceptions_import_without_cycles_or_loading_application_state(modules: list[str]) -> None:
    script = (
        'import importlib, sys\n'
        f'for name in {modules!r}: importlib.import_module(name)\n'
        'assert not {"config.env", "config.database", "redis", "sqlalchemy", "fastapi"}.intersection(sys.modules)\n'
    )
    result = subprocess.run(
        [sys.executable, '-X', 'utf8', '-c', script],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
