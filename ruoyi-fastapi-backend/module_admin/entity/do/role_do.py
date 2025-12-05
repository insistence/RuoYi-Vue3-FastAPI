from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, SmallInteger, String
from sqlalchemy.dialects import mysql

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysRole(Base):
    """
    角色信息表
    """

    __tablename__ = 'sys_role'
    __table_args__ = {'comment': '角色信息表'}

    role_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='角色ID')
    role_name = Column(String(30), nullable=False, comment='角色名称')
    role_key = Column(String(100), nullable=False, comment='角色权限字符串')
    role_sort = Column(Integer, nullable=False, comment='显示顺序')
    data_scope = Column(
        CHAR(1),
        nullable=True,
        server_default='1',
        comment='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）',
    )
    menu_check_strictly = Column(
        mysql.TINYINT(display_width=1) if DataBaseConfig.db_type == 'mysql' else SmallInteger,
        nullable=True,
        server_default='1',
        comment='菜单树选择项是否关联显示',
    )
    dept_check_strictly = Column(
        mysql.TINYINT(display_width=1) if DataBaseConfig.db_type == 'mysql' else SmallInteger,
        nullable=True,
        server_default='1',
        comment='部门树选择项是否关联显示',
    )
    status = Column(CHAR(1), nullable=False, comment='角色状态（0正常 1停用）')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0代表存在 2代表删除）')
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


class SysRoleDept(Base):
    """
    角色和部门关联表
    """

    __tablename__ = 'sys_role_dept'
    __table_args__ = {'comment': '角色和部门关联表'}

    role_id = Column(BigInteger, primary_key=True, nullable=False, comment='角色ID')
    dept_id = Column(BigInteger, primary_key=True, nullable=False, comment='部门ID')


class SysRoleMenu(Base):
    """
    角色和菜单关联表
    """

    __tablename__ = 'sys_role_menu'
    __table_args__ = {'comment': '角色和菜单关联表'}

    role_id = Column(BigInteger, primary_key=True, nullable=False, comment='角色ID')
    menu_id = Column(BigInteger, primary_key=True, nullable=False, comment='菜单ID')
