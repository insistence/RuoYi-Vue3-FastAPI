from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OidcConfig
from module_identity.dao.oauth_client_dao import OAuthClientDao


class DiscoveryService:
    """
    OIDC Discovery 模块服务层
    """

    @staticmethod
    async def supported_scopes(db: AsyncSession) -> list[str]:
        """
        读取启用 Scope 并稳定合并到协议元数据

        :param db: 异步数据库会话
        :return: 启用 Scope 名称列表
        """
        scopes = await OAuthClientDao.list_scope_definitions(db, active_only=True)
        dynamic = tuple(
            value if isinstance(value, str) else value.scope_code
            for value in scopes
            if isinstance(value, str) or isinstance(value.scope_code, str)
        )
        return list(
            dict.fromkeys((*('openid', 'profile', 'email', 'phone', 'dept', 'roles', 'offline_access'), *dynamic))
        )

    @staticmethod
    def _issuer() -> str:
        """
        读取签发者地址

        :return: OIDC 签发者地址
        """
        return OidcConfig.oidc_issuer.rstrip('/')

    @classmethod
    def openid_metadata(cls) -> dict[str, object]:
        """
        构建 OpenID 元数据

        :return: 协议元数据映射
        """
        issuer = cls._issuer()
        return {
            'issuer': issuer,
            'authorization_endpoint': f'{issuer}/oauth2/authorize',
            'token_endpoint': f'{issuer}/oauth2/token',
            'userinfo_endpoint': f'{issuer}/oauth2/userinfo',
            'jwks_uri': f'{issuer}/oauth2/jwks',
            'revocation_endpoint': f'{issuer}/oauth2/revoke',
            'introspection_endpoint': f'{issuer}/oauth2/introspect',
            'end_session_endpoint': f'{issuer}/oauth2/logout',
            'scopes_supported': ['openid', 'profile', 'email', 'phone', 'dept', 'roles', 'offline_access'],
            'response_types_supported': ['code'],
            'response_modes_supported': ['query'],
            'grant_types_supported': ['authorization_code', 'refresh_token', 'client_credentials'],
            'subject_types_supported': ['public'],
            'id_token_signing_alg_values_supported': ['RS256'],
            'token_endpoint_auth_methods_supported': ['none', 'client_secret_basic'],
            'code_challenge_methods_supported': ['S256'],
            'claims_supported': [
                'sub',
                'name',
                'preferred_username',
                'picture',
                'email',
                'email_verified',
                'phone_number',
                'phone_number_verified',
                'dept_id',
                'dept_name',
                'roles',
                'auth_time',
                'acr',
                'amr',
                'sid',
            ],
            'authorization_response_iss_parameter_supported': True,
            'backchannel_logout_supported': True,
            'backchannel_logout_session_supported': True,
        }

    @classmethod
    def oauth_metadata(cls) -> dict[str, object]:
        """
        构建 OAuth 元数据

        :return: 协议元数据映射
        """
        issuer = cls._issuer()
        return {
            'issuer': issuer,
            'authorization_endpoint': f'{issuer}/oauth2/authorize',
            'token_endpoint': f'{issuer}/oauth2/token',
            'jwks_uri': f'{issuer}/oauth2/jwks',
            'revocation_endpoint': f'{issuer}/oauth2/revoke',
            'introspection_endpoint': f'{issuer}/oauth2/introspect',
            'scopes_supported': ['openid', 'profile', 'email', 'phone', 'dept', 'roles', 'offline_access'],
            'response_types_supported': ['code'],
            'response_modes_supported': ['query'],
            'grant_types_supported': ['authorization_code', 'refresh_token', 'client_credentials'],
            'token_endpoint_auth_methods_supported': ['none', 'client_secret_basic'],
            'code_challenge_methods_supported': ['S256'],
            'authorization_response_iss_parameter_supported': True,
        }

    @classmethod
    async def openid_metadata_with_scopes(cls, db: AsyncSession) -> dict[str, object]:
        """
        构建带动态 Scope 的 OpenID 元数据

        :param db: 异步数据库会话
        :return: 协议元数据映射
        """
        payload = cls.openid_metadata()
        payload['scopes_supported'] = await cls.supported_scopes(db)
        return payload

    @classmethod
    async def oauth_metadata_with_scopes(cls, db: AsyncSession) -> dict[str, object]:
        """
        构建带动态 Scope 的 OAuth 元数据

        :param db: 异步数据库会话
        :return: 协议元数据映射
        """
        payload = cls.oauth_metadata()
        payload['scopes_supported'] = await cls.supported_scopes(db)
        return payload
