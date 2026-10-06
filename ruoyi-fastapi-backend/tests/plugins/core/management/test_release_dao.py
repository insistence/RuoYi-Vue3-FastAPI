import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.database import Base
from plugins.core.management.dao.release_dao import PluginReleaseConflictError, PluginReleaseDao
from plugins.core.management.entity.do.models import SysPlugin
from plugins.core.management.entity.do.release_models import SysPluginArtifact, SysPluginRelease, SysPluginWorker

DIGEST_A = 'a' * 64
DIGEST_B = 'b' * 64
WORKER_ID = '1' * 32
EXPECTED_WORKERS = 2
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """创建仅含发布相关表的临时数据库会话工厂。"""
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "releases.sqlite"}')
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                SysPlugin.__table__,
                SysPluginArtifact.__table__,
                SysPluginRelease.__table__,
                SysPluginWorker.__table__,
            ],
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def register(db: AsyncSession, digest: str = DIGEST_A, version: str = '1.0.0') -> SysPluginArtifact:
    """为测试登记指定摘要与版本的制品索引。"""
    return await PluginReleaseDao.register_artifact(
        db,
        digest=digest,
        plugin_id='demo',
        version=version,
        key_id='publisher',
        relative_path=f'demo/{version}/{digest}',
        manifest_json='{"id":"demo"}',
        created_by='maintainer',
    )


async def prepare(db: AsyncSession) -> SysPluginRelease:
    """为测试建立制品与已安装版本匹配的准备证据。"""
    await register(db)
    db.add(SysPlugin(plugin_id='demo', plugin_name='Demo', version='1.0.0', installed_version='1.0.0'))
    await db.flush()
    return await PluginReleaseDao.set_preparation_status(
        db, 'demo', status='prepared', prepared_digest=DIGEST_A, prepared_version='1.0.0'
    )


@pytest.mark.asyncio
async def test_artifact_is_immutable_and_same_version_can_have_multiple_digests(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证制品记录不可覆盖且同一版本允许多个摘要。"""
    async with sessions() as db:
        original = await register(db)
        again = await PluginReleaseDao.register_artifact(
            db,
            digest=DIGEST_A,
            plugin_id='demo',
            version='1.0.0',
            key_id='publisher',
            relative_path=f'demo/1.0.0/{DIGEST_A}',
            manifest_json='{ "id": "demo" }',
            created_by='another-operator',
        )
        assert again is original
        assert again.created_by == 'maintainer'
        await register(db, DIGEST_B)
        assert [row.digest for row in await PluginReleaseDao.list_artifacts(db, 'demo')] == [DIGEST_A, DIGEST_B]
        with pytest.raises(ValueError, match='拒绝覆盖'):
            await register(db, DIGEST_A, '2.0.0')


@pytest.mark.asyncio
async def test_all_dao_writes_remain_in_callers_transaction(sessions: async_sessionmaker[AsyncSession]) -> None:
    """验证所有数据访问写操作由调用方事务统一提交或回滚。"""
    async with sessions() as db:
        await register(db)
        await PluginReleaseDao.ensure_release(db, 'demo')
        await PluginReleaseDao.upsert_worker_report(
            db, worker_id=WORKER_ID, plugin_id='__runtime__', state='ready', heartbeat_time=NOW
        )
        await db.rollback()
    async with sessions() as db:
        assert await PluginReleaseDao.list_artifacts(db) == []
        assert await PluginReleaseDao.list_releases(db) == []
        assert await PluginReleaseDao.list_worker_reports(db) == []


@pytest.mark.asyncio
async def test_select_requires_exact_preparation_and_never_changes_installed_version(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证选择目标要求完整准备证据且不更改安装版本。"""
    async with sessions() as db:
        release = await prepare(db)
        old_generation = release.generation
        await register(db, DIGEST_B)
        with pytest.raises(ValueError, match='尚未完成维护准备'):
            await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_B, expected_generation=old_generation)
        selected = await PluginReleaseDao.select_target(
            db, 'demo', target_digest=DIGEST_A, expected_generation=old_generation, expected_workers=EXPECTED_WORKERS
        )
        assert selected.target_digest == DIGEST_A
        assert selected.previous_digest is None
        assert selected.generation != old_generation
        assert selected.expected_workers == EXPECTED_WORKERS
        assert (await db.get(SysPlugin, 'demo')).installed_version == '1.0.0'
        with pytest.raises(PluginReleaseConflictError):
            await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_A, expected_generation=old_generation)
        with pytest.raises(PluginReleaseConflictError):
            await PluginReleaseDao.set_preparation_status(
                db, 'demo', status='failed', last_error='late result', expected_generation=old_generation
            )
        await db.refresh(selected)
        assert selected.prepare_status == 'prepared'


