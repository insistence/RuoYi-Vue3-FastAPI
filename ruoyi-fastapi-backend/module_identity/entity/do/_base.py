from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer


def primary_key_type() -> BigInteger:
    """
    返回同时适用于 SQLite 和生产数据库的自增主键类型。
    """
    return BigInteger().with_variant(Integer, 'sqlite')


def current_time() -> datetime:
    """
    返回当前项目时间。

    统一认证中心暂时沿用项目现有的无时区时间约定。
    """
    return datetime.now()


IDENTITY_DATETIME = DateTime()
