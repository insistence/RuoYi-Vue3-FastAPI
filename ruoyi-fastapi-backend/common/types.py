import re
from datetime import date, datetime, time, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, AwareDatetime, BeforeValidator, PlainSerializer
from sqlalchemy import DateTime
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

from utils.time_util import TimezoneUtil


def validate_aware_datetime_input(value: Any) -> datetime:
    """
    校验API输入的真实时刻

    :param value: 待校验的输入值
    :return: 携带UTC时区的毫秒精度时刻
    """
    return TimezoneUtil.parse_rfc3339(value)


ApiUtcDateTime = Annotated[
    AwareDatetime,
    BeforeValidator(validate_aware_datetime_input),
    AfterValidator(TimezoneUtil.to_utc_milliseconds),
    PlainSerializer(TimezoneUtil.format_rfc3339, return_type=str, when_used='json'),
]


def validate_business_time_input(value: Any) -> time:
    """
    校验不含日期和时区的一天内时间

    仅接受time对象或HH:mm:ss格式字符串，可含小数秒，不接受时间戳或持续时长。

    :param value: 待校验的输入值
    :return: 一天内的时间对象
    """
    if isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?', value):
        value = time.fromisoformat(value)
    if not isinstance(value, time) or value.tzinfo is not None:
        raise ValueError('一天内时间必须为 HH:mm:ss，可含小数秒，不能带时区')
    return value


BusinessDate = Annotated[date, BeforeValidator(TimezoneUtil.parse_business_date)]
BusinessTime = Annotated[time, BeforeValidator(validate_business_time_input)]


class DbUtcDateTime(TypeDecorator[datetime]):
    """
    SQLAlchemy数据库列的UTC时刻类型。

    PostgreSQL使用带时区时间戳；MySQL和SQLite在驱动边界保存naive UTC，
    应用层始终只接收和返回aware UTC datetime。
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        """
        获取当前数据库对应的毫秒精度时间类型

        :param dialect: SQLAlchemy数据库方言
        :return: 数据库实际使用的时间类型
        """
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(TIMESTAMP(timezone=True, precision=3))
        if dialect.name == 'mysql':
            return dialect.type_descriptor(DATETIME(fsp=3))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """
        在写入边界统一UTC时区和毫秒精度

        :param value: 待写入时刻
        :param dialect: SQLAlchemy数据库方言
        :return: 符合驱动要求的UTC时刻，空值返回None
        """
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('DbUtcDateTime只接受携带时区信息的datetime')
        utc_value = TimezoneUtil.to_utc_milliseconds(value)
        if dialect.name in {'mysql', 'sqlite'}:
            return utc_value.replace(tzinfo=None)
        return utc_value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """
        将数据库读出的时间恢复为带时区UTC时刻

        :param value: 驱动返回的时间值
        :param dialect: SQLAlchemy数据库方言
        :return: 携带UTC时区的毫秒精度时刻，空值返回None
        """
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        return TimezoneUtil.to_utc_milliseconds(value)
