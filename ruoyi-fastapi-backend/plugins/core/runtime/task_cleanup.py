import asyncio
import math
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

CANCEL_TIMEOUT_SECONDS = 5.0
_unfinished_tasks: set[asyncio.Task[Any]] = set()


def pending_plugin_tasks(tasks: Iterable[asyncio.Task[Any]] | None = None) -> frozenset[asyncio.Task[Any]]:
    """
    读取取消后仍未退出的宿主任务，可限制到已知插件任务，避免推测任务归属。

    :param tasks: 可选的插件所属任务集合，省略时读取当前 worker 的通用回收集合
    :return: 尚未退出的任务只读快照，不包含已完成任务且不修改回收状态
    """
    selected = _unfinished_tasks if tasks is None else _unfinished_tasks.intersection(tasks)
    return frozenset(task for task in selected if not task.done())


def _finish_task(task: asyncio.Task[Any]) -> None:
    """
    回收延迟退出的任务及其异常，避免丢失后台任务引用。

    :param task: 已经结束的插件任务
    :return: None
    """
    _unfinished_tasks.discard(task)
    with suppress(asyncio.CancelledError, Exception):
        task.result()


async def cancel_plugin_tasks(
    tasks: Iterable[asyncio.Task[Any]], *, timeout: float = CANCEL_TIMEOUT_SECONDS
) -> set[asyncio.Task[Any]]:
    """
    并发取消并限时等待；等待者被取消时也保留未退出任务。

    :param tasks: 本次需要回收的任务，不取消调用者自身
    :param timeout: 整批任务允许的取消等待秒数
    :return: 等待结束后仍未退出的任务
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('任务取消等待时间必须大于零')
    selected = set(tasks) - {asyncio.current_task()}
    for task in selected:
        if not task.done():
            task.cancel()
    try:
        if selected:
            await asyncio.wait(selected, timeout=timeout)
    finally:
        for task in selected:
            if task.done():
                _finish_task(task)
            elif task not in _unfinished_tasks:
                _unfinished_tasks.add(task)
                task.add_done_callback(_finish_task)
    return {task for task in selected if not task.done()}
