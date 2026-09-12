import re
from calendar import monthrange
from datetime import datetime, timezone

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.cron.expressions import AllExpression
from apscheduler.triggers.cron.fields import DayOfMonthField

from utils.time_util import TimezoneUtil


class NearestWeekdayExpression(AllExpression):
    """
    支持Quartz最近工作日语法的日期表达式
    """

    SATURDAY = 5
    SUNDAY = 6

    value_re = re.compile(r'(?P<day>[1-9]|[12]\d|3[01])W$', re.IGNORECASE)

    def __init__(self, day: str) -> None:
        """
        初始化最近工作日表达式

        :param day: W前指定的日序号，取值为1至31
        """
        super().__init__(None)
        self.day = int(day)

    def get_next_value(self, date: datetime, field: DayOfMonthField) -> int | None:
        """
        计算当前月份中满足条件的最近工作日

        :param date: 当前查找的日期
        :param field: APScheduler传入的日期字段
        :return: 符合条件的日序号，当月无候选时返回None
        """
        last = monthrange(date.year, date.month)[1]
        if self.day > last:
            return None
        target = date.replace(day=self.day)
        day = self.day
        if target.weekday() == self.SATURDAY:
            day += 2 if day == 1 else -1
        elif target.weekday() == self.SUNDAY:
            day += -2 if day == last else 1
        return day if day >= date.day else None

    def __str__(self) -> str:
        """
        返回Quartz最近工作日表达式

        :return: 日序号和W组成的表达式
        """
        return f'{self.day}W'


class QuartzDayOfMonthField(DayOfMonthField):
    """
    注册最近工作日表达式的Quartz日期字段
    """

    COMPILERS = [NearestWeekdayExpression, *DayOfMonthField.COMPILERS]


class MyCronTrigger(CronTrigger):
    """
    统一任务注册和预览行为的Quartz触发器
    """

    CRON_FIELDS_WITH_YEAR = 7

    FIELDS_MAP = {**CronTrigger.FIELDS_MAP, 'day': QuartzDayOfMonthField}
    WEEKDAYS = ('sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat')
    NUMERIC_FIELD = re.compile(r'(?:\*|\d+(?:-\d+)?)(?:/\d+)?(?:,(?:\*|\d+(?:-\d+)?)(?:/\d+)?)*')

    def __getstate__(self) -> dict:
        """
        序列化Cron规则及业务分组快照

        :return: 触发器持久化状态
        """
        return {**super().__getstate__(), 'task_job_group': getattr(self, 'task_job_group', 'default')}

    def __setstate__(self, state: dict) -> None:
        """
        恢复Cron规则及业务分组快照

        :param state: 触发器持久化状态
        :return: None
        """
        super().__setstate__(state)
        self.task_job_group = state.get('task_job_group', 'default')

    def get_next_fire_time(self, previous_fire_time: datetime | None, now: datetime) -> datetime | None:
        """
        计算下一次有效执行时刻

        夏令时跳转中不存在的当地时间跳过，重复时间仅取第一次。

        :param previous_fire_time: 上一次执行时刻，首次查找时为None
        :param now: 本次查找的起算时刻
        :return: 下一次执行时刻，无未来结果时返回None
        """
        candidate = super().get_next_fire_time(previous_fire_time, now)
        while candidate is not None:
            normalized = candidate.astimezone(timezone.utc).astimezone(self.timezone)
            if candidate.isoformat() == normalized.isoformat() and candidate.fold == 0:
                return candidate
            candidate = super().get_next_fire_time(candidate, candidate)
        return None

    @classmethod
    def from_crontab(cls, expr: str, timezone: str) -> 'MyCronTrigger':
        """
        根据Quartz表达式和任务时区创建触发器

        :param expr: 包含6或7个字段的Quartz表达式
        :param timezone: 任务IANA时区名称
        :return: 配置完成的Cron触发器
        """
        values = expr.split()
        if len(values) not in (6, 7):
            raise ValueError('Cron 表达式必须包含 6 或 7 个字段')
        second, minute, hour, day, month, weekday = values[:6]
        year = values[6] if len(values) == cls.CRON_FIELDS_WITH_YEAR else '*'
        for value in (second, minute, hour, month, year):
            if not cls.NUMERIC_FIELD.fullmatch(value):
                raise ValueError(f'无效的 Cron 字段：{value}')
        day_of_week = '*'
        if match := re.fullmatch(r'([1-7])#([1-5])', weekday):
            if day not in ('?', '*'):
                raise ValueError('使用周序号时，日字段必须为 ? 或 *')
            position = ('1st', '2nd', '3rd', '4th', '5th')[int(match[2]) - 1]
            day = f'{position} {cls.WEEKDAYS[int(match[1]) - 1]}'
        elif match := re.fullmatch(r'([1-7])L', weekday):
            if day not in ('?', '*'):
                raise ValueError('使用最后一个星期时，日字段必须为 ? 或 *')
            day = f'last {cls.WEEKDAYS[int(match[1]) - 1]}'
        else:
            if weekday not in ('?', '*'):
                day_of_week = cls._weekday_names(weekday)
            if day == '?':
                day = '*'
            elif day == 'L':
                day = 'last'
            elif not (re.fullmatch(r'([1-9]|[12]\d|3[01])W', day) or cls.NUMERIC_FIELD.fullmatch(day)):
                raise ValueError(f'无效的 Cron 日字段：{day}')
        return cls(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            year=year,
            timezone=TimezoneUtil.get_timezone(timezone),
        )

    @classmethod
    def _weekday_names(cls, expression: str) -> str:
        """
        将Quartz星期编号转换为APScheduler星期名称

        Quartz的1表示星期日；APScheduler的数字0表示星期一。

        :param expression: Quartz周字段表达式
        :return: 逗号分隔的星期名称
        """
        weekdays = set()
        for part in expression.split(','):
            match = re.fullmatch(r'([1-7])(?:-([1-7]))?', part)
            if not match:
                raise ValueError(f'无效的 Cron 周字段：{expression}')
            first, last = int(match[1]), int(match[2] or match[1])
            if first > last:
                raise ValueError('Cron 周范围的结束值不能早于开始值')
            weekdays.update(range(first, last + 1))
        return ','.join(cls.WEEKDAYS[day - 1] for day in sorted(weekdays))


class CronUtil:
    """
    Cron表达式工具类
    """

    MAX_PREVIEW_COUNT = 20
    ONE_YEAR_LENGTH = 4
    MAX_YEAR = 2099
    CRON_EXPRESSION_LENGTH_MIN = 6
    CRON_EXPRESSION_LENGTH_MAX = 7

    @classmethod
    def __valid_range(cls, search_str: str, start_range: int, end_range: int) -> bool:
        match = re.match(r'^(\d+)-(\d+)$', search_str)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return start_range <= start < end <= end_range
        return False

    @classmethod
    def __valid_sum(
        cls, search_str: str, start_range_a: int, start_range_b: int, end_range_a: int, end_range_b: int, sum_range: int
    ) -> bool:
        match = re.match(r'^(\d+)/(\d+)$', search_str)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return (
                start_range_a <= start <= start_range_b
                and end_range_a <= end <= end_range_b
                and start + end <= sum_range
            )
        return False

    @classmethod
    def validate_second_or_minute(cls, second_or_minute: str) -> bool:
        """
        校验秒或分钟值是否正确

        :param second_or_minute: 秒或分钟值
        :return: 校验结果
        """
        return bool(
            second_or_minute == '*'
            or ('-' in second_or_minute and cls.__valid_range(second_or_minute, 0, 59))
            or ('/' in second_or_minute and cls.__valid_sum(second_or_minute, 0, 58, 1, 59, 59))
            or re.match(r'^(?:[0-5]?\d|59)(?:,[0-5]?\d|59)*$', second_or_minute)
        )

    @classmethod
    def validate_hour(cls, hour: str) -> bool:
        """
        校验小时值是否正确

        :param hour: 小时值
        :return: 校验结果
        """
        return bool(
            hour == '*'
            or ('-' in hour and cls.__valid_range(hour, 0, 23))
            or ('/' in hour and cls.__valid_sum(hour, 0, 22, 1, 23, 23))
            or re.match(r'^(?:0|[1-9]|1\d|2[0-3])(?:,(?:0|[1-9]|1\d|2[0-3]))*$', hour)
        )

    @classmethod
    def validate_day(cls, day: str) -> bool:
        """
        校验日值是否正确

        :param day: 日值
        :return: 校验结果
        """
        return bool(
            day in ['*', '?', 'L']
            or ('-' in day and cls.__valid_range(day, 1, 31))
            or ('/' in day and cls.__valid_sum(day, 1, 30, 1, 30, 31))
            or ('W' in day and re.match(r'^(?:[1-9]|1\d|2\d|3[01])W$', day))
            or re.match(r'^(?:0|[1-9]|1\d|2[0-9]|3[0-1])(?:,(?:0|[1-9]|1\d|2[0-9]|3[0-1]))*$', day)
        )

    @classmethod
    def validate_month(cls, month: str) -> bool:
        """
        校验月值是否正确

        :param month: 月值
        :return: 校验结果
        """
        return bool(
            month == '*'
            or ('-' in month and cls.__valid_range(month, 1, 12))
            or ('/' in month and cls.__valid_sum(month, 1, 11, 1, 11, 12))
            or re.match(r'^(?:0|[1-9]|1[0-2])(?:,(?:0|[1-9]|1[0-2]))*$', month)
        )

    @classmethod
    def validate_week(cls, week: str) -> bool:
        """
        校验周值是否正确

        :param week: 周值
        :return: 校验结果
        """
        return bool(
            week in ['*', '?']
            or ('-' in week and cls.__valid_range(week, 1, 7))
            or ('#' in week and re.match(r'^[1-7]#[1-4]$', week))
            or ('L' in week and re.match(r'^[1-7]L$', week))
            or re.match(r'^[1-7](?:(,[1-7]))*$', week)
        )

    @classmethod
    def validate_year(cls, year: str, timezone: str) -> bool:
        """
        校验年值是否正确

        :param year: 年值
        :param timezone: 任务IANA时区名称，用于确定当前业务年份
        :return: 校验结果
        """
        current_year = TimezoneUtil.to_business_time(TimezoneUtil.utc_now(), timezone).year
        future_years = [current_year + i for i in range(9)]
        return bool(
            year == '*'
            or ('-' in year and cls.__valid_range(year, current_year, 2099))
            or ('/' in year and cls.__valid_sum(year, current_year, 2098, 1, 2099 - current_year, 2099))
            or ('#' in year and re.match(r'^[1-7]#[1-4]$', year))
            or ('L' in year and re.match(r'^[1-7]L$', year))
            or (
                (len(year) == cls.ONE_YEAR_LENGTH or ',' in year)
                and all(
                    int(item) in future_years and current_year <= int(item) <= cls.MAX_YEAR for item in year.split(',')
                )
            )
        )

    @classmethod
    def validate_cron_expression(cls, cron_expression: str, timezone: str) -> bool:
        """
        校验Cron表达式是否正确

        :param cron_expression: Cron表达式
        :param timezone: 任务IANA时区名称
        :return: 校验结果
        """
        try:
            MyCronTrigger.from_crontab(cron_expression, timezone)
        except (ValueError, TypeError, AttributeError):
            return False
        return True

    @classmethod
    def next_run_times(
        cls, cron_expression: str, time_zone: str, start_time: datetime, count: int = 5
    ) -> list[datetime]:
        """
        从指定时刻开始枚举未来UTC执行时刻

        :param cron_expression: Quartz表达式
        :param time_zone: 任务IANA时区名称
        :param start_time: 查找起算时刻，包含该时刻
        :param count: 最多返回的执行时刻数量，取值为1至20
        :return: 按时间排序的UTC时刻列表，无未来结果时返回空列表
        """
        if not 1 <= count <= cls.MAX_PREVIEW_COUNT:
            raise ValueError('预览数量必须在 1 至 20 之间')
        trigger = MyCronTrigger.from_crontab(cron_expression, time_zone)
        now = TimezoneUtil.to_utc(start_time)
        previous = None
        result = []
        for _ in range(count):
            candidate = trigger.get_next_fire_time(previous, now)
            if candidate is None:
                break
            result.append(TimezoneUtil.to_utc(candidate))
            previous = now = candidate
        return result
