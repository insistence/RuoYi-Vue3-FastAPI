from datetime import datetime


def current_time() -> datetime:
    """
    获取当前项目时间

    统一认证中心暂时沿用项目现有的无时区时间约定。全系统时区统一后，
    再统一调整该辅助函数及相关数据迁移。

    :return: 当前项目时间
    """
    return datetime.now()


def local_datetime(value: datetime | None) -> datetime | None:
    """
    将时间规范化为项目使用的本地无时区时间

    :param value: 可选的 datetime 值
    :return: 本地无时区时间或 None
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def escape_like(value: str) -> str:
    """
    转义 LIKE 查询中的通配符

    :param value: 用户输入的查询文本
    :return: 可安全用于反斜杠转义 LIKE 表达式的文本
    """
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
