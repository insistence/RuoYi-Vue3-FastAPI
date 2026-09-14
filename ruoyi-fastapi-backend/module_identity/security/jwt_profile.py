import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from jwt.exceptions import PyJWTError

ACCESS_TOKEN_ALGORITHM = 'RS256'
ACCESS_TOKEN_TYPE = 'at+jwt'
ID_TOKEN_TYPE = 'JWT'
LOGOUT_TOKEN_TYPE = 'logout+jwt'
BACKCHANNEL_LOGOUT_EVENT = 'http://schemas.openid.net/event/backchannel-logout'
ALLOWED_SIGNING_ALGORITHMS = frozenset({ACCESS_TOKEN_ALGORITHM})


class JwtProfileError(ValueError):
    """
    JWT Profile 校验失败
    """


def _key_for_kid(verification_keys: object, kid: str) -> object:
    """
    按 Key ID 选择本地验签密钥

    :param verification_keys: 验签密钥、按 Key ID 索引的映射或查找回调
    :param kid: JWT Header 中的 Key ID
    :return: 匹配的验签密钥
    :raises JwtProfileError: 验签密钥缺失或 Key ID 未知
    """

    if verification_keys is None:
        raise JwtProfileError('signing key is required')
    if isinstance(verification_keys, Mapping):
        try:
            return verification_keys[kid]
        except KeyError:
            raise JwtProfileError('unknown signing key') from None
    if callable(verification_keys):
        value = verification_keys(kid)
        if value is None:
            raise JwtProfileError('unknown signing key')
        return value
    return verification_keys


def _header(token: str) -> dict[str, Any]:
    """
    读取并校验 JWT Header 安全字段

    :param token: 待读取的 JWT
    :return: 通过固定算法与 Header 白名单校验的字段映射
    :raises JwtProfileError: JWT 编码、算法或 Header 字段不合法
    """

    try:
        value = jwt.get_unverified_header(token)
    except (PyJWTError, TypeError, ValueError) as exc:
        raise JwtProfileError('invalid JWT encoding') from exc
    if value.get('alg') not in ALLOWED_SIGNING_ALGORITHMS:
        raise JwtProfileError('unsupported JWT algorithm')
    if any(name in value for name in ('crit', 'jku', 'jwk', 'x5u', 'x5c')):
        raise JwtProfileError('unsupported JWT header parameter')
    if not isinstance(value.get('kid'), str) or not value['kid'].strip():
        raise JwtProfileError('JWT kid is required')
    return value


