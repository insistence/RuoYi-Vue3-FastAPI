import inspect
import json
import time
from collections.abc import Awaitable
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Literal, Optional, TypeVar

import httpx
from async_lru import alru_cache
from fastapi import Request
from fastapi.responses import JSONResponse, ORJSONResponse, UJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_200_OK
from typing_extensions import ParamSpec
from user_agents import parse

from common.context import RequestContext
from common.enums import BusinessType
from config.env import AppConfig
from exceptions.exception import LoginException, ServiceException, ServiceWarning
from module_admin.entity.vo.log_vo import LogininforModel, OperLogModel
from module_admin.service.log_service import LoginLogService, OperationLogService
from utils.dependency_util import DependencyUtil
from utils.log_util import logger
from utils.response_util import ResponseUtil

P = ParamSpec('P')
R = TypeVar('R')


class Log:
    """
    日志装饰器
    """

    def __init__(
        self,
        title: str,
        business_type: BusinessType,
        log_type: Optional[Literal['login', 'operation']] = 'operation',
    ) -> None:
        """
        日志装饰器

        :param title: 当前日志装饰器装饰的模块标题
        :param business_type: 业务类型（OTHER其它 INSERT新增 UPDATE修改 DELETE删除 GRANT授权 EXPORT导出 IMPORT导入 FORCE强退 GENCODE生成代码 CLEAN清空数据）
        :param log_type: 日志类型（login表示登录日志，operation表示为操作日志）
        :return:
        """
        self.title = title
        self.business_type = business_type.value
        self.log_type = log_type
        self._oper_param_len = 2000

    def __call__(self, func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.perf_counter()
            # 获取当前被装饰函数所在路径
            func_path = self._get_decorator_func_path(func)
            # 获取上下文信息
            request_name_list = get_function_parameters_name_by_type(func, Request)
            request = get_function_parameters_value_by_name(func, request_name_list[0], *args, **kwargs)
            DependencyUtil.check_exclude_routes(request, err_msg='当前路由不在认证规则内，不可使用Log装饰器')
            session_name_list = get_function_parameters_name_by_type(func, AsyncSession)
            query_db = get_function_parameters_value_by_name(func, session_name_list[0], *args, **kwargs)
            request_method = request.method
            user_agent = request.headers.get('User-Agent')
            # 获取操作类型
            operator_type = self._get_oper_type(user_agent)
            # 获取请求的url
            oper_url = request.url.path
            # 获取请求ip
            oper_ip = request.headers.get('X-Forwarded-For')
            # 获取请求ip归属区域
            oper_location = await self._get_oper_location(oper_ip)
            # 获取请求参数
            oper_param = await self._get_request_params(request)
            # 日志表请求参数字段长度最大为2000，因此在此处判断长度
            if len(oper_param) > self._oper_param_len:
                oper_param = '请求参数过长'

            # 获取操作时间
            oper_time = datetime.now()
            # 此处在登录之前向原始函数传递一些登录信息，用于监测在线用户的相关信息
            login_log = self._get_login_log(user_agent, oper_ip, oper_location, oper_time, kwargs)
            try:
                # 调用原始函数
                result = await func(*args, **kwargs)
            except (LoginException, ServiceWarning) as e:
                logger.warning(e.message)
                result = ResponseUtil.failure(data=e.data, msg=e.message)
            except ServiceException as e:
                logger.error(e.message)
                result = ResponseUtil.error(data=e.data, msg=e.message)
            except Exception as e:
                logger.exception(e)
                result = ResponseUtil.error(msg=str(e))
            # 获取请求耗时
            cost_time = float(time.perf_counter() - start_time) * 1000
            # 判断请求是否来自api文档
            request_from_swagger, request_from_redoc = self._is_request_from_swagger_or_redoc(request)
            # 根据响应结果的类型使用不同的方法获取响应结果参数
            result_dict = self._get_result_dict(result, request_from_swagger, request_from_redoc)
            json_result = json.dumps(result_dict, ensure_ascii=False)
            # 根据响应结果获取响应状态及异常信息
            status, error_msg = self._get_status_and_error_msg(result_dict)
            # 根据日志类型向对应的日志表插入数据
            if self.log_type == 'login':
                # 登录请求来自于api文档时不记录登录日志，其余情况则记录
                if request_from_swagger or request_from_redoc:
                    pass
                else:
                    user = kwargs.get('form_data')
                    login_log.update(
                        {
                            'loginTime': oper_time,
                            'userName': user.username,
                            'status': str(status),
                            'msg': result_dict.get('msg'),
                        }
                    )

                    await LoginLogService.add_login_log_services(query_db, LogininforModel(**login_log))
            else:
                current_user = RequestContext.get_current_user()
                oper_name = current_user.user.user_name
                dept_name = current_user.user.dept.dept_name if current_user.user.dept else None
                operation_log = OperLogModel(
                    title=self.title,
                    businessType=self.business_type,
                    method=func_path,
                    requestMethod=request_method,
                    operatorType=operator_type,
                    operName=oper_name,
                    deptName=dept_name,
                    operUrl=oper_url,
                    operIp=oper_ip,
                    operLocation=oper_location,
                    operParam=oper_param,
                    jsonResult=json_result,
                    status=status,
                    errorMsg=error_msg,
                    operTime=oper_time,
                    costTime=int(cost_time),
                )
                await OperationLogService.add_operation_log_services(query_db, operation_log)

            return result

        return wrapper

    def _get_decorator_func_path(self, func: Callable) -> str:
        """
        获取被装饰函数所在路径

        :param func: 被装饰函数
        :return: 被装饰函数所在路径
        """
        # 获取被装饰函数所在的模块
        module = inspect.getmodule(func)
        # 获取完整模块路径
        module_path = module.__name__ if module else ''
        # 获取当前被装饰函数所在路径
        func_path = f'{module_path}.{func.__name__}()'

        return func_path

    def _get_oper_type(self, user_agent: Any) -> int:
        """
        获取操作类型

        :param user_agent: 用户代理字符串
        :return: 操作类型
        """
        operator_type = 0
        if 'Windows' in user_agent or 'Macintosh' in user_agent or 'Linux' in user_agent:
            operator_type = 1
        if 'Mobile' in user_agent or 'Android' in user_agent or 'iPhone' in user_agent:
            operator_type = 2

        return operator_type

    async def _get_oper_location(self, oper_ip: str) -> str:
        """
        获取请求IP归属区域

        :param oper_ip: 请求IP
        :return: 请求IP归属区域
        """
        oper_location = '内网IP'
        if AppConfig.app_ip_location_query:
            oper_location = await get_ip_location(oper_ip)

        return oper_location

    async def _get_request_params(self, request: Request) -> str:
        """
        获取请求参数

        :param request: Request对象
        :return: 格式化后的请求参数字符串
        """
        params = {}

        # 路径和查询参数
        path_params = dict(request.path_params)
        query_params = dict(request.query_params)
        params.update({k: v for k, v in {'path_params': path_params, 'query_params': query_params}.items() if v})

        # 请求体处理
        content_type = request.headers.get('Content-Type', '')

        # JSON请求
        if 'application/json' in content_type:
            json_body = await request.json()
            if json_body:
                params['json_body'] = json_body

        # 表单数据
        elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form_data = await request.form()
            if form_data:
                # 过滤掉文件对象，只保留普通表单字段
                form_dict = {key: value for key, value in form_data.items() if not hasattr(value, 'filename')}
                if form_dict:
                    params['form_data'] = form_dict

                # 仅在multipart时尝试处理文件
                if 'multipart/form-data' in content_type:
                    file_info = {}
                    for key, value in form_data.items():
                        if hasattr(value, 'filename'):
                            file_info[key] = {
                                'filename': value.filename,
                                'content_type': value.content_type,
                                'size': value.size,
                                'headers': dict(value.headers),
                            }
                    if file_info:
                        params['files'] = file_info

        # 其他文本请求
        elif 'application/octet-stream' not in content_type:
            body = await request.body()
            if body:
                params['raw_body'] = body.decode('utf-8')

        return json.dumps(params, ensure_ascii=False, indent=2) if params else ''

    def _get_login_log(
        self, user_agent: Any, oper_ip: str, oper_location: str, oper_time: datetime, origin_kwargs: dict
    ) -> dict:
        """
        获取登录日志信息

        :param user_agent: 用户代理字符串
        :param oper_ip: 操作ip
        :param oper_location: 操作区域
        :param oper_time: 操作时间
        :param origin_kwargs: 原始函数参数
        :return: 登录日志信息
        """
        login_log = {}
        if self.log_type == 'login':
            user_agent_info = parse(user_agent)
            browser = f'{user_agent_info.browser.family}'
            system_os = f'{user_agent_info.os.family}'
            if user_agent_info.browser.version != ():
                browser += f' {user_agent_info.browser.version[0]}'
            if user_agent_info.os.version != ():
                system_os += f' {user_agent_info.os.version[0]}'
            login_log = {
                'ipaddr': oper_ip,
                'loginLocation': oper_location,
                'browser': browser,
                'os': system_os,
                'loginTime': oper_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            self._set_login_data(login_log, origin_kwargs)

        return login_log

    def _set_login_data(self, login_log: dict, origin_kwargs: dict) -> None:
        """
        设置登录日志数据

        :param login_log: 登录日志信息
        :param origin_kwargs: 原始函数参数
        :return: None
        """
        if 'form_data' in origin_kwargs:
            origin_kwargs['form_data'].login_info = login_log

    def _get_status_and_error_msg(self, result_dict: dict) -> tuple[int, str]:
        """
        获取操作状态和错误信息

        :param result_dict: 操作结果字典
        :return: 操作状态和错误信息元组
        """
        status = 1
        error_msg = ''
        if result_dict.get('code') == HTTP_200_OK:
            status = 0
        else:
            error_msg = result_dict.get('msg')

        return status, error_msg

    def _is_request_from_swagger_or_redoc(self, request: Request) -> tuple[bool, bool]:
        """
        判断请求是否来自swagger或redoc

        :param request: Request对象
        :return: 是否来自swagger请求和是否来自redoc请求元组
        """
        request_from_swagger = (
            request.headers.get('referer').endswith('docs') if request.headers.get('referer') else False
        )
        request_from_redoc = (
            request.headers.get('referer').endswith('redoc') if request.headers.get('referer') else False
        )

        return request_from_swagger, request_from_redoc

    def _get_result_dict(self, result: Any, request_from_swagger: bool, request_from_redoc: bool) -> dict:
        """
        获取操作结果字典

        :param result: 操作结果
        :param request_from_swagger: 是否来自swagger请求
        :param request_from_redoc: 是否来自redoc请求
        :return: 操作结果字典
        """
        if isinstance(result, (JSONResponse, ORJSONResponse, UJSONResponse)):
            result_dict = json.loads(str(result.body, 'utf-8'))
        elif request_from_swagger or request_from_redoc:
            result_dict = {}
        elif result.status_code == HTTP_200_OK:
            result_dict = {'code': result.status_code, 'message': '获取成功'}
        else:
            result_dict = {'code': result.status_code, 'message': '获取失败'}

        return result_dict


@alru_cache()
async def get_ip_location(oper_ip: str) -> str:
    """
    查询ip归属区域

    :param oper_ip: 需要查询的ip
    :return: ip归属区域
    """
    oper_location = '内网IP'
    try:
        if oper_ip not in ['127.0.0.1', 'localhost']:
            oper_location = '未知'
            async with httpx.AsyncClient() as client:
                ip_result = await client.get(f'https://qifu-api.baidubce.com/ip/geo/v1/district?ip={oper_ip}')
                if ip_result.status_code == HTTP_200_OK:
                    prov = ip_result.json().get('data', {}).get('prov')
                    city = ip_result.json().get('data', {}).get('city')
                    if prov or city:
                        oper_location = f'{prov}-{city}'
    except Exception as e:
        oper_location = '未知'
        print(e)
    return oper_location


def get_function_parameters_name_by_type(func: Callable, param_type: Any) -> list:
    """
    获取函数指定类型的参数名称

    :param func: 函数
    :param arg_type: 参数类型
    :return: 函数指定类型的参数名称
    """
    # 获取函数的参数信息
    parameters = inspect.signature(func).parameters
    # 找到指定类型的参数名称
    parameters_name_list = []
    # 遍历所有参数
    for name, param in parameters.items():
        # 处理参数注解
        annotation = param.annotation
        # 检查参数类型是否匹配
        # 1. 直接匹配
        # 2. 检查是否为Annotated类型（通过类型名称判断）
        if annotation == param_type or (
            hasattr(annotation, '__class__')
            and annotation.__class__.__name__ == '_AnnotatedAlias'
            and annotation.__origin__ == param_type
        ):
            parameters_name_list.append(name)
    return parameters_name_list


def get_function_parameters_value_by_name(func: Callable, name: str, *args, **kwargs) -> Any:
    """
    获取函数指定参数的值

    :param func: 函数
    :param name: 参数名
    :return: 参数值
    """
    # 获取参数值
    bound_parameters = inspect.signature(func).bind(*args, **kwargs)
    bound_parameters.apply_defaults()
    parameters_value = bound_parameters.arguments.get(name)

    return parameters_value
