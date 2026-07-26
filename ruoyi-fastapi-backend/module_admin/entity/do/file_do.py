from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Index, Integer, String, Text, UniqueConstraint

from config.database import Base


class SysFileInfo(Base):
    """
    文件信息表
    """

    __tablename__ = 'sys_file_info'
    __table_args__ = (
        UniqueConstraint(
            'storage_type',
            'access_type',
            'storage_key',
            name='uk_sys_file_info_storage_location',
        ),
        Index('idx_sys_file_info_access_status', 'access_type', 'status'),
        Index('idx_sys_file_info_owner_status', 'owner_user_id', 'status'),
        Index('idx_sys_file_info_dept_status', 'dept_id', 'status'),
        Index('idx_sys_file_info_status_deleted_time', 'status', 'deleted_time'),
        {'comment': '文件信息表'},
    )

    file_id = Column(String(36), primary_key=True, nullable=False, comment='文件ID')
    original_name = Column(String(255), nullable=False, comment='原始文件名')
    stored_name = Column(String(255), nullable=False, comment='存储文件名')
    storage_key = Column(String(500), nullable=False, comment='存储相对路径')
    storage_type = Column(String(20), nullable=False, server_default='local', comment='存储类型')
    access_type = Column(String(20), nullable=False, server_default='public', comment='访问类型')
    upload_user_id = Column(BigInteger, nullable=True, comment='上传用户ID')
    uploader_access_enabled = Column(
        CHAR(1),
        nullable=False,
        server_default='1',
        comment='是否保留上传人访问权限',
    )
    owner_user_id = Column(BigInteger, nullable=True, comment='所有者用户ID')
    dept_id = Column(BigInteger, nullable=True, comment='所属部门ID')
    acl_version = Column(Integer, nullable=False, server_default='0', comment='访问控制版本')
    business_type = Column(String(50), nullable=True, comment='业务类型')
    business_id = Column(String(64), nullable=True, comment='业务ID')
    extension = Column(String(20), nullable=False, server_default="''", comment='文件扩展名')
    content_type = Column(String(255), nullable=True, comment='内容类型')
    file_size = Column(BigInteger, nullable=False, server_default='0', comment='文件大小')
    file_hash = Column(String(64), nullable=False, comment='文件SHA-256')
    status = Column(String(20), nullable=False, server_default='active', comment='文件状态')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=False, default=datetime.now, comment='更新时间')
    expire_time = Column(DateTime, nullable=True, comment='过期时间')
    deleted_time = Column(DateTime, nullable=True, comment='移入回收站时间')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志')


class SysFileReference(Base):
    """
    文件业务引用表
    """

    __tablename__ = 'sys_file_reference'
    __table_args__ = (
        UniqueConstraint(
            'file_id',
            'business_type',
            'business_id',
            name='uk_sys_file_reference_business',
        ),
        Index('idx_sys_file_reference_file', 'file_id'),
        Index('idx_sys_file_reference_business', 'business_type', 'business_id'),
        {'comment': '文件业务引用表'},
    )

    reference_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='引用ID')
    file_id = Column(String(36), nullable=False, comment='文件ID')
    business_type = Column(String(50), nullable=False, comment='业务类型')
    business_id = Column(String(64), nullable=False, comment='业务ID')
    business_name = Column(String(255), nullable=True, comment='业务名称')
    retention_expire_time = Column(DateTime, nullable=True, comment='保留期限到期时间')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')


class SysFileRetentionPolicy(Base):
    """
    文件业务保留策略表
    """

    __tablename__ = 'sys_file_retention_policy'
    __table_args__ = {'comment': '文件业务保留策略表'}

    business_type = Column(String(50), primary_key=True, nullable=False, comment='业务类型')
    retention_days = Column(Integer, nullable=False, comment='保留天数')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0启用 1停用）')
    remark = Column(String(500), nullable=True, comment='备注')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=False, default=datetime.now, comment='更新时间')


