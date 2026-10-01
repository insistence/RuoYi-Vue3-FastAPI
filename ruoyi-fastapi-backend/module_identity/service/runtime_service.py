import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from common.constant import OidcAuditEvent
from config.database import DataSourceRegistry
from config.env import OidcConfig
from config.scheduler.manager import SchedulerManager
from module_identity.dao.oauth_audit_dao import OAuthAuditDao
from module_identity.service.audit_service import AuditService
from module_identity.service.key_service import KeyService, KeyServiceError
from module_identity.service.oauth_management_service import OAuthClientManagementService
from module_identity.service.session_service import LogoutService
from utils.log_util import logger
from utils.time_util import TimezoneUtil


@dataclass(frozen=True, slots=True)
class OidcReadiness:
    """
    OIDC 协议运行时就绪快照

    ``enabled`` 只表示部署配置已开启协议，``ready`` 还要求数据库中
    存在可加载的 active 签名密钥。两者分离后，管理后台可以在协议
    尚未就绪时继续启动并完成首把密钥初始化。
    """

    enabled: bool
    ready: bool
    reason: str
    checked_at: datetime

    def as_dict(self) -> dict[str, object]:
        """
        转换为可安全返回给管理端的状态字段

        :return: OIDC 运行时状态字段映射
        """

        return {
            'enabled': self.enabled,
            'ready': self.ready,
            'readinessReason': self.reason,
            'readinessCheckedAt': self.checked_at,
        }


