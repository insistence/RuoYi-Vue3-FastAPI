from sqlalchemy import JSON, BigInteger, CheckConstraint, Column, Index, Integer, String, Text, UniqueConstraint

from common.types import DbUtcDateTime
from config.database import Base
from utils.time_util import TimezoneUtil


class SysOidcSigningKey(Base):
    """
    OIDC签名密钥表
    """

    __tablename__ = 'sys_oidc_signing_key'
    __table_args__ = (
        UniqueConstraint('kid', name='uk_oidc_signing_key_kid'),
        CheckConstraint(
            '((CASE WHEN private_key_ref IS NULL THEN 0 ELSE 1 END) + '
            '(CASE WHEN private_key_ciphertext IS NULL THEN 0 ELSE 1 END)) = 1',
            name='ck_oidc_signing_key_private_material',
        ),
        Index('idx_oidc_signing_key_status_publish', 'status', 'publish_at'),
        Index('idx_oidc_signing_key_jwks_remove', 'status', 'remove_from_jwks_at'),
        {'comment': 'OIDC Signing Key'},
    )

    key_pk = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        nullable=False,
        autoincrement=True,
        comment='内部主键',
    )
    kid = Column(String(100), nullable=False, comment='JWKS Key ID')
    key_use = Column(String(16), nullable=False, server_default='sig', comment='JWK 用途')
    alg = Column(String(16), nullable=False, server_default='RS256', comment='签名算法')
    public_jwk = Column(JSON, nullable=False, comment='公开 JWK')
    private_key_ref = Column(String(1000), nullable=True, comment='KMS/HSM/文件引用')
    private_key_ciphertext = Column(Text, nullable=True, comment='加密私钥材料')
    status = Column(String(16), nullable=False, comment='密钥状态')
    publish_at = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='发布时间')
    signing_start_at = Column(DbUtcDateTime(), nullable=True, comment='开始签名时间')
    signing_stop_at = Column(DbUtcDateTime(), nullable=True, comment='停止签名时间')
    remove_from_jwks_at = Column(DbUtcDateTime(), nullable=True, comment='移出 JWKS 时间')
    create_by = Column(String(64), nullable=False, comment='创建者')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')
    remark = Column(String(500), nullable=True, comment='备注')
