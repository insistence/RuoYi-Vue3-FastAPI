from sqlalchemy import (
    CHAR,
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
)

from common.types import DbUtcDateTime
from config.database import Base
from utils.time_util import TimezoneUtil


class SysOAuthResource(Base):
    """
    OAuth资源服务器表
    """

    __tablename__ = 'sys_oauth_resource'
    __table_args__ = (
        UniqueConstraint('resource_id', name='uk_oauth_resource_resource_id'),
        UniqueConstraint('audience', name='uk_oauth_resource_audience'),
        Index('idx_oauth_resource_status', 'status'),
        {'comment': 'OAuth Resource'},
    )

    resource_pk = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        nullable=False,
        autoincrement=True,
        comment='内部主键',
    )
    resource_id = Column(String(64), nullable=False, comment='Resource ID')
    resource_name = Column(String(100), nullable=False, comment='Resource 名称')
    audience = Column(String(500), nullable=False, comment='Access Token audience')
    token_format = Column(String(16), nullable=False, server_default='jwt', comment='Token 格式')
    signing_alg = Column(String(16), nullable=False, server_default='RS256', comment='签名算法')
    access_token_ttl_seconds = Column(Integer, nullable=True, comment='Access Token 有效期')
    introspection_client_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_client.client_pk', name='fk_oauth_resource_introspection_client', ondelete='RESTRICT'),
        nullable=True,
        comment='Introspection Client 主键',
    )
    allowed_claims = Column(JSON, nullable=False, comment='允许的 Claims')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0正常 1停用）')
    create_by = Column(String(64), nullable=False, comment='创建者')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')
    update_by = Column(String(64), nullable=False, comment='更新者')
    update_time = Column(
        DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, onupdate=TimezoneUtil.utc_now, comment='更新时间'
    )
    remark = Column(String(500), nullable=True, comment='备注')


class SysOAuthScope(Base):
    """
    OAuth权限表
    """

    __tablename__ = 'sys_oauth_scope'
    __table_args__ = (
        UniqueConstraint('scope_code', name='uk_oauth_scope_code'),
        Index('idx_oauth_scope_status', 'status'),
        Index('idx_oauth_scope_resource', 'resource_pk'),
        {'comment': 'OAuth Scope'},
    )

    scope_pk = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        nullable=False,
        autoincrement=True,
        comment='内部主键',
    )
    scope_code = Column(String(100), nullable=False, comment='Scope 编码')
    scope_name = Column(String(100), nullable=False, comment='Scope 名称')
    scope_type = Column(String(16), nullable=False, comment='Scope 类型')
    resource_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_resource.resource_pk', name='fk_oauth_scope_resource', ondelete='RESTRICT'),
        nullable=True,
        comment='Resource 主键',
    )
    claims = Column(JSON, nullable=False, comment='Claims 列表')
    consent_required = Column(SmallInteger, nullable=False, server_default='1', comment='是否需要同意')
    sensitive = Column(SmallInteger, nullable=False, server_default='0', comment='是否敏感')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0正常 1停用）')
    create_by = Column(String(64), nullable=False, comment='创建者')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')
    update_by = Column(String(64), nullable=False, comment='更新者')
    update_time = Column(
        DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, onupdate=TimezoneUtil.utc_now, comment='更新时间'
    )
    remark = Column(String(500), nullable=True, comment='备注')


class SysOAuthClientScope(Base):
    """
    OAuth客户端与权限关联表
    """

    __tablename__ = 'sys_oauth_client_scope'
    __table_args__ = (
        PrimaryKeyConstraint('client_pk', 'scope_pk', name='pk_oauth_client_scope'),
        Index('idx_oauth_client_scope_scope', 'scope_pk'),
        {'comment': 'OAuth Client Scope'},
    )

    client_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_client.client_pk', name='fk_oauth_client_scope_client', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='Client 主键',
    )
    scope_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_scope.scope_pk', name='fk_oauth_client_scope_scope', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='Scope 主键',
    )
    is_default = Column(SmallInteger, nullable=False, server_default='0', comment='是否默认 Scope')
    pre_authorized = Column(SmallInteger, nullable=False, server_default='0', comment='是否预授权')
    claim_filter = Column(JSON, nullable=True, comment='Client Claim 过滤策略')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')


class SysOAuthClientResource(Base):
    """
    OAuth客户端与资源关联表
    """

    __tablename__ = 'sys_oauth_client_resource'
    __table_args__ = (
        PrimaryKeyConstraint('client_pk', 'resource_pk', name='pk_oauth_client_resource'),
        Index('idx_oauth_client_resource_resource', 'resource_pk'),
        {'comment': 'OAuth Client Resource'},
    )

    client_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_client.client_pk', name='fk_oauth_client_resource_client', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='Client 主键',
    )
    resource_pk = Column(
        BigInteger,
        ForeignKey('sys_oauth_resource.resource_pk', name='fk_oauth_client_resource_resource', ondelete='RESTRICT'),
        primary_key=True,
        nullable=False,
        comment='Resource 主键',
    )
    is_default = Column(SmallInteger, nullable=False, server_default='0', comment='是否默认 Resource')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')