class OidcRuntimeService:
    """
    OIDC 运行时模块服务层
    """

    _AUDIT_ARCHIVE_INTERVAL_SECONDS = 86400
    _READINESS_CACHE_SECONDS = 5
    _CORS_CACHE_SECONDS = 5
    _CORS_VERSION_KEY = 'oidc:runtime:cors_version'

    @staticmethod
    def _disabled_readiness() -> OidcReadiness:
        """
        构造 OIDC 协议关闭状态

        :return: OIDC 协议关闭时的就绪快照
        """

        return OidcReadiness(
            enabled=False,
            ready=False,
            reason='disabled',
            checked_at=TimezoneUtil.utc_now(),
        )

    @classmethod
    async def inspect_readiness(cls, db: AsyncSession) -> OidcReadiness:
        """
        检查 OIDC 是否具备对外提供协议服务的签名能力

        密钥不存在或密钥材料不可用都会被收敛为未就绪状态，不会影响
        管理后台启动；数据库基础设施异常仍向上抛出，由应用通用健康
        机制处理。

        :param db: 异步数据库会话
        :return: OIDC 运行时就绪快照
        """

        if not OidcConfig.oidc_enabled:
            return cls._disabled_readiness()
        try:
            await KeyService.get_signing_key(db)
        except KeyServiceError:
            return OidcReadiness(
                enabled=True,
                ready=False,
                reason='signing_key_unavailable',
                checked_at=TimezoneUtil.utc_now(),
            )
        return OidcReadiness(
            enabled=True,
            ready=True,
            reason='ready',
            checked_at=TimezoneUtil.utc_now(),
        )

    @classmethod
    async def refresh_readiness(cls, app: FastAPI, db: AsyncSession | None = None) -> OidcReadiness:
        """
        刷新并保存当前 Worker 的 OIDC 就绪快照

        :param app: FastAPI 应用
        :param db: 可复用的异步数据库会话
        :return: 刷新后的 OIDC 运行时就绪快照
        """

        if not OidcConfig.oidc_enabled:
            readiness = cls._disabled_readiness()
        elif db is not None:
            readiness = await cls.inspect_readiness(db)
        else:
            async with DataSourceRegistry.session() as current_db:
                readiness = await cls.inspect_readiness(current_db)
        app.state.oidc_readiness = readiness

        return readiness

    @classmethod
    async def cached_readiness(cls, app: FastAPI, db: AsyncSession) -> OidcReadiness:
        """
        读取带短时缓存的 OIDC 就绪状态

        缓存避免每个协议请求都重复解密私钥；未就绪状态也会很快重新
        检查，因此其他 Worker 在首把密钥激活后无需重启即可恢复。

        :param app: FastAPI 应用
        :param db: 异步数据库会话
        :return: 当前 Worker 的 OIDC 运行时就绪快照
        """

        current = TimezoneUtil.utc_now()
        readiness = getattr(app.state, 'oidc_readiness', None)
        if isinstance(readiness, OidcReadiness):
            age = (current - readiness.checked_at).total_seconds()
            if age < cls._READINESS_CACHE_SECONDS:
                return readiness
        lock = getattr(app.state, 'oidc_readiness_lock', None)
        if lock is None:
            lock = asyncio.Lock()
            app.state.oidc_readiness_lock = lock
        async with lock:
            readiness = getattr(app.state, 'oidc_readiness', None)
            current = TimezoneUtil.utc_now()
            if isinstance(readiness, OidcReadiness):
                age = (current - readiness.checked_at).total_seconds()
                if age < cls._READINESS_CACHE_SECONDS:
                    return readiness
            return await cls.refresh_readiness(app, db)

    @classmethod
    async def validate_runtime(cls, app: FastAPI | None = None) -> OidcReadiness:
        """
        检查启动阶段的 OIDC 就绪状态，但不阻断管理后台启动

        协议启用但尚无 active 密钥时记录明确告警，公共 OIDC 端点随后
        返回 503；管理员仍可登录后台创建并激活首把密钥。

        :param app: 需要保存就绪快照的 FastAPI 应用
        :return: 启动阶段的 OIDC 运行时就绪快照
        """

        if not OidcConfig.oidc_enabled:
            readiness = cls._disabled_readiness()
        else:
            async with DataSourceRegistry.session() as db:
                readiness = await cls.inspect_readiness(db)
        if app is not None:
            app.state.oidc_readiness = readiness
            app.state.oidc_readiness_lock = asyncio.Lock()
        if readiness.enabled and not readiness.ready:
            logger.warning('统一认证中心已启用但尚未就绪；请创建并激活有效签名密钥，就绪前协议接口返回 503')
        return readiness

    @staticmethod
    async def load_cors_origins() -> tuple[str, ...]:
        """
        加载启用的 CORS Origin

        :return: 启用的 CORS Origin 元组
        """

        async with DataSourceRegistry.session() as db:
            origins = await OAuthClientManagementService.list_active_cors_origins(db)
        return tuple(origins)

    @classmethod
    async def refresh_cors_snapshot(cls, app: FastAPI) -> tuple[str, ...]:
        """
        刷新应用的 CORS Origin 快照

        :param app: FastAPI 应用
        :return: 刷新后的 CORS Origin 元组
        """

        if not OidcConfig.oidc_enabled:
            app.state.oidc_registered_cors_origins = ()
            return ()
        origins = await cls.load_cors_origins()
        app.state.oidc_registered_cors_origins = origins
        app.state.oidc_cors_loaded_at = monotonic()

        return origins

    @classmethod
    async def ensure_cors_snapshot(cls, app: FastAPI) -> None:
        """
        刷新当前Worker的客户端跨域策略快照

        通过共享版本号发现变更，并以有时限的数据库缓存兜底。

        :param app: FastAPI应用对象
        :return: 无
        """

        if not OidcConfig.oidc_enabled:
            app.state.oidc_registered_cors_origins = ()
            return
        lock = getattr(app.state, 'oidc_cors_lock', None)
        if lock is None:
            lock = asyncio.Lock()
            app.state.oidc_cors_lock = lock
        async with lock:
            redis = getattr(app.state, 'redis', None)
            revision = None
            try:
                if redis is not None:
                    revision = await redis.get(cls._CORS_VERSION_KEY)
            except Exception:
                # 共享版本源不可用时，不延长旧跨域白名单的缓存期限
                app.state.oidc_cors_loaded_at = None
            if isinstance(revision, bytes):
                revision = revision.decode('ascii')
            loaded_at = getattr(app.state, 'oidc_cors_loaded_at', None)
            fresh = loaded_at is not None and monotonic() - loaded_at < cls._CORS_CACHE_SECONDS
            if fresh and revision == getattr(app.state, 'oidc_cors_revision', None):
                return
            try:
                await cls.refresh_cors_snapshot(app)
                app.state.oidc_cors_revision = revision
            except Exception:
                app.state.oidc_registered_cors_origins = ()
                app.state.oidc_cors_loaded_at = None
                logger.error('OAuth 已注册跨域来源快照刷新失败')

    @classmethod
    def cors_snapshot_callback(cls, app: FastAPI) -> Callable[[], Awaitable[None]]:
        """
        构造提交后刷新 CORS 快照的回调

        :param app: 需要更新 CORS Origin 快照的 FastAPI 应用
        :return: 无参数异步 CORS 快照刷新回调
        """

        async def refresh() -> None:
            """
            刷新应用 CORS Origin 快照

            :return: None
            """

            redis = getattr(app.state, 'redis', None)
            try:
                if redis is not None:
                    await redis.incr(cls._CORS_VERSION_KEY)
            except Exception:
                logger.error('OAuth 跨域配置失效通知发布失败，各工作进程将在缓存有效期内刷新')
            app.state.oidc_cors_loaded_at = None
            await cls.ensure_cors_snapshot(app)

        return refresh

    @classmethod
    async def start_background_tasks(cls, app: FastAPI) -> None:
        """
        每个 Worker 启动待命循环，仅当前 Leader 执行业务；重新获租后自动恢复

        :param app: FastAPI 应用
        :return: None
        """

        redis = app.state.redis
        app.state.oidc_key_lifecycle_task = (
            asyncio.create_task(cls.key_lifecycle_loop(app)) if OidcConfig.oidc_enabled else None
        )
        app.state.oidc_backchannel_retry_task = (
            asyncio.create_task(cls.backchannel_retry_loop(redis)) if OidcConfig.oidc_enabled else None
        )

    @classmethod
    async def key_lifecycle_loop(cls, app: FastAPI) -> None:
        """
        运行签名密钥生命周期后台循环

        :param app: FastAPI 应用，包含 Redis 与 OIDC 就绪状态
        :return: None
        """

        last_archive_at: datetime | None = None
        redis = app.state.redis
        while True:
            await asyncio.sleep(60)
            if not SchedulerManager.is_application_leader():
                continue
            try:
                async with DataSourceRegistry.session() as db:
                    activated = await KeyService.activate_due(db, redis=redis)
                    if activated:
                        await cls.refresh_readiness(app, db)
                    changed = await KeyService.retire_due(db)
                    if changed:
                        await AuditService.record(
                            db,
                            OidcAuditEvent.SIGNING_KEY_ROTATED,
                            'success',
                            detail={'action': 'retired_due', 'count': changed, 'actor': 'system:lifecycle'},
                        )
                        await db.commit()
                    current = TimezoneUtil.utc_now()
                    if (
                        last_archive_at is None
                        or (current - last_archive_at).total_seconds() >= cls._AUDIT_ARCHIVE_INTERVAL_SECONDS
                    ):
                        before = current - timedelta(days=OidcConfig.oidc_audit_retention_days)
                        while await OAuthAuditDao.archive_before(db, before):
                            await db.commit()
                        last_archive_at = current
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error('OIDC 签名密钥生命周期维护任务执行失败')

    @staticmethod
    async def backchannel_retry_loop(redis: object) -> None:
        """
        运行 Back-Channel 重试后台循环

        :param redis: 异步 Redis 客户端
        :return: None
        """

        while True:
            await asyncio.sleep(1)
            if not SchedulerManager.is_application_leader():
                continue
            try:
                async with DataSourceRegistry.session() as db:
                    await LogoutService.consume_backchannel_retry(db, redis, max_items=32)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error('OIDC 后端退出通知重试任务执行失败')

    @staticmethod
    async def stop_background_tasks(app: FastAPI) -> None:
        """
        停止 OIDC 后台任务

        :param app: FastAPI 应用
        :return: None
        """

        for name in ('oidc_key_lifecycle_task', 'oidc_backchannel_retry_task'):
            task = getattr(app.state, name, None)
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