def _numeric_claims(payload: Mapping[str, Any], *, now: float, skew: float, verify_exp: bool = True) -> None:
    """
    校验 JWT NumericDate 类型和时效

    :param payload: 已验签的 JWT Claims
    :param now: 当前 UTC 时间戳
    :param skew: 允许的时钟偏差秒数
    :param verify_exp: 是否校验过期时间，仅退出提示流程可关闭
    :return: None
    :raises JwtProfileError: NumericDate 类型或时效不合法
    """

    for name in ('iat', 'exp', 'nbf', 'auth_time'):
        if name not in payload:
            if name == 'iat':
                raise JwtProfileError('JWT iat claim is required')
            continue
        value = payload[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise JwtProfileError(f'JWT {name} claim is invalid')
        if name == 'iat' and value > now + skew:
            raise JwtProfileError('JWT issued-at is in the future')
        if name == 'auth_time' and value > now + skew:
            raise JwtProfileError('JWT auth_time is in the future')
        if name == 'exp' and verify_exp and now - skew >= value:
            raise JwtProfileError('JWT is expired')
        if name == 'nbf' and now + skew < value:
            raise JwtProfileError('JWT is not active yet')


def _validate_numeric_types(payload: Mapping[str, Any]) -> None:
    """
    仅校验 NumericDate 类型，不在签发时用当前时间判断有效期

    :param payload: 待签发的 JWT Claims
    :return: None
    :raises JwtProfileError: NumericDate 类型不合法
    """

    for name in ('iat', 'exp', 'nbf', 'auth_time'):
        if name in payload and (
            isinstance(payload[name], bool)
            or not isinstance(payload[name], (int, float))
            or not math.isfinite(payload[name])
        ):
            raise JwtProfileError(f'JWT {name} claim is invalid')


def _audience_matches(actual: object, expected: str | Sequence[str] | None) -> bool:
    """
    判断实际 Audience 是否匹配允许值

    :param actual: JWT 中的 Audience
    :param expected: 允许的单个或多个 Audience
    :return: Audience 是否匹配
    """

    if expected is None:
        return True
    values = [actual] if isinstance(actual, str) else actual
    if not isinstance(values, (list, tuple, set)) or any(not isinstance(item, str) for item in values):
        return False
    wanted = [expected] if isinstance(expected, str) else list(expected)

    return any(item in wanted for item in values)


def _validate_string_claim(payload: Mapping[str, Any], name: str, required: bool = True) -> None:
    """
    校验 JWT 字符串 Claim

    :param payload: JWT Claims
    :param name: Claim 名称
    :param required: 是否要求 Claim 必须存在
    :return: None
    :raises JwtProfileError: Claim 缺失或不是非空字符串
    """

    value = payload.get(name)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise JwtProfileError(f'JWT {name} claim is invalid')


def _validate_string_list(payload: Mapping[str, Any], name: str, required: bool = True) -> None:
    """
    校验 JWT 字符串列表 Claim

    :param payload: JWT Claims
    :param name: Claim 名称
    :param required: 是否要求 Claim 必须存在
    :return: None
    :raises JwtProfileError: Claim 缺失或不是非空字符串列表
    """

    value = payload.get(name)
    if value is None and not required:
        return
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise JwtProfileError(f'JWT {name} claim is invalid')


def _validate_audience_claim(payload: Mapping[str, Any]) -> None:
    """
    校验 JWT Audience Claim

    :param payload: JWT Claims
    :return: None
    :raises JwtProfileError: Audience 结构、内容或唯一性不合法
    """

    aud = payload.get('aud')
    if not isinstance(aud, (str, list)):
        raise JwtProfileError('JWT aud claim is invalid')
    if isinstance(aud, list) and (not aud or any(not isinstance(item, str) or not item for item in aud)):
        raise JwtProfileError('JWT aud claim is invalid')
    if isinstance(aud, list) and len(set(aud)) != len(aud):
        raise JwtProfileError('JWT aud claim is invalid')
    if isinstance(aud, str) and not aud:
        raise JwtProfileError('JWT aud claim is invalid')


def _validate_access_claims(payload: Mapping[str, Any]) -> None:
    """
    校验 Access Token Profile Claims

    :param payload: Access Token Claims
    :return: None
    :raises JwtProfileError: 必需 Claim 或身份绑定不合法
    """

    for name in ('iss', 'sub', 'client_id', 'scope'):
        _validate_string_claim(payload, name)
    _validate_audience_claim(payload)
    _validate_string_claim(payload, 'gty')
    if payload.get('gty') not in {'authorization_code', 'refresh_token', 'client_credentials'}:
        raise JwtProfileError('access token grant type is invalid')
    for name in ('exp', 'iat', 'nbf', 'jti'):
        if name not in payload:
            raise JwtProfileError(f'access token required claim is missing: {name}')
    _validate_string_claim(payload, 'jti')
    if payload['gty'] == 'client_credentials':
        if payload.get('sub') != f'client:{payload["client_id"]}' or any(
            name in payload for name in ('sid', 'ver', 'auth_time', 'acr', 'amr')
        ):
            raise JwtProfileError('machine access token identity binding is invalid')
        return
    for name in ('sid', 'acr'):
        _validate_string_claim(payload, name)
    _validate_string_list(payload, 'amr')
    if (
        'ver' not in payload
        or isinstance(payload['ver'], bool)
        or not isinstance(payload['ver'], int)
        or payload['ver'] < 1
    ):
        raise JwtProfileError('access token version is invalid')
    if 'auth_time' not in payload:
        raise JwtProfileError('access token auth_time is required')


def _validate_id_claims(payload: Mapping[str, Any]) -> None:
    """
    校验 ID Token Profile Claims

    :param payload: ID Token Claims
    :return: None
    :raises JwtProfileError: 必需 Claim 不合法
    """

    for name in ('iss', 'sub', 'sid', 'acr', 'nonce'):
        _validate_string_claim(payload, name)
    _validate_audience_claim(payload)
    _validate_string_list(payload, 'amr')
    for name in ('exp', 'iat', 'auth_time'):
        if name not in payload:
            raise JwtProfileError(f'ID token required claim is missing: {name}')


def _validate_logout_claims(payload: Mapping[str, Any]) -> None:
    """
    校验 Logout Token Profile Claims

    :param payload: Logout Token Claims
    :return: None
    :raises JwtProfileError: 必需 Claim、事件或主体绑定不合法
    """

    for name in ('iss', 'jti'):
        _validate_string_claim(payload, name)
    _validate_audience_claim(payload)
    for name in ('sid', 'sub'):
        _validate_string_claim(payload, name, required=False)
    if 'iat' not in payload:
        raise JwtProfileError('logout token required claim is missing: iat')
    if not payload.get('sid') and not payload.get('sub'):
        raise JwtProfileError('logout token requires sid or sub')
    events = payload.get('events')
    if not isinstance(events, dict) or BACKCHANNEL_LOGOUT_EVENT not in events or events[BACKCHANNEL_LOGOUT_EVENT] != {}:
        raise JwtProfileError('logout token events claim is invalid')
    if 'nonce' in payload:
        raise JwtProfileError('Logout Token must not contain nonce')


def _validate_profile_claims(profile: str, payload: Mapping[str, Any]) -> None:
    """
    按 JWT Profile 分派 Claims 校验

    :param profile: access、id 或 logout Profile
    :param payload: JWT Claims
    :return: None
    :raises JwtProfileError: Profile Claims 不合法
    """

    if profile == 'access':
        _validate_access_claims(payload)
    elif profile == 'id':
        _validate_id_claims(payload)
    else:
        _validate_logout_claims(payload)


def _decode(
    token: str,
    verification_keys: object,
    issuer: str,
    audience: str | Sequence[str] | None,
    *,
    profile: str,
    expected_type: str,
    required_claims: set[str],
    clock_skew: float = 60,
    verification_key: object | None = None,
    allow_expired_hint: bool = False,
) -> dict[str, Any]:
    """
    按固定 Profile 验签并校验 JWT

    :param token: 待验证的 JWT
    :param verification_keys: 验签密钥、映射或查找回调
    :param issuer: 必须精确匹配的 Issuer
    :param audience: 允许的 Audience
    :param profile: access、id 或 logout Profile
    :param expected_type: 预期的 JWT typ
    :param required_claims: PyJWT 必须检查的 Claim 集合
    :param clock_skew: 允许的时钟偏差秒数
    :param verification_key: 可选的单一验签密钥
    :param allow_expired_hint: 是否允许退出提示使用过期ID Token
    :return: 已验签并通过 Profile 校验的 Claims
    :raises JwtProfileError: Header、签名、Issuer、Audience 或 Claims 不合法
    """

    if clock_skew < 0:
        raise JwtProfileError('clock_skew must not be negative')
    headers = _header(token)
    if headers.get('typ') != expected_type:
        raise JwtProfileError('unexpected JWT type')
    key_source = verification_key if verification_key is not None else verification_keys
    key = _key_for_kid(key_source, str(headers['kid']))
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[ACCESS_TOKEN_ALGORITHM],
            leeway=clock_skew,
            options={
                'require': sorted(required_claims),
                'verify_aud': False,
                'verify_iss': False,
                'verify_exp': not allow_expired_hint,
            },
        )
    except PyJWTError as exc:
        raise JwtProfileError('JWT signature or registered claim validation failed') from exc
    if payload.get('iss') != issuer or not _audience_matches(payload.get('aud'), audience):
        raise JwtProfileError('JWT issuer or audience mismatch')
    _validate_profile_claims(profile, payload)
    now = datetime.now(timezone.utc).timestamp()
    _numeric_claims(payload, now=now, skew=clock_skew, verify_exp=not allow_expired_hint)

    return dict(payload)


