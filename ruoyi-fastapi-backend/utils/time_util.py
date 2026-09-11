import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from exceptions.exception import ServiceWarning


class TimezoneUtil:
    """
    时区工具类
    """

    RFC3339_PATTERN = re.compile(
        r'\d{4}-\d{2}-\d{2}[Tt](?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d'
        r'(?:\.\d+)?(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)'
    )
    ISO_DATE_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}')

    @classmethod
    def get_timezone(cls, timezone_name: str) -> ZoneInfo:
        """
        获取并缓存有效的IANA时区对象

        :param timezone_name: IANA时区名称
        :return: 时区对象
        """
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            raise ValueError('IANA时区不能为空')
        return cls._load_timezone(timezone_name.strip())

    @classmethod
    @cache
    def _load_timezone(cls, timezone_name: str) -> ZoneInfo:
        """
        加载时区对象，仅缓存校验成功的名称

        :param timezone_name: IANA时区名称
        :return: 时区对象
        """
        try:
            return ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f'不是有效的IANA时区：{timezone_name}') from None

    @classmethod
    def validate_timezone_name(cls, timezone_name: str) -> str:
        """
        校验并返回规范化的IANA时区名称

        :param timezone_name: IANA时区名称
        :return: 去除首尾空白后的有效时区名称
        """
        return cls.get_timezone(timezone_name).key

    @classmethod
    def validate_timezone_preference(cls, value: str) -> str:
        """
        校验账号时区偏好，auto表示由客户端提供设备时区

        :param value: auto或IANA时区名称
        :return: 校验后的账号偏好
        """
        return 'auto' if value == 'auto' else cls.validate_timezone_name(value)

    @classmethod
    def get_request_timezone(cls) -> str:
        """
        获取当前请求的显示时区，未指定时回退到业务时区

        :return: 当前请求使用的IANA时区名称
        """
        from common.context import RequestContext  # noqa: PLC0415

        return RequestContext.get_current_timezone() or cls.get_app_timezone().key

    @classmethod
    def parse_business_date(cls, value: str | date) -> date:
        """
        解析纯业务日期

        仅接受date对象或YYYY-MM-DD字符串，拒绝日期时间和数字。

        :param value: 待校验的输入值
        :return: 不含时间和时区的日期对象
        """
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str) and cls.ISO_DATE_PATTERN.fullmatch(value):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise ValueError('业务日期必须是有效的YYYY-MM-DD')

    @classmethod
    def parse_rfc3339(cls, value: str | datetime) -> datetime:
        """
        解析带时区的RFC 3339时刻并归一化为UTC毫秒

        兼容Python 3.10的ISO格式解析，不接受无时区的日期时间。

        :param value: 待校验的输入值
        :return: 携带UTC时区的毫秒精度时刻
        """
        if isinstance(value, datetime):
            return cls.to_utc_milliseconds(value)
        if isinstance(value, str) and cls.RFC3339_PATTERN.fullmatch(value):
            try:
                return cls.to_utc_milliseconds(datetime.fromisoformat(value.upper().replace('Z', '+00:00')))
            except ValueError:
                pass
        raise ValueError('时刻必须是有效的带offset的RFC 3339字符串或aware datetime')

    @classmethod
    def get_app_timezone(cls) -> ZoneInfo:
        """
        获取应用配置的业务时区

        :return: APP_TIMEZONE对应的时区对象
        """
        # 配置校验也会调用本模块，延迟导入避免循环依赖。
        from config.env import AppConfig  # noqa: PLC0415

        return cls.get_timezone(AppConfig.app_timezone)

    @classmethod
    def utc_now(cls) -> datetime:
        """
        获取当前UTC时刻

        :return: 携带UTC时区的当前时刻
        """
        return datetime.now(timezone.utc)

    @classmethod
    def ensure_aware(cls, value: datetime, *, field_name: str = 'datetime') -> datetime:
        """
        校验时刻是否携带有效时区信息

        :param value: 待校验时刻
        :param field_name: 校验错误中使用的字段名称
        :return: 校验通过的原时刻
        """
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f'{field_name}必须携带时区信息')
        return value

    @classmethod
    def to_utc(cls, value: datetime) -> datetime:
        """
        将带时区的时刻转换为UTC

        :param value: 携带时区信息的时刻
        :return: 携带UTC时区的时刻
        """
        return cls.ensure_aware(value).astimezone(timezone.utc)

    @classmethod
    def to_utc_milliseconds(cls, value: datetime) -> datetime:
        """
        将带时区的时刻转换为毫秒精度UTC

        :param value: 携带时区信息的时刻
        :return: 截断微秒尾数后的UTC时刻
        """
        utc_value = cls.to_utc(value)
        return utc_value.replace(microsecond=(utc_value.microsecond // 1000) * 1000)

    @classmethod
    def to_business_time(cls, value: datetime, timezone_name: str | None = None) -> datetime:
        """
        将时刻转换为指定业务时区

        :param value: 携带时区信息的时刻
        :param timezone_name: 目标IANA时区名称，省略时使用APP_TIMEZONE
        :return: 目标业务时区下的时刻
        """
        target_timezone = cls.get_timezone(timezone_name) if timezone_name else cls.get_app_timezone()
        return cls.ensure_aware(value).astimezone(target_timezone)

    @classmethod
    def local_date_range_to_utc(
        cls,
        begin_date: date,
        end_date: date,
        timezone_name: str | None = None,
    ) -> tuple[datetime, datetime]:
        """
        将包含首尾日期的业务日期范围转换为UTC半开区间

        :param begin_date: 起始业务日期
        :param end_date: 结束业务日期，包含当天
        :param timezone_name: 业务IANA时区名称，省略时使用APP_TIMEZONE
        :return: UTC半开区间[start, end)
        """
        if end_date < begin_date:
            raise ValueError('结束日期不能早于开始日期')
        business_timezone = cls.get_timezone(timezone_name) if timezone_name else cls.get_app_timezone()
        start = datetime.combine(begin_date, time.min, tzinfo=business_timezone)
        end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=business_timezone)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    @classmethod
    def local_date_strings_to_utc(
        cls,
        begin_date: str | date | None,
        end_date: str | date | None,
        timezone_name: str | None = None,
    ) -> tuple[datetime | None, datetime | None] | None:
        """
        将可选业务日期边界转换为UTC半开区间

        :param begin_date: 起始业务日期，为空时不限制下界
        :param end_date: 结束业务日期，包含当天，为空时不限制上界
        :param timezone_name: 业务IANA时区名称，省略时使用APP_TIMEZONE
        :return: UTC起止边界；缺失的边界为None，两边均缺失时返回None
        """
        if not begin_date and not end_date:
            return None
        begin = cls.parse_business_date(begin_date) if begin_date else None
        end = cls.parse_business_date(end_date) if end_date else None
        if begin and end and end < begin:
            raise ValueError('结束日期不能早于开始日期')
        if end == date.max:
            raise ValueError('结束日期必须早于9999-12-31')
        business_timezone = cls.get_timezone(timezone_name) if timezone_name else cls.get_app_timezone()
        start = datetime.combine(begin, time.min, tzinfo=business_timezone).astimezone(timezone.utc) if begin else None
        stop = (
            datetime.combine(end + timedelta(days=1), time.min, tzinfo=business_timezone).astimezone(timezone.utc)
            if end
            else None
        )
        return start, stop

    @classmethod
    def rfc3339_range_to_utc(
        cls,
        begin_time: str | datetime | None,
        end_time: str | datetime | None,
    ) -> tuple[datetime | None, datetime | None] | None:
        """
        解析可选的RFC 3339时刻范围

        :param begin_time: 起始时刻，为空时不限制下界
        :param end_time: 结束时刻，为空时不限制上界
        :return: UTC起止时刻；缺失的边界为None，两边均缺失时返回None
        """
        if not begin_time and not end_time:
            return None
        start = cls.parse_rfc3339(begin_time) if begin_time else None
        end = cls.parse_rfc3339(end_time) if end_time else None
        if start and end and end < start:
            raise ValueError('结束时间不能早于开始时间')
        return start, end

    @classmethod
    def format_rfc3339(cls, value: datetime) -> str:
        """
        将时刻格式化为固定毫秒精度的UTC字符串

        :param value: 携带时区信息的时刻
        :return: 以Z结尾的RFC 3339字符串
        """
        utc_value = cls.to_utc(value)
        return utc_value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


@dataclass(frozen=True)
class TimeSemantics:
    """
    时间字段在Python、ORM、API和页面控件间的类型映射
    """

    kind: str
    python_type: str
    sqlalchemy_type: str
    vo_type: str
    control: str


class GenTimeUtil:
    """
    代码生成器时间字段工具类
    """

    DATE = TimeSemantics(
        kind='date', python_type='date', sqlalchemy_type='Date', vo_type='BusinessDate', control='date'
    )
    TIME = TimeSemantics(
        kind='time', python_type='time', sqlalchemy_type='Time', vo_type='BusinessTime', control='time'
    )
    INSTANT = TimeSemantics(
        kind='instant',
        python_type='datetime',
        sqlalchemy_type='DbUtcDateTime',
        vo_type='ApiUtcDateTime',
        control='datetime',
    )

    @classmethod
    def normalize_db_type(cls, column_type: str) -> str:
        """
        规范化数据库类型名称，保留PostgreSQL时区限定

        :param column_type: 包含精度等修饰的数据库列类型
        :return: 去除精度和unsigned修饰后的类型名称
        """
        normalized_type = re.sub(r'\([^)]*\)', '', column_type.lower()).removesuffix(' unsigned')
        return ' '.join(normalized_type.split())

    @classmethod
    def get_time_semantics(cls, column_type: str, db_type: str) -> TimeSemantics | None:
        """
        根据数据库列类型获取时间字段语义

        :param column_type: 数据库列类型
        :param db_type: 数据源类型
        :return: 时间字段的类型映射，非时间字段返回None
        """
        data_type = cls.normalize_db_type(column_type)
        if data_type == 'date':
            return cls.DATE
        if data_type in {'time', 'time without time zone'}:
            return cls.TIME
        if db_type == 'mysql' and data_type in {'datetime', 'timestamp'}:
            return cls.INSTANT
        if db_type == 'postgresql':
            if data_type in {'timestamptz', 'timestamp with time zone'}:
                return cls.INSTANT
            if data_type in {'timestamp', 'timestamp without time zone'}:
                raise ServiceWarning(
                    message='PostgreSQL 无时区 timestamp 含义不明确，请将真实时刻列改为 TIMESTAMP(3) WITH TIME ZONE 后重新导入生成配置'
                )
            if data_type in {'timetz', 'time with time zone'}:
                raise ServiceWarning(
                    message='带时区的 time 不能作为一天内时间生成，请使用 TIME WITHOUT TIME ZONE；真实时刻请使用 TIMESTAMP(3) WITH TIME ZONE'
                )
        return None

    @classmethod
    def validate_time_control(cls, column_type: str, db_type: str, control: str | None) -> None:
        """
        校验MySQL TIME字段是否已确认表示一天内时间

        :param column_type: 数据库列类型
        :param db_type: 数据源类型
        :param control: 代码生成器配置的显示类型
        """
        if db_type == 'mysql' and cls.normalize_db_type(column_type) == 'time' and control != 'time':
            raise ServiceWarning(
                message='MySQL TIME 也可表示时长。确认字段表示一天内时间后，将显示类型设为“时间（一天内）”；时长请使用明确单位的数值列后重新导入'
            )
