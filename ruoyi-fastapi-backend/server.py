import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.constant import LockConstant
from common.router import auto_register_routers
from config.env import AppConfig
from config.get_db import close_async_engine, init_create_table
from config.get_redis import RedisUtil
from config.get_scheduler import SchedulerUtil
from exceptions.handle import handle_exception
from middlewares.handle import handle_middleware
from module_admin.service.log_service import LogAggregatorService
from sub_applications.handle import handle_sub_applications
from utils.common_util import worship
from utils.log_util import logger
from utils.server_util import APIDocsUtil, IPUtil, StartupUtil
from utils.transport_crypto_util import TransportKeyProvider


async def _start_background_tasks(app: FastAPI) -> None:
    """
    启动应用后台任务

    :param app: FastAPI对象
    :return: None
    """
    await SchedulerUtil.init_system_scheduler(app.state.redis)
    app.state.log_aggregator_task = asyncio.create_task(LogAggregatorService.consume_stream(app.state.redis))


async def _stop_background_tasks(app: FastAPI) -> None:
    """
    停止应用后台任务并释放资源

    :param app: FastAPI对象
    :return: None
    """
    log_task = getattr(app.state, 'log_aggregator_task', None)
    if log_task:
        log_task.cancel()
        try:
            await log_task
        except asyncio.CancelledError:
            pass
    lock_task = getattr(app.state, 'lock_renewal_task', None)
    if lock_task:
        lock_task.cancel()
        try:
            await lock_task
        except asyncio.CancelledError:
            pass
    await RedisUtil.close_redis_pool(app)
    await SchedulerUtil.close_system_scheduler()
    await close_async_engine()


# 生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理

    :param app: FastAPI对象
    :return: None
    """
    app.state.redis = await RedisUtil.create_redis_pool(log_enabled=False)
    startup_log_enabled = await StartupUtil.acquire_startup_log_gate(
        redis=app.state.redis,
        lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
        worker_id=SchedulerUtil._worker_id,
        lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
    )
    app.state.startup_log_enabled = startup_log_enabled

    # 获取锁成功后立即启动锁续期任务，避免初始化时间过长导致锁过期
    if startup_log_enabled:
        app.state.lock_renewal_task = StartupUtil.start_lock_renewal(
            redis=app.state.redis,
            lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
            worker_id=SchedulerUtil._worker_id,
            lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
            interval_seconds=LockConstant.LOCK_RENEWAL_INTERVAL,
            on_lock_lost=SchedulerUtil.on_lock_lost,
        )

    with logger.contextualize(startup_phase=True, startup_log_enabled=startup_log_enabled):
        logger.info(f'⏰️ {AppConfig.app_name}开始启动')
        if startup_log_enabled:
            worship()
        TransportKeyProvider.validate_runtime_configuration()
        await init_create_table()
        await RedisUtil.check_redis_connection(app.state.redis, log_enabled=startup_log_enabled)
        await RedisUtil.init_sys_dict(app.state.redis)
        await RedisUtil.init_sys_config(app.state.redis)
        await _start_background_tasks(app)

    if startup_log_enabled:
        # 短暂等待确保下面的启动日志在最后打印
        await asyncio.sleep(0.5)
        logger.info(f'🚀 {AppConfig.app_name}启动成功')
        host = AppConfig.app_host
        port = AppConfig.app_port
        if host == '0.0.0.0':
            local_ip = IPUtil.get_local_ip()
            network_ips = IPUtil.get_network_ips()
        else:
            local_ip = host
            network_ips = [host]

        app_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}</cyan>']
        app_links.extend(f'📡 Network:  <cyan>http://{ip}:{port}</cyan>' for ip in network_ips)
        logger.opt(colors=True).info('💻 应用地址:\n' + '\n'.join(app_links))

        if not AppConfig.app_disable_swagger:
            swagger_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}{APIDocsUtil.docs_url()}</cyan>']
            swagger_links.extend(
                f'📡 Network:  <cyan>http://{ip}:{port}{APIDocsUtil.docs_url()}</cyan>' for ip in network_ips
            )
            logger.opt(colors=True).info('📄 Swagger文档:\n' + '\n'.join(swagger_links))

        if not AppConfig.app_disable_redoc:
            redoc_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}{APIDocsUtil.redoc_url()}</cyan>']
            redoc_links.extend(
                f'📡 Network:  <cyan>http://{ip}:{port}{APIDocsUtil.redoc_url()}</cyan>' for ip in network_ips
            )
            logger.opt(colors=True).info('📚 ReDoc文档:\n' + '\n'.join(redoc_links))
    yield
    shutdown_log_enabled = getattr(app.state, 'startup_log_enabled', False)
    with logger.contextualize(startup_phase=True, startup_log_enabled=shutdown_log_enabled):
        await _stop_background_tasks(app)


def create_app() -> FastAPI:
    """
    创建FastAPI应用

    :return: FastAPI对象
    """
    # 配置API文档静态资源
    APIDocsUtil.setup_docs_static_resources()
    # 初始化FastAPI对象
    app = FastAPI(
        title=AppConfig.app_name,
        description=f'{AppConfig.app_name}接口文档',
        version=AppConfig.app_version,
        lifespan=lifespan,
        openapi_url=APIDocsUtil.proxy_openapi_url(),
        docs_url=APIDocsUtil.proxy_docs_url(),
        redoc_url=APIDocsUtil.proxy_redoc_url(),
        swagger_ui_oauth2_redirect_url=APIDocsUtil.proxy_oauth2_redirect_url(),
    )

    # 自定义API文档路由，修复无法直接通过后端地址访问文档的问题
    APIDocsUtil.custom_api_docs_router(app)

    # 挂载子应用
    handle_sub_applications(app)
    # 加载中间件处理方法
    handle_middleware(app)
    # 加载全局异常处理方法
    handle_exception(app)
    # 自动注册路由
    auto_register_routers(app)

    return app
