import asyncio

import pytest

from plugins.core.runtime.task_cleanup import _unfinished_tasks, cancel_plugin_tasks


@pytest.mark.asyncio
async def test_batch_cancellation_releases_cooperative_tasks_and_ignores_caller() -> None:
    stopped = []

    async def work() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    tasks = {asyncio.create_task(work()) for _ in range(3)}
    await asyncio.sleep(0)
    assert await cancel_plugin_tasks(tasks | {asyncio.current_task()}, timeout=0.01) == set()
    assert len(stopped) == len(tasks)
    assert all(task.cancelled() for task in tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_waiter', [False, True])
async def test_uncooperative_task_is_retained_even_when_waiter_is_cancelled(cancel_waiter: bool) -> None:
    opened, interrupted, release = (asyncio.Event() for _ in range(3))

    async def work() -> None:
        opened.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            interrupted.set()
            await release.wait()
            raise ValueError('late failure') from None

    child = asyncio.create_task(work())
    await opened.wait()
    waiter = asyncio.create_task(cancel_plugin_tasks({child}, timeout=0.01 if not cancel_waiter else 1))
    try:
        await interrupted.wait()
        if cancel_waiter:
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        else:
            assert await waiter == {child}
        assert child in _unfinished_tasks
        release.set()
        await asyncio.wait({child}, timeout=1)
        await asyncio.sleep(0)
        assert child.done() and child not in _unfinished_tasks
        assert child._log_traceback is False  # 迟到异常已被回收，不产生未读取异常告警。
    finally:
        release.set()
        await asyncio.gather(waiter, child, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan')])
async def test_invalid_timeout_is_rejected_before_any_cancellation(timeout: float) -> None:
    task = asyncio.create_task(asyncio.sleep(10))
    try:
        with pytest.raises(ValueError, match='大于零'):
            await cancel_plugin_tasks({task}, timeout=timeout)
        assert not task.done()
    finally:
        await cancel_plugin_tasks({task}, timeout=0.01)
