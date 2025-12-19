from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String

from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class SysPost(Base):
    """
    岗位信息表
    """

    __tablename__ = 'sys_post'
    __table_args__ = {'comment': '岗位信息表'}

    post_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='岗位ID')
    post_code = Column(String(64), nullable=False, comment='岗位编码')
    post_name = Column(String(50), nullable=False, comment='岗位名称')
    post_sort = Column(Integer, nullable=False, comment='显示顺序')
    status = Column(CHAR(1), nullable=False, comment='状态（0正常 1停用）')
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
