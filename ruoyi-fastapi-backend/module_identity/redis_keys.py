import hashlib
import hmac
import re
from typing import Final


class OidcRedisKey:
    """
    统一认证中心 Redis Key Builder。
    """

    PREFIX: Final[str] = 'oidc'
    SESSION_REVOKED_CHANNEL: Final[str] = 'oidc:event:session_revoked'
    USER_SECURITY_CHANGED_CHANNEL: Final[str] = 'oidc:event:user_security_changed'
    _COMPONENT_PATTERN: Final[re.Pattern[str]] = re.compile(r'^[A-Za-z0-9._-]{1,128}$')
    _SHA256_HEX_LENGTH: Final[int] = 64
    _PEPPER_MIN_BYTES: Final[int] = 32

    @classmethod
    def _safe_component(cls, value: str | int, *, name: str = 'Redis Key 组件') -> str:
        """
        校验可作为 Key 路径组件的标识符。

        :param value: 待校验的标识符
        :param name: 错误信息中的字段名称
        :return: 原样返回的安全组件
        :raises ValueError: 组件为空或包含路径/控制字符
        """
        component = str(value)
        if not cls._COMPONENT_PATTERN.fullmatch(component):
            raise ValueError(f'{name} 包含不允许的字符')
        return component

    @staticmethod
    def _safe_hex_digest(value: str | bytes) -> str:
        """
        校验已生成的 SHA-256 十六进制摘要。

        :param value: 摘要文本或 ASCII 字节
        :return: 小写十六进制摘要
        :raises TypeError: 输入不是 str 或 bytes
        :raises ValueError: 摘要长度或字符集不正确
        """
        if not isinstance(value, (str, bytes)):
            raise TypeError('摘要必须是 str 或 bytes')
        if isinstance(value, bytes):
            try:
                value = value.decode('ascii')
            except UnicodeDecodeError as exc:
                raise ValueError('摘要必须是 SHA-256 十六进制字符串') from exc
        if len(value) != OidcRedisKey._SHA256_HEX_LENGTH:
            raise ValueError('摘要必须是 SHA-256 十六进制字符串')
        try:
            bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError('摘要必须是 SHA-256 十六进制字符串') from exc
        return value.lower()

    @classmethod
    def hash_sensitive_identifier(cls, value: str | bytes, pepper: str | bytes) -> str:
        """
        使用独立 Pepper 对敏感标识生成 HMAC-SHA256 摘要。

        :param value: 用户名、IP 等敏感标识
        :param pepper: 独立于 JWT/传输加密密钥的 Pepper，至少 32 bytes
        :return: 64 位小写 HMAC-SHA256 摘要
        :raises TypeError: 标识或 Pepper 类型错误
        :raises ValueError: Pepper 为空或长度不足
        """
        if not isinstance(value, (str, bytes)) or not isinstance(pepper, (str, bytes)):
            raise TypeError('敏感标识和 Pepper 必须是 str 或 bytes')
        raw_value = value.encode('utf-8') if isinstance(value, str) else value
        raw_pepper = pepper.encode('utf-8') if isinstance(pepper, str) else pepper
        if len(raw_pepper) < cls._PEPPER_MIN_BYTES:
            raise ValueError('敏感标识摘要 Pepper 至少需要 32 bytes')
        return hmac.new(raw_pepper, raw_value, hashlib.sha256).hexdigest()

    @classmethod
    def interaction(cls, interaction_id: str) -> str:
        """
        生成 Interaction 状态键。

        :param interaction_id: Interaction 标识
        :return: Redis Key
        """
        return f'{cls.PREFIX}:interaction:{cls._safe_component(interaction_id, name="interaction_id")}'

    @classmethod
    def authorization_code(cls, code_id: str) -> str:
        """
        生成授权码状态键。

        :param code_id: 授权码内部标识
        :return: Redis Key
        """
        return f'{cls.PREFIX}:authorization_code:{cls._safe_component(code_id, name="code_id")}'

    @classmethod
    def authorization_code_consumed(cls, code_id: str) -> str:
        """生成授权码消费短期 tombstone 键。

        :param code_id: 授权码公开标识部分。
        :return: 不含授权码 Secret 的消费状态键。
        """
        return f'{cls.PREFIX}:authorization_code_consumed:{cls._safe_component(code_id, name="code_id")}'

    @classmethod
    def authorization_code_consumed_payload(cls, code_id: str) -> str:
        """
        生成授权码消费绑定载荷短期键。

        :param code_id: 授权码公开标识部分
        :return: 不含授权码 Secret 的消费绑定载荷键
        """
        return f'{cls.PREFIX}:authorization_code_consumed_payload:{cls._safe_component(code_id, name="code_id")}'

    @classmethod
    def sso_session(cls, sid: str) -> str:
        """
        生成 SSO 会话热缓存键。

        :param sid: SSO 会话标识
        :return: Redis Key
        """
        return f'{cls.PREFIX}:sso_session:{cls._safe_component(sid, name="sid")}'

    @classmethod
    def user_sessions(cls, user_id: str | int) -> str:
        """
        生成用户 SSO 会话索引键。

        :param user_id: 内部用户标识
        :return: Redis Key
        """
        return f'{cls.PREFIX}:user_sessions:{cls._safe_component(user_id, name="user_id")}'

    @classmethod
    def sso_cookie(cls, session_hash: str) -> str:
        """
        生成 SSO Cookie 摘要索引键。

        :param session_hash: Cookie Secret 的 SHA-256 摘要
        :return: Redis Key
        """
        return f'{cls.PREFIX}:sso_cookie:{cls._safe_hex_digest(session_hash)}'

    @classmethod
    def revoked_jti(cls, jti: str) -> str:
        """
        生成 Access Token JTI 撤销键。

        :param jti: Access Token 的 JTI
        :return: Redis Key
        """
        return f'{cls.PREFIX}:revoked_jti:{cls._safe_component(jti, name="jti")}'

    @classmethod
    def backchannel_retry_queue(cls) -> str:
        """
        返回 Back-Channel Logout 有界重试队列键。
        """

        return f'{cls.PREFIX}:backchannel:retry'

    @classmethod
    def signing_key_rotation_lock(cls) -> str:
        """返回跨实例签名密钥轮换锁键。

        :return: OIDC 签名密钥轮换专用 Redis 锁键。
        """

        return f'{cls.PREFIX}:signing_key:rotation_lock'

    @classmethod
    def authorize_ip_rate_limit(cls, ip_hash: str) -> str:
        """
        生成按 IP 限流键。

        :param ip_hash: 使用独立 Pepper 生成的 IP 摘要
        :return: Redis Key
        """
        return f'{cls.PREFIX}:rate_limit:authorize:ip:{cls._safe_hex_digest(ip_hash)}'

    @classmethod
    def login_user_rate_limit(cls, user_name_hash: str) -> str:
        """
        生成按用户限流键。

        :param user_name_hash: 使用独立 Pepper 生成的用户名摘要
        :return: Redis Key
        """
        return f'{cls.PREFIX}:rate_limit:login:user:{cls._safe_hex_digest(user_name_hash)}'

    @classmethod
    def interaction_captcha_rate_limit(cls, subject_hash: str) -> str:
        """生成认证中心验证码专用限流键。

        :param subject_hash: Interaction 与来源地址组合的 HMAC 摘要。
        :return: 验证码端点独立 Redis Key。
        """
        return f'{cls.PREFIX}:rate_limit:interaction:captcha:{cls._safe_hex_digest(subject_hash)}'

    @classmethod
    def token_client_rate_limit(cls, client_id: str) -> str:
        """
        生成按 Client 限流键。

        :param client_id: 外部 Client ID
        :return: Redis Key
        """
        return f'{cls.PREFIX}:rate_limit:token:client:{cls._safe_component(client_id, name="client_id")}'

    @classmethod
    def introspect_client_rate_limit(cls, client_id: str) -> str:
        """
        生成按 introspection Client 限流键。

        :param client_id: introspection Client ID
        :return: Redis Key
        """
        return f'{cls.PREFIX}:rate_limit:introspect:client:{cls._safe_component(client_id, name="client_id")}'

    @classmethod
    def revoke_client_rate_limit(cls, client_id: str) -> str:
        """返回独立于 Token Endpoint 的撤销端点限流键。

        :param client_id: 撤销调用方的外部 Client ID 或匿名占位标识。
        :return: 撤销端点专用 Redis Key。
        """
        return f'{cls.PREFIX}:rate_limit:revoke:client:{cls._safe_component(client_id, name="client_id")}'

    @classmethod
    def logout_rate_limit(cls, scope: str = 'anonymous') -> str:
        """返回按安全摘要隔离的 RP-Initiated Logout 限流键。

        :param scope: 已由调用方 HMAC 的 IP 或安全 fallback 摘要。
        :return: Logout Endpoint 专用 Redis Key。
        """
        return f'{cls.PREFIX}:rate_limit:logout:{cls._safe_component(scope, name="logout_scope")}'

    @classmethod
    def event_session_revoked(cls) -> str:
        """
        返回 SSO 会话撤销事件频道。

        :return: Redis Pub/Sub 频道名
        """
        return cls.SESSION_REVOKED_CHANNEL

    @classmethod
    def event_user_security_changed(cls) -> str:
        """
        返回用户安全变化事件频道。

        :return: Redis Pub/Sub 频道名
        """
        return cls.USER_SECURITY_CHANGED_CHANNEL
