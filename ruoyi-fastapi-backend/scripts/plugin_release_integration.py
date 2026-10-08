from __future__ import annotations

import argparse
import asyncio
import base64
import json
import multiprocessing
import os
import re
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = 'release_it_demo'
TTL_SECONDS = 12
OPT_IN = 'RUOYI_PLUGIN_IT_ALLOW'
EXPECTED_WORKER_COUNT = 2


@dataclass(frozen=True)
class RunSpec:
    """
    可跨进程序列化的隔离运行信息，不包含连接密码。
    """

    engine: str
    run_id: str
    root: str

    @property
    def database(self) -> str:
        """
        获取仅属于当前验收运行的数据库名称。

        :return: 隔离数据库名称
        """
        return f'ruoyi_plugin_it_{self.run_id}'

    @property
    def redis_prefix(self) -> str:
        """
        获取仅属于当前验收运行的 Redis 键前缀。

        :return: 隔离 Redis 键前缀
        """
        return f'ruoyi_plugin_it:{self.run_id}:'

    def validate(self) -> None:
        """
        校验数据库类型、运行标识和绝对输出路径。

        :return: None
        """
        if self.engine not in {'mysql', 'postgresql'} or not re.fullmatch(r'[0-9a-f]{32}', self.run_id):
            raise ValueError('Invalid isolated integration run identity')
        if not Path(self.root).is_absolute():
            raise ValueError('Integration output root must be absolute')


def require_opt_in(engine: str) -> None:
    """
    在导入服务依赖前检查显式授权和连接凭据环境变量。

    :param engine: 验收使用的数据库引擎
    :return: None
    """
    if os.environ.get(OPT_IN) != '1':
        raise ValueError(f'Real-service tests are disabled; explicitly set {OPT_IN}=1')
    if engine not in {'mysql', 'postgresql'}:
        raise ValueError('Select mysql or postgresql explicitly')
    db_variable = 'RUOYI_IT_MYSQL_PASSWORD' if engine == 'mysql' else 'RUOYI_IT_PG_PASSWORD'
    for variable in (db_variable, 'RUOYI_IT_REDIS_PASSWORD'):
        if variable not in os.environ:
            raise ValueError(f'Set {variable} in the process environment (empty is allowed)')


def safe_error(exc: BaseException) -> str:
    """
    移除名称含 PASSWORD 或 SECRET 的环境变量值，并限制错误输出长度。

    :param exc: 需要脱敏的异常
    :return: 可安全输出的异常说明
    """
    message = f'{type(exc).__name__}: {exc}'
    for name, value in os.environ.items():
        if value and ('PASSWORD' in name.upper() or 'SECRET' in name.upper()):
            message = message.replace(value, '<redacted>')
    return message[:6000]


def check(condition: bool, message: str) -> None:
    """
    检查验收条件，不成立时抛出带说明的断言异常。

    :param condition: 预期成立的验收条件
    :param message: 条件不成立时的错误说明
    :return: None
    """
    if not condition:
        raise AssertionError(message)


def emit(phase: str, **details: Any) -> None:
    """
    输出一条可及时刷新的 JSON 验收进度。

    :param phase: 验收阶段标识
    :param details: 当前阶段的结构化结果
    :return: None
    """
    print(json.dumps({'phase': phase, **details}, ensure_ascii=False), flush=True)


def configure_process(spec: RunSpec) -> None:
    """
    配置隔离环境并禁用默认应用连接，避免意外使用业务配置。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :return: None
    """
    require_opt_in(spec.engine)
    spec.validate()
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    os.environ['APP_ENV'] = f'plugin_it_{spec.run_id}'
    os.environ['APP_DEFAULT_ENABLED_PLUGINS'] = ''
    os.environ['DB_DEFAULT_SOURCE'] = 'primary'
    os.environ['DB_SOURCES'] = json.dumps(
        {
            'primary': {
                'db_type': spec.engine,
                'db_host': '127.0.0.1',
                'db_port': 1,
                'db_username': 'integration_injection_required',
                'db_password': 'unused',
                'db_database': spec.database,
                'db_echo': False,
                'db_connect_timeout': 1,
            }
        }
    )
    os.environ['LOG_FILE_ENABLED'] = 'false'
    os.environ['LOG_FILE_BASE_DIR'] = str(Path(spec.root) / 'logs')
    sys.dont_write_bytecode = True
    from utils.log_util import logger  # noqa: PLC0415

    # 验收只输出已限制长度并脱敏的进度和错误记录。
    logger.remove()


