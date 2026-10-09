from sqlalchemy import CheckConstraint, Column, Index, Integer, String, Text

from common.mixin import AuditTimeMixin, CreateTimeMixin
from common.types import DbUtcDateTime
from config.database import Base


class SysPluginArtifact(CreateTimeMixin, Base):
    """
    已验证不可变制品索引，同一插件版本允许登记多个平台构建。
    """

    __tablename__ = 'sys_plugin_artifact'
    __table_args__ = (
        Index('idx_sys_plugin_artifact_plugin', 'plugin_id', 'version'),
        {'comment': '插件已验证制品表'},
    )

    digest = Column(String(64), primary_key=True, nullable=False, comment='制品SHA256')
    plugin_id = Column(String(64), nullable=False, comment='插件ID')
    version = Column(String(32), nullable=False, comment='制品版本')
    key_id = Column(String(128), nullable=False, comment='签名公钥标识')
    relative_path = Column(String(512), nullable=False, comment='制品存储内不可变相对目录')
    manifest_json = Column(Text, nullable=False, comment='验证后的清单JSON')
    created_by = Column(String(64), nullable=True, comment='导入者')


class SysPluginRelease(AuditTimeMixin, Base):
    """
    代码发布目标及维护准备证据，与数据结构安装版本分别保存。
    """

    __tablename__ = 'sys_plugin_release'
    __table_args__ = (
        CheckConstraint('expected_workers >= 1', name='ck_sys_plugin_release_workers'),
        CheckConstraint(
            "prepare_status in ('idle', 'preparing', 'prepared', 'failed')",
            name='ck_sys_plugin_release_prepare',
        ),
        {'comment': '插件目标发布表'},
    )

    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID')
    target_digest = Column(String(64), nullable=True, comment='目标制品SHA256')
    previous_digest = Column(String(64), nullable=True, comment='上一次目标制品SHA256')
    prepared_digest = Column(String(64), nullable=True, comment='维护准备成功的制品SHA256')
    generation = Column(String(32), nullable=False, comment='目标发布代际UUID')
    expected_workers = Column(Integer, nullable=False, server_default='1', comment='预期宿主worker数量')
    prepare_status = Column(String(16), nullable=False, server_default='idle', comment='维护准备状态')
    prepared_version = Column(String(32), nullable=True, comment='维护确认的数据结构安装版本')
    last_error = Column(Text, nullable=True, comment='维护准备错误')
    create_by = Column(String(64), nullable=True, comment='创建者')
    update_by = Column(String(64), nullable=True, comment='更新者')


class SysPluginWorker(AuditTimeMixin, Base):
    """
    宿主和插件实际运行报告，__runtime__ 行记录宿主存活状态。
    """

    __tablename__ = 'sys_plugin_worker'
    __table_args__ = (
        CheckConstraint("state in ('starting', 'ready', 'failed', 'stopped')", name='ck_sys_plugin_worker_state'),
        Index('idx_sys_plugin_worker_plugin', 'plugin_id', 'heartbeat_time'),
        {'comment': '插件worker加载状态表'},
    )

    worker_id = Column(String(32), primary_key=True, nullable=False, comment='宿主进程UUID')
    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID或__runtime__')
    artifact_digest = Column(String(64), nullable=True, comment='实际加载的制品SHA256')
    version = Column(String(32), nullable=True, comment='实际加载的制品版本')
    generation = Column(String(32), nullable=True, comment='实际加载的发布代际UUID')
    state = Column(String(16), nullable=False, comment='worker状态')
    heartbeat_time = Column(DbUtcDateTime(), nullable=False, comment='UTC心跳时间')
    error = Column(Text, nullable=True, comment='加载或运行错误')
