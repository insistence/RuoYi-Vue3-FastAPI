from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysDept(Base):
    """
    部门表
    """

    __tablename__ = 'sys_dept'
    __table_args__ = {'comment': '部门表'}

    dept_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='部门id')
    parent_id = Column(BigInteger, server_default='0', comment='父部门id')
    ancestors = Column(String(50), nullable=True, server_default="''", comment='祖级列表')
    dept_name = Column(String(30), nullable=True, server_default="''", comment='部门名称')
    order_num = Column(Integer, server_default='0', comment='显示顺序')
    leader = Column(
        String(20),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='负责人',
    )
    phone = Column(
        String(11),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='联系电话',
    )
    email = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='邮箱',
    )
    status = Column(CHAR(1), nullable=True, server_default='0', comment='部门状态（0正常 1停用）')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0代表存在 2代表删除）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
