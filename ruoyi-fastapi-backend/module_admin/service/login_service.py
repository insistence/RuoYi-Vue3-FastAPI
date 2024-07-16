import jwt
import random
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Form, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional, Union
from config.constant import CommonConstant, MenuConstant
from config.enums import RedisInitKeyConfig
from config.env import AppConfig, JwtConfig
from config.get_db import get_db
from exceptions.exception import LoginException, AuthException, ServiceException
from module_admin.dao.login_dao import login_by_account
from module_admin.dao.user_dao import UserDao
from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.login_vo import MenuTreeModel, MetaModel, RouterModel, SmsCode, UserLogin, UserRegister
from module_admin.entity.vo.user_vo import AddUserModel, CurrentUserModel, ResetUserModel, TokenData, UserInfoModel
from module_admin.service.user_service import UserService
from utils.common_util import CamelCaseUtil
from utils.log_util import logger
from utils.message_util import message_service
from utils.pwd_util import PwdUtil

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')


class CustomOAuth2PasswordRequestForm(OAuth2PasswordRequestForm):
    """
    自定义OAuth2PasswordRequestForm类，增加验证码及会话编号参数
    """

    def __init__(
        self,
        grant_type: str = Form(default=None, regex='password'),
        username: str = Form(),
        password: str = Form(),
        scope: str = Form(default=''),
        client_id: Optional[str] = Form(default=None),
        client_secret: Optional[str] = Form(default=None),
        code: Optional[str] = Form(default=''),
        uuid: Optional[str] = Form(default=''),
        login_info: Optional[Dict[str, str]] = Form(default=None),
    ):
        super().__init__(
            grant_type=grant_type,
            username=username,
            password=password,
            scope=scope,
            client_id=client_id,
            client_secret=client_secret,
        )
        self.code = code
        self.uuid = uuid
        self.login_info = login_info


