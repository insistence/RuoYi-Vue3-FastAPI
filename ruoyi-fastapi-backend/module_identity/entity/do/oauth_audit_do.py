from sqlalchemy import JSON, BigInteger, Column, Index, Integer, String

from common.types import DbUtcDateTime
from config.database import Base
from utils.time_util import TimezoneUtil


class SysOAuthAuditLog(Base):
    """
    OAuth/OIDC安全审计日志表
    """

    __tablename__ = 'sys_oauth_audit_log'
    __table_args__ = (
        Index('idx_oauth_audit_time', 'create_time'),
        Index('idx_oauth_audit_client', 'client_id', 'create_time'),
        Index('idx_oauth_audit_user', 'user_id', 'create_time'),
        Index('idx_oauth_audit_event', 'event_type', 'result', 'create_time'),
        Index('idx_oauth_audit_risk', 'risk_level', 'create_time'),
        {'comment': 'OAuth Audit Log'},
    )

    event_id = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        nullable=False,
        autoincrement=True,
        comment='事件ID',
    )
    trace_id = Column(String(64), nullable=True, comment='链路追踪ID')
    event_type = Column(String(64), nullable=False, comment='事件类型')
    result = Column(String(16), nullable=False, comment='结果')
    risk_level = Column(String(16), nullable=False, server_default='normal', comment='风险等级')
    client_id = Column(String(64), nullable=True, comment='Client ID 快照')
    resource_id = Column(String(64), nullable=True, comment='Resource ID 快照')
    user_id = Column(BigInteger, nullable=True, comment='用户ID快照')
    subject_id = Column(String(36), nullable=True, comment='Subject 快照')
    sid = Column(String(36), nullable=True, comment='SSO Session ID')
    grant_id = Column(String(36), nullable=True, comment='Grant ID')
    token_id = Column(String(36), nullable=True, comment='Token ID')
    ip_address = Column(String(128), nullable=True, comment='客户端 IP')
    user_agent = Column(String(500), nullable=True, comment='脱敏 User-Agent')
    failure_code = Column(String(64), nullable=True, comment='失败码')
    detail = Column(JSON, nullable=True, comment='脱敏扩展详情')
    create_time = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='事件时间')


class SysOAuthAuditArchive(Base):
    """
    OAuth/OIDC安全审计归档表
    """

    __tablename__ = 'sys_oauth_audit_archive'
    __table_args__ = (
        Index('idx_oauth_audit_archive_time', 'create_time'),
        Index('idx_oauth_audit_archive_event', 'event_type', 'result', 'create_time'),
        {'comment': 'OAuth Audit Archive'},
    )

    event_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False, comment='原事件ID')
    trace_id = Column(String(64), nullable=True, comment='链路追踪ID')
    event_type = Column(String(64), nullable=False, comment='事件类型')
    result = Column(String(16), nullable=False, comment='结果')
    risk_level = Column(String(16), nullable=False, comment='风险等级')
    client_id = Column(String(64), nullable=True, comment='Client ID 快照')
    resource_id = Column(String(64), nullable=True, comment='Resource ID 快照')
    user_id = Column(BigInteger, nullable=True, comment='用户ID快照')
    subject_id = Column(String(36), nullable=True, comment='Subject 快照')
    sid = Column(String(36), nullable=True, comment='SSO Session ID')
    grant_id = Column(String(36), nullable=True, comment='Grant ID')
    token_id = Column(String(36), nullable=True, comment='Token ID')
    ip_address = Column(String(128), nullable=True, comment='客户端 IP')
    user_agent = Column(String(500), nullable=True, comment='脱敏 User-Agent')
    failure_code = Column(String(64), nullable=True, comment='失败码')
    detail = Column(JSON, nullable=True, comment='脱敏扩展详情')
    create_time = Column(DbUtcDateTime(), nullable=False, comment='事件时间')
    archived_at = Column(DbUtcDateTime(), nullable=False, default=TimezoneUtil.utc_now, comment='归档时间')