class SysFileRetentionNotice(Base):
    """
    文件保留期限提醒表
    """

    __tablename__ = 'sys_file_retention_notice'
    __table_args__ = (
        UniqueConstraint(
            'file_id',
            'notice_type',
            'expire_time',
            name='uk_sys_file_retention_notice_file_type_time',
        ),
        Index('idx_sys_file_retention_notice_file', 'file_id'),
        Index('idx_sys_file_retention_notice_status_time', 'status', 'create_time'),
        {'comment': '文件保留期限提醒表'},
    )

    notice_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='提醒ID')
    file_id = Column(String(36), nullable=False, comment='文件ID')
    notice_type = Column(String(20), nullable=False, comment='提醒类型')
    expire_time = Column(DateTime, nullable=False, comment='文件过期时间')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态（0未读 1已读 2已失效）')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    read_by = Column(String(64), nullable=True, server_default="''", comment='读取者')
    read_time = Column(DateTime, nullable=True, comment='读取时间')


class SysFileAcl(Base):
    """
    文件访问控制表
    """

    __tablename__ = 'sys_file_acl'
    __table_args__ = (
        UniqueConstraint(
            'file_id',
            'subject_type',
            'subject_id',
            'permission',
            name='uk_sys_file_acl_subject_permission',
        ),
        Index('idx_sys_file_acl_file_status', 'file_id', 'del_flag', 'expire_time'),
        Index('idx_sys_file_acl_subject', 'subject_type', 'subject_id'),
        {'comment': '文件访问控制表'},
    )

    acl_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='访问控制ID')
    file_id = Column(String(36), nullable=False, comment='文件ID')
    subject_type = Column(String(20), nullable=False, comment='主体类型')
    subject_id = Column(BigInteger, nullable=False, comment='主体ID')
    permission = Column(String(20), nullable=False, server_default='download', comment='权限类型')
    effect = Column(String(10), nullable=False, server_default='allow', comment='授权效果')
    include_children = Column(CHAR(1), nullable=False, server_default='0', comment='部门是否包含下级')
    expire_time = Column(DateTime, nullable=True, comment='授权过期时间')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=False, default=datetime.now, comment='创建时间')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志')


class SysFileAccessLog(Base):
    """
    文件访问审计表
    """

    __tablename__ = 'sys_file_access_log'
    __table_args__ = (
        Index('idx_sys_file_access_log_file_time', 'file_id', 'access_time'),
        Index('idx_sys_file_access_log_actor_time', 'actor_user_id', 'access_time'),
        {'comment': '文件访问审计表'},
    )

    audit_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='审计ID')
    file_id = Column(String(36), nullable=False, comment='文件ID')
    action = Column(String(20), nullable=False, comment='操作类型')
    actor_user_id = Column(BigInteger, nullable=True, comment='操作用户ID')
    actor_name = Column(String(64), nullable=True, server_default="''", comment='操作用户名称')
    result = Column(String(20), nullable=False, comment='操作结果')
    request_id = Column(String(64), nullable=True, server_default="''", comment='请求ID')
    trace_id = Column(String(64), nullable=True, server_default="''", comment='链路ID')
    ip_address = Column(String(128), nullable=True, server_default="''", comment='客户端地址')
    user_agent = Column(String(500), nullable=True, server_default="''", comment='用户代理')
    bytes_sent = Column(BigInteger, nullable=False, server_default='0', comment='发送字节数')
    error_message = Column(String(500), nullable=True, server_default="''", comment='失败原因')
    operation_detail = Column(Text, nullable=True, comment='操作详情')
    access_time = Column(DateTime, nullable=False, default=datetime.now, comment='访问时间')


