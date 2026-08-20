from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import cache
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config.env import DataBaseConfig, DataBaseSettings, DataSourceSettings
from exceptions.exception import (
    DataSourceInitializationException,
    DataSourceNotFoundException,
    DataSourceUnavailableException,
)
from utils.log_util import logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_HEALTH_RETRY_COOLDOWN = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class DatabaseDriverAdapter:
    """
    数据库驱动适配器
    """

    db_type: str
    async_driver: str
    sync_driver: str
    async_connect_timeout_key: str
    sync_connect_timeout_key: str

    def build_url(self, config: DataSourceSettings, *, sync: bool) -> URL:
        """
        根据数据源配置构建SQLAlchemy数据库连接URL

        :param config: 数据源配置
        :param sync: 是否构建同步数据库连接URL
        :return: SQLAlchemy数据库连接URL
        """
        return URL.create(
            drivername=self.sync_driver if sync else self.async_driver,
            username=config.db_username,
            password=_secret_value(config.db_password),
            host=config.db_host,
            port=int(config.db_port),
            database=config.db_database,
        )

    def build_connect_args(self, config: DataSourceSettings, *, sync: bool) -> dict[str, int]:
        """
        构建数据库驱动连接参数

        :param config: 数据源配置
        :param sync: 是否构建同步数据库连接参数
        :return: 数据库驱动连接参数
        """
        timeout_key = self.sync_connect_timeout_key if sync else self.async_connect_timeout_key
        return {timeout_key: config.db_connect_timeout}


_DATABASE_DRIVER_ADAPTERS = {
    adapter.db_type: adapter
    for adapter in (
        DatabaseDriverAdapter(
            db_type='mysql',
            async_driver='mysql+asyncmy',
            sync_driver='mysql+pymysql',
            async_connect_timeout_key='connect_timeout',
            sync_connect_timeout_key='connect_timeout',
        ),
        DatabaseDriverAdapter(
            db_type='postgresql',
            async_driver='postgresql+asyncpg',
            sync_driver='postgresql+psycopg2',
            async_connect_timeout_key='timeout',
            sync_connect_timeout_key='connect_timeout',
        ),
    )
}


def _secret_value(value: SecretStr | str) -> str:
    """
    获取密码配置的原始值

    :param value: 密码配置
    :return: 密码原始值
    """
    return value.get_secret_value() if isinstance(value, SecretStr) else value


def _database_source(config: DataBaseSettings | DataSourceSettings) -> DataSourceSettings:
    """
    获取指定配置对应的数据源配置

    :param config: 数据库集合配置或单个数据源配置
    :return: 单个数据源配置
    """
    return config.get_source() if isinstance(config, DataBaseSettings) else config


def _driver_adapter(config: DataSourceSettings) -> DatabaseDriverAdapter:
    """
    获取数据库驱动适配器

    :param config: 数据源配置
    :return: 数据库驱动适配器
    """
    adapter = _DATABASE_DRIVER_ADAPTERS.get(config.db_type)
    if adapter is None:
        raise ValueError(f'不支持的数据库类型：{config.db_type!r}')
    return adapter


def _build_url(config: DataSourceSettings, *, sync: bool) -> URL:
    """
    使用对应的数据库驱动适配器构建连接URL

    :param config: 数据源配置
    :param sync: 是否构建同步数据库连接URL
    :return: SQLAlchemy数据库连接URL
    """
    return _driver_adapter(config).build_url(config, sync=sync)


def build_async_sqlalchemy_database_url(config: DataBaseSettings | DataSourceSettings | None = None) -> URL:
    """
    构建异步SQLAlchemy数据库连接URL

    :param config: 数据库集合配置或单个数据源配置
    :return: 异步SQLAlchemy数据库连接URL
    """
    return _build_url(_database_source(config or DataBaseConfig), sync=False)


def build_sync_sqlalchemy_database_url(config: DataBaseSettings | DataSourceSettings | None = None) -> URL:
    """
    构建同步SQLAlchemy数据库连接URL

    :param config: 数据库集合配置或单个数据源配置
    :return: 同步SQLAlchemy数据库连接URL
    """
    return _build_url(_database_source(config or DataBaseConfig), sync=True)


def _engine_options(config: DataSourceSettings, echo: bool | None = None) -> dict[str, Any]:
    """
    构建数据库引擎连接池参数

    :param config: 数据源配置
    :param echo: 是否输出SQLAlchemy SQL日志
    :return: 数据库引擎连接池参数
    """
    return {
        'echo': config.db_echo if echo is None else echo,
        'max_overflow': config.db_max_overflow,
        'pool_size': config.db_pool_size,
        'pool_recycle': config.db_pool_recycle,
        'pool_timeout': config.db_pool_timeout,
        'pool_pre_ping': True,
        'pool_use_lifo': True,
    }


