import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(BACKEND_ROOT))

from plugins.core.runtime.service.lifecycle.runner import (  # noqa: E402
    PluginLifecycleStep,
    PluginLifecycleStepFailed,
    PluginLifecycleStepRunner,
    PluginLifecycleStepStop,
)


@pytest.mark.asyncio
async def test_lifecycle_step_runner_runs_steps_in_order() -> None:
    """
    校验生命周期步骤运行器按声明顺序执行步骤。

    :return: None
    """
    calls = []

    async def first(context: dict[str, object]) -> None:
        context['first'] = True
        calls.append('first')

    async def second(context: dict[str, object]) -> None:
        context['second'] = bool(context['first'])
        calls.append('second')

    result = await PluginLifecycleStepRunner(
        [PluginLifecycleStep('first', first), PluginLifecycleStep('second', second)]
    ).run({})

    assert calls == ['first', 'second']
    assert result.context == {'first': True, 'second': True}
    assert result.stop is None


@pytest.mark.asyncio
async def test_lifecycle_step_runner_stops_when_step_returns_payload() -> None:
    """
    校验生命周期步骤返回 payload 时中止后续步骤。

    :return: None
    """
    calls = []

    async def stop(context: dict[str, object]) -> dict[str, object]:
        calls.append('stop')
        return {'ok': False, 'message': 'blocked'}

    async def skipped(context: dict[str, object]) -> None:
        calls.append('skipped')

    result = await PluginLifecycleStepRunner(
        [PluginLifecycleStep('stop', stop), PluginLifecycleStep('skipped', skipped)]
    ).run({})

    assert calls == ['stop']
    assert isinstance(result.stop, PluginLifecycleStepStop)
    assert result.stop.payload == {'ok': False, 'message': 'blocked'}


@pytest.mark.asyncio
async def test_lifecycle_step_runner_records_failed_step() -> None:
    """
    校验生命周期步骤异常时记录失败步骤。

    :return: None
    """

    async def broken(context: dict[str, object]) -> None:
        raise RuntimeError('broken step')

    with pytest.raises(PluginLifecycleStepFailed) as exc_info:
        await PluginLifecycleStepRunner([PluginLifecycleStep('broken', broken)]).run({})

    assert exc_info.value.step_name == 'broken'
    assert str(exc_info.value.original_error) == 'broken step'
