import asyncio
from types import SimpleNamespace

import pytest
from loguru import logger

from utils.log_util import LoggerInitializer


def build_log_record(*, level: str, level_no: int, extra: dict[str, object]) -> dict[str, object]:
    """构建 Logger filter 所需的最小日志记录。"""
    return {
        'level': SimpleNamespace(name=level, no=level_no),
        'extra': dict(extra),
    }


@pytest.mark.parametrize(
    ('level', 'level_no'),
    [
        ('INFO', 20),
        ('WARNING', 30),
        ('ERROR', 40),
    ],
)
def test_startup_worker_role_never_suppresses_log_records(level: str, level_no: int) -> None:
    """校验启动标签和非 leader 标记不再充当日志访问控制。"""
    initializer = LoggerInitializer()
    record = build_log_record(
        level=level,
        level_no=level_no,
        extra={
            'startup_phase': 'application_startup',
            'startup_log_enabled': False,
        },
    )

    assert initializer._filter(record) is True
    assert record['extra']['startup_phase'] == 'application_startup'
    assert record['extra']['startup_log_enabled'] is False


def test_startup_worker_role_never_suppresses_info_or_error_file_records() -> None:
    """校验info与error文件filter同样只按级别分流，不按worker角色丢弃。"""
    initializer = LoggerInitializer()
    info_record = build_log_record(
        level='INFO',
        level_no=20,
        extra={'startup_phase': 'application_startup', 'startup_log_enabled': False},
    )
    error_record = build_log_record(
        level='ERROR',
        level_no=40,
        extra={'startup_phase': 'application_startup', 'startup_log_enabled': False},
    )

    assert initializer._info_file_filter(info_record) is True
    assert initializer._error_file_filter(error_record) is True


@pytest.mark.asyncio
async def test_background_task_inheriting_old_startup_context_still_emits_logs() -> None:
    """校验 create_task 复制旧启动上下文后，后台任务日志仍然可见。"""
    initializer = LoggerInitializer()
    outputs: list[str] = []
    handler_id = logger.add(
        lambda message: outputs.append(message.record['message']),
        filter=initializer._filter,
        format='{message}',
    )

    async def emit_from_background_task() -> None:
        """在复制的上下文中输出后台任务日志。"""
        await asyncio.sleep(0)
        logger.info('background startup log')

    try:
        with logger.contextualize(startup_phase='application_startup', startup_log_enabled=False):
            task = asyncio.create_task(emit_from_background_task())
        await task
    finally:
        logger.remove(handler_id)

    assert outputs == ['background startup log']