def _encode(claims: Mapping[str, Any], signing_key: RSAPrivateKey, kid: str, expected_type: str, profile: str) -> str:
    """
    按固定 Profile Header 签发 JWT

    :param claims: 待签发且已包含协议必需字段的 Claims
    :param signing_key: RSA 私钥
    :param kid: 签名密钥标识
    :param expected_type: 固定 JWT typ
    :param profile: access、id 或 logout
    :return: 签名后的 JWT 字符串
    :raises JwtProfileError: Key ID、Claims 或编码过程不合法
    """

    payload = dict(claims)
    if not isinstance(kid, str) or not kid.strip():
        raise JwtProfileError('JWT kid is required')
    _validate_profile_claims(profile, payload)
    _validate_numeric_types(payload)
    headers = {'alg': ACCESS_TOKEN_ALGORITHM, 'kid': kid, 'typ': expected_type}
    try:
        return jwt.encode(payload, signing_key, algorithm=ACCESS_TOKEN_ALGORITHM, headers=headers)
    except PyJWTError as exc:
        raise JwtProfileError('JWT encoding failed') from exc


def encode_access_token(claims: Mapping[str, Any], signing_key: RSAPrivateKey, kid: str) -> str:
    """
    签发 JWT Access Token

    :param claims: Access Token Claims
    :param signing_key: RSA 私钥
    :param kid: 签名密钥标识
    :return: typ 为 at+jwt 的 JWT
    :raises JwtProfileError: Claims 或签名参数不合法
    """

    return _encode(claims, signing_key, kid, ACCESS_TOKEN_TYPE, 'access')


