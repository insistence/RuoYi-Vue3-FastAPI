from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager
from module_admin.controller.login_controller import loginController
from module_admin.controller.captcha_controller import captchaController
from module_admin.controller.user_controller import userController
from module_admin.controller.menu_controller import menuController
from module_admin.controller.dept_controller import deptController
from module_admin.controller.role_controller import roleController
from module_admin.controller.post_controler import postController
from module_admin.controller.dict_controller import dictController
from module_admin.controller.config_controller import configController
from module_admin.controller.notice_controller import noticeController
from module_admin.controller.log_controller import logController
from module_admin.controller.online_controller import onlineController
from module_admin.controller.job_controller import jobController
from module_admin.controller.server_controller import serverController
from module_admin.controller.cache_controller import cacheController
from module_admin.controller.common_controller import commonController
from config.env import AppConfig, UploadConfig
from config.get_redis import RedisUtil
from config.get_db import init_create_table
from config.get_scheduler import SchedulerUtil
from utils.response_util import *
from utils.log_util import logger
from utils.common_util import worship


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"{AppConfig.app_name}开始启动")
    worship()
    await init_create_table()
    app.state.redis = await RedisUtil.create_redis_pool()
    await RedisUtil.init_sys_dict(app.state.redis)
    await RedisUtil.init_sys_config(app.state.redis)
    await SchedulerUtil.init_system_scheduler()
    logger.info(f"{AppConfig.app_name}启动成功")
    yield
    await RedisUtil.close_redis_pool(app)
    await SchedulerUtil.close_system_scheduler()


app = FastAPI(
    title=AppConfig.app_name,
    description=f'{AppConfig.app_name}接口文档',
    version=AppConfig.app_version,
    lifespan=lifespan
)

# 前端页面url
origins = [
    "http://localhost:81",
    "http://127.0.0.1:81",
]

# 后台api允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件路径
app.mount(f"{UploadConfig.UPLOAD_PREFIX}", StaticFiles(directory=f"{UploadConfig.UPLOAD_PATH}"), name="profile")


# 自定义token检验异常
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return ResponseUtil.unauthorized(data=exc.data, msg=exc.message)


# 自定义权限检验异常
@app.exception_handler(PermissionException)
async def permission_exception_handler(request: Request, exc: PermissionException):
    return ResponseUtil.forbidden(data=exc.data, msg=exc.message)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        content=jsonable_encoder({"message": exc.detail, "code": exc.status_code}),
        status_code=exc.status_code
    )


controller_list = [
    {'router': loginController, 'tags': ['登录模块']},
    {'router': captchaController, 'tags': ['验证码模块']},
    {'router': userController, 'tags': ['系统管理-用户管理']},
    {'router': roleController, 'tags': ['系统管理-角色管理']},
    {'router': menuController, 'tags': ['系统管理-菜单管理']},
    {'router': deptController, 'tags': ['系统管理-部门管理']},
    {'router': postController, 'tags': ['系统管理-岗位管理']},
    {'router': dictController, 'tags': ['系统管理-字典管理']},
    {'router': configController, 'tags': ['系统管理-参数管理']},
    {'router': noticeController, 'tags': ['系统管理-通知公告管理']},
    {'router': logController, 'tags': ['系统管理-日志管理']},
    {'router': onlineController, 'tags': ['系统监控-在线用户']},
    {'router': jobController, 'tags': ['系统监控-定时任务']},
    {'router': serverController, 'tags': ['系统监控-菜单管理']},
    {'router': cacheController, 'tags': ['系统监控-缓存监控']},
    {'router': commonController, 'tags': ['通用模块']}
]

for controller in controller_list:
    app.include_router(router=controller.get('router'), tags=controller.get('tags'))

if __name__ == '__main__':
    uvicorn.run(app='app:app', host=AppConfig.app_host, port=AppConfig.app_port, root_path=AppConfig.app_root_path, reload=AppConfig.app_reload)
