"""标准协议 DTO 约束测试。"""

import pytest
from pydantic import ValidationError

from module_identity.entity.vo.oauth_session_vo import AuditPageQueryModel
from module_identity.entity.vo.protocol_vo import (
    AuthorizeRequest,
    ErrorResponse,
    OAuthServerMetadata,
    TokenRequest,
    UserInfoResponse,
)
from module_identity.security.pkce import generate_code_challenge, generate_code_verifier

_AUDIT_USER_ID = 1001


def test_protocol_models_emit_snake_case_and_require_oidc_nonce() -> None:
    challenge = generate_code_challenge(generate_code_verifier())
    with pytest.raises(ValidationError):
        AuthorizeRequest(
            response_type='code',
            client_id='external',
            redirect_uri='https://client.example/callback',
            scope='openid profile',
            code_challenge=challenge,
            code_challenge_method='S256',
        )
    model = AuthorizeRequest(
        response_type='code',
        client_id='external',
        redirect_uri='https://client.example/callback',
        scope='openid profile',
        nonce='nonce',
        code_challenge=challenge,
        code_challenge_method='S256',
    )
    assert 'client_id' in model.model_dump()
    assert 'clientId' not in model.model_dump()


def test_protocol_enum_values_are_preserved_for_business_error_mapping() -> None:
    """未知协议枚举保留给服务层生成 OAuth 标准错误，而非直接 422。"""
    challenge = generate_code_challenge(generate_code_verifier())
    authorize = AuthorizeRequest(
        response_type='unsupported',
        client_id='external',
        redirect_uri='https://client.example/callback',
        scope='openid',
        nonce='nonce',
        code_challenge=challenge,
        code_challenge_method='plain',
    )
    assert authorize.response_type == 'unsupported'
    assert authorize.code_challenge_method == 'plain'
    token = TokenRequest(grant_type='urn:example:unknown')
    assert token.grant_type == 'urn:example:unknown'


def test_token_request_code_requires_redirect_uri_and_userinfo_claims_are_allowed() -> None:
    with pytest.raises(ValidationError):
        TokenRequest(grant_type='authorization_code', code='ac1.code.secret', code_verifier='a' * 43)
    with pytest.raises(ValidationError):
        TokenRequest(
            grant_type='authorization_code',
            code='ac1.code.secret',
            code_verifier='a' * 43,
            redirect_uri='https://client.example/callback',
            scope='openid',
        )
    with pytest.raises(ValidationError):
        TokenRequest(grant_type='refresh_token', refresh_token='rt1.token.secret', redirect_uri='https://example/cb')
    with pytest.raises(ValidationError):
        TokenRequest(grant_type='client_credentials', redirect_uri='https://example/cb')
    info = UserInfoResponse(sub='subject', email='a@example.com', roles=['reader'])
    assert info.email == 'a@example.com'
    assert ErrorResponse(error='invalid_request').as_dict() == {'error': 'invalid_request'}
    metadata = OAuthServerMetadata(
        issuer='https://issuer.example',
        authorization_endpoint='https://issuer.example/oauth2/authorize',
        token_endpoint='https://issuer.example/oauth2/token',
        jwks_uri='https://issuer.example/oauth2/jwks',
    )
    assert 'userinfo_endpoint' not in metadata.model_dump()


def test_token_request_limits_untrusted_form_string_lengths() -> None:
    """Token 表单中的 opaque 字符串必须有明确长度上限。"""
    with pytest.raises(ValidationError):
        TokenRequest(
            grant_type='authorization_code',
            code='c',
            code_verifier='a' * 43,
            redirect_uri='https://client.example/callback',
            resource='r' * 1001,
        )
    with pytest.raises(ValidationError):
        TokenRequest(grant_type='refresh_token', refresh_token='r' * 4097)


def test_audit_query_supports_owner_and_time_filters() -> None:
    query = AuditPageQueryModel(
        clientId='external-client',
        userId=_AUDIT_USER_ID,
        startTime='2026-01-01T00:00:00Z',
        endTime='2026-01-02T00:00:00Z',
    )
    assert query.client_id == 'external-client'
    assert query.user_id == _AUDIT_USER_ID
    with pytest.raises(ValidationError):
        AuditPageQueryModel(startTime='2026-01-02T00:00:00Z', endTime='2026-01-01T00:00:00Z')
