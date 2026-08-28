import hashlib

from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import validates

from config.database import Base
from module_identity.entity.do._base import IDENTITY_DATETIME, current_time, primary_key_type


class SysOAuthClient(Base):
    """
    OAuth 客户端。
    """

    __tablename__ = 'sys_oauth_client'
    __table_args__ = (
        UniqueConstraint('client_id', name='uk_oauth_client_client_id'),
        Index('idx_oauth_client_status', 'status'),
        {'comment': 'OAuth Client'},
    )

    client_pk = Column(primary_key_type(), primary_key=True, nullable=False, autoincrement=True, comment='内部主键')
    client_id = Column(String(64), nullable=False, comment='Client ID')
    client_name = Column(String(100), nullable=False, comment='客户端名称')
    client_type = Column(String(20), nullable=False, comment='Client 类型')
    token_endpoint_auth_method = Column(String(32), nullable=False, comment='Token 端点认证方式')
    grant_types = Column(JSON, nullable=False, comment='Grant Type 列表')
    response_types = Column(JSON, nullable=False, comment='Response Type 列表')
    subject_type = Column(String(16), nullable=False, server_default='public', comment='Subject 类型')
    require_pkce = Column(SmallInteger, nullable=False, server_default='1', comment='是否要求 PKCE')
    require_consent = Column(SmallInteger, nullable=False, server_default='1', comment='是否要求同意')
    trusted_client = Column(SmallInteger, nullable=False, server_default='0', comment='是否受信任 Client')
    policy_version = Column(BigInteger, nullable=False, server_default='1', comment='安全策略版本')
    id_token_signed_response_alg = Column(String(16), nullable=False, server_default='RS256', comment='ID Token 算法')
    access_token_ttl_seconds = Column(Integer, nullable=True, comment='Access Token 有效期')
    refresh_token_idle_seconds = Column(Integer, nullable=True, comment='Refresh Token 闲置有效期')
    refresh_token_absolute_seconds = Column(Integer, nullable=True, comment='Refresh Token 绝对有效期')
    logo_uri = Column(String(500), nullable=True, comment='Logo URI')
    policy_uri = Column(String(500), nullable=True, comment='隐私政策 URI')
    tos_uri = Column(String(500), nullable=True, comment='服务条款 URI')
    backchannel_logout_session_required = Column(
        SmallInteger, nullable=False, server_default='1', comment='是否要求 Back-Channel Session'
    )
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0正常 1停用）')
    create_by = Column(String(64), nullable=False, server_default='', comment='创建者')
    create_time = Column(IDENTITY_DATETIME, nullable=False, default=current_time, comment='创建时间')
    update_by = Column(String(64), nullable=False, server_default='', default='', comment='更新者')
    update_time = Column(
        IDENTITY_DATETIME, nullable=False, default=current_time, onupdate=current_time, comment='更新时间'
    )
    remark = Column(String(500), nullable=True, comment='备注')


class SysOAuthClientSecret(Base):
    """
    OAuth 客户端密钥，仅保存强哈希。
    """

    __tablename__ = 'sys_oauth_client_secret'
    __table_args__ = (
        Index('idx_oauth_client_secret_client', 'client_pk', 'status'),
        {'comment': 'OAuth Client Secret'},
    )

    secret_id = Column(String(36), primary_key=True, nullable=False, comment='Secret ID')
    client_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_client.client_pk', name='fk_oauth_client_secret_client', ondelete='RESTRICT'),
        nullable=False,
        comment='Client 主键',
    )
    secret_hash = Column(String(100), nullable=False, comment='Secret 强哈希')
    secret_hint = Column(String(12), nullable=False, comment='Secret 提示')
    status = Column(String(16), nullable=False, server_default='active', comment='Secret 状态')
    not_before = Column(IDENTITY_DATETIME, nullable=False, default=current_time, comment='生效时间')
    expires_at = Column(IDENTITY_DATETIME, nullable=True, comment='过期时间')
    last_used_at = Column(IDENTITY_DATETIME, nullable=True, comment='最近使用时间')
    create_by = Column(String(64), nullable=False, comment='创建者')
    create_time = Column(IDENTITY_DATETIME, nullable=False, default=current_time, comment='创建时间')
    revoked_by = Column(String(64), nullable=True, comment='撤销者')
    revoked_at = Column(IDENTITY_DATETIME, nullable=True, comment='撤销时间')


class SysOAuthClientUri(Base):
    """
    OAuth 客户端注册 URI。
    """

    __tablename__ = 'sys_oauth_client_uri'
    __table_args__ = (
        UniqueConstraint('client_pk', 'uri_type', 'uri_hash', name='uk_oauth_client_uri_hash'),
        Index('idx_oauth_client_uri_type', 'client_pk', 'uri_type', 'status'),
        {'comment': 'OAuth Client URI'},
    )

    uri_id = Column(primary_key_type(), primary_key=True, nullable=False, autoincrement=True, comment='URI 主键')
    client_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_client.client_pk', name='fk_oauth_client_uri_client', ondelete='RESTRICT'),
        nullable=False,
        comment='Client 主键',
    )
    uri_type = Column(String(32), nullable=False, comment='URI 类型')
    uri = Column(String(1000), nullable=False, comment='精确 URI')
    uri_hash = Column(CHAR(64), nullable=False, comment='URI SHA-256 摘要')
    is_default = Column(SmallInteger, nullable=False, server_default='0', comment='是否默认 URI')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0正常 1停用）')
    create_time = Column(IDENTITY_DATETIME, nullable=False, default=current_time, comment='创建时间')

    @validates('uri')
    def derive_uri_hash(self, key: str, value: str) -> str:
        """
        根据 URI 更新摘要。
        """
        self.uri_hash = hashlib.sha256(value.encode('utf-8')).hexdigest()
        return value
