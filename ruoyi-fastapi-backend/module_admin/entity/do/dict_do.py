from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from config.database import Base


class SysDictType(Base):
    """
    字典类型表
    """

    __tablename__ = 'sys_dict_type'

    dict_id = Column(Integer, primary_key=True, autoincrement=True, comment='字典主键')
    dict_name = Column(String(100), nullable=True, default='', comment='字典名称')
    dict_type = Column(String(100), nullable=True, default='', comment='字典类型')
    status = Column(String(1), nullable=True, default='0', comment='状态（0正常 1停用）')
    create_by = Column(String(64), nullable=True, default='', comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, default='', comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(String(500), nullable=True, default=None, comment='备注')

    __table_args__ = (UniqueConstraint('dict_type', name='uq_sys_dict_type_dict_type'),)


class SysDictData(Base):
    """
    字典数据表
    """

    __tablename__ = 'sys_dict_data'

    dict_code = Column(Integer, primary_key=True, autoincrement=True, comment='字典编码')
    dict_sort = Column(Integer, nullable=True, default=0, comment='字典排序')
    dict_label = Column(String(100), nullable=True, default='', comment='字典标签')
    dict_value = Column(String(100), nullable=True, default='', comment='字典键值')
    dict_type = Column(String(100), nullable=True, default='', comment='字典类型')
    css_class = Column(String(100), nullable=True, default=None, comment='样式属性（其他样式扩展）')
    list_class = Column(String(100), nullable=True, default=None, comment='表格回显样式')
    is_default = Column(String(1), nullable=True, default='N', comment='是否默认（Y是 N否）')
    status = Column(String(1), nullable=True, default='0', comment='状态（0正常 1停用）')
    create_by = Column(String(64), nullable=True, default='', comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, default='', comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    remark = Column(String(500), nullable=True, default=None, comment='备注')
