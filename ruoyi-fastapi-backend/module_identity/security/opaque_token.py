import base64
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass

from utils.oidc_util import OidcUtil


class OpaqueTokenError(ValueError):
    """
    不透明令牌结构、类型或 Secret 不符合安全约束
    """


@dataclass(frozen=True, slots=True)
class ParsedOpaqueToken:
    """
    已解析但尚未证明有效的不透明令牌

    解析结果只描述格式，数据库摘要校验成功后才具有凭据语义
    """

    prefix: str
    token_id: str
    secret: str

    @property
    def value(self) -> str:
        """
        返回完整的不透明令牌文本

        :return: 带类型前缀的完整令牌
        """

        return f'{self.prefix}.{self.token_id}.{self.secret}'


_PREFIXES = frozenset({'ac1', 'rt1', 'ss1'})
_TOKEN_ID_RE = re.compile(r'^[A-Za-z0-9_-]{8,128}$')
_SECRET_RE = re.compile(r'^[A-Za-z0-9_-]{32,256}$')
_SECRET_BYTES = 32
_MIN_PEPPER_BYTES = 32
_OPAQUE_PART_COUNT = 3


def generate_opaque_token(prefix: str, token_id: str | None = None) -> str:
    """
    生成带类型前缀和 256 bit 随机 Secret 的不透明令牌

    :param prefix: ac1、rt1 或 ss1
    :param token_id: 可选的外部 ID
    :return: 完整不透明令牌
    """

    if prefix not in _PREFIXES:
        raise OpaqueTokenError(f'不支持的不透明令牌前缀：{prefix}')
    identifier = token_id or str(uuid.uuid4())
    if not _TOKEN_ID_RE.fullmatch(identifier):
        raise OpaqueTokenError('不透明令牌标识无效')
    return f'{prefix}.{identifier}.{OidcUtil.base64url_encode(secrets.token_bytes(_SECRET_BYTES))}'


def generate_authorization_code(code_id: str | None = None) -> str:
    """
    生成授权码

    :param code_id: 可选的授权码 ID
    :return: ac1 前缀的不透明授权码
    """

    return generate_opaque_token('ac1', code_id)


def generate_refresh_token(token_id: str | None = None) -> str:
    """
    生成 Refresh Token

    :param token_id: 可选的 Refresh Token ID
    :return: rt1 前缀的不透明 Refresh Token
    """

    return generate_opaque_token('rt1', token_id)


def generate_sso_cookie(sid: str | None = None) -> str:
    """
    生成 SSO Cookie Secret

    :param sid: 可选的 SSO Session ID
    :return: ss1 前缀的 Cookie 值
    """

    return generate_opaque_token('ss1', sid)


def parse_opaque_token(token: str, expected_prefix: str | None = None) -> ParsedOpaqueToken:
    """
    解析令牌结构，不把 token_id 当作 Secret 证明

    :param token: 待解析的不透明令牌
    :param expected_prefix: 可选的预期类型前缀
    :return: 结构化令牌
    :raises OpaqueTokenError: 令牌结构、类型或 Secret 不合法
    """

    if not isinstance(token, str):
        raise OpaqueTokenError('不透明令牌必须为字符串')
    parts = token.split('.')
    if len(parts) != _OPAQUE_PART_COUNT:
        raise OpaqueTokenError('不透明令牌格式无效')
    prefix, token_id, secret = parts
    if prefix not in _PREFIXES or (expected_prefix is not None and prefix != expected_prefix):
        raise OpaqueTokenError('不透明令牌类型不匹配')
    if not _TOKEN_ID_RE.fullmatch(token_id):
        raise OpaqueTokenError('不透明令牌标识无效')
    if not _SECRET_RE.fullmatch(secret):
        raise OpaqueTokenError('不透明令牌密钥无效')
    try:
        decoded = base64.urlsafe_b64decode(secret + '=' * (-len(secret) % 4))
    except (ValueError, UnicodeError):
        raise OpaqueTokenError('不透明令牌密钥无效') from None
    if len(decoded) != _SECRET_BYTES:
        raise OpaqueTokenError('不透明令牌密钥必须为 256 位')
    return ParsedOpaqueToken(prefix, token_id, secret)


def _pepper_bytes(pepper: str | bytes) -> bytes:
    """
    校验并转换令牌摘要 Pepper

    :param pepper: 字符串或字节形式的摘要 Pepper
    :return: 长度满足安全约束的 Pepper 字节
    :raises ValueError: Pepper 类型或长度不符合安全约束
    """

    value = pepper.encode('utf-8') if isinstance(pepper, str) else pepper
    if not isinstance(value, bytes) or len(value) < _MIN_PEPPER_BYTES:
        raise ValueError('身份令牌摘要密钥至少需要 256 位')
    return value


def token_digest(token: str, pepper: str | bytes) -> str:
    """
    返回完整不透明令牌的 HMAC-SHA256 十六进制摘要

    :param token: 完整 typed opaque token
    :param pepper: 独立的摘要 Pepper
    :return: 64 位十六进制摘要
    """

    return OidcUtil.hmac_sha256(token.encode('utf-8'), _pepper_bytes(pepper))


def verify_token_digest(token: str, expected_digest: str, pepper: str | bytes) -> bool:
    """
    恒定时间校验摘要，畸形 token 或 digest 时拒绝验证

    :param token: 完整 typed opaque token
    :param expected_digest: 数据库存储的摘要
    :param pepper: 独立的摘要 Pepper
    :return: 摘要是否匹配完整令牌
    """

    if not isinstance(expected_digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_digest):
        return False
    try:
        # 先验证完整 typed token；token_id 本身不能成为可摘要认证凭据
        parse_opaque_token(token)
        actual = token_digest(token, pepper)
    except (TypeError, ValueError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected_digest.lower())