class SysFileReconcileRun(Base):
    """
    文件存储对账任务表
    """

    __tablename__ = 'sys_file_reconcile_run'
    __table_args__ = (
        UniqueConstraint('lock_name', name='uk_sys_file_reconcile_run_lock'),
        Index('idx_sys_file_reconcile_run_status_time', 'status', 'started_time'),
        {'comment': '文件存储对账任务表'},
    )

    run_id = Column(String(36), primary_key=True, nullable=False, comment='任务ID')
    trigger_type = Column(String(20), nullable=False, comment='触发类型')
    status = Column(String(20), nullable=False, comment='任务状态')
    check_hash = Column(CHAR(1), nullable=False, server_default='0', comment='是否校验文件摘要')
    lock_name = Column(String(32), nullable=True, comment='运行锁名称')
    scanned_file_count = Column(BigInteger, nullable=False, server_default='0', comment='扫描文件记录数')
    scanned_storage_count = Column(BigInteger, nullable=False, server_default='0', comment='扫描物理文件数')
    issue_count = Column(BigInteger, nullable=False, server_default='0', comment='发现异常数')
    new_issue_count = Column(BigInteger, nullable=False, server_default='0', comment='新增或重新出现异常数')
    resolved_issue_count = Column(BigInteger, nullable=False, server_default='0', comment='自动恢复异常数')
    started_by = Column(String(64), nullable=True, server_default="''", comment='发起人')
    started_time = Column(DateTime, nullable=False, default=datetime.now, comment='开始时间')
    finished_time = Column(DateTime, nullable=True, comment='完成时间')
    error_message = Column(Text, nullable=True, comment='失败原因')


class SysFileReconcileIssue(Base):
    """
    文件存储对账异常表
    """

    __tablename__ = 'sys_file_reconcile_issue'
    __table_args__ = (
        UniqueConstraint('issue_key', name='uk_sys_file_reconcile_issue_key'),
        Index('idx_sys_file_reconcile_issue_status_severity', 'status', 'severity'),
        Index('idx_sys_file_reconcile_issue_file', 'file_id'),
        Index('idx_sys_file_reconcile_issue_run', 'last_run_id'),
        {'comment': '文件存储对账异常表'},
    )

    issue_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='异常ID')
    issue_key = Column(String(64), nullable=False, comment='异常唯一标识')
    last_run_id = Column(String(36), nullable=False, comment='最近发现任务ID')
    issue_type = Column(String(32), nullable=False, comment='异常类型')
    severity = Column(String(10), nullable=False, comment='严重级别')
    file_id = Column(String(36), nullable=True, comment='文件ID')
    storage_type = Column(String(20), nullable=True, comment='存储类型')
    access_type = Column(String(20), nullable=True, comment='访问类型')
    expected_root = Column(String(20), nullable=True, comment='预期存储区域')
    expected_key = Column(String(500), nullable=True, comment='预期相对路径')
    actual_root = Column(String(20), nullable=True, comment='实际存储区域')
    actual_key = Column(String(500), nullable=True, comment='实际相对路径')
    expected_size = Column(BigInteger, nullable=True, comment='预期文件大小')
    actual_size = Column(BigInteger, nullable=True, comment='实际文件大小')
    expected_hash = Column(String(64), nullable=True, comment='预期SHA-256')
    actual_hash = Column(String(64), nullable=True, comment='实际SHA-256')
    status = Column(String(20), nullable=False, server_default='open', comment='处理状态')
    detail = Column(Text, nullable=True, comment='异常说明')
    occurrence_count = Column(Integer, nullable=False, server_default='1', comment='发现次数')
    first_seen_time = Column(DateTime, nullable=False, default=datetime.now, comment='首次发现时间')
    last_seen_time = Column(DateTime, nullable=False, default=datetime.now, comment='最近发现时间')
    handle_action = Column(String(32), nullable=True, comment='处理动作')
    handle_reason = Column(String(500), nullable=True, comment='处理原因')
    handled_by = Column(String(64), nullable=True, comment='处理人')
    handled_time = Column(DateTime, nullable=True, comment='处理时间')
    quarantine_key = Column(String(500), nullable=True, comment='隔离区相对路径')
