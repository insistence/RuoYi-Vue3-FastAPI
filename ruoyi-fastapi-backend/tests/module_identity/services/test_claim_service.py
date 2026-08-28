"""OIDC Claim 服务行为测试。"""

from datetime import datetime

import pytest

from exceptions.exception import OAuthProtocolException
from module_identity.service.identity_service import ClaimService


def test_claims_require_requested_client_and_resource_intersection() -> None:
    """只有三重交集中的 Claim 才能生成。"""
    allowed = ClaimService.effective_claims(
        'openid profile email phone',
        {'openid': True, 'profile': ['name'], 'email': ['email'], 'phone': ['phone_number']},
        ['sub', 'name', 'email'],
    )
    assert allowed == {'sub', 'name', 'email'}


def test_claim_builder_does_not_leak_local_identity_or_unapproved_contact() -> None:
    """本地 user_id、密码以及未获授权的手机号不得进入 Claims。"""
    user = {
        'user_id': 99,
        'password': 'plain-or-hash',
        'user_name': 'alice',
        'nick_name': 'Alice',
        'email': 'alice@example.com',
        'phonenumber': '13800000000',
        'subject_id': 'stable-sub',
        'roles': ['admin'],
    }
    claims = ClaimService.build_claims(
        user,
        {'openid', 'profile', 'email', 'phone', 'roles'},
        {'openid': True, 'profile': ['name'], 'email': ['email'], 'phone': ['phone_number'], 'roles': ['roles']},
        {'allowed_claims': ['sub', 'name', 'email', 'roles']},
    )
    assert claims == {'sub': 'stable-sub', 'name': 'Alice', 'email': 'alice@example.com', 'roles': ['admin']}
    assert 'user_id' not in claims
    assert 'password' not in claims
    assert 'phone_number' not in claims


@pytest.mark.parametrize(
    'user, policy, resource',
    [
        ({'subject_id': None}, {'openid': True}, ['name']),
        ({'subject_id': 'stable-sub'}, {'openid': ['name']}, ['name']),
    ],
)
def test_openid_fails_closed_when_subject_or_sub_policy_is_missing(
    user: dict[str, object], policy: dict[str, object], resource: list[str]
) -> None:
    """openid 请求缺少稳定 Subject 或 sub 策略时不得静默生成 Claims。"""
    with pytest.raises(OAuthProtocolException):
        ClaimService.build_claims(user, {'openid'}, policy, resource)


def test_updated_at_is_numeric_date_and_roles_are_role_keys() -> None:
    """本地更新时间输出 NumericDate，角色查询语句使用 role_key。"""
    user = {'subject_id': 'stable-sub', 'update_time': datetime(1970, 1, 1, 0, 0, 1)}
    claims = ClaimService.build_claims(
        user,
        {'openid', 'profile', 'roles'},
        {'openid': True, 'profile': ['updated_at'], 'roles': ['roles']},
        ['sub', 'updated_at', 'roles'],
        roles=['admin_key'],
    )
    assert claims['updated_at'] == int(datetime(1970, 1, 1, 0, 0, 1).timestamp())
    assert claims['roles'] == ['admin_key']
