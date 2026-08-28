import base64
import binascii
import secrets
from collections.abc import Callable, Iterable, Mapping
from typing import Any
from urllib.parse import unquote_plus

from module_identity.security.principal import OAuthClientPrincipal
from utils.pwd_util import PwdUtil

_MISSING_STATUS = object()


class ClientAuthenticationError(ValueError):
    """
    客户端认证失败

    协议层应将此异常统一映射为 invalid_client，不能泄漏 Secret 细节
    """


def generate_client_secret() -> str:
    """
    生成仅应展示一次的高熵 Client Secret

    :return: 带 cs1 类型前缀的随机 Secret
    """

    return f'cs1.{secrets.token_urlsafe(32)}'


def hash_client_secret(client_secret: str) -> str:
    """
    使用项目密码哈希器保存 Client Secret

    :param client_secret: 仅在创建/轮换时可见的明文 Secret
    :return: 可持久化的强哈希
    """

    if not isinstance(client_secret, str) or not client_secret:
        raise ValueError('client_secret must not be empty')
    return PwdUtil.get_password_hash(client_secret)


def verify_client_secret(client_secret: str, secret_hash: str) -> bool:
    """
    验证 Client Secret，错误输入统一返回 False

    :param client_secret: 请求携带的明文 Secret
    :param secret_hash: 已存储的 Secret 哈希
    :return: Secret 是否匹配
    """

    if not isinstance(client_secret, str) or not isinstance(secret_hash, str) or not secret_hash:
        return False
    try:
        return bool(PwdUtil.verify_password(client_secret, secret_hash))
    except (ValueError, TypeError, OSError):
        return False


def parse_client_secret_basic(authorization: str) -> tuple[str, str]:
    """
    解析 RFC 7617 Basic Header，不接受请求体 Secret 回退

    :param authorization: Authorization Header
    :return: 解码后的 client_id 与 client_secret
    :raises ClientAuthenticationError: Header、Base64 或凭据格式不合法
    """

    if not isinstance(authorization, str) or not authorization.startswith('Basic '):
        raise ClientAuthenticationError('invalid client authentication')
    encoded = authorization[6:].strip()
    if not encoded:
        raise ClientAuthenticationError('invalid client authentication')
    try:
        decoded = base64.b64decode(encoded, validate=True).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ClientAuthenticationError('invalid client authentication') from None
    if ':' not in decoded:
        raise ClientAuthenticationError('invalid client authentication')
    client_id, client_secret = decoded.split(':', 1)
    # OAuth 表单客户端认证使用 application/x-www-form-urlencoded 约定
    # 该约定同时正确处理 client_id 中的空格与 Secret 中的百分号编码冒号
    client_id, client_secret = unquote_plus(client_id), unquote_plus(client_secret)
    if not client_id or not client_secret:
        raise ClientAuthenticationError('invalid client authentication')
    # RFC 7617 user-id 不能包含冒号，但分割后的 Secret 可以包含冒号
    if any(ord(char) < _ASCII_CONTROL_LIMIT for char in client_id):
        raise ClientAuthenticationError('invalid client authentication')
    return client_id, client_secret


def _get(client: Any, name: str, default: Any = None) -> Any:
    """
    从映射或对象读取 Client 属性

    :param client: Client 映射或对象
    :param name: 属性名称
    :param default: 属性不存在时的默认值
    :return: Client 属性值
    """
    if isinstance(client, Mapping):
        return client.get(name, default)
    return getattr(client, name, default)


def _secret_hashes(client: Any, explicit: Iterable[str] | None = None) -> list[str]:
    """
    收集 Client 当前可用的 Secret 哈希

    :param client: Client 映射或对象
    :param explicit: 调用方显式提供的 Secret 哈希集合
    :return: 规范化后的 Secret 哈希列表
    """
    values = explicit
    if values is None:
        values = _get(client, 'secret_hashes')
    if values is None:
        values = _get(client, 'secrets')
    if values is None:
        one = _get(client, 'secret_hash')
        values = [one] if one else []
    result: list[str] = []
    for item in values:
        if isinstance(item, str):
            result.append(item)
        else:
            value = _get(item, 'secret_hash')
            if isinstance(value, str):
                result.append(value)
    return result


def authenticate_client(  # noqa: PLR0912
    client: Any,
    authorization: str | None = None,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    secret_hashes: Iterable[str] | None = None,
    client_lookup: Callable[[str], Any] | None = None,
    secret_match_callback: Callable[[str], None] | None = None,
) -> OAuthClientPrincipal:
    """
    按已注册 Client 策略认证

    机密 Client 仅接受 Basic；公共 Client 仅接受 form 的 client_id 且不得
    携带 Secret。``client_lookup`` 仅用于在 Header client_id 与传入对象
    分离时查找注册记录

    :param client: 已注册 Client 或支持属性访问的对象
    :param authorization: RFC 7617 Basic Header
    :param client_id: 公共 Client 的表单 client_id
    :param client_secret: 仅用于拒绝请求体 Secret 的参数
    :param secret_hashes: 可注入的有效 Secret 哈希集合
    :param client_lookup: 按 client_id 查找注册 Client 的回调
    :param secret_match_callback: Secret 匹配时接收其哈希的同步回调
    :return: 已认证的 OAuth Client 主体
    :raises ClientAuthenticationError: Client 策略或凭据不匹配
    """

    supplied_id = client_id
    supplied_secret = client_secret
    auth_method = 'none'
    if authorization is not None:
        if client_secret is not None:
            raise ClientAuthenticationError('invalid client authentication')
        basic_id, basic_secret = parse_client_secret_basic(authorization)
        if supplied_id is not None and supplied_id != basic_id:
            raise ClientAuthenticationError('invalid client authentication')
        supplied_id, supplied_secret, auth_method = basic_id, basic_secret, 'client_secret_basic'
    if supplied_id is None:
        supplied_id = _get(client, 'client_id')
    if client_lookup is not None and supplied_id:
        looked_up = client_lookup(supplied_id)
        if looked_up is not None:
            client = looked_up
    registered_id = _get(client, 'client_id')
    if not registered_id or not supplied_id or not secrets.compare_digest(str(registered_id), str(supplied_id)):
        raise ClientAuthenticationError('invalid client authentication')
    status = _get(client, 'status', _MISSING_STATUS)
    if status not in ('0', 0, 'active'):
        raise ClientAuthenticationError('invalid client authentication')
    client_type = _get(client, 'client_type', 'confidential')
    registered_method = _get(client, 'token_endpoint_auth_method', 'client_secret_basic')
    if client_type == 'public':
        if registered_method != 'none' or authorization is not None or supplied_secret is not None:
            raise ClientAuthenticationError('invalid client authentication')
        return OAuthClientPrincipal(str(registered_id), 'public', 'none')
    if (
        client_type != 'confidential'
        or registered_method != 'client_secret_basic'
        or auth_method != 'client_secret_basic'
    ):
        raise ClientAuthenticationError('invalid client authentication')
    matched = False
    matched_hash: str | None = None
    for item in _secret_hashes(client, secret_hashes):
        current_match = verify_client_secret(supplied_secret or '', item)
        if current_match and matched_hash is None:
            matched_hash = item
        matched = current_match or matched
    if not supplied_secret or not matched:
        raise ClientAuthenticationError('invalid client authentication')
    if matched_hash is not None and secret_match_callback is not None:
        secret_match_callback(matched_hash)
    return OAuthClientPrincipal(str(registered_id), 'confidential', 'client_secret_basic')


_ASCII_CONTROL_LIMIT = 0x20