class LoginService:
    """
    登录模块服务层
    """

    @classmethod
    async def authenticate_user(cls, request: Request, query_db: AsyncSession, login_user: UserLogin):
        """
        根据用户名密码校验用户登录

        :param request: Request对象
        :param query_db: orm对象
        :param login_user: 登录用户对象
        :return: 校验结果
        """
        await cls.__check_login_ip(request)
        account_lock = await request.app.state.redis.get(
            f'{RedisInitKeyConfig.ACCOUNT_LOCK.key}:{login_user.user_name}'
        )
        if login_user.user_name == account_lock:
            logger.warning('账号已锁定，请稍后再试')
            raise LoginException(data='', message='账号已锁定，请稍后再试')
        # 判断请求是否来自于api文档，如果是返回指定格式的结果，用于修复api文档认证成功后token显示undefined的bug
        request_from_swagger = (
            request.headers.get('referer').endswith('docs') if request.headers.get('referer') else False
        )
        request_from_redoc = (
            request.headers.get('referer').endswith('redoc') if request.headers.get('referer') else False
        )
        # 判断是否开启验证码，开启则验证，否则不验证（dev模式下来自API文档的登录请求不检验）
        if not login_user.captcha_enabled or (
            (request_from_swagger or request_from_redoc) and AppConfig.app_env == 'dev'
        ):
            pass
        else:
            await cls.__check_login_captcha(request, login_user)
        user = await login_by_account(query_db, login_user.user_name)
        if not user:
            logger.warning('用户不存在')
            raise LoginException(data='', message='用户不存在')
        if not PwdUtil.verify_password(login_user.password, user[0].password):
            cache_password_error_count = await request.app.state.redis.get(
                f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{login_user.user_name}'
            )
            password_error_counted = 0
            if cache_password_error_count:
                password_error_counted = cache_password_error_count
            password_error_count = int(password_error_counted) + 1
            await request.app.state.redis.set(
                f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{login_user.user_name}',
                password_error_count,
                ex=timedelta(minutes=10),
            )
            if password_error_count > 5:
                await request.app.state.redis.delete(
                    f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{login_user.user_name}'
                )
                await request.app.state.redis.set(
                    f'{RedisInitKeyConfig.ACCOUNT_LOCK.key}:{login_user.user_name}',
                    login_user.user_name,
                    ex=timedelta(minutes=10),
                )
                logger.warning('10分钟内密码已输错超过5次，账号已锁定，请10分钟后再试')
                raise LoginException(data='', message='10分钟内密码已输错超过5次，账号已锁定，请10分钟后再试')
            logger.warning('密码错误')
            raise LoginException(data='', message='密码错误')
        if user[0].status == '1':
            logger.warning('用户已停用')
            raise LoginException(data='', message='用户已停用')
        await request.app.state.redis.delete(f'{RedisInitKeyConfig.PASSWORD_ERROR_COUNT.key}:{login_user.user_name}')
        return user

    @classmethod
    async def __check_login_ip(cls, request: Request):
        """
        校验用户登录ip是否在黑名单内

        :param request: Request对象
        :return: 校验结果
        """
        black_ip_value = await request.app.state.redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.login.blackIPList')
        black_ip_list = black_ip_value.split(',') if black_ip_value else []
        if request.headers.get('X-Forwarded-For') in black_ip_list:
            logger.warning('当前IP禁止登录')
            raise LoginException(data='', message='当前IP禁止登录')
        return True

    @classmethod
    async def __check_login_captcha(cls, request: Request, login_user: UserLogin):
        """
        校验用户登录验证码

        :param request: Request对象
        :param login_user: 登录用户对象
        :return: 校验结果
        """
        captcha_value = await request.app.state.redis.get(f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{login_user.uuid}')
        if not captcha_value:
            logger.warning('验证码已失效')
            raise LoginException(data='', message='验证码已失效')
        if login_user.code != str(captcha_value):
            logger.warning('验证码错误')
            raise LoginException(data='', message='验证码错误')
        return True

    @classmethod
    async def create_access_token(cls, data: dict, expires_delta: Union[timedelta, None] = None):
        """
        根据登录信息创建当前用户token

        :param data: 登录信息
        :param expires_delta: token有效期
        :return: token
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=30)
        to_encode.update({'exp': expire})
        encoded_jwt = jwt.encode(to_encode, JwtConfig.jwt_secret_key, algorithm=JwtConfig.jwt_algorithm)
        return encoded_jwt

    @classmethod
    async def get_current_user(
        cls, request: Request = Request, token: str = Depends(oauth2_scheme), query_db: AsyncSession = Depends(get_db)
    ):
        """
        根据token获取当前用户信息

        :param request: Request对象
        :param token: 用户token
        :param query_db: orm对象
        :return: 当前用户信息对象
        :raise: 令牌异常AuthException
        """
        # if token[:6] != 'Bearer':
        #     logger.warning("用户token不合法")
        #     raise AuthException(data="", message="用户token不合法")
        try:
            if token.startswith('Bearer'):
                token = token.split(' ')[1]
            payload = jwt.decode(token, JwtConfig.jwt_secret_key, algorithms=[JwtConfig.jwt_algorithm])
            user_id: str = payload.get('user_id')
            session_id: str = payload.get('session_id')
            if not user_id:
                logger.warning('用户token不合法')
                raise AuthException(data='', message='用户token不合法')
            token_data = TokenData(user_id=int(user_id))
        except InvalidTokenError:
            logger.warning('用户token已失效，请重新登录')
            raise AuthException(data='', message='用户token已失效，请重新登录')
        query_user = await UserDao.get_user_by_id(query_db, user_id=token_data.user_id)
        if query_user.get('user_basic_info') is None:
            logger.warning('用户token不合法')
            raise AuthException(data='', message='用户token不合法')
        if AppConfig.app_same_time_login:
            redis_token = await request.app.state.redis.get(f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}')
        else:
            # 此方法可实现同一账号同一时间只能登录一次
            redis_token = await request.app.state.redis.get(
                f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{query_user.get('user_basic_info').user_id}"
            )
        if token == redis_token:
            if AppConfig.app_same_time_login:
                await request.app.state.redis.set(
                    f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}',
                    redis_token,
                    ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes),
                )
            else:
                await request.app.state.redis.set(
                    f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{query_user.get('user_basic_info').user_id}",
                    redis_token,
                    ex=timedelta(minutes=JwtConfig.jwt_redis_expire_minutes),
                )

            role_id_list = [item.role_id for item in query_user.get('user_role_info')]
            if 1 in role_id_list:
                permissions = ['*:*:*']
            else:
                permissions = [row.perms for row in query_user.get('user_menu_info')]
            post_ids = ','.join([str(row.post_id) for row in query_user.get('user_post_info')])
            role_ids = ','.join([str(row.role_id) for row in query_user.get('user_role_info')])
            roles = [row.role_key for row in query_user.get('user_role_info')]

            current_user = CurrentUserModel(
                permissions=permissions,
                roles=roles,
                user=UserInfoModel(
                    **CamelCaseUtil.transform_result(query_user.get('user_basic_info')),
                    postIds=post_ids,
                    roleIds=role_ids,
                    dept=CamelCaseUtil.transform_result(query_user.get('user_dept_info')),
                    role=CamelCaseUtil.transform_result(query_user.get('user_role_info')),
                ),
            )
            return current_user
        else:
            logger.warning('用户token已失效，请重新登录')
            raise AuthException(data='', message='用户token已失效，请重新登录')

    @classmethod
    async def get_current_user_routers(cls, user_id: int, query_db: AsyncSession):
        """
        根据用户id获取当前用户路由信息

        :param user_id: 用户id
        :param query_db: orm对象
        :return: 当前用户路由信息对象
        """
        query_user = await UserDao.get_user_by_id(query_db, user_id=user_id)
        user_router_menu = sorted(
            [
                row
                for row in query_user.get('user_menu_info')
                if row.menu_type in [MenuConstant.TYPE_DIR, MenuConstant.TYPE_MENU]
            ],
            key=lambda x: x.order_num,
        )
        menus = cls.__generate_menus(0, user_router_menu)
        user_router = cls.__generate_user_router_menu(menus)
        return [router.model_dump(exclude_unset=True, by_alias=True) for router in user_router]

    @classmethod
    def __generate_menus(cls, pid: int, permission_list: List[SysMenu]):
        """
        工具方法：根据菜单信息生成菜单信息树形嵌套数据

        :param pid: 菜单id
        :param permission_list: 菜单列表信息
        :return: 菜单信息树形嵌套数据
        """
        menu_list: List[MenuTreeModel] = []
        for permission in permission_list:
            if permission.parent_id == pid:
                children = cls.__generate_menus(permission.menu_id, permission_list)
                menu_list_data = MenuTreeModel(**CamelCaseUtil.transform_result(permission))
                if children:
                    menu_list_data.children = children
                menu_list.append(menu_list_data)

        return menu_list

    @classmethod
    def __generate_user_router_menu(cls, permission_list: List[MenuTreeModel]):
        """
        工具方法：根据菜单树信息生成路由信息树形嵌套数据

        :param permission_list: 菜单树列表信息
        :return: 路由信息树形嵌套数据
        """
        router_list: List[RouterModel] = []
        for permission in permission_list:
            router = RouterModel(
                hidden=True if permission.visible == '1' else False,
                name=RouterUtil.get_router_name(permission),
                path=RouterUtil.get_router_path(permission),
                component=RouterUtil.get_component(permission),
                query=permission.query,
                meta=MetaModel(
                    title=permission.menu_name,
                    icon=permission.icon,
                    noCache=True if permission.is_cache == 1 else False,
                    link=permission.path if RouterUtil.is_http(permission.path) else None,
                ),
            )
            c_menus = permission.children
            if c_menus and permission.menu_type == MenuConstant.TYPE_DIR:
                router.always_show = True
                router.redirect = 'noRedirect'
                router.children = cls.__generate_user_router_menu(c_menus)
            elif RouterUtil.is_menu_frame(permission):
                router.meta = None
                children_list: List[RouterModel] = []
                children = RouterModel(
                    path=permission.path,
                    component=permission.component,
                    name=RouterUtil.get_route_name(permission.route_name, permission.path),
                    meta=MetaModel(
                        title=permission.menu_name,
                        icon=permission.icon,
                        noCache=True if permission.is_cache == 1 else False,
                        link=permission.path if RouterUtil.is_http(permission.path) else None,
                    ),
                    query=permission.query,
                )
                children_list.append(children)
                router.children = children_list
            elif permission.parent_id == 0 and RouterUtil.is_inner_link(permission):
                router.meta = MetaModel(title=permission.menu_name, icon=permission.icon)
                router.path = '/'
                children_list: List[RouterModel] = []
                router_path = RouterUtil.inner_link_replace_each(permission.path)
                children = RouterModel(
                    path=router_path,
                    component=MenuConstant.INNER_LINK,
                    name=RouterUtil.get_route_name(permission.route_name, permission.path),
                    meta=MetaModel(
                        title=permission.menu_name,
                        icon=permission.icon,
                        link=permission.path if RouterUtil.is_http(permission.path) else None,
                    ),
                )
                children_list.append(children)
                router.children = children_list

            router_list.append(router)

        return router_list

    @classmethod
    async def register_user_services(cls, request: Request, query_db: AsyncSession, user_register: UserRegister):
        """
        用户注册services

        :param request: Request对象
        :param query_db: orm对象
        :param user_register: 注册用户对象
        :return: 注册结果
        """
        register_enabled = (
            True
            if await request.app.state.redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.registerUser')
            == 'true'
            else False
        )
        captcha_enabled = (
            True
            if await request.app.state.redis.get(f'{RedisInitKeyConfig.SYS_CONFIG.key}:sys.account.captchaEnabled')
            == 'true'
            else False
        )
        if user_register.password == user_register.confirm_password:
            if register_enabled:
                if captcha_enabled:
                    captcha_value = await request.app.state.redis.get(
                        f'{RedisInitKeyConfig.CAPTCHA_CODES.key}:{user_register.uuid}'
                    )
                    if not captcha_value:
                        raise ServiceException(message='验证码已失效')
                    elif user_register.code != str(captcha_value):
                        raise ServiceException(message='验证码错误')
                add_user = AddUserModel(
                    userName=user_register.username,
                    nickName=user_register.username,
                    password=PwdUtil.get_password_hash(user_register.password),
                )
                result = await UserService.add_user_services(query_db, add_user)
                return result
            else:
                raise ServiceException(message='注册程序已关闭，禁止注册')
        else:
            raise ServiceException(message='两次输入的密码不一致')

    @classmethod
    async def get_sms_code_services(cls, request: Request, query_db: AsyncSession, user: ResetUserModel):
        """
        获取短信验证码service

        :param request: Request对象
        :param query_db: orm对象
        :param user: 用户对象
        :return: 短信验证码对象
        """
        redis_sms_result = await request.app.state.redis.get(f'{RedisInitKeyConfig.SMS_CODE.key}:{user.session_id}')
        if redis_sms_result:
            return SmsCode(**dict(is_success=False, sms_code='', session_id='', message='短信验证码仍在有效期内'))
        is_user = await UserDao.get_user_by_name(query_db, user.user_name)
        if is_user:
            sms_code = str(random.randint(100000, 999999))
            session_id = str(uuid.uuid4())
            await request.app.state.redis.set(
                f'{RedisInitKeyConfig.SMS_CODE.key}:{session_id}', sms_code, ex=timedelta(minutes=2)
            )
            # 此处模拟调用短信服务
            message_service(sms_code)

            return SmsCode(**dict(is_success=True, sms_code=sms_code, session_id=session_id, message='获取成功'))

        return SmsCode(**dict(is_success=False, sms_code='', session_id='', message='用户不存在'))

    @classmethod
    async def forget_user_services(cls, request: Request, query_db: AsyncSession, forget_user: ResetUserModel):
        """
        用户忘记密码services

        :param request: Request对象
        :param query_db: orm对象
        :param forget_user: 重置用户对象
        :return: 重置结果
        """
        redis_sms_result = await request.app.state.redis.get(
            f'{RedisInitKeyConfig.SMS_CODE.key}:{forget_user.session_id}'
        )
        if forget_user.sms_code == redis_sms_result:
            forget_user.password = PwdUtil.get_password_hash(forget_user.password)
            forget_user.user_id = (await UserDao.get_user_by_name(query_db, forget_user.user_name)).user_id
            edit_result = await UserService.reset_user_services(query_db, forget_user)
            result = edit_result.dict()
        elif not redis_sms_result:
            result = dict(is_success=False, message='短信验证码已过期')
        else:
            await request.app.state.redis.delete(f'{RedisInitKeyConfig.SMS_CODE.key}:{forget_user.session_id}')
            result = dict(is_success=False, message='短信验证码不正确')

        return CrudResponseModel(**result)

    @classmethod
    async def logout_services(cls, request: Request, session_id: str):
        """
        退出登录services

        :param request: Request对象
        :param session_id: 会话编号
        :return: 退出登录结果
        """
        await request.app.state.redis.delete(f'{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}')
        # await request.app.state.redis.delete(f'{current_user.user.user_id}_access_token')
        # await request.app.state.redis.delete(f'{current_user.user.user_id}_session_id')

        return True


class RouterUtil:
    """
    路由处理工具类
    """

    @classmethod
    def get_router_name(cls, menu: MenuTreeModel):
        """
        获取路由名称

        :param menu: 菜单数对象
        :return: 路由名称
        """
        # 非外链并且是一级目录（类型为目录）
        if cls.is_menu_frame(menu):
            return ''

        return cls.get_route_name(menu.route_name, menu.path)

    @classmethod
    def get_route_name(cls, name: str, path: str):
        """
        获取路由名称，如没有配置路由名称则取路由地址

        :param name: 路由名称
        :param path: 路由地址
        :return: 路由名称（驼峰格式）
        """
        router_name = name if name else path
        return router_name.capitalize()

    @classmethod
    def get_router_path(cls, menu: MenuTreeModel):
        """
        获取路由地址

        :param menu: 菜单数对象
        :return: 路由地址
        """
        # 内链打开外网方式
        router_path = menu.path
        if menu.parent_id != 0 and cls.is_inner_link(menu):
            router_path = cls.inner_link_replace_each(router_path)
        # 非外链并且是一级目录（类型为目录）
        if menu.parent_id == 0 and menu.menu_type == MenuConstant.TYPE_DIR and menu.is_frame == MenuConstant.NO_FRAME:
            router_path = f'/{menu.path}'
        # 非外链并且是一级目录（类型为菜单）
        elif cls.is_menu_frame(menu):
            router_path = '/'
        return router_path

    @classmethod
    def get_component(cls, menu: MenuTreeModel):
        """
        获取组件信息

        :param menu: 菜单数对象
        :return: 组件信息
        """
        component = MenuConstant.LAYOUT
        if menu.component and not cls.is_menu_frame(menu):
            component = menu.component
        elif (menu.component is None or menu.component == '') and menu.parent_id != 0 and cls.is_inner_link(menu):
            component = MenuConstant.INNER_LINK
        elif (menu.component is None or menu.component == '') and cls.is_parent_view(menu):
            component = MenuConstant.PARENT_VIEW
        return component

    @classmethod
    def is_menu_frame(cls, menu: MenuTreeModel):
        """
        判断是否为菜单内部跳转

        :param menu: 菜单数对象
        :return: 是否为菜单内部跳转
        """
        return (
            menu.parent_id == 0 and menu.menu_type == MenuConstant.TYPE_MENU and menu.is_frame == MenuConstant.NO_FRAME
        )

    @classmethod
    def is_inner_link(cls, menu: MenuTreeModel):
        """
        判断是否为内链组件

        :param menu: 菜单数对象
        :return: 是否为内链组件
        """
        return menu.is_frame == MenuConstant.NO_FRAME and cls.is_http(menu.path)

    @classmethod
    def is_parent_view(cls, menu: MenuTreeModel):
        """
        判断是否为parent_view组件

        :param menu: 菜单数对象
        :return: 是否为parent_view组件
        """
        return menu.parent_id != 0 and menu.menu_type == MenuConstant.TYPE_DIR

    @classmethod
    def is_http(cls, link: str):
        """
        判断是否为http(s)://开头

        :param link: 链接
        :return: 是否为http(s)://开头
        """
        return link.startswith(CommonConstant.HTTP) or link.startswith(CommonConstant.HTTPS)

    @classmethod
    def inner_link_replace_each(cls, path: str):
        """
        内链域名特殊字符替换

        :param path: 内链域名
        :return: 替换后的内链域名
        """
        old_values = [CommonConstant.HTTP, CommonConstant.HTTPS, CommonConstant.WWW, '.', ':']
        new_values = ['', '', '', '/', '/']
        for old, new in zip(old_values, new_values):
            path = path.replace(old, new)
        return path
