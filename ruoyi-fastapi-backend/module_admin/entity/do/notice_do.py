from datetime import datetime

from sqlalchemy import CHAR, Column, DateTime, Integer, LargeBinary, String
from sqlalchemy.dialects import mysql

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysNotice(Base):
    """
    通知公告表
    """

    __tablename__ = 'sys_notice'
    __table_args__ = {'comment': '通知公告表'}

    notice_id = Column(Integer, primary_key=True, nullable=False, autoincrement=True, comment='公告ID')
    notice_title = Column(String(50), nullable=False, comment='公告标题')
    notice_type = Column(CHAR(1), nullable=False, comment='公告类型（1通知 2公告）')
    notice_content = Column(
        mysql.LONGBLOB if DataBaseConfig.db_type == 'mysql' else LargeBinary,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='公告内容',
    )
    status = Column(CHAR(1), nullable=True, server_default='0', comment='公告状态（0正常 1关闭）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, comment='创建时间', default=datetime.now())
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, comment='更新时间', default=datetime.now())
    remark = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )
