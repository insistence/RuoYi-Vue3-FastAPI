from datetime import date, datetime
from typing import Any, ClassVar

from pydantic import field_validator, model_validator
from sqlalchemy import Column
from sqlalchemy.orm import Mapped, declared_attr

from common.types import DbUtcDateTime
from utils.time_util import TimezoneUtil


class CreateTimeMixin:
    """
    创建时间字段Mixin
    """

    __create_time_nullable__ = True
    __create_time_comment__ = '创建时间'

    @declared_attr
    def create_time(cls) -> Mapped[datetime]:  # noqa: N805
        return Column(
            DbUtcDateTime(),
            nullable=cls.__create_time_nullable__,
            default=TimezoneUtil.utc_now,
            comment=cls.__create_time_comment__,
        )


class UpdateTimeMixin:
    """
    更新时间字段Mixin
    """

    __update_time_nullable__ = True
    __update_time_insert_default__ = True
    __update_time_comment__ = '更新时间'

    @declared_attr
    def update_time(cls) -> Mapped[datetime]:  # noqa: N805
        return Column(
            DbUtcDateTime(),
            nullable=cls.__update_time_nullable__,
            default=TimezoneUtil.utc_now if cls.__update_time_insert_default__ else None,
            onupdate=TimezoneUtil.utc_now,
            comment=cls.__update_time_comment__,
        )


class AuditTimeMixin(CreateTimeMixin, UpdateTimeMixin):
    """
    创建时间和更新时间字段Mixin
    """


class DateRangeQueryMixin:
    """
    业务日期范围查询校验混入类
    """

    @field_validator('begin_time', 'end_time', mode='before', check_fields=False)
    @classmethod
    def validate_date_boundary(cls, value: Any) -> str | None:
        """
        校验日期查询边界并保留纯日期字符串协议

        :param value: 待校验的输入值
        :return: YYYY-MM-DD字符串，空值返回None
        """
        if value is None or value == '':
            return None
        return TimezoneUtil.parse_business_date(value).isoformat()

    @model_validator(mode='after')
    def validate_date_range(self) -> 'DateRangeQueryMixin':
        """
        校验业务日期范围顺序和结束日期上限

        :return: 校验通过的查询模型
        """
        begin, end = self.begin_time, self.end_time
        if begin and end and end < begin:
            raise ValueError('结束日期不能早于开始日期')
        if end == date.max.isoformat():
            raise ValueError('结束日期必须早于9999-12-31')
        return self


class InstantRangeQueryMixin:
    """
    RFC 3339时刻范围查询校验混入类
    """

    @field_validator('begin_time', 'end_time', mode='before', check_fields=False)
    @classmethod
    def validate_instant_boundary(cls, value: Any) -> str | None:
        """
        校验精确时刻查询边界并归一化为UTC

        :param value: 待校验的输入值
        :return: 携带UTC偏移的毫秒精度字符串，空值返回None
        """
        if value is None or value == '':
            return None
        return TimezoneUtil.parse_rfc3339(value).isoformat(timespec='milliseconds')

    @model_validator(mode='after')
    def validate_instant_range(self) -> 'InstantRangeQueryMixin':
        """
        按真实时刻校验查询范围顺序

        :return: 校验通过的查询模型
        """
        begin, end = self.begin_time, self.end_time
        if begin and end and TimezoneUtil.parse_rfc3339(end) < TimezoneUtil.parse_rfc3339(begin):
            raise ValueError('结束时间不能早于开始时间')
        return self


class GeneratedTimeRangeQueryMixin:
    """
    代码生成器命名时间范围校验混入类
    """

    time_range_fields: ClassVar[dict[str, str]] = {}

    @model_validator(mode='after')
    def validate_generated_time_ranges(self) -> 'GeneratedTimeRangeQueryMixin':
        """
        校验生成模型中的命名时间范围

        :return: 校验通过的查询模型
        """
        for name, kind in self.time_range_fields.items():
            begin, end = getattr(self, f'begin_{name}'), getattr(self, f'end_{name}')
            if begin is not None and end is not None and end < begin:
                raise ValueError(f'{name}: 结束值不能早于开始值')
            if kind == 'instant' and end == date.max:
                raise ValueError(f'{name}: 结束日期必须早于9999-12-31')
        return self
