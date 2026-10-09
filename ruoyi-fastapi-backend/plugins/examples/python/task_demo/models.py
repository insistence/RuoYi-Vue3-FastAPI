from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import CheckConstraint, Column, MetaData, String, Table

from common.types import DbUtcDateTime

MIN_PRINTABLE_CODEPOINT = 32
metadata = MetaData()
tasks = Table(
    'ruoyi_plugin_task_demo',
    metadata,
    Column('id', String(32), primary_key=True),
    Column('title', String(120), nullable=False),
    Column('description', String(500), nullable=False, server_default=''),
    Column('status', String(4), nullable=False, server_default='todo'),
    Column('created_at', DbUtcDateTime, nullable=False),
    Column('updated_at', DbUtcDateTime, nullable=False),
    Column('priority', String(6), nullable=False, server_default='normal'),
    CheckConstraint("status IN ('todo', 'done')", name='ck_task_demo_status'),
    CheckConstraint("priority IN ('normal', 'high')", name='ck_task_demo_priority'),
)


class TaskInput(BaseModel):
    """任务创建和完整更新的输入字段。"""

    model_config = ConfigDict(extra='forbid')

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    description: str = Field(default='', max_length=500)
    status: Literal['todo', 'done'] = 'todo'
    priority: Literal['normal', 'high'] = 'normal'

    @field_validator('title', 'description')
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        """
        拒绝不可显示控制字符，使最大分页仍处于浏览器桥响应上限内。

        :param value: 标题或描述文本
        :return: 已校验的文本
        """
        if any(ord(character) < MIN_PRINTABLE_CODEPOINT and character not in '\n\r\t' for character in value):
            raise ValueError('文本不能包含不可显示的控制字符')
        return value


class TaskQuery(BaseModel):
    """限制单次响应体积，并提供稳定的分页和状态筛选。"""

    model_config = ConfigDict(extra='forbid')

    page: int = Field(default=1, ge=1, le=1_000_000)
    page_size: int = Field(default=10, ge=1, le=20, alias='pageSize')
    status: Literal['todo', 'done'] | None = None


class TaskIdentifier(BaseModel):
    """用于路径参数的插件任务标识。"""

    id: str = Field(pattern=r'^[0-9a-f]{32}$')
