from sqlalchemy import CHAR, BigInteger, Column, Float, Integer, String

from common.mixin import AuditTimeMixin
from config.database import Base
from config.env import DataBaseConfig
from utils.common_util import SqlalchemyUtil


class AiModels(AuditTimeMixin, Base):
    """
    AI模型表
    """

    __tablename__ = 'ai_models'
    __table_args__ = {'comment': 'AI模型表'}

    model_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='模型主键')
    model_code = Column(String(100), nullable=False, comment='模型编码')
    model_name = Column(
        String(100),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='模型名称',
    )
    provider = Column(String(50), nullable=False, comment='提供商')
    model_sort = Column(Integer, nullable=False, comment='显示顺序')
    api_key = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='API Key',
    )
    base_url = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='Base URL',
    )
    model_type = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='模型类型',
    )
    max_tokens = Column(Integer, nullable=True, comment='最大输出token')
    temperature = Column(Float, nullable=True, comment='默认温度')
    support_reasoning = Column(CHAR(1), server_default='N', comment='是否支持推理')
    support_images = Column(CHAR(1), server_default='N', comment='是否支持图片')
    status = Column(CHAR(1), server_default='0', comment='模型状态')
    user_id = Column(BigInteger, nullable=True, comment='用户ID')
    dept_id = Column(BigInteger, nullable=True, comment='部门ID')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.default_source.db_type),
        comment='备注',
    )
