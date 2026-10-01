from typing import Final

from utils.oidc_util import OidcUtil


class OidcRedisKey:
    """
    统一认证中心 Redis Key Builder
    """

    PREFIX: Final[str] = 'oidc'
    SESSION_REVOKED_CHANNEL: Final[str] = 'oidc:event:session_revoked'
    USER_SECURITY_CHANGED_CHANNEL: Final[str] = 'oidc:event:user_security_changed'

    @classmethod
    def interaction(cls, interaction_id: str) -> str:
        """
        生成 Interaction 状态键

        :param interaction_id: Interaction 标识
        :return: Redis Key
        """

        return f'{cls.PREFIX}:interaction:{OidcUtil.redis_key_component(interaction_id, name="interaction_id")}'

    @classmethod
    def authorization_code(cls, code_id: str) -> str:
        """
        生成授权码状态键

        :param code_id: 授权码内部标识
        :return: Redis Key
        """

        return f'{cls.PREFIX}:authorization_code:{OidcUtil.redis_key_component(code_id, name="code_id")}'

    @classmethod
    def authorization_code_consumed(cls, code_id: str) -> str:
        """
        生成授权码消费短期 tombstone 键

        :param code_id: 授权码公开标识部分
        :return: 不含授权码 Secret 的消费状态键
        """

        return f'{cls.PREFIX}:authorization_code_consumed:{OidcUtil.redis_key_component(code_id, name="code_id")}'

    @classmethod
    def authorization_code_consumed_payload(cls, code_id: str) -> str:
        """
        生成授权码消费绑定载荷短期键

        :param code_id: 授权码公开标识部分
        :return: 不含授权码 Secret 的消费绑定载荷键
        """

        return (
            f'{cls.PREFIX}:authorization_code_consumed_payload:{OidcUtil.redis_key_component(code_id, name="code_id")}'
        )

    @classmethod
    def sso_session(cls, sid: str) -> str:
        """
        生成 SSO 会话热缓存键

        :param sid: SSO 会话标识
        :return: Redis Key
        """

        return f'{cls.PREFIX}:sso_session:{OidcUtil.redis_key_component(sid, name="sid")}'

    @classmethod
    def user_sessions(cls, user_id: str | int) -> str:
        """
        生成用户 SSO 会话索引键

        :param user_id: 内部用户标识
        :return: Redis Key
        """

        return f'{cls.PREFIX}:user_sessions:{OidcUtil.redis_key_component(user_id, name="user_id")}'

    @classmethod
    def sso_cookie(cls, session_hash: str) -> str:
        """
        生成 SSO Cookie 摘要索引键

        :param session_hash: Cookie Secret 的 SHA-256 摘要
        :return: Redis Key
        """

        return f'{cls.PREFIX}:sso_cookie:{OidcUtil.sha256_hex_digest(session_hash)}'

    @classmethod
    def revoked_jti(cls, jti: str) -> str:
        """
        生成 Access Token JTI 撤销键

        :param jti: Access Token 的 JTI
        :return: Redis Key
        """

        return f'{cls.PREFIX}:revoked_jti:{OidcUtil.redis_key_component(jti, name="jti")}'

    @classmethod
    def backchannel_retry_queue(cls) -> str:
        """
        返回 Back-Channel Logout 有界重试队列键
        """

        return f'{cls.PREFIX}:backchannel:retry'

    @classmethod
    def signing_key_rotation_lock(cls) -> str:
        """
        返回跨实例签名密钥轮换锁键

        :return: OIDC 签名密钥轮换专用 Redis 锁键
        """

        return f'{cls.PREFIX}:signing_key:rotation_lock'

    @classmethod
    def authorize_ip_rate_limit(cls, ip_hash: str) -> str:
        """
        生成按 IP 限流键

        :param ip_hash: 使用独立 Pepper 生成的 IP 摘要
        :return: Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:authorize:ip:{OidcUtil.sha256_hex_digest(ip_hash)}'

    @classmethod
    def login_user_rate_limit(cls, user_name_hash: str) -> str:
        """
        生成按用户限流键

        :param user_name_hash: 使用独立 Pepper 生成的用户名摘要
        :return: Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:login:user:{OidcUtil.sha256_hex_digest(user_name_hash)}'

    @classmethod
    def interaction_captcha_rate_limit(cls, subject_hash: str) -> str:
        """
        生成认证中心验证码专用限流键

        :param subject_hash: Interaction 与来源地址组合的 HMAC 摘要
        :return: 验证码端点独立 Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:interaction:captcha:{OidcUtil.sha256_hex_digest(subject_hash)}'

    @classmethod
    def token_client_rate_limit(cls, client_id: str) -> str:
        """
        生成按 Client 限流键

        :param client_id: 外部 Client ID
        :return: Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:token:client:{OidcUtil.redis_key_component(client_id, name="client_id")}'

    @classmethod
    def introspect_client_rate_limit(cls, client_id: str) -> str:
        """
        生成按 introspection Client 限流键

        :param client_id: introspection Client ID
        :return: Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:introspect:client:{OidcUtil.redis_key_component(client_id, name="client_id")}'

    @classmethod
    def revoke_client_rate_limit(cls, client_id: str) -> str:
        """
        返回独立于 Token Endpoint 的撤销端点限流键

        :param client_id: 撤销调用方的外部 Client ID 或匿名占位标识
        :return: 撤销端点专用 Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:revoke:client:{OidcUtil.redis_key_component(client_id, name="client_id")}'

    @classmethod
    def logout_rate_limit(cls, scope: str = 'anonymous') -> str:
        """
        返回按安全摘要隔离的 RP-Initiated Logout 限流键

        :param scope: 已由调用方 HMAC 的 IP 或安全 fallback 摘要
        :return: Logout Endpoint 专用 Redis Key
        """

        return f'{cls.PREFIX}:rate_limit:logout:{OidcUtil.redis_key_component(scope, name="logout_scope")}'

    @classmethod
    def event_session_revoked(cls) -> str:
        """
        返回 SSO 会话撤销事件频道

        :return: Redis Pub/Sub 频道名
        """

        return cls.SESSION_REVOKED_CHANNEL

    @classmethod
    def event_user_security_changed(cls) -> str:
        """
        返回用户安全变化事件频道

        :return: Redis Pub/Sub 频道名
        """

        return cls.USER_SECURITY_CHANGED_CHANNEL
