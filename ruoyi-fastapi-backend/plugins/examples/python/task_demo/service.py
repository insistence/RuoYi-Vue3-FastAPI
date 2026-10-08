from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, update

from plugins.core.sdk import PluginRequestContext
from utils.time_util import TimezoneUtil

from .models import TaskQuery, tasks


def can_write(context: PluginRequestContext) -> bool:
    """
    判断当前用户是否能够修改任务。

    :param context: 宿主提供的请求身份
    :return: 是否具有写权限或管理员通配权限
    """
    return bool({'task_demo:write', '*:*:*'} & context.permissions)


def _task_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    将数据库任务转换为跨语言接口字段及 UTC 时间。

    :param row: 数据库任务记录
    :return: 可序列化的任务对象
    """
    return {
        'id': row['id'],
        'title': row['title'],
        'description': row['description'],
        'status': row['status'],
        'priority': row['priority'],
        'createdAt': TimezoneUtil.format_rfc3339(row['created_at']),
        'updatedAt': TimezoneUtil.format_rfc3339(row['updated_at']),
    }


async def list_tasks(context: PluginRequestContext, query: TaskQuery) -> dict[str, Any]:
    """
    在独立事务中读取筛选后的总数与当前页。

    :param context: 宿主提供的请求身份
    :param query: 已校验的分页与状态参数
    :return: 任务分页结果和当前用户写权限
    """
    filters = [tasks.c.status == query.status] if query.status else []
    async with context.transaction() as transaction:
        db = transaction.transaction_session()
        total = await db.scalar(select(func.count()).select_from(tasks).where(*filters))
        result = await db.execute(
            select(tasks)
            .where(*filters)
            .order_by(tasks.c.created_at.desc(), tasks.c.id.desc())
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        )
        items = [_task_payload(row) for row in result.mappings()]
    return {
        'items': items,
        'total': total,
        'page': query.page,
        'pageSize': query.page_size,
        'canWrite': can_write(context),
    }


async def get_task(context: PluginRequestContext, task_id: str) -> dict[str, Any]:
    """
    在独立事务中读取指定任务。

    :param context: 宿主提供的请求身份
    :param task_id: 已校验的任务标识
    :return: 任务对象；不存在时返回 HTTP 404
    """
    async with context.transaction() as transaction:
        result = await transaction.transaction_session().execute(select(tasks).where(tasks.c.id == task_id))
        row = result.mappings().one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail='任务不存在')
        return _task_payload(row)


async def create_task(context: PluginRequestContext, values: dict[str, Any]) -> dict[str, Any]:
    """
    在独立事务中写入任务，成功提交后返回任务对象。

    :param context: 宿主提供的请求身份
    :param values: 已校验的任务输入
    :return: 新建的任务对象
    """
    now = TimezoneUtil.to_utc_milliseconds(TimezoneUtil.utc_now())
    row = {**values, 'id': uuid4().hex, 'created_at': now, 'updated_at': now}
    async with context.transaction() as transaction:
        await transaction.transaction_session().execute(insert(tasks).values(**row))
        return _task_payload(row)


async def update_task(context: PluginRequestContext, task_id: str, values: dict[str, Any]) -> dict[str, Any]:
    """
    在独立事务中完整更新任务，保留创建时间。

    :param context: 宿主提供的请求身份
    :param task_id: 已校验的任务标识
    :param values: 已校验的任务输入
    :return: 更新后的任务对象；不存在时返回 HTTP 404
    """
    async with context.transaction() as transaction:
        db = transaction.transaction_session()
        result = await db.execute(
            update(tasks).where(tasks.c.id == task_id).values(**values, updated_at=TimezoneUtil.utc_now())
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail='任务不存在')
        result = await db.execute(select(tasks).where(tasks.c.id == task_id))
        return _task_payload(result.mappings().one())


async def delete_task(context: PluginRequestContext, task_id: str) -> dict[str, bool]:
    """
    在独立事务中删除指定任务。

    :param context: 宿主提供的请求身份
    :param task_id: 已校验的任务标识
    :return: 删除确认；不存在时返回 HTTP 404
    """
    async with context.transaction() as transaction:
        result = await transaction.transaction_session().execute(delete(tasks).where(tasks.c.id == task_id))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail='任务不存在')
    return {'deleted': True}
