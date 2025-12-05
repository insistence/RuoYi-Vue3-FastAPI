from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysMenu(Base):
    """
    菜单权限表
    """

    __tablename__ = 'sys_menu'
    __table_args__ = {'comment': '菜单权限表'}

    menu_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='菜单ID')
    menu_name = Column(String(50), nullable=False, comment='菜单名称')
    parent_id = Column(BigInteger, nullable=True, server_default='0', comment='父菜单ID')
    order_num = Column(Integer, server_default='0', comment='显示顺序')
    path = Column(String(200), nullable=True, server_default="''", comment='路由地址')
    component = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='组件路径',
    )
    query = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='路由参数',
    )
    route_name = Column(String(50), nullable=True, server_default="''", comment='路由名称')
    is_frame = Column(Integer, nullable=True, server_default='1', comment='是否为外链（0是 1否）')
    is_cache = Column(Integer, nullable=True, server_default='0', comment='是否缓存（0缓存 1不缓存）')
    menu_type = Column(CHAR(1), nullable=True, server_default="''", comment='菜单类型（M目录 C菜单 F按钮）')
    visible = Column(CHAR(1), nullable=True, server_default='0', comment='菜单状态（0显示 1隐藏）')
    status = Column(CHAR(1), nullable=True, server_default='0', comment='菜单状态（0正常 1停用）')
    perms = Column(
        String(100),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='权限标识',
    )
    icon = Column(String(100), nullable=True, server_default='#', comment='菜单图标')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(String(500), nullable=True, server_default="''", comment='备注')
