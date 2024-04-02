from fastapi import APIRouter
from module_admin.service.login_service import *
from module_admin.entity.vo.login_vo import *
from module_admin.dao.login_dao import *
from module_admin.annotation.log_annotation import log_decorator
from config.env import JwtConfig, RedisInitKeyConfig
from utils.response_util import ResponseUtil
from utils.log_util import *
from datetime import timedelta


loginController = APIRouter()


@loginController.post("/login", response_model=Token)
@log_decorator(title='用户登录', business_type=0, log_type='login')
async def login(request: Request, form_data: CustomOAuth2PasswordRequestForm = Depends(), query_db: Session = Depends(get_db)):
    captcha_enabled = True if await request.app.state.redis.get(f"{RedisInitKeyConfig.SYS_CONFIG.get('key')}:sys.account.captchaEnabled") == 'true' else False
    user = UserLogin(
        userName=form_data.username,
        password=form_data.password,
        code=form_data.code,
        uuid=form_data.uuid,
        loginInfo=form_data.login_info,
        captchaEnabled=captcha_enabled
    )
    try:
        result = await LoginService.authenticate_user(request, query_db, user)
    except LoginException as e:
        return ResponseUtil.failure(msg=e.message)
    try:
        access_token_expires = timedelta(minutes=JwtConfig.jwt_expire_minutes)
        session_id = str(uuid.uuid4())
        access_token = LoginService.create_access_token(
            data={
                "user_id": str(result[0].user_id),
                "user_name": result[0].user_name,
                "dept_name": result[1].dept_name if result[1] else None,
                "session_id": session_id,
                "login_info": user.login_info
            },
            expires_delta=access_token_expires
        )
        if AppConfig.app_same_time_login:
            await request.app.state.redis.set(f"{RedisInitKeyConfig.ACCESS_TOKEN.get('key')}:{session_id}", access_token,
                                              ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes))
        else:
            # 此方法可实现同一账号同一时间只能登录一次
            await request.app.state.redis.set(f"{RedisInitKeyConfig.ACCESS_TOKEN.get('key')}:{result[0].user_id}", access_token,
                                              ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes))
        UserService.edit_user_services(query_db, EditUserModel(userId=result[0].user_id, loginDate=datetime.now(), type='status'))
        logger.info('登录成功')
        # 判断请求是否来自于api文档，如果是返回指定格式的结果，用于修复api文档认证成功后token显示undefined的bug
        request_from_swagger = request.headers.get('referer').endswith('docs') if request.headers.get('referer') else False
        request_from_redoc = request.headers.get('referer').endswith('redoc') if request.headers.get('referer') else False
        if request_from_swagger or request_from_redoc:
            return {'access_token': access_token, 'token_type': 'Bearer'}
        return ResponseUtil.success(
            msg='登录成功',
            dict_content={'token': access_token}
        )
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@loginController.get("/getInfo", response_model=CurrentUserModel)
async def get_login_user_info(request: Request, current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        logger.info('获取成功')
        return ResponseUtil.success(model_content=current_user)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@loginController.get("/getRouters")
async def get_login_user_routers(request: Request, current_user: CurrentUserModel = Depends(LoginService.get_current_user), query_db: Session = Depends(get_db)):
    try:
        logger.info('获取成功')
        user_routers = await LoginService.get_current_user_routers(current_user.user.user_id, query_db)
        return ResponseUtil.success(data=user_routers)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@loginController.post("/register", response_model=CrudResponseModel)
async def register_user(request: Request, user_register: UserRegister, query_db: Session = Depends(get_db)):
    try:
        user_register_result = await LoginService.register_user_services(request, query_db, user_register)
        if user_register_result.is_success:
            logger.info(user_register_result.message)
            return ResponseUtil.success(data=user_register_result, msg=user_register_result.message)
        else:
            logger.warning(user_register_result.message)
            return ResponseUtil.failure(msg=user_register_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


# @loginController.post("/getSmsCode", response_model=SmsCode)
# async def get_sms_code(request: Request, user: ResetUserModel, query_db: Session = Depends(get_db)):
#     try:
#         sms_result = await LoginService.get_sms_code_services(request, query_db, user)
#         if sms_result.is_success:
#             logger.info('获取成功')
#             return ResponseUtil.success(data=sms_result)
#         else:
#             logger.warning(sms_result.message)
#             return ResponseUtil.failure(msg=sms_result.message)
#     except Exception as e:
#         logger.exception(e)
#         return ResponseUtil.error(msg=str(e))
#
#
# @loginController.post("/forgetPwd", response_model=CrudResponseModel)
# async def forget_user_pwd(request: Request, forget_user: ResetUserModel, query_db: Session = Depends(get_db)):
#     try:
#         forget_user_result = await LoginService.forget_user_services(request, query_db, forget_user)
#         if forget_user_result.is_success:
#             logger.info(forget_user_result.message)
#             return ResponseUtil.success(data=forget_user_result, msg=forget_user_result.message)
#         else:
#             logger.warning(forget_user_result.message)
#             return ResponseUtil.failure(msg=forget_user_result.message)
#     except Exception as e:
#         logger.exception(e)
#         return ResponseUtil.error(msg=str(e))


@loginController.post("/logout")
async def logout(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JwtConfig.jwt_secret_key, algorithms=[JwtConfig.jwt_algorithm], options={'verify_exp': False})
        session_id: str = payload.get("session_id")
        await LoginService.logout_services(request, session_id)
        logger.info('退出成功')
        return ResponseUtil.success(msg="退出成功")
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
