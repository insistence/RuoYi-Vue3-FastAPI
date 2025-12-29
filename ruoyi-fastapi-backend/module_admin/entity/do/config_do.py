from datetime import datetime

from sqlalchemy import CHAR, Column, DateTime, Integer, String

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysConfig(Base):
    """
    参数配置表
    """

    __tablename__ = 'sys_config'
    __table_args__ = {'comment': '参数配置表'}

    config_id = Column(Integer, primary_key=True, nullable=False, autoincrement=True, comment='参数主键')
    config_name = Column(String(100), nullable=True, server_default="''", comment='参数名称')
    config_key = Column(String(100), nullable=True, server_default="''", comment='参数键名')
    config_value = Column(String(500), nullable=True, server_default="''", comment='参数键值')
    config_type = Column(CHAR(1), nullable=True, server_default='N', comment='系统内置（Y是 N否）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )
