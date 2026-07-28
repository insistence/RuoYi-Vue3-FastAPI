from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from config.get_redis import RedisUtil


@pytest.mark.asyncio
async def test_redis_startup_error_is_logged_when_success_summary_is_disabled() -> None:
    """校验非Application leader的Redis错误不会随成功摘要一起被关闭。"""
    redis = AsyncMock()
    redis.ping.side_effect = RedisConnectionError('redis unavailable')

    with patch('config.get_redis.logger') as mocked_logger:
        await RedisUtil.check_redis_connection(
            redis,
            log_enabled=False,
            log_error_enabled=True,
        )

    mocked_logger.info.assert_not_called()
    mocked_logger.error.assert_called_once()
    assert 'redis连接错误' in mocked_logger.error.call_args.args[0]


@pytest.mark.asyncio
async def test_redis_success_summary_can_be_silenced_without_error() -> None:
    """校验非leader的成功连接检查不产生重复INFO。"""
    redis = AsyncMock()
    redis.ping.return_value = True

    with patch('config.get_redis.logger') as mocked_logger:
        await RedisUtil.check_redis_connection(
            redis,
            log_enabled=False,
            log_error_enabled=True,
        )

    mocked_logger.info.assert_not_called()
    mocked_logger.error.assert_not_called()
