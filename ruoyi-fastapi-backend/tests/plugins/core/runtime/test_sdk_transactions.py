import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plugins.core.runtime.host_services import build_host_services
from plugins.core.sdk import PluginHostContext, PluginRequestContext


@pytest_asyncio.fixture
async def sdk_sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """使用独立 SQLite 验证提交、回滚和会话所有权。"""
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "sdk.sqlite"}')
    async with engine.begin() as db:
        await db.execute(text('CREATE TABLE sdk_effect (value INTEGER NOT NULL)'))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def request_context(tmp_path: Path, sessions: async_sessionmaker[AsyncSession]) -> PluginRequestContext:
    """构建只授予示例业务权限的宿主身份。"""
    host = PluginHostContext('sdk_demo', tmp_path, session_factory=sessions)
    return PluginRequestContext(host, SimpleNamespace(user=SimpleNamespace(user_id=7)), frozenset({'sdk_demo:profile'}))


@pytest.mark.asyncio
async def test_explicit_transaction_commits_and_profile_reuses_owned_session(
    tmp_path: Path, sdk_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """同一事务中的宿主服务复用会话，退出后一次提交。"""
    context = request_context(tmp_path, sdk_sessions)
    fallback = Mock(side_effect=AssertionError('service must reuse the transaction'))
    profile = SimpleNamespace(
        data=SimpleNamespace(user_id=7, user_name='demo', nick_name='Demo', avatar=''), post_group='', role_group=''
    )
    service = build_host_services('sdk_demo', fallback)['users.current_profile.v1']
    with patch(
        'module_admin.service.user_service.UserService.user_profile_services', new=AsyncMock(return_value=profile)
    ) as read:
        async with context.transaction() as transaction:
            await transaction.query_db.execute(text('INSERT INTO sdk_effect VALUES (1)'))
            assert (await service(transaction))['userId'] == context.user.user.user_id
            read.assert_awaited_once_with(transaction.query_db, 7)
    fallback.assert_not_called()
    assert context.query_db is None
    async with sdk_sessions() as db:
        assert (await db.execute(text('SELECT value FROM sdk_effect'))).scalars().all() == [1]
    with pytest.raises(RuntimeError, match='失效'):
        transaction.transaction_session()
    with pytest.raises(RuntimeError, match='失效'):
        await service(transaction)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_failed_or_cancelled_transaction_rolls_back(
    tmp_path: Path, sdk_sessions: async_sessionmaker[AsyncSession], cancelled: bool
) -> None:
    """异常和取消均不能留下已提交的业务数据。"""
    context = request_context(tmp_path, sdk_sessions)
    entered = asyncio.Event()
    captured = []

    async def write() -> None:
        async with context.transaction() as transaction:
            captured.append(transaction)
            await transaction.query_db.execute(text('INSERT INTO sdk_effect VALUES (2)'))
            entered.set()
            if cancelled:
                await asyncio.Event().wait()
            raise ValueError('business failure')

    task = asyncio.create_task(write())
    await asyncio.wait_for(entered.wait(), timeout=2)
    if cancelled:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancelled else ValueError):
        await task
    async with sdk_sessions() as db:
        assert not (await db.execute(text('SELECT value FROM sdk_effect'))).all()
    with pytest.raises(RuntimeError, match='失效'):
        captured[0].transaction_session()


@pytest.mark.asyncio
async def test_transaction_rejects_nested_and_parallel_session_use(
    tmp_path: Path, sdk_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """嵌套事务和另一个 asyncio 任务不能复用当前会话。"""
    context = request_context(tmp_path, sdk_sessions)

    async def foreign_task(transaction: PluginRequestContext) -> None:
        transaction.transaction_session()

    async with context.transaction() as transaction:
        with pytest.raises(RuntimeError, match='跨 asyncio'):
            await asyncio.create_task(foreign_task(transaction))
        with pytest.raises(RuntimeError, match='嵌套'):
            async with transaction.transaction():
                pytest.fail('nested transaction entered')
        assert transaction.transaction_session() is transaction.query_db


@pytest.mark.asyncio
async def test_unowned_session_and_missing_factory_are_rejected(tmp_path: Path) -> None:
    """会话不能通过任意 query_db 注入绕过所有权检查。"""
    context = PluginRequestContext(PluginHostContext('sdk_demo', tmp_path), object())
    with pytest.raises(RuntimeError, match='会话工厂'):
        async with context.transaction():
            pytest.fail('missing factory entered')
    with pytest.raises(RuntimeError, match='不是由宿主创建'):
        replace(context, query_db=object()).transaction_session()
