from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, UniqueConstraint

from common.types import DbUtcDateTime
from config.database import Base
from utils.time_util import TimezoneUtil


class SysIdentitySubject(Base):
    """
    统一认证主体关联表
    """

    __tablename__ = 'sys_identity_subject'
    __table_args__ = (
        UniqueConstraint('user_id', name='uk_identity_subject_user'),
        UniqueConstraint('subject_id', name='uk_identity_subject_subject'),
        Index('idx_identity_subject_auth_version', 'auth_version'),
        {'comment': '统一认证主体关联表'},
    )

    identity_id = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        nullable=False,
        autoincrement=True,
        comment='内部主键',
    )
    user_id = Column(
        BigInteger,
        ForeignKey('sys_user.user_id', name='fk_identity_subject_user', ondelete='RESTRICT'),
        nullable=False,
        comment='本地用户ID',
    )
    subject_id = Column(String(36), nullable=False, comment='OIDC Subject')
    auth_version = Column(BigInteger, nullable=False, server_default='1', comment='认证安全版本')
    create_by = Column(String(64), nullable=True, comment='创建者')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='创建时间')
    update_by = Column(String(64), nullable=True, comment='更新者')
    update_time = Column(DbUtcDateTime(), nullable=True, onupdate=TimezoneUtil.utc_now, comment='更新时间')