def create_async_db_engine(
    echo: bool | None = None, config: DataBaseSettings | DataSourceSettings | None = None
) -> AsyncEngine:
    """
    创建异步SQLAlchemy Engine

    :param echo: 是否输出SQLAlchemy SQL日志
    :param config: 数据库集合配置或单个数据源配置
    :return: 异步SQLAlchemy Engine
    """
    source = _database_source(config or DataBaseConfig)
    adapter = _driver_adapter(source)
    return create_async_engine(
        adapter.build_url(source, sync=False),
        connect_args=adapter.build_connect_args(source, sync=False),
        **_engine_options(source, echo),
    )


def create_sync_db_engine(
    echo: bool | None = None, config: DataBaseSettings | DataSourceSettings | None = None
) -> Engine:
    """
    创建同步SQLAlchemy Engine

    :param echo: 是否输出SQLAlchemy SQL日志
    :param config: 数据库集合配置或单个数据源配置
    :return: 同步SQLAlchemy Engine
    """
    source = _database_source(config or DataBaseConfig)
    adapter = _driver_adapter(source)
    return create_engine(
        adapter.build_url(source, sync=True),
        connect_args=adapter.build_connect_args(source, sync=True),
        **_engine_options(source, echo),
    )


def create_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    创建异步Session工厂

    :param engine: 异步SQLAlchemy Engine
    :return: 异步Session工厂
    """
    return async_sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def create_sync_session_factory(engine: Engine) -> sessionmaker:
    """
    创建同步Session工厂

    :param engine: 同步SQLAlchemy Engine
    :return: 同步Session工厂
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@dataclass(slots=True)
class DataSourceRuntime:
    """
    数据源运行时状态
    """

    name: str
    config: DataSourceSettings
    async_engine: AsyncEngine | None = None
    async_session_factory: async_sessionmaker[AsyncSession] | None = None
    sync_engine: Engine | None = None
    available: bool = False
    last_health_check_at: datetime | None = None
    next_retry_at: datetime | None = None
    health_lock: asyncio.Lock | None = None