def decode_access_token(
    token: str,
    verification_keys: object | None = None,
    issuer: str | None = None,
    audience: str | Sequence[str] | None = None,
    *,
    clock_skew: float = 60,
    verification_key: RSAPublicKey | None = None,
) -> dict[str, Any]:
    """
    验证 JWT Access Token Profile

    :param token: 待验证 JWT
    :param verification_keys: 按 kid 索引的公钥、单一公钥或查找回调
    :param issuer: 必须精确匹配的 issuer
    :param audience: 允许的 audience
    :param clock_skew: 允许的时钟偏差秒数
    :param verification_key: 可选的单一 RSA 公钥
    :return: 已验签的 Access Token Claims
    :raises JwtProfileError: Access Token 不符合固定 Profile
    """

    if issuer is None:
        raise JwtProfileError('issuer is required')
    return _decode(
        token,
        verification_keys,
        issuer,
        audience,
        profile='access',
        expected_type=ACCESS_TOKEN_TYPE,
        required_claims={'iss', 'sub', 'aud', 'exp', 'iat', 'nbf', 'jti', 'client_id', 'scope', 'gty'},
        clock_skew=clock_skew,
        verification_key=verification_key,
    )


def encode_id_token(claims: Mapping[str, Any], signing_key: RSAPrivateKey, kid: str) -> str:
    """
    签发 OIDC ID Token

    :param claims: ID Token Claims
    :param signing_key: RSA 私钥
    :param kid: 签名密钥标识
    :return: typ 为 JWT 的 ID Token
    :raises JwtProfileError: Claims 或签名参数不合法
    """

    return _encode(claims, signing_key, kid, ID_TOKEN_TYPE, 'id')


