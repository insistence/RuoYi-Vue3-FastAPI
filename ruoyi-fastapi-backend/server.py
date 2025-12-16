from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, applications
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse

from config.env import AppConfig
from config.get_db import init_create_table
from config.get_redis import RedisUtil
from config.get_scheduler import SchedulerUtil
from exceptions.handle import handle_exception
from middlewares.handle import handle_middleware
from module_admin.controller.cache_controller import cache_controller
from module_admin.controller.captcha_controller import captcha_controller
from module_admin.controller.common_controller import common_controller
from module_admin.controller.config_controller import config_controller
from module_admin.controller.dept_controller import dept_controller
from module_admin.controller.dict_controller import dict_controller
from module_admin.controller.job_controller import job_controller
from module_admin.controller.log_controller import log_controller
from module_admin.controller.login_controller import login_controller
from module_admin.controller.menu_controller import menu_controller
from module_admin.controller.notice_controller import notice_controller
from module_admin.controller.online_controller import online_controller
from module_admin.controller.post_controller import post_controller
from module_admin.controller.role_controller import role_controller
from module_admin.controller.server_controller import server_controller
from module_admin.controller.user_controller import user_controller
from module_generator.controller.gen_controller import gen_controller
from sub_applications.handle import handle_sub_applications
from utils.common_util import worship
from utils.log_util import logger


# 生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(f'⏰️ {AppConfig.app_name}开始启动')
    worship()
    await init_create_table()
    app.state.redis = await RedisUtil.create_redis_pool()
    await RedisUtil.init_sys_dict(app.state.redis)
    await RedisUtil.init_sys_config(app.state.redis)
    await SchedulerUtil.init_system_scheduler()
    logger.info(f'🚀 {AppConfig.app_name}启动成功')
    yield
    await RedisUtil.close_redis_pool(app)
    await SchedulerUtil.close_system_scheduler()


def setup_docs_static_resources(
    redoc_js_url: str = 'https://registry.npmmirror.com/redoc/2/files/bundles/redoc.standalone.js',
    redoc_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
    swagger_js_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui-bundle.js',
    swagger_css_url: str = 'https://registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui.css',
    swagger_favicon_url: str = 'https://fastapi.tiangolo.com/img/favicon.png',
) -> None:
    """
    配置文档静态资源

    :param redoc_js_url: 用于加载ReDoc JavaScript的URL
    :param redoc_favicon_url: ReDoc要使用的favicon的URL
    :param swagger_js_url: 用于加载Swagger UI JavaScript的URL
    :param swagger_css_url: 用于加载Swagger UI CSS的URL
    :param swagger_favicon_url: Swagger UI要使用的favicon的URL
    :return:
    """

    def redoc_monkey_patch(*args, **kwargs) -> HTMLResponse:
        return get_redoc_html(
            *args,
            **kwargs,
            redoc_js_url=redoc_js_url,
            redoc_favicon_url=redoc_favicon_url,
        )

    def swagger_ui_monkey_patch(*args, **kwargs) -> HTMLResponse:
        return get_swagger_ui_html(
            *args,
            **kwargs,
            swagger_js_url=swagger_js_url,
            swagger_css_url=swagger_css_url,
            swagger_favicon_url=swagger_favicon_url,
        )

    applications.get_redoc_html = redoc_monkey_patch
    applications.get_swagger_ui_html = swagger_ui_monkey_patch


def register_routers(app: FastAPI) -> None:
    """
    注册路由

    :param app: FastAPI对象
    :return:
    """
    # 加载路由列表
    controller_list = [
        {'router': login_controller, 'tags': ['登录模块']},
        {'router': captcha_controller, 'tags': ['验证码模块']},
        {'router': user_controller, 'tags': ['系统管理-用户管理']},
        {'router': role_controller, 'tags': ['系统管理-角色管理']},
        {'router': menu_controller, 'tags': ['系统管理-菜单管理']},
        {'router': dept_controller, 'tags': ['系统管理-部门管理']},
        {'router': post_controller, 'tags': ['系统管理-岗位管理']},
        {'router': dict_controller, 'tags': ['系统管理-字典管理']},
        {'router': config_controller, 'tags': ['系统管理-参数管理']},
        {'router': notice_controller, 'tags': ['系统管理-通知公告管理']},
        {'router': log_controller, 'tags': ['系统管理-日志管理']},
        {'router': online_controller, 'tags': ['系统监控-在线用户']},
        {'router': job_controller, 'tags': ['系统监控-定时任务']},
        {'router': server_controller, 'tags': ['系统监控-服务监控']},
        {'router': cache_controller, 'tags': ['系统监控-缓存监控']},
        {'router': common_controller, 'tags': ['通用模块']},
        {'router': gen_controller, 'tags': ['代码生成']},
    ]

    for controller in controller_list:
        app.include_router(router=controller.get('router'), tags=controller.get('tags'))


def create_app() -> FastAPI:
    """
    创建FastAPI应用

    :return: FastAPI对象
    """
    # 配置文档静态资源
    setup_docs_static_resources()
    # 初始化FastAPI对象
    app = FastAPI(
        title=AppConfig.app_name,
        description=f'{AppConfig.app_name}接口文档',
        version=AppConfig.app_version,
        lifespan=lifespan,
    )

    # 挂载子应用
    handle_sub_applications(app)
    # 加载中间件处理方法
    handle_middleware(app)
    # 加载全局异常处理方法
    handle_exception(app)
    # 注册路由
    register_routers(app)

    return app