def database_engine(spec: RunSpec, *, admin: bool = False) -> Any:
    """
    从验收专用环境变量创建异步数据库连接池。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param admin: 是否连接管理数据库以创建或删除隔离数据库
    :return: 隔离验收使用的异步数据库连接池
    """
    from sqlalchemy import URL  # noqa: PLC0415
    from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

    spec.validate()
    prefix = 'RUOYI_IT_MYSQL' if spec.engine == 'mysql' else 'RUOYI_IT_PG'
    mysql = spec.engine == 'mysql'
    url = URL.create(
        'mysql+asyncmy' if mysql else 'postgresql+asyncpg',
        username=os.environ.get(f'{prefix}_USER', 'root' if mysql else 'postgres'),
        password=os.environ[f'{prefix}_PASSWORD'],
        host=os.environ.get(f'{prefix}_HOST', '127.0.0.1'),
        port=int(os.environ.get(f'{prefix}_PORT', '3306' if mysql else '5432')),
        database=('information_schema' if mysql else 'postgres') if admin else spec.database,
    )
    connect_args = (
        {'connect_timeout': 10, 'init_command': "SET time_zone = '+00:00'", 'charset': 'utf8mb4'}
        if mysql
        else {'timeout': 10, 'server_settings': {'timezone': 'UTC'}}
    )
    options = {'isolation_level': 'AUTOCOMMIT'} if admin else {}
    return create_async_engine(
        url, echo=False, hide_parameters=True, pool_size=3, max_overflow=2, connect_args=connect_args, **options
    )


def redis_client() -> Any:
    """
    从验收专用环境变量创建异步 Redis 客户端。

    :return: 隔离验收使用的 Redis 客户端
    """
    from redis.asyncio import Redis  # noqa: PLC0415

    return Redis(
        host=os.environ.get('RUOYI_IT_REDIS_HOST', '127.0.0.1'),
        port=int(os.environ.get('RUOYI_IT_REDIS_PORT', '6379')),
        db=int(os.environ.get('RUOYI_IT_REDIS_DB', '2')),
        username=os.environ.get('RUOYI_IT_REDIS_USER') or None,
        password=os.environ['RUOYI_IT_REDIS_PASSWORD'] or None,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )


def wire_runtime(spec: RunSpec, engine: Any) -> tuple[Any, Any]:
    """
    替换资源工厂和 Redis 命名空间，保留真实 DAO、锁与续租逻辑。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param engine: 隔离数据库的异步连接池
    :return: 制品部署配置和异步会话工厂
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: PLC0415

    from config.database import DataSourceRegistry  # noqa: PLC0415
    from config.get_redis import RedisUtil  # noqa: PLC0415
    from plugins.core.deployment.config import PluginDeploymentConfig  # noqa: PLC0415
    from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock  # noqa: PLC0415

    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def isolated_session(*args: Any, **kwargs: Any) -> AsyncGenerator[Any, None]:
        """
        仅开放当前验收的默认数据库会话，拒绝命名业务数据源。

        :param args: 宿主会话工厂的位置参数，验收时禁止指定命名数据源
        :param kwargs: 宿主会话工厂的关键字参数
        :return: 异步上下文中的隔离数据库会话
        """
        if args or kwargs.get('name') is not None:
            raise ValueError('Named application data sources are forbidden in integration acceptance')
        async with sessions() as session:
            yield session

    async def isolated_redis(*args: Any, **kwargs: Any) -> Any:
        """
        为宿主资源工厂返回验收专用 Redis 客户端。

        :param args: 兼容宿主 Redis 工厂的位置参数，验收不使用这些参数
        :param kwargs: 兼容宿主 Redis 工厂的关键字参数，验收不使用这些参数
        :return: 验收专用 Redis 客户端
        """
        return redis_client()

    DataSourceRegistry.session = isolated_session
    RedisUtil.create_redis_pool = staticmethod(isolated_redis)
    RedisPluginLifecycleLock._build_lock_key = staticmethod(lambda: f'{spec.redis_prefix}lifecycle:global')
    root = Path(spec.root)
    config = PluginDeploymentConfig(
        root / 'host', root / 'store', root / 'trusted.json', heartbeat_seconds=1, worker_ttl_seconds=TTL_SECONDS
    )
    return config, sessions


async def create_isolated_database(spec: RunSpec, admin: Any) -> None:
    """
    创建全新的隔离数据库，名称冲突时直接失败。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param admin: 用于创建和删除隔离数据库的管理连接池
    :return: None
    """
    spec.validate()
    quote = '`' if spec.engine == 'mysql' else '"'
    suffix = ' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci' if spec.engine == 'mysql' else ''
    async with admin.connect() as connection:
        # 不使用 IF NOT EXISTS，名称冲突必须失败，避免接管已有数据库。
        await connection.exec_driver_sql(f'CREATE DATABASE {quote}{spec.database}{quote}{suffix}')


async def drop_isolated_database(spec: RunSpec, admin: Any) -> None:
    """
    删除隔离数据库；调用方必须先确认本轮创建成功。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param admin: 用于创建和删除隔离数据库的管理连接池
    :return: None
    """
    spec.validate()
    quote = '`' if spec.engine == 'mysql' else '"'
    async with admin.connect() as connection:
        await connection.exec_driver_sql(f'DROP DATABASE {quote}{spec.database}{quote}')


async def clear_own_redis_keys(spec: RunSpec) -> int:
    """
    只清理当前运行前缀下的 Redis 键，并验证没有残留。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :return: 删除的 Redis 键数量
    """
    spec.validate()
    client = redis_client()
    removed = 0
    try:
        async for key in client.scan_iter(match=f'{spec.redis_prefix}*', count=100):
            check(key.startswith(spec.redis_prefix), 'Refusing Redis cleanup outside this run prefix')
            removed += await client.delete(key)
        check(not [key async for key in client.scan_iter(match=f'{spec.redis_prefix}*')], 'Redis keys remain')
    finally:
        await client.aclose()
    return removed


async def prepare_schema(spec: RunSpec, engine: Any) -> None:
    """
    从初始化 SQL 提取所需宿主表和索引，在隔离空库中创建并验证发布表。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param engine: 隔离数据库的异步连接池
    :return: None
    """
    from sqlalchemy import select  # noqa: PLC0415

    from plugins.core.lifecycle.script import PluginLifecycleScriptHelper  # noqa: PLC0415
    from plugins.core.management.entity.do.release_models import (  # noqa: PLC0415
        SysPluginArtifact,
        SysPluginRelease,
        SysPluginWorker,
    )

    required_tables = {
        'sys_menu',
        'sys_job',
        'sys_plugin',
        'sys_plugin_config',
        'sys_plugin_menu',
        'sys_plugin_migration',
        'sys_plugin_operation_log',
        'sys_plugin_artifact',
        'sys_plugin_release',
        'sys_plugin_worker',
    }
    initial_filename = 'ruoyi-fastapi.sql' if spec.engine == 'mysql' else 'ruoyi-fastapi-pg.sql'
    initial_statements = PluginLifecycleScriptHelper.split_sql_statements(
        (BACKEND_ROOT / 'sql' / initial_filename).read_text('utf-8')
    )
    table_statements = {}
    index_statements = []
    for statement in initial_statements:
        match = re.match(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(', statement, re.IGNORECASE)
        if match and match[1].lower() in required_tables:
            table_name = match[1].lower()
            check(table_name not in table_statements, f'Duplicate host table DDL: {table_name}')
            table_statements[table_name] = statement
        index_match = re.match(
            r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+(\w+)\s*\(',
            statement,
            re.IGNORECASE,
        )
        if index_match and index_match[1].lower() in required_tables:
            index_statements.append(statement)
    check(table_statements.keys() == required_tables, f'Incomplete host table DDL in {initial_filename}')

    async with engine.begin() as connection:
        # 只执行所需宿主表和索引的创建语句，不执行删除、种子数据或其他语句。
        for statement in table_statements.values():
            await connection.exec_driver_sql(statement)
        for statement in index_statements:
            await connection.exec_driver_sql(statement)
        # 发布表必须由初始化 SQL 创建，不能由 ORM 补建。
        for model in (SysPluginArtifact, SysPluginRelease, SysPluginWorker):
            check(not (await connection.execute(select(model))).all(), f'{model.__tablename__} is not empty')
    emit(
        'schema_ddl',
        engine=spec.engine,
        script=initial_filename,
        tables=len(table_statements),
        indexes=len(index_statements),
        ormTables=3,
    )


def make_artifacts(spec: RunSpec) -> tuple[Path, Path]:
    """
    生成两个包含真实迁移的签名测试制品和临时信任配置。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :return: 初始版本和升级版本的制品路径
    """
    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: PLC0415

    from plugins.core.artifacts import build_artifact  # noqa: PLC0415

    root = Path(spec.root)
    (root / 'host' / 'plugins').mkdir(parents=True)
    private_key = Ed25519PrivateKey.generate()
    public = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    (root / 'trusted.json').write_text(
        json.dumps(
            {
                'schemaVersion': 1,
                'keys': [
                    {'keyId': 'integration', 'publicKey': base64.b64encode(public).decode(), 'pluginIds': [PLUGIN_ID]}
                ],
            }
        ),
        encoding='utf-8',
    )
    archives = []
    for version in ('1.0.0', '2.0.0'):
        source = root / f'source-{version}' / PLUGIN_ID
        (source / 'migrations').mkdir(parents=True)
        migrations = '    - migrations/001_probe.sql\n'
        (source / 'migrations' / '001_probe.sql').write_text(
            'CREATE TABLE plugin_it_probe (id INTEGER NOT NULL PRIMARY KEY, value VARCHAR(32) NOT NULL);\n'
            "INSERT INTO plugin_it_probe (id, value) VALUES (1, 'installed_v1');\n",
            encoding='utf-8',
        )
        if version == '2.0.0':
            migrations += '    - migrations/002_upgrade.sql\n'
            (source / 'migrations' / '002_upgrade.sql').write_text(
                "INSERT INTO plugin_it_probe (id, value) VALUES (2, 'upgraded_v2');\n", encoding='utf-8'
            )
        (source / 'plugin.yaml').write_text(
            f'manifestVersion: 2\nid: {PLUGIN_ID}\nname: Real service acceptance\nversion: {version}\n'
            f'backend:\n  runtime: python\n  integration: asgi\n  module: plugins.{PLUGIN_ID}\n'
            f'  entrypoint: plugins.{PLUGIN_ID}:create_plugin\n  migrations:\n{migrations}'
            'frontend:\n  delivery:\n    type: none\n',
            encoding='utf-8',
        )
        (source / '__init__.py').write_text(
            'import os\nfrom contextlib import asynccontextmanager\nfrom fastapi import FastAPI\n'
            'from plugins.core.sdk import PluginDefinition\n'
            f'LOADED_VERSION = {version!r}\n'
            'def create_plugin(host):\n    assert not host.startup_write_enabled\n'
            '    return PluginDefinition(app_factory=create_app)\n'
            'def create_app(host):\n    @asynccontextmanager\n    async def lifespan(app):\n'
            '        if os.environ.get("RUOYI_PLUGIN_IT_FAIL_WORKER") == "1":\n'
            '            raise RuntimeError("intentional integration lifespan failure")\n'
            '        yield\n    return FastAPI(lifespan=lifespan)\n',
            encoding='utf-8',
        )
        archive = root / f'{version}.rpk'
        build_artifact(source, archive, private_key, 'integration')
        archives.append(archive)
    return archives[0], archives[1]


async def test_real_lock(spec: RunSpec) -> None:
    """
    验证真实 Redis 锁的互斥、自动续租和按所有者释放行为。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :return: None
    """
    from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock  # noqa: PLC0415

    client = redis_client()
    key = f'{spec.redis_prefix}lifecycle:global'
    lock = RedisPluginLifecycleLock(expire_seconds=3)
    try:
        async with lock.lock(PLUGIN_ID, 'renewal_check') as held:
            check(held.acquired, 'Initial real Redis lock acquisition failed')
            await asyncio.sleep(4.2)
            check(await client.ttl(key) > 0, 'Real lock renewal did not keep the lease alive')
            async with RedisPluginLifecycleLock().lock(PLUGIN_ID, 'contender') as second:
                check(not second.acquired, 'NX lock allowed a competing holder')
        check(await client.get(key) is None, 'Owned lock was not released')
        async with lock.lock(PLUGIN_ID, 'compare_delete_check') as held:
            check(held.acquired, 'Compare-delete setup could not acquire lock')
            await client.set(key, 'replacement-owner', ex=10)
        check(await client.get(key) == 'replacement-owner', 'Lua release deleted a replacement owner')
        await client.delete(key)
    finally:
        await client.aclose()
    emit('redis_lock', nx=True, renewal=True, compareDelete=True)


async def maintenance_process(spec: RunSpec, action: str, digest: str | None) -> dict[str, Any]:
    """
    在独立进程中准备、选择或回滚目标制品。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param action: 当前命令需要执行的操作
    :param digest: 已导入制品的 SHA256 摘要
    :return: 维护操作结果
    """
    from plugins.core.deployment.service import PluginDeploymentService  # noqa: PLC0415
    from plugins.core.management.dao.release_dao import PluginReleaseDao  # noqa: PLC0415

    engine = database_engine(spec)
    config, sessions = wire_runtime(spec, engine)
    service = PluginDeploymentService(config, session_factory=sessions)
    try:
        if action == 'prepare':
            return await service.prepare(PLUGIN_ID, str(digest), maintenance=True, actor='real-service-it')
        async with sessions() as db:
            release = await PluginReleaseDao.get_release(db, PLUGIN_ID)
            generation = release.generation
        if action == 'select':
            return await service.select(
                PLUGIN_ID,
                str(digest),
                expected_generation=generation,
                expected_workers=2,
                maintenance=True,
                actor='real-service-it',
            )
        if action == 'rollback':
            return await service.rollback(
                PLUGIN_ID,
                expected_generation=generation,
                schema_compatible=True,
                maintenance=True,
                actor='real-service-it',
            )
        raise ValueError('Unknown isolated maintenance action')
    finally:
        await engine.dispose()


async def worker_process(spec: RunSpec, queue: Any, stop: Any, launch: str, fail: bool) -> None:
    """
    启动真实插件运行流程，上报实际加载结果并等待独立停止事件。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param queue: 仅传递结果和脱敏错误的进程队列
    :param stop: 当前 worker 独享的停止事件
    :param launch: 本轮 worker 启动标识
    :param fail: 是否让当前 worker 在插件启动时主动失败
    :return: None
    """
    from fastapi import FastAPI  # noqa: PLC0415

    from plugins.core.deployment.worker import PluginReleaseWorker  # noqa: PLC0415
    from plugins.core.management.service.startup_gateway import (  # noqa: PLC0415
        PluginManagementRouteStateGateway,
        PluginManagementStartupGateway,
    )
    from plugins.core.runtime.application import PluginApplicationRuntime  # noqa: PLC0415
    from plugins.core.runtime.bootstrap import PluginRuntimeBuilder  # noqa: PLC0415
    from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock  # noqa: PLC0415
    from plugins.core.runtime.startup import PluginRuntimeStartupManager  # noqa: PLC0415

    os.environ['RUOYI_PLUGIN_IT_FAIL_WORKER'] = '1' if fail else '0'
    engine = database_engine(spec)
    config, sessions = wire_runtime(spec, engine)
    client = redis_client()
    app = FastAPI()
    app.state.redis = client
    builder = PluginRuntimeBuilder(config.backend_root)
    manager = PluginRuntimeStartupManager(
        builder,
        management_gateway=PluginManagementStartupGateway(),
        route_state_gateway=PluginManagementRouteStateGateway(),
        default_enabled_builtin_plugin_ids=set(),
    )
    worker = PluginReleaseWorker(config, session_factory=sessions)
    runtime = PluginApplicationRuntime(
        manager,
        ready_key=f'{spec.redis_prefix}ready',
        startup_generation=launch,
        lifecycle_lock=RedisPluginLifecycleLock(expire_seconds=6),
        release_worker=worker,
        ready_wait_timeout_seconds=60,
        ready_wait_interval_seconds=0.1,
    )
    runtime.bind_app(app)

    async def create_tables() -> None:
        # 表结构已经准备完成，此处只通过真实 Redis 统计启动写入回调的执行次数。
        """
        通过 Redis 计数验证只有启动写入进程执行此回调。

        :return: None
        """
        await client.incr(f'{spec.redis_prefix}writer:{launch}')

    started = False
    try:
        await runtime.startup(app, create_tables=create_tables)
        started = True
        target = worker.targets[0]
        module = sys.modules[f'plugins.{PLUGIN_ID}']
        loaded = app.state.plugin_explicit_runtime.loaded[PLUGIN_ID]
        await app.state.plugin_diagnostics_reporter.publish()
        queue.put(
            {
                'ok': True,
                'workerId': worker.worker_id,
                'version': module.LOADED_VERSION,
                'modulePath': module.__file__,
                'active': loaded.active,
                'digest': target.digest,
                'artifactGeneration': target.generation,
                'writer': bool(app.state.plugin_startup_write_enabled),
                'failed': fail,
                'generation': app.state.plugin_startup_generation,
            }
        )
        await asyncio.to_thread(stop.wait)
    finally:
        if started:
            await runtime.shutdown(app)
        await client.aclose()
        await engine.dispose()


def child_entry(spec: RunSpec, queue: Any, action: str, payload: Any, stop: Any = None) -> None:
    """
    执行隔离子进程入口，参数和结果队列均不传递连接密码。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param queue: 仅传递结果和脱敏错误的进程队列
    :param action: 当前命令需要执行的操作
    :param payload: 当前子进程操作需要的参数
    :param stop: 当前 worker 独享的停止事件
    :return: None
    """
    try:
        configure_process(spec)
        if action == 'worker':
            asyncio.run(worker_process(spec, queue, stop, payload['launch'], payload['fail']))
        else:
            result = asyncio.run(maintenance_process(spec, action, payload))
            queue.put({'ok': True, 'result': result})
    except BaseException as exc:
        queue.put({'ok': False, 'action': action, 'error': safe_error(exc)})
        raise SystemExit(1) from None


async def run_maintenance(spec: RunSpec, action: str, digest: str | None = None) -> dict[str, Any]:
    """
    启动独立维护进程并回收进程与队列资源。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param action: 当前命令需要执行的操作
    :param digest: 已导入制品的 SHA256 摘要
    :return: 维护进程返回的操作结果
    """
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    process = context.Process(target=child_entry, args=(spec, queue, action, digest))
    process.start()
    try:
        result = await asyncio.to_thread(queue.get, True, 90)
        check(result['ok'], str(result))
        await asyncio.to_thread(process.join, 20)
        check(process.exitcode == 0, f'Maintenance process did not exit cleanly: {process.exitcode}')
        return result['result']
    finally:
        if process.is_alive():
            process.terminate()
            await asyncio.to_thread(process.join, 10)
        queue.close()
        queue.join_thread()


class Workers:
    """
    负责全部验收 worker 的启动与回收，包括启动未完成的进程组。
    """

    def __init__(self, spec: RunSpec, *, one_fails: bool = False) -> None:
        """
        创建两个 worker 及各自独立的停止事件。

        :param spec: 当前验收的隔离运行信息，不包含连接密码
        :param one_fails: 是否让第二个 worker 主动触发启动失败
        :return: None
        """
        self.spec = spec
        self.launch = uuid4().hex
        self.context = multiprocessing.get_context('spawn')
        self.queue = self.context.Queue()
        # 强制终止正在 Event.wait() 的进程可能残留 Condition 等待状态。
        # 每个 worker 使用独立停止事件，避免影响其他进程的正常退出。
        self.stops = [self.context.Event() for _ in range(EXPECTED_WORKER_COUNT)]
        self.processes = [
            self.context.Process(
                target=child_entry,
                args=(
                    spec,
                    self.queue,
                    'worker',
                    {'launch': self.launch, 'fail': one_fails and index == 1},
                    self.stops[index],
                ),
            )
            for index in range(EXPECTED_WORKER_COUNT)
        ]
        self.reports: list[dict[str, Any]] = []
        self.killed: set[int] = set()

    async def __aenter__(self) -> Workers:
        """
        启动全部 worker，并验证身份、发布代际和单写入进程约束。

        :return: 已启动并收集上报结果的 worker 管理器
        """
        from plugins.core.runtime.diagnostics_store import (  # noqa: PLC0415
            diagnostics_namespace,
            read_runtime_diagnostics,
        )

        try:
            for process in self.processes:
                process.start()
            self.reports = [await asyncio.to_thread(self.queue.get, True, 90) for _ in self.processes]
            check(all(item.get('ok') for item in self.reports), str(self.reports))
            check(len({item['workerId'] for item in self.reports}) == EXPECTED_WORKER_COUNT, 'Worker IDs collided')
            check(len({item['generation'] for item in self.reports}) == 1, 'Workers used different startup generations')
            check(sum(item['writer'] for item in self.reports) == 1, 'Expected one startup writer and one reader')
            client = redis_client()
            try:
                check(
                    await client.get(f'{self.spec.redis_prefix}writer:{self.launch}') == '1',
                    'Writer callback ran more than once',
                )
                diagnostics = await read_runtime_diagnostics(
                    client, diagnostics_namespace(f'{self.spec.redis_prefix}ready'), PLUGIN_ID
                )
                check(diagnostics['scope'] == 'reporting_workers', 'Runtime diagnostics are unavailable')
                check(diagnostics['currentWorkerId'] is None, 'Maintenance reader fabricated a local worker')
                observed = {item['workerId']: item for item in diagnostics['workers']}
                check(
                    set(observed) == {item['workerId'] for item in self.reports},
                    'Runtime diagnostics do not match the live child processes',
                )
                for report in self.reports:
                    actual = observed[report['workerId']]['plugins']
                    check(len(actual) == 1, 'Runtime diagnostics omitted the loaded plugin')
                    check(
                        actual[0]['version'] == report['version']
                        and actual[0]['digest'] == report['digest']
                        and actual[0]['generation'] == report['artifactGeneration']
                        and actual[0]['active'] == report['active']
                        and actual[0]['ready'] == report['active'],
                        'Runtime diagnostics disagree with the actual loaded plugin',
                    )
                emit('runtime_diagnostics', launch=self.launch, observedWorkers=len(observed), actualStateVerified=True)
            finally:
                await client.aclose()
            return self
        except BaseException:
            await self.close()
            raise

    async def kill_failed_worker(self) -> None:
        # 预设失败的是第二个进程，不能根据队列上报顺序判断进程身份。
        """
        终止预设失败的第二个 worker，供心跳过期验收使用。

        :return: None
        """
        process = self.processes[1]
        self.killed.add(1)
        process.terminate()
        await asyncio.to_thread(process.join, 10)
        check(not process.is_alive(), 'Failed worker did not terminate')

    async def close(self) -> None:
        """
        停止仍存活的 worker 并关闭队列，异常退出时给出验收错误。

        :return: None
        """
        for index, process in enumerate(self.processes):
            if index not in self.killed and process.pid is not None and process.is_alive():
                self.stops[index].set()
        bad_exits = []
        for index, process in enumerate(self.processes):
            if process.pid is None:
                continue
            await asyncio.to_thread(process.join, 20)
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 10)
                bad_exits.append(index)
            elif index not in self.killed and process.exitcode != 0:
                bad_exits.append(index)
        self.queue.close()
        self.queue.join_thread()
        check(not bad_exits, f'Workers failed to stop cleanly: {bad_exits}')

    async def __aexit__(self, *args: Any) -> None:
        """
        离开上下文时回收全部 worker 和队列。

        :param args: 异步上下文管理协议传入的异常信息
        :return: None
        """
        await self.close()


async def release_state(service: Any) -> dict[str, Any]:
    """
    读取测试插件唯一的聚合发布状态。

    :param service: 连接到隔离数据库的发布服务
    :return: 测试插件的发布状态
    """
    result = await service.status(PLUGIN_ID)
    check(len(result['releases']) == 1, 'Expected exactly one integration release')
    return result['releases'][0]


async def expect_maintenance_blocked(service: Any, digest: str) -> None:
    """
    验证存在存活 worker 时维护准备会被拒绝。

    :param service: 连接到隔离数据库的发布服务
    :param digest: 已导入制品的 SHA256 摘要
    :return: None
    """
    try:
        await service.prepare(PLUGIN_ID, digest, maintenance=True)
    except ValueError as exc:
        check('存活' in str(exc), f'Maintenance failed for the wrong reason: {safe_error(exc)}')
    else:
        raise AssertionError('Maintenance preparation ignored live host workers')


async def verify_migrations(sessions: Any, installed: str, rows: int) -> None:
    """
    核对数据准备版本、迁移探针记录和维护审计。

    :param sessions: 隔离数据库的异步会话工厂
    :param installed: 预期数据库安装版本
    :param rows: 预期迁移探针数据和迁移历史的记录数
    :return: None
    """
    from sqlalchemy import select, text  # noqa: PLC0415

    from plugins.core.management.dao.dao import PluginDao  # noqa: PLC0415
    from plugins.core.management.entity.do.models import SysPluginMigration, SysPluginOperationLog  # noqa: PLC0415

    async with sessions() as db:
        plugin = await PluginDao.get_plugin_by_id(db, PLUGIN_ID)
        check(plugin.installed_version == installed, f'Unexpected installedVersion: {plugin.installed_version}')
        check(await db.scalar(text('SELECT COUNT(*) FROM plugin_it_probe')) == rows, 'Migration probe rows changed')
        migrations = (await db.scalars(select(SysPluginMigration))).all()
        check(
            len(migrations) == rows and all(item.status == 'success' for item in migrations),
            'Migration evidence missing',
        )
        logs = (await db.scalars(select(SysPluginOperationLog))).all()
        check(any(item.operation == 'install' for item in logs), 'Real maintenance install audit missing')
        if installed == '2.0.0':
            check(any(item.operation == 'upgrade' for item in logs), 'Real maintenance upgrade audit missing')


async def exercise_release(spec: RunSpec, engine: Any) -> None:
    """
    依次验收发布、升级、代码回滚以及失败和过期 worker 状态。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :param engine: 隔离数据库的异步连接池
    :return: None
    """
    from plugins.core.deployment.service import PluginDeploymentService  # noqa: PLC0415

    config, sessions = wire_runtime(spec, engine)
    service = PluginDeploymentService(config, session_factory=sessions)
    archive1, archive2 = make_artifacts(spec)
    digest1 = (await service.catalog.import_artifact(archive1))['digest']
    digest2 = (await service.catalog.import_artifact(archive2))['digest']
    await test_real_lock(spec)
    await run_maintenance(spec, 'prepare', digest1)
    await verify_migrations(sessions, '1.0.0', 1)
    await run_maintenance(spec, 'select', digest1)
    async with Workers(spec) as workers:
        state = await release_state(service)
        check(
            state['status'] == 'active' and state['healthyWorkers'] == EXPECTED_WORKER_COUNT,
            f'Initial release not active: {state}',
        )
        check(
            all(
                item['version'] == '1.0.0' and item['digest'] == digest1 and item['active'] for item in workers.reports
            ),
            'Wrong initial runtime code',
        )
        check(
            all(Path(item['modulePath']).is_relative_to(config.store_root) for item in workers.reports),
            'Worker loaded outside artifact store',
        )
        await expect_maintenance_blocked(service, digest2)
        emit('initial_active', workers=2, writer=1, reader=1, maintenanceBlocked=True)
    await run_maintenance(spec, 'prepare', digest2)
    await verify_migrations(sessions, '2.0.0', 2)
    await run_maintenance(spec, 'select', digest2)
    async with Workers(spec) as workers:
        state = await release_state(service)
        check(state['status'] == 'active', f'Upgrade did not converge: {state}')
        check(
            all(item['version'] == '2.0.0' and item['digest'] == digest2 for item in workers.reports),
            'Upgrade reused old code',
        )
        emit('upgrade_active', codeVersion='2.0.0', installedVersion=state['installedVersion'])
    await run_maintenance(spec, 'rollback')
    await verify_migrations(sessions, '2.0.0', 2)
    async with Workers(spec) as workers:
        state = await release_state(service)
        check(
            state['status'] == 'active' and state['installedVersion'] == '2.0.0', f'Rollback lost schema state: {state}'
        )
        check(
            all(item['version'] == '1.0.0' and item['digest'] == digest1 for item in workers.reports),
            'Rollback did not load prior artifact',
        )
        emit('rollback_active', codeVersion='1.0.0', installedVersion='2.0.0', migrationRows=2)
    async with Workers(spec, one_fails=True) as workers:
        state = await release_state(service)
        check(
            state['status'] == 'partial' and state['healthyWorkers'] == 1 and state['failedWorkers'] == 1,
            f'Failure reported as healthy: {state}',
        )
        await workers.kill_failed_worker()
        await asyncio.sleep(TTL_SECONDS + 1)
        state = await release_state(service)
        check(
            state['status'] == 'partial' and state['healthyWorkers'] == 1 and state['staleWorkers'] >= 1,
            f'Expired process was counted live: {state}',
        )
        check(state['liveWorkers'] == 1, 'Dead worker still contributes to live count')
        emit('partial_and_stale', healthyWorkers=1, liveWorkers=1, staleWorkers=state['staleWorkers'])
    await service.catalog.get(digest1)
    await service.catalog.get(digest2)
    check(not list(config.store_root.rglob('*.pyc')), 'Artifact runtime produced bytecode inside immutable store')
    check(f'plugins.{PLUGIN_ID}' not in sys.modules, 'Supervisor imported plugin runtime code')


async def run(spec: RunSpec) -> None:
    """
    创建隔离资源并执行完整验收，结束时回收本轮资源。

    :param spec: 当前验收的隔离运行信息，不包含连接密码
    :return: None
    """
    task_source = BACKEND_ROOT / 'plugins' / 'examples' / 'python' / 'task_demo'
    if not (task_source / 'web' / 'dist' / 'index.html').is_file():
        raise ValueError('请先按 task_demo/README.md 安装前端依赖并构建 web/dist，再运行真实发布验收')
    configure_process(spec)
    admin = database_engine(spec, admin=True)
    engine = None
    created = False
    cleanup_errors = []
    try:
        await create_isolated_database(spec, admin)
        created = True
        emit('isolated_database_created', engine=spec.engine, database=spec.database, redisPrefix=spec.redis_prefix)
        engine = database_engine(spec)
        await prepare_schema(spec, engine)
        await exercise_release(spec, engine)
        from plugins.core.deployment.service import PluginDeploymentService  # noqa: PLC0415
        from scripts.plugin_task_integration import exercise_task_delivery  # noqa: PLC0415

        config, sessions = wire_runtime(spec, engine)
        task_result = await exercise_task_delivery(
            PluginDeploymentService(config, session_factory=sessions),
            sessions,
            task_source,
            Path(spec.root) / 'task-delivery',
        )
        emit('task_delivery', **task_result)
    finally:
        if engine is not None:
            try:
                await engine.dispose()
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        try:
            removed = await clear_own_redis_keys(spec)
            emit('redis_cleanup', removedKeys=removed)
        except Exception as exc:
            cleanup_errors.append(safe_error(exc))
        if created:
            try:
                await drop_isolated_database(spec, admin)
                emit('database_cleanup', database=spec.database, dropped=True)
            except Exception as exc:
                cleanup_errors.append(safe_error(exc))
        try:
            await admin.dispose()
        except Exception as exc:
            cleanup_errors.append(safe_error(exc))
        if cleanup_errors:
            raise RuntimeError(f'Isolated resources require cleanup: {cleanup_errors}')


def main(argv: list[str] | None = None) -> int:
    """
    校验显式授权后运行验收，并输出脱敏的退出结果。

    :param argv: 命令行参数；未传入时读取当前进程参数
    :return: 进程退出码
    """
    parser = argparse.ArgumentParser(
        description=(
            '需显式授权的真实 Redis 与 MySQL/PostgreSQL 插件发布验收脚本。\n\n'
            '运行前须按 plugins/examples/python/task_demo/README.md 构建任务示例的 web/dist。\n'
            '仅用于研发验收；通过 RUOYI_PLUGIN_IT_ALLOW=1 显式开启。导入本模块不会加载宿主配置、\n'
            '建立连接或读取应用的 .env 文件。'
        )
    )
    parser.add_argument('--engine', required=True, choices=('mysql', 'postgresql'))
    args = parser.parse_args(argv)
    try:
        require_opt_in(args.engine)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='ruoyi_plugin_it_') as directory:
            spec = RunSpec(args.engine, uuid4().hex, str(Path(directory).resolve()))
            asyncio.run(run(spec))
        emit('passed', engine=args.engine, elapsedSeconds=round(time.monotonic() - started, 2))
        return 0
    except BaseException as exc:
        emit('failed', error=safe_error(exc))
        return 1


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