class _DataSourceRegistry:
    """
    数据源注册中心
    """

    def __init__(self, settings: DataBaseSettings | None = None) -> None:
        self.settings = settings or DataBaseConfig
        self._runtimes: dict[str, DataSourceRuntime] = {}
        self._initialized = False
        self._configs = dict(self.settings.db_sources)

    def _resolve_name(self, name: str | None = None) -> str:
        """
        解析并校验数据源名称

        :param name: 数据源名称
        :return: 已配置的数据源名称
        """
        source_name = name or self.settings.db_default_source
        if source_name not in self._configs:
            raise DataSourceNotFoundException(source_name)
        return source_name

    def _runtime(self, name: str | None = None) -> DataSourceRuntime:
        """
        获取或创建数据源运行时状态

        :param name: 数据源名称
        :return: 数据源运行时状态
        """
        source_name = self._resolve_name(name)
        runtime = self._runtimes.get(source_name)
        if runtime is None:
            runtime = DataSourceRuntime(
                name=source_name,
                config=self._configs[source_name],
                health_lock=asyncio.Lock(),
            )
            self._runtimes[source_name] = runtime
        return runtime

    @staticmethod
    def _mark_unavailable(runtime: DataSourceRuntime) -> None:
        """
        标记数据源不可用并设置下次重试时间

        :param runtime: 数据源运行时状态
        :return: None
        """
        now = datetime.now(timezone.utc)
        runtime.available = False
        runtime.last_health_check_at = now
        runtime.next_retry_at = now + _HEALTH_RETRY_COOLDOWN

    @classmethod
    def _ensure_async_resources(cls, runtime: DataSourceRuntime) -> None:
        """
        确保数据源异步引擎和Session工厂已创建

        :param runtime: 数据源运行时状态
        :return: None
        """
        if runtime.async_engine is not None and runtime.async_session_factory is not None:
            return
        try:
            engine = create_async_db_engine(config=runtime.config)
            session_factory = create_async_session_factory(engine)
        except Exception:
            cls._mark_unavailable(runtime)
            raise DataSourceInitializationException(runtime.name) from None
        runtime.async_engine = engine
        runtime.async_session_factory = session_factory

    async def initialize(self) -> None:
        """
        初始化并检查所有数据源的连接状态

        :return: None
        """
        if self._initialized:
            return
        names = tuple(self._configs)
        results = await asyncio.gather(*(self._check_health(name) for name in names), return_exceptions=True)
        default_name = self._resolve_name()
        for name, result in zip(names, results, strict=True):
            source_logger = logger.bind(
                data_source=name,
                database_type=self._configs[name].db_type,
                required=self._configs[name].db_required or name == default_name,
            )
            if not isinstance(result, BaseException):
                source_logger.info('✅ 数据源初始化成功')
                continue
            config = self._configs[name]
            required = config.db_required or name == default_name
            if required:
                source_logger.error('❌ 必需数据源连接检查失败')
                await self.dispose_all()
                raise DataSourceInitializationException(name) from None
            source_logger.warning('⚠️ 非必需数据源连接检查失败，应用将降级启动')
        self._initialized = True

    def get_async_engine(self, name: str | None = None) -> AsyncEngine:
        """
        获取数据源异步引擎

        :param name: 数据源名称
        :return: 异步SQLAlchemy Engine
        """
        runtime = self._runtime(name)
        self._ensure_async_resources(runtime)
        assert runtime.async_engine is not None
        return runtime.async_engine

    def get_sync_engine(self, name: str | None = None) -> Engine:
        """
        获取数据源同步引擎

        :param name: 数据源名称
        :return: 同步SQLAlchemy Engine
        """
        runtime = self._runtime(name)
        if runtime.sync_engine is None:
            try:
                runtime.sync_engine = create_sync_db_engine(config=runtime.config)
            except Exception:
                raise DataSourceInitializationException(runtime.name) from None
        return runtime.sync_engine

    async def _check_health(self, name: str) -> None:
        """
        检查指定数据源的连接状态

        :param name: 数据源名称
        :return: None
        """
        runtime = self._runtime(name)
        lock = runtime.health_lock
        assert lock is not None
        async with lock:
            await self._check_health_locked(runtime)

    async def _check_health_locked(self, runtime: DataSourceRuntime) -> None:
        """
        在持有健康检查锁时检查数据源连接状态

        :param runtime: 数据源运行时状态
        :return: None
        """
        try:
            self._ensure_async_resources(runtime)
            assert runtime.async_engine is not None
            async with runtime.async_engine.begin() as connection:
                await connection.execute(text('SELECT 1'))
        except Exception:
            self._mark_unavailable(runtime)
            raise DataSourceUnavailableException(runtime.name) from None
        runtime.available = True
        runtime.last_health_check_at = datetime.now(timezone.utc)
        runtime.next_retry_at = None

    async def _ensure_available(self, runtime: DataSourceRuntime) -> None:
        """
        确保指定数据源当前可用

        :param runtime: 数据源运行时状态
        :return: None
        """
        lock = runtime.health_lock
        assert lock is not None
        async with lock:
            if runtime.available:
                return
            now = datetime.now(timezone.utc)
            if runtime.next_retry_at is not None and now < runtime.next_retry_at:
                raise DataSourceUnavailableException(runtime.name)
            await self._check_health_locked(runtime)
            logger.bind(data_source=runtime.name).info('✅ 数据源连接已恢复')

    @asynccontextmanager
    async def connection(self, name: str | None = None) -> AsyncGenerator[AsyncConnection, None]:
        """
        创建指定数据源的异步数据库连接事务

        :param name: 数据源名称
        :return: 异步数据库连接
        """
        runtime = self._runtime(name)
        await self._ensure_available(runtime)
        assert runtime.async_engine is not None
        try:
            async with runtime.async_engine.begin() as connection:
                yield connection
        except (InterfaceError, OperationalError):
            self._mark_unavailable(runtime)
            raise DataSourceUnavailableException(runtime.name) from None
        except DBAPIError as exc:
            if not exc.connection_invalidated:
                raise
            self._mark_unavailable(runtime)
            raise DataSourceUnavailableException(runtime.name) from None

    @asynccontextmanager
    async def session(self, name: str | None = None) -> AsyncGenerator[AsyncSession, None]:
        """
        创建指定数据源的异步数据库会话

        :param name: 数据源名称
        :return: 异步数据库会话
        """
        runtime = self._runtime(name)
        await self._ensure_available(runtime)
        factory = runtime.async_session_factory
        assert factory is not None
        try:
            async with factory() as current_db:
                yield current_db
        except (InterfaceError, OperationalError):
            self._mark_unavailable(runtime)
            raise DataSourceUnavailableException(runtime.name) from None
        except DBAPIError as exc:
            if not exc.connection_invalidated:
                raise
            self._mark_unavailable(runtime)
            raise DataSourceUnavailableException(runtime.name) from None

    async def dispose_all(self) -> None:
        """
        释放所有数据源的同步和异步引擎

        :return: None
        """
        runtimes = tuple(self._runtimes.values())
        self._runtimes.clear()
        self._initialized = False
        for runtime in runtimes:
            if runtime.sync_engine is not None:
                runtime.sync_engine.dispose()
        async_engines = [runtime.async_engine for runtime in runtimes if runtime.async_engine is not None]
        await asyncio.gather(*(engine.dispose() for engine in async_engines), return_exceptions=False)


DataSourceRegistry = _DataSourceRegistry()


class Base(AsyncAttrs, DeclarativeBase):
    pass


@cache
def get_data_source_base(source_name: str) -> type[DeclarativeBase]:
    """
    获取指定数据源独立且可复用的ORM元数据基类

    :param source_name: 数据源名称
    :return: ORM元数据基类
    """
    DataBaseConfig.get_source(source_name)

    class NamedDataSourceBase(AsyncAttrs, DeclarativeBase):
        pass

    NamedDataSourceBase.__name__ = f'{source_name.title().replace("_", "").replace("-", "")}DataSourceBase'
    return NamedDataSourceBase
