from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import Mapped, declared_attr


class CreateTimeMixin:
    """
    创建时间字段Mixin
    """

    __create_time_nullable__ = True
    __create_time_comment__ = '创建时间'

    @declared_attr
    def create_time(cls) -> Mapped[datetime]:  # noqa: N805
        return Column(
            DateTime,
            nullable=cls.__create_time_nullable__,
            default=datetime.now,
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
            DateTime,
            nullable=cls.__update_time_nullable__,
            default=datetime.now if cls.__update_time_insert_default__ else None,
            onupdate=datetime.now,
            comment=cls.__update_time_comment__,
        )


class AuditTimeMixin(CreateTimeMixin, UpdateTimeMixin):
    """
    创建时间和更新时间字段Mixin
    """