def decode_id_token(
    token: str,
    verification_keys: object | None = None,
    issuer: str | None = None,
    audience: str | Sequence[str] | None = None,
    *,
    nonce: str | None = None,
    clock_skew: float = 60,
    verification_key: RSAPublicKey | None = None,
) -> dict[str, Any]:
    """
    验证 OIDC ID Token 并可校验 nonce

    :param token: 待验证 ID Token
    :param verification_keys: 按 kid 索引的公钥、单一公钥或查找回调
    :param issuer: 必须精确匹配的 issuer
    :param audience: OIDC Client ID
    :param nonce: 可选的原始授权 nonce
    :param clock_skew: 允许的时钟偏差秒数
    :param verification_key: 可选的单一 RSA 公钥
    :return: 已验签的 ID Token Claims
    :raises JwtProfileError: ID Token 不符合固定 Profile 或 nonce 不匹配
    """

    if issuer is None:
        raise JwtProfileError('issuer is required')
    claims = _decode(
        token,
        verification_keys,
        issuer,
        audience,
        profile='id',
        expected_type=ID_TOKEN_TYPE,
        required_claims={'iss', 'sub', 'aud', 'exp', 'iat', 'auth_time', 'nonce', 'sid', 'acr', 'amr'},
        clock_skew=clock_skew,
        verification_key=verification_key,
    )
    if nonce is not None and claims.get('nonce') != nonce:
        raise JwtProfileError('ID token nonce mismatch')
    return claims


def decode_id_token_hint(
    token: str,
    *,
    verification_key: RSAPublicKey,
    issuer: str,
    audience: str,
    clock_skew: float = 60,
) -> dict[str, Any]:
    """
    校验退出请求中的ID Token提示

    仅退出流程允许使用过期ID Token，调用方仍需将其绑定到已知会话。

    :param token: ID Token字符串
    :param verification_key: 签名验证公钥
    :param issuer: 预期签发方
    :param audience: 预期接收方
    :param clock_skew: 允许的时钟偏差，单位为秒
    :return: 已校验的ID Token声明
    """

    return _decode(
        token,
        None,
        issuer,
        audience,
        profile='id',
        expected_type=ID_TOKEN_TYPE,
        required_claims={'iss', 'sub', 'aud', 'exp', 'iat', 'auth_time', 'nonce', 'sid', 'acr', 'amr'},
        verification_key=verification_key,
        clock_skew=clock_skew,
        allow_expired_hint=True,
    )


def encode_logout_token(claims: Mapping[str, Any], signing_key: RSAPrivateKey, kid: str) -> str:
    """
    签发 Back-Channel Logout Token

    :param claims: Logout Token Claims
    :param signing_key: RSA 私钥
    :param kid: 签名密钥标识
    :return: typ 为 logout+jwt 的 JWT
    :raises JwtProfileError: Claims 或签名参数不合法
    """

    return _encode(claims, signing_key, kid, LOGOUT_TOKEN_TYPE, 'logout')


def decode_logout_token(
    token: str,
    verification_keys: object | None = None,
    issuer: str | None = None,
    audience: str | Sequence[str] | None = None,
    *,
    clock_skew: float = 60,
    verification_key: RSAPublicKey | None = None,
) -> dict[str, Any]:
    """
    验证 Back-Channel Logout Token

    :param token: 待验证 Logout Token
    :param verification_keys: 按 kid 索引的公钥、单一公钥或查找回调
    :param issuer: 必须精确匹配的 issuer
    :param audience: 目标 Client ID
    :param clock_skew: 允许的时钟偏差秒数
    :param verification_key: 可选的单一 RSA 公钥
    :return: 已验签的 Logout Token Claims
    :raises JwtProfileError: Logout Token 不符合固定 Profile
    """

    if issuer is None:
        raise JwtProfileError('issuer is required')
    return _decode(
        token,
        verification_keys,
        issuer,
        audience,
        profile='logout',
        expected_type=LOGOUT_TOKEN_TYPE,
        required_claims={'iss', 'aud', 'iat', 'jti', 'events'},
        clock_skew=clock_skew,
        verification_key=verification_key,
    )
