"""OAuth Client Authentication 单元测试。"""

import base64

import pytest

from module_identity.entity.vo.oauth_client_vo import ClientCreateModel, ClientUriModel
from module_identity.security.client_auth import (
    ClientAuthenticationError,
    authenticate_client,
    generate_client_secret,
    hash_client_secret,
    parse_client_secret_basic,
)


@pytest.mark.parametrize('scheme', ['Basic', 'basic', 'BASIC', 'bAsIc'])
def test_basic_credentials_decode_both_form_sides_and_colon(scheme: str) -> None:
    raw = 'client+id:secret%2Bvalue%3A2'
    header = scheme + ' ' + base64.b64encode(raw.encode()).decode()

    assert parse_client_secret_basic(header) == ('client id', 'secret+value:2')


def test_basic_requires_strict_standard_base64() -> None:
    with pytest.raises(ClientAuthenticationError):
        parse_client_secret_basic('Basic !!!not-base64!!!')


@pytest.mark.parametrize('prefix', ['', 'Bearer ', 'BasicX ', ' Basic ', 'Basic\t'])
def test_basic_rejects_other_schemes_and_missing_space(prefix: str) -> None:
    header = prefix + base64.b64encode(b'client:SecretCase').decode()
    with pytest.raises(ClientAuthenticationError):
        parse_client_secret_basic(header)


def test_public_and_confidential_client_policy() -> None:
    public = {
        'client_id': 'public-app',
        'client_type': 'public',
        'token_endpoint_auth_method': 'none',
        'status': '0',
    }
    assert authenticate_client(public, client_id='public-app').auth_method == 'none'
    with pytest.raises(ClientAuthenticationError):
        authenticate_client(public, client_id='public-app', client_secret='unexpected')

    secret = generate_client_secret()
    confidential = {
        'client_id': 'server-app',
        'client_type': 'confidential',
        'token_endpoint_auth_method': 'client_secret_basic',
        'secret_hash': hash_client_secret(secret),
        'status': '0',
    }
    header = 'Basic ' + base64.b64encode(f'server-app:{secret}'.encode()).decode()
    assert authenticate_client(confidential, header).client_id == 'server-app'
    with pytest.raises(ClientAuthenticationError):
        authenticate_client(confidential, header, client_secret='body-secret')
    with pytest.raises(ClientAuthenticationError):
        authenticate_client(confidential, client_id='server-app', client_secret=secret)
    for status in (None, '1', 'disabled'):
        invalid = {**confidential, 'status': status}
        with pytest.raises(ClientAuthenticationError):
            authenticate_client(invalid, header)


def test_client_pkce_grant_and_uri_policy() -> None:
    with pytest.raises(ValueError):
        ClientCreateModel(
            client_name='public',
            client_type='public',
            token_endpoint_auth_method='none',
            grant_types=['authorization_code'],
            require_pkce=False,
        )
    with pytest.raises(ValueError):
        ClientUriModel(uri_type='redirect', uri='https://client.example/callback#fragment')
    with pytest.raises(ValueError):
        ClientUriModel(uri_type='cors_origin', uri='https://client.example/path')
    with pytest.raises(ValueError):
        ClientCreateModel(
            client_name='missing-callback',
            client_type='confidential',
            token_endpoint_auth_method='client_secret_basic',
        )
    with pytest.raises(ValueError):
        ClientCreateModel(
            client_name='refresh-only',
            client_type='confidential',
            token_endpoint_auth_method='client_secret_basic',
            grant_types=['refresh_token'],
            response_types=[],
        )

    credentials_only = ClientCreateModel(
        client_name='credentials-only',
        client_type='confidential',
        token_endpoint_auth_method='client_secret_basic',
        grant_types=['client_credentials'],
        redirect_uris=[],
    )
    assert credentials_only.grant_types == ['client_credentials']
    assert credentials_only.response_types == []
    with pytest.raises(ValueError):
        ClientCreateModel(
            client_name='public-credentials',
            client_type='public',
            token_endpoint_auth_method='none',
            grant_types=['client_credentials'],
            response_types=[],
        )
    with pytest.raises(ValueError):
        ClientCreateModel(
            client_name='wrong-code-response',
            client_type='confidential',
            token_endpoint_auth_method='client_secret_basic',
            grant_types=['authorization_code'],
            response_types=[],
            redirect_uris=['https://client.example/callback'],
        )

    valid = {
        'client_name': 'server',
        'client_type': 'confidential',
        'token_endpoint_auth_method': 'client_secret_basic',
        'redirect_uris': ['https://client.example/callback'],
        'post_logout_redirect_uris': ['https://client.example/logout'],
        'backchannel_logout_uris': ['https://client.example/backchannel'],
        'cors_origins': ['https://client.example:8443'],
    }
    assert ClientCreateModel(**valid).cors_origins == ['https://client.example:8443']
    for field in ('redirect_uris', 'post_logout_redirect_uris', 'backchannel_logout_uris', 'cors_origins'):
        with pytest.raises(ValueError):
            ClientCreateModel(**{**valid, field: ['https://user:password@client.example/callback']})
