"""认证中心启动密钥校验测试。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from module_identity.service.key_service import KeyServiceError
from module_identity.service.runtime_service import OidcRuntimeService
from server import _start_background_tasks


@pytest.mark.asyncio
async def test_oidc_runtime_validation_is_a_noop_when_disabled() -> None:
    """关闭认证中心时不得创建额外数据库会话。"""
    with (
        patch('module_identity.service.runtime_service.OidcConfig.oidc_enabled', False),
        patch('module_identity.service.runtime_service.DataSourceRegistry.session') as session,
        patch(
            'module_identity.service.runtime_service.KeyService.get_signing_key',
            new_callable=AsyncMock,
        ) as get_signing_key,
    ):
        await OidcRuntimeService.validate_runtime()

    session.assert_not_called()
    get_signing_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_cors_snapshot_callback_fails_closed_without_raising() -> None:
    """管理提交后的 CORS 刷新失败时运行时快照必须进入拒绝态。"""
    app = SimpleNamespace(state=SimpleNamespace(oidc_registered_cors_origins=('https://old.example',)))
    with patch.object(OidcRuntimeService, 'refresh_cors_snapshot', new=AsyncMock(side_effect=RuntimeError('db down'))):
        await OidcRuntimeService.cors_snapshot_callback(app)()
    assert app.state.oidc_registered_cors_origins == ()


@pytest.mark.asyncio
async def test_oidc_runtime_validation_loads_database_active_key() -> None:
    """启用认证中心时每个 worker 都验证数据库事实源中的 active 私钥。"""
    db = object()

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield db

    with (
        patch('module_identity.service.runtime_service.OidcConfig.oidc_enabled', True),
        patch('module_identity.service.runtime_service.DataSourceRegistry.session', side_effect=session),
        patch(
            'module_identity.service.runtime_service.KeyService.get_signing_key',
            new_callable=AsyncMock,
        ) as get_signing_key,
    ):
        await OidcRuntimeService.validate_runtime()

    get_signing_key.assert_awaited_once()
    assert get_signing_key.await_args.args == (db,)


@pytest.mark.asyncio
async def test_oidc_runtime_validation_fails_closed_without_usable_key() -> None:
    """active 元数据或私钥不可用时后台继续启动，但 OIDC 标记为未就绪。"""

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    with (
        patch('module_identity.service.runtime_service.OidcConfig.oidc_enabled', True),
        patch('module_identity.service.runtime_service.DataSourceRegistry.session', side_effect=session),
        patch(
            'module_identity.service.runtime_service.KeyService.get_signing_key',
            new=AsyncMock(side_effect=KeyServiceError('private key does not match public JWK')),
        ),
    ):
        readiness = await OidcRuntimeService.validate_runtime()

    assert readiness.enabled is True
    assert readiness.ready is False
    assert readiness.reason == 'signing_key_unavailable'


@pytest.mark.asyncio
async def test_background_loops_wait_in_both_leader_and_follower() -> None:
    """Leader 和 Follower 都启动循环，由每轮当前租约决定是否执行业务。"""
    app = SimpleNamespace(state=SimpleNamespace(redis=object(), application_leader=True))
    fake_key_task = object()
    fake_retry_task = object()
    created: list[object] = []

    def create_task(coro: object) -> object:
        created.append(coro)
        coro.close()
        return (fake_key_task, fake_retry_task)[len(created) - 1]

    with (
        patch('module_identity.service.runtime_service.OidcConfig.oidc_enabled', True),
        patch('module_identity.service.runtime_service.SchedulerManager.is_application_leader', return_value=True),
        patch('module_identity.service.runtime_service.asyncio.create_task', side_effect=create_task),
    ):
        await OidcRuntimeService.start_background_tasks(app)
    assert app.state.oidc_key_lifecycle_task is fake_key_task
    assert app.state.oidc_backchannel_retry_task is fake_retry_task

    app.state.application_leader = False
    created.clear()
    with (
        patch('module_identity.service.runtime_service.OidcConfig.oidc_enabled', True),
        patch('module_identity.service.runtime_service.SchedulerManager.is_application_leader', return_value=False),
        patch('module_identity.service.runtime_service.asyncio.create_task', side_effect=create_task),
    ):
        await OidcRuntimeService.start_background_tasks(app)
    assert app.state.oidc_key_lifecycle_task is fake_key_task
    assert app.state.oidc_backchannel_retry_task is fake_retry_task


@pytest.mark.asyncio
@pytest.mark.parametrize('loop', ['key', 'retry'])
async def test_background_loops_resume_after_lease_reacquisition(loop: str) -> None:
    db = SimpleNamespace(commit=AsyncMock())

    @asynccontextmanager
    async def session() -> AsyncIterator[SimpleNamespace]:
        yield db

    with (
        patch(
            'module_identity.service.runtime_service.SchedulerManager.is_application_leader',
            side_effect=[False, True, False, True],
        ),
        patch(
            'module_identity.service.runtime_service.asyncio.sleep',
            new=AsyncMock(side_effect=[None, None, None, None, asyncio.CancelledError()]),
        ),
        patch('module_identity.service.runtime_service.DataSourceRegistry.session', side_effect=session),
        patch(
            'module_identity.service.runtime_service.KeyService.activate_due', new=AsyncMock(return_value=0)
        ) as activate,
        patch('module_identity.service.runtime_service.KeyService.retire_due', new=AsyncMock(return_value=0)),
        patch('module_identity.service.runtime_service.OAuthAuditDao.archive_before', new=AsyncMock(return_value=0)),
        patch(
            'module_identity.service.runtime_service.LogoutService.consume_backchannel_retry',
            new=AsyncMock(return_value=0),
        ) as consume,
        pytest.raises(asyncio.CancelledError),
    ):
        if loop == 'key':
            await OidcRuntimeService.key_lifecycle_loop(SimpleNamespace(state=SimpleNamespace(redis=object())))
        else:
            await OidcRuntimeService.backchannel_retry_loop(object())
    expected_leader_periods = 2
    assert (activate if loop == 'key' else consume).await_count == expected_leader_periods


@pytest.mark.asyncio
async def test_server_background_task_setup_delegates_oidc_runtime() -> None:
    """应用入口只负责装配通用任务和认证中心运行时。"""
    app = SimpleNamespace(state=SimpleNamespace(redis=object()))
    log_task = object()

    def create_task(coro: object) -> object:
        coro.close()
        return log_task

    with (
        patch('server.SchedulerManager.init_system_scheduler', new_callable=AsyncMock) as init_scheduler,
        patch('server.LogAggregatorService.consume_stream', new_callable=AsyncMock),
        patch('server.asyncio.create_task', side_effect=create_task),
        patch.object(OidcRuntimeService, 'start_background_tasks', new_callable=AsyncMock) as start_oidc,
    ):
        await _start_background_tasks(app)

    init_scheduler.assert_awaited_once_with(app.state.redis)
    start_oidc.assert_awaited_once_with(app)
