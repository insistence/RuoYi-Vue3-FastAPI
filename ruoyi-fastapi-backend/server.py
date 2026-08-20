import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.constant import LockConstant
from common.router import auto_register_routers
from config.database import DataSourceRegistry
from config.env import AppConfig
from config.get_redis import RedisUtil
from config.get_scheduler import SchedulerUtil
from config.lifecycle import init_create_table
from exceptions.handle import handle_exception
from middlewares.handle import handle_middleware
from module_admin.service.log_service import LogAggregatorService
from plugins.core.runtime.application import get_plugin_application_runtime
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
    try:
        log_task = getattr(app.state, 'log_aggregator_task', None)
        if log_task:
            log_task.cancel()
            try:
                await log_task
            except asyncio.CancelledError:
                pass
    finally:
        try:
            # Scheduler负责停止续期并释放Application租约，必须先于Redis连接池关闭。
            await SchedulerUtil.close_system_scheduler()
        finally:
            try:
                await RedisUtil.close_redis_pool(app)
            finally:
                await DataSourceRegistry.dispose_all()


async def _shutdown_application_runtime(app: FastAPI) -> None:
    """
    关闭插件运行时并保证基础设施资源始终释放。

    :param app: FastAPI对象
    :return: None
    """
    try:
        if getattr(app.state, 'plugin_application_runtime_started', False):
            await get_plugin_application_runtime().shutdown(app)
    finally:
        try:
            await _stop_background_tasks(app)
        finally:
            # 所有sink均使用enqueue=True，进程退出前必须等待插件Hook等尾部日志落盘。
            await logger.complete()


def _show_startup_addresses() -> None:
    """
    显示应用及接口文档访问地址

    :return: None
    """
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


# 生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理

    :param app: FastAPI对象
    :return: None
    """
    app.state.redis = None
    app.state.plugin_application_runtime_started = False
    try:
        app.state.redis = await RedisUtil.create_redis_pool(log_enabled=False)
        application_lock_owner_token = SchedulerUtil.get_application_lock_owner_token()
        application_leader = await StartupUtil.acquire_application_leader(
            redis=app.state.redis,
            lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
            owner_token=application_lock_owner_token,
            lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
        )
        app.state.application_leader = application_leader
        app.state.application_lock_owner_token = application_lock_owner_token

        # 获取锁成功后立即启动锁续期任务，避免初始化时间过长导致锁过期
        if application_leader:
            SchedulerUtil.start_application_lock_renewal(app.state.redis)

        await DataSourceRegistry.initialize()

        startup_logger = logger.bind(
            startup_phase='application_startup',
            startup_role='application_leader',
        )
        if application_leader:
            startup_logger.info(f'⏰️ {AppConfig.app_name}开始启动')
            worship()
        TransportKeyProvider.validate_runtime_configuration()
        await _initialize_application_runtime(app, application_leader=application_leader)

        # 初始化期间可能因续期失败失去租约；此时不得继续输出leader专属成功摘要。
        application_leader = application_leader and SchedulerUtil.is_application_leader()
        app.state.application_leader = application_leader
        if application_leader:
            # 短暂等待确保下面的启动日志在最后打印
            await asyncio.sleep(1)
            startup_logger.info(f'🚀 {AppConfig.app_name}启动成功')
            _show_startup_addresses()
        # 确保启动阶段的插件摘要在ASGI lifespan启动完成前已写入stdout和日志文件。
        await logger.complete()
        yield
    finally:
        if app.state.redis is None:
            await DataSourceRegistry.dispose_all()
            await logger.complete()
        else:
            await _shutdown_application_runtime(app)


async def _initialize_application_runtime(app: FastAPI, application_leader: bool) -> None:
    """
    初始化应用运行时资源。

    :param app: FastAPI对象
    :param application_leader: 当前worker是否为Application leader
    :return: None
    """
    plugin_runtime = get_plugin_application_runtime()
    plugin_runtime.prepare_metadata(app)

    await init_create_table(
        stage='platform',
        log_success_enabled=application_leader,
    )

    async def create_plugin_entity_tables() -> None:
        """在插件 writer 导入实体后同步插件表。"""
        await init_create_table(
            stage='plugin_entities',
            log_success_enabled=True,
        )

    await plugin_runtime.startup(
        app,
        create_tables=create_plugin_entity_tables,
    )
    app.state.plugin_application_runtime_started = True
    await RedisUtil.check_redis_connection(
        app.state.redis,
        log_enabled=application_leader,
        log_error_enabled=True,
    )
    await RedisUtil.init_sys_dict(app.state.redis)
    await RedisUtil.init_sys_config(app.state.redis)
    await _start_background_tasks(app)


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
    # 自动注册内置路由
    auto_register_routers(app)
    # 初始化插件应用运行时
    get_plugin_application_runtime().bind_app(app)

    return app
