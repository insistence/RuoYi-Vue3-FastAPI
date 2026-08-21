from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, DateTime, Integer, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin, CreateTimeMixin
from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysPlugin(AuditTimeMixin, Base):
    """
    插件信息表。

    字段说明通过 SQLAlchemy Column 的 comment 声明。
    """

    __tablename__ = 'sys_plugin'
    __table_args__ = (
        CheckConstraint("enabled in ('0', '1')", name='ck_sys_plugin_enabled'),
        CheckConstraint(
            "status in ('discovered', 'installed', 'pending_upgrade', 'error')",
            name='ck_sys_plugin_status',
        ),
        {'comment': '插件信息表'},
    )

    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID')
    plugin_name = Column(String(128), nullable=False, comment='插件名称')
    version = Column(String(32), nullable=False, comment='当前源码版本')
    installed_version = Column(String(32), nullable=True, comment='已安装版本')
    enabled = Column(CHAR(1), nullable=False, server_default='0', comment='是否启用（0启用 1停用）')
    status = Column(String(32), nullable=False, server_default='discovered', comment='插件状态')
    source = Column(String(32), nullable=False, server_default='local', comment='插件来源')
    backend_path = Column(String(255), nullable=True, comment='后端插件相对路径')
    frontend_path = Column(String(255), nullable=True, comment='前端插件相对路径')
    last_error = Column(String(1000), nullable=True, comment='最近一次错误信息')
    description = Column(String(500), nullable=True, comment='插件说明')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='备注',
    )


class SysPluginMenu(CreateTimeMixin, Base):
    """
    插件和菜单关联表。

    字段说明通过 SQLAlchemy Column 的 comment 声明。
    """

    __tablename__ = 'sys_plugin_menu'
    __table_args__ = (
        UniqueConstraint('plugin_id', 'menu_key', name='uk_sys_plugin_menu_key'),
        {'comment': '插件和菜单关联表'},
    )

    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID')
    menu_id = Column(BigInteger, primary_key=True, nullable=False, comment='菜单ID')
    menu_key = Column(String(255), nullable=False, comment='插件内菜单自然键')


class SysPluginMigration(AuditTimeMixin, Base):
    """
    插件 migration 执行历史表。

    字段说明通过 SQLAlchemy Column 的 comment 声明。
    """

    __tablename__ = 'sys_plugin_migration'
    __create_time_comment__ = '执行时间'
    __update_time_insert_default__ = False
    __table_args__ = {'comment': '插件 migration 执行历史表'}

    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID')
    migration_path = Column(String(255), primary_key=True, nullable=False, comment='migration 相对路径')
    migration_checksum = Column(String(64), nullable=False, comment='migration 内容校验值')
    version = Column(String(32), nullable=True, comment='执行时插件版本')
    statement_count = Column(Integer, nullable=False, default=0, comment='SQL 语句数量')
    status = Column(String(32), nullable=False, server_default='success', comment='执行状态')
    error_message = Column(Text, nullable=True, comment='失败错误信息')
    attempt_count = Column(Integer, nullable=False, default=0, comment='尝试次数')
    started_time = Column(DateTime, nullable=True, comment='最近开始时间')
    finished_time = Column(DateTime, nullable=True, comment='最近结束时间')


class SysPluginConfig(AuditTimeMixin, Base):
    """
    插件配置表。

    字段说明通过 SQLAlchemy Column 的 comment 声明。
    """

    __tablename__ = 'sys_plugin_config'
    __table_args__ = {'comment': '插件配置表'}

    plugin_id = Column(String(64), primary_key=True, nullable=False, comment='插件ID')
    config_key = Column(String(128), primary_key=True, nullable=False, comment='配置键名')
    config_label = Column(String(128), nullable=True, comment='配置展示名称')
    config_type = Column(String(32), nullable=False, server_default='string', comment='配置值类型')
    config_value = Column(Text, nullable=True, comment='配置值')
    default_value = Column(Text, nullable=True, comment='默认配置值')
    required = Column(CHAR(1), nullable=False, server_default='1', comment='是否必填（0是 1否）')
    secret = Column(CHAR(1), nullable=False, server_default='1', comment='是否敏感（0是 1否）')
    options = Column(Text, nullable=True, comment='配置选项JSON')
    description = Column(String(500), nullable=True, comment='配置说明')


class SysPluginOperationLog(CreateTimeMixin, Base):
    """
    插件批量操作审计日志表。

    字段说明通过 SQLAlchemy Column 的 comment 声明。
    """

    __tablename__ = 'sys_plugin_operation_log'
    __table_args__ = {'comment': '插件批量操作审计日志表'}

    operation_id = Column(
        BigInteger().with_variant(Integer, 'sqlite'),
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment='操作日志ID',
    )
    operation = Column(String(32), nullable=False, comment='操作类型')
    plugin_ids = Column(Text, nullable=True, comment='目标插件ID JSON')
    dry_run = Column(CHAR(1), nullable=False, server_default='1', comment='是否预演（0是 1否）')
    continue_on_error = Column(CHAR(1), nullable=False, server_default='1', comment='失败后是否继续（0是 1否）')
    status = Column(String(32), nullable=False, comment='执行状态')
    summary = Column(Text, nullable=True, comment='执行汇总JSON')
    result = Column(Text, nullable=True, comment='完整执行结果JSON')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='备注',
    )