@pytest.mark.asyncio
async def test_prepare_failure_preserves_target_and_clears_preparation_proof(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证准备失败保留运行目标并清除旧准备证据。"""
    async with sessions() as db:
        release = await prepare(db)
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_A, expected_generation=release.generation)
        generation = release.generation
        await PluginReleaseDao.set_preparation_status(db, 'demo', status='failed', last_error='migration failed')
        assert release.target_digest == DIGEST_A
        assert release.generation == generation
        assert release.prepared_digest is None
        assert release.prepared_version is None
        assert release.last_error == 'migration failed'
        assert (await db.get(SysPlugin, 'demo')).installed_version == '1.0.0'


@pytest.mark.asyncio
async def test_explicit_code_rollback_can_keep_newer_data_schema(sessions: async_sessionmaker[AsyncSession]) -> None:
    """验证显式代码回滚可以保留较新的数据结构版本。"""
    async with sessions() as db:
        release = await prepare(db)
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_A, expected_generation=release.generation)
        await register(db, DIGEST_B, '2.0.0')
        plugin = await db.get(SysPlugin, 'demo')
        plugin.installed_version = '2.0.0'
        await db.flush()
        with pytest.raises(ValueError, match='安装版本不一致'):
            await PluginReleaseDao.select_target(
                db, 'demo', target_digest=DIGEST_A, expected_generation=release.generation
            )
        await PluginReleaseDao.set_preparation_status(
            db, 'demo', status='prepared', prepared_digest=DIGEST_B, prepared_version='2.0.0'
        )
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_B, expected_generation=release.generation)
        assert release.previous_digest == DIGEST_A
        await PluginReleaseDao.set_preparation_status(
            db, 'demo', status='prepared', prepared_digest=DIGEST_A, prepared_version='2.0.0'
        )
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_A, expected_generation=release.generation)
        assert release.target_digest == DIGEST_A
        assert release.previous_digest == DIGEST_B
        await db.refresh(plugin)
        assert plugin.installed_version == '2.0.0'


@pytest.mark.asyncio
async def test_competing_target_selections_only_one_generation_wins(sessions: async_sessionmaker[AsyncSession]) -> None:
    """验证并发目标选择只有一个操作能提交匹配代际。"""
    async with sessions() as db:
        release = await prepare(db)
        generation = release.generation
        await db.commit()

    async def select_once() -> str:
        async with sessions() as db:
            try:
                row = await PluginReleaseDao.select_target(
                    db, 'demo', target_digest=DIGEST_A, expected_generation=generation
                )
                await db.commit()
                return row.generation
            except PluginReleaseConflictError:
                await db.rollback()
                return 'conflict'

    results = await asyncio.gather(select_once(), select_once())
    assert results.count('conflict') == 1
    async with sessions() as db:
        release = await PluginReleaseDao.get_release(db, 'demo')
        assert release.generation in results
        assert release.generation != generation


@pytest.mark.asyncio
async def test_reselecting_target_preserves_previous_release(sessions: async_sessionmaker[AsyncSession]) -> None:
    """验证重复选择同一目标不会丢失上一发布制品。"""
    async with sessions() as db:
        release = await prepare(db)
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_A, expected_generation=release.generation)
        await register(db, DIGEST_B)
        await PluginReleaseDao.set_preparation_status(
            db, 'demo', status='prepared', prepared_digest=DIGEST_B, prepared_version='1.0.0'
        )
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_B, expected_generation=release.generation)
        generation = release.generation
        await PluginReleaseDao.select_target(db, 'demo', target_digest=DIGEST_B, expected_generation=generation)
        assert release.target_digest == DIGEST_B
        assert release.previous_digest == DIGEST_A
        assert release.generation != generation


@pytest.mark.asyncio
async def test_reports_do_not_change_target_and_old_heartbeats_cannot_resurrect_stopped_worker(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证进程报告不修改目标且旧心跳不能恢复已停止进程。"""
    async with sessions() as db:
        release = await prepare(db)
        generation = release.generation
        await PluginReleaseDao.upsert_worker_report(
            db, worker_id=WORKER_ID, plugin_id='__runtime__', state='ready', heartbeat_time=NOW
        )
        await PluginReleaseDao.upsert_worker_report(
            db,
            worker_id=WORKER_ID,
            plugin_id='demo',
            state='stopped',
            heartbeat_time=NOW + timedelta(seconds=15),
            artifact_digest=DIGEST_A,
            generation=generation,
            version='1.0.0',
        )
        row = await PluginReleaseDao.upsert_worker_report(
            db, worker_id=WORKER_ID, plugin_id='demo', state='ready', heartbeat_time=NOW
        )
        assert row.state == 'stopped'
        assert row.artifact_digest == DIGEST_A
        assert row.heartbeat_time == NOW + timedelta(seconds=15)
        await db.refresh(release)
        assert release.target_digest is None
        assert release.generation == generation
        assert {row.plugin_id for row in await PluginReleaseDao.list_worker_reports(db, 'demo')} == {
            'demo',
            '__runtime__',
        }


@pytest.mark.asyncio
async def test_database_rejects_invalid_worker_and_release_states(sessions: async_sessionmaker[AsyncSession]) -> None:
    """验证数据库约束拒绝非法进程和发布状态。"""
    async with sessions() as db:
        db.add(SysPluginRelease(plugin_id='demo', generation=WORKER_ID, expected_workers=0, prepare_status='idle'))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
        db.add(SysPluginRelease(plugin_id='demo', generation=WORKER_ID, expected_workers=1, prepare_status='unknown'))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
        db.add(SysPluginWorker(worker_id=WORKER_ID, plugin_id='demo', state='active', heartbeat_time=NOW))
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.asyncio
async def test_worker_reports_require_utc_and_separate_host_from_plugin(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """验证报告时间规范及宿主与插件字段边界。"""
    async with sessions() as db:
        with pytest.raises(ValueError, match='时区'):
            await PluginReleaseDao.upsert_worker_report(
                db, worker_id=WORKER_ID, plugin_id='demo', state='ready', heartbeat_time=NOW.replace(tzinfo=None)
            )
        with pytest.raises(ValueError, match='宿主worker'):
            await PluginReleaseDao.upsert_worker_report(
                db,
                worker_id=WORKER_ID,
                plugin_id='__runtime__',
                state='ready',
                heartbeat_time=NOW,
                artifact_digest=DIGEST_A,
            )
