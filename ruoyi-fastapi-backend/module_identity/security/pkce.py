import base64
import hashlib
import hmac
import re
import secrets


class PkceError(ValueError):
    """
    PKCE 参数格式错误或使用了不支持的算法
    """


_MIN_VERIFIER_LENGTH = 43
_MAX_VERIFIER_LENGTH = 128
_VERIFIER_RE = re.compile(r'^[A-Za-z0-9._~-]+$')
_CHALLENGE_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')


def validate_code_verifier(code_verifier: str) -> str:
    """
    校验并返回 RFC 7636 code_verifier

    :param code_verifier: 客户端生成的 PKCE verifier
    :return: 原样返回已校验 verifier
    :raises PkceError: 长度、字符集或类型不合法
    """

    if not isinstance(code_verifier, str):
        raise PkceError('code_verifier must be a string')
    if not _MIN_VERIFIER_LENGTH <= len(code_verifier) <= _MAX_VERIFIER_LENGTH:
        raise PkceError('code_verifier must contain 43 to 128 characters')
    if not _VERIFIER_RE.fullmatch(code_verifier):
        raise PkceError('code_verifier contains characters outside the RFC 7636 set')
    return code_verifier


def generate_code_verifier(length: int = 64) -> str:
    """
    生成至少 256 bit 熵的 code_verifier

    :param length: verifier 长度，范围为 43 至 128
    :return: 随机 code_verifier
    """

    if not _MIN_VERIFIER_LENGTH <= length <= _MAX_VERIFIER_LENGTH:
        raise ValueError('code_verifier length must be between 43 and 128')
    # token_urlsafe 的结果可能略长；截断仍保留足够熵且满足 RFC 字符集
    return validate_code_verifier(secrets.token_urlsafe(length)[:length])


def generate_code_challenge(code_verifier: str) -> str:
    """
    计算未填充的 base64url(SHA-256(verifier))

    :param code_verifier: 已校验的 PKCE verifier
    :return: S256 code_challenge
    """

    verifier = validate_code_verifier(code_verifier)

    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')


def verify_code_challenge(code_verifier: str, code_challenge: str, method: str = 'S256') -> bool:
    """
    以恒定时间比较 challenge，畸形值统一返回 False

    :param code_verifier: Token Endpoint 提交的 verifier
    :param code_challenge: Authorization Endpoint 保存的 challenge
    :param method: PKCE 方法，仅支持 S256
    :return: verifier 是否匹配 challenge
    :raises PkceError: 使用不支持的 PKCE 方法
    """

    if method != 'S256':
        raise PkceError('only PKCE S256 is supported')
    try:
        if not isinstance(code_challenge, str) or not _CHALLENGE_RE.fullmatch(code_challenge):
            return False
        expected = generate_code_challenge(code_verifier)
    except (PkceError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(expected, code_challenge)
