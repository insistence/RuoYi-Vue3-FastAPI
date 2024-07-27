import inspect
import json
import os
import requests
import time
import warnings
from datetime import datetime
from fastapi import Request
from fastapi.responses import JSONResponse, ORJSONResponse, UJSONResponse
from functools import lru_cache, wraps
from typing import Literal, Optional, Union
from user_agents import parse
from module_admin.entity.vo.log_vo import LogininforModel, OperLogModel
from module_admin.service.log_service import LoginLogService, OperationLogService
from module_admin.service.login_service import LoginService
from config.enums import BusinessType
from config.env import AppConfig
from exceptions.exception import LoginException, ServiceException, ServiceWarning
from utils.response_util import ResponseUtil


class Log:
    """
    日志装饰器
    """

    def __init__(
        self,
        title: str,
        business_type: BusinessType,
        log_type: Optional[Literal['login', 'operation']] = 'operation',
    ):
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

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            # 获取被装饰函数的文件路径
            file_path = inspect.getfile(func)
            # 获取项目根路径
            project_root = os.getcwd()
            # 处理文件路径，去除项目根路径部分
            relative_path = os.path.relpath(file_path, start=project_root)[0:-2].replace('\\', '.')
            # 获取当前被装饰函数所在路径
            func_path = f'{relative_path}{func.__name__}()'
            # 获取上下文信息
            request: Request = kwargs.get('request')
            token = request.headers.get('Authorization')
            query_db = kwargs.get('query_db')
            request_method = request.method
            operator_type = 0
            user_agent = request.headers.get('User-Agent')
            if 'Windows' in user_agent or 'Macintosh' in user_agent or 'Linux' in user_agent:
                operator_type = 1
            if 'Mobile' in user_agent or 'Android' in user_agent or 'iPhone' in user_agent:
                operator_type = 2
            # 获取请求的url
            oper_url = request.url.path
            # 获取请求的ip及ip归属区域
            oper_ip = request.headers.get('X-Forwarded-For')
            oper_location = '内网IP'
            if AppConfig.app_ip_location_query:
                oper_location = get_ip_location(oper_ip)
            # 根据不同的请求类型使用不同的方法获取请求参数
            content_type = request.headers.get('Content-Type')
            if content_type and (
                'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type
            ):
                payload = await request.form()
                oper_param = '\n'.join([f'{key}: {value}' for key, value in payload.items()])
            else:
                payload = await request.body()
                # 通过 request.path_params 直接访问路径参数
                path_params = request.path_params
                oper_param = {}
                if payload:
                    oper_param.update(json.loads(str(payload, 'utf-8')))
                if path_params:
                    oper_param.update(path_params)
                oper_param = json.dumps(oper_param, ensure_ascii=False)
            # 日志表请求参数字段长度最大为2000，因此在此处判断长度
            if len(oper_param) > 2000:
                oper_param = '请求参数过长'

            # 获取操作时间
            oper_time = datetime.now()
            # 此处在登录之前向原始函数传递一些登录信息，用于监测在线用户的相关信息
            login_log = {}
            if self.log_type == 'login':
                user_agent_info = parse(user_agent)
                browser = f'{user_agent_info.browser.family}'
                system_os = f'{user_agent_info.os.family}'
                if user_agent_info.browser.version != ():
                    browser += f' {user_agent_info.browser.version[0]}'
                if user_agent_info.os.version != ():
                    system_os += f' {user_agent_info.os.version[0]}'
                login_log = dict(
                    ipaddr=oper_ip,
                    loginLocation=oper_location,
                    browser=browser,
                    os=system_os,
                    loginTime=oper_time.strftime('%Y-%m-%d %H:%M:%S'),
                )
                kwargs['form_data'].login_info = login_log
            try:
                # 调用原始函数
                result = await func(*args, **kwargs)
            except LoginException as e:
                result = ResponseUtil.failure(data=e.data, msg=e.message)
            except ServiceException as e:
                result = ResponseUtil.error(data=e.data, msg=e.message)
            except ServiceWarning as e:
                result = ResponseUtil.failure(data=e.data, msg=e.message)
            except Exception as e:
                result = ResponseUtil.error(msg=str(e))
            # 获取请求耗时
            cost_time = float(time.time() - start_time) * 100
            # 判断请求是否来自api文档
            request_from_swagger = (
                request.headers.get('referer').endswith('docs') if request.headers.get('referer') else False
            )
            request_from_redoc = (
                request.headers.get('referer').endswith('redoc') if request.headers.get('referer') else False
            )
            # 根据响应结果的类型使用不同的方法获取响应结果参数
            if (
                isinstance(result, JSONResponse)
                or isinstance(result, ORJSONResponse)
                or isinstance(result, UJSONResponse)
            ):
                result_dict = json.loads(str(result.body, 'utf-8'))
            else:
                if request_from_swagger or request_from_redoc:
                    result_dict = {}
                else:
                    if result.status_code == 200:
                        result_dict = {'code': result.status_code, 'message': '获取成功'}
                    else:
                        result_dict = {'code': result.status_code, 'message': '获取失败'}
            json_result = json.dumps(result_dict, ensure_ascii=False)
            # 根据响应结果获取响应状态及异常信息
            status = 1
            error_msg = ''
            if result_dict.get('code') == 200:
                status = 0
            else:
                error_msg = result_dict.get('msg')
            # 根据日志类型向对应的日志表插入数据
            if self.log_type == 'login':
                # 登录请求来自于api文档时不记录登录日志，其余情况则记录
                if request_from_swagger or request_from_redoc:
                    pass
                else:
                    user = kwargs.get('form_data')
                    user_name = user.username
                    login_log['loginTime'] = oper_time
                    login_log['userName'] = user_name
                    login_log['status'] = str(status)
                    login_log['msg'] = result_dict.get('msg')

                    await LoginLogService.add_login_log_services(query_db, LogininforModel(**login_log))
            else:
                current_user = await LoginService.get_current_user(request, token, query_db)
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


def log_decorator(
    title: str,
    business_type: Union[Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], BusinessType],
    log_type: Optional[Literal['login', 'operation']] = 'operation',
):
    """
    日志装饰器

    :param title: 当前日志装饰器装饰的模块标题
    :param business_type: 业务类型（0其它 1新增 2修改 3删除 4授权 5导出 6导入 7强退 8生成代码 9清空数据）
    :param log_type: 日志类型（login表示登录日志，operation表示为操作日志）
    :return:
    """
    warnings.simplefilter('always', category=DeprecationWarning)
    if isinstance(business_type, BusinessType):
        business_type = business_type.value
    warnings.warn(
        '未来版本将会移除@log_decorator装饰器，请使用@Log装饰器',
        category=DeprecationWarning,
        stacklevel=2,
    )

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            # 获取被装饰函数的文件路径
            file_path = inspect.getfile(func)
            # 获取项目根路径
            project_root = os.getcwd()
            # 处理文件路径，去除项目根路径部分
            relative_path = os.path.relpath(file_path, start=project_root)[0:-2].replace('\\', '.')
            # 获取当前被装饰函数所在路径
            func_path = f'{relative_path}{func.__name__}()'
            # 获取上下文信息
            request: Request = kwargs.get('request')
            token = request.headers.get('Authorization')
            query_db = kwargs.get('query_db')
            request_method = request.method
            operator_type = 0
            user_agent = request.headers.get('User-Agent')
            if 'Windows' in user_agent or 'Macintosh' in user_agent or 'Linux' in user_agent:
                operator_type = 1
            if 'Mobile' in user_agent or 'Android' in user_agent or 'iPhone' in user_agent:
                operator_type = 2
            # 获取请求的url
            oper_url = request.url.path
            # 获取请求的ip及ip归属区域
            oper_ip = request.headers.get('X-Forwarded-For')
            oper_location = '内网IP'
            if AppConfig.app_ip_location_query:
                oper_location = get_ip_location(oper_ip)
            # 根据不同的请求类型使用不同的方法获取请求参数
            content_type = request.headers.get('Content-Type')
            if content_type and (
                'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type
            ):
                payload = await request.form()
                oper_param = '\n'.join([f'{key}: {value}' for key, value in payload.items()])
            else:
                payload = await request.body()
                # 通过 request.path_params 直接访问路径参数
                path_params = request.path_params
                oper_param = {}
                if payload:
                    oper_param.update(json.loads(str(payload, 'utf-8')))
                if path_params:
                    oper_param.update(path_params)
                oper_param = json.dumps(oper_param, ensure_ascii=False)
            # 日志表请求参数字段长度最大为2000，因此在此处判断长度
            if len(oper_param) > 2000:
                oper_param = '请求参数过长'

            # 获取操作时间
            oper_time = datetime.now()
            # 此处在登录之前向原始函数传递一些登录信息，用于监测在线用户的相关信息
            login_log = {}
            if log_type == 'login':
                user_agent_info = parse(user_agent)
                browser = f'{user_agent_info.browser.family}'
                system_os = f'{user_agent_info.os.family}'
                if user_agent_info.browser.version != ():
                    browser += f' {user_agent_info.browser.version[0]}'
                if user_agent_info.os.version != ():
                    system_os += f' {user_agent_info.os.version[0]}'
                login_log = dict(
                    ipaddr=oper_ip,
                    loginLocation=oper_location,
                    browser=browser,
                    os=system_os,
                    loginTime=oper_time.strftime('%Y-%m-%d %H:%M:%S'),
                )
                kwargs['form_data'].login_info = login_log
            try:
                # 调用原始函数
                result = await func(*args, **kwargs)
            except LoginException as e:
                result = ResponseUtil.failure(data=e.data, msg=e.message)
            except ServiceException as e:
                result = ResponseUtil.error(data=e.data, msg=e.message)
            except ServiceWarning as e:
                result = ResponseUtil.failure(data=e.data, msg=e.message)
            except Exception as e:
                result = ResponseUtil.error(msg=str(e))
            # 获取请求耗时
            cost_time = float(time.time() - start_time) * 100
            # 判断请求是否来自api文档
            request_from_swagger = (
                request.headers.get('referer').endswith('docs') if request.headers.get('referer') else False
            )
            request_from_redoc = (
                request.headers.get('referer').endswith('redoc') if request.headers.get('referer') else False
            )
            # 根据响应结果的类型使用不同的方法获取响应结果参数
            if (
                isinstance(result, JSONResponse)
                or isinstance(result, ORJSONResponse)
                or isinstance(result, UJSONResponse)
            ):
                result_dict = json.loads(str(result.body, 'utf-8'))
            else:
                if request_from_swagger or request_from_redoc:
                    result_dict = {}
                else:
                    if result.status_code == 200:
                        result_dict = {'code': result.status_code, 'message': '获取成功'}
                    else:
                        result_dict = {'code': result.status_code, 'message': '获取失败'}
            json_result = json.dumps(result_dict, ensure_ascii=False)
            # 根据响应结果获取响应状态及异常信息
            status = 1
            error_msg = ''
            if result_dict.get('code') == 200:
                status = 0
            else:
                error_msg = result_dict.get('msg')
            # 根据日志类型向对应的日志表插入数据
            if log_type == 'login':
                # 登录请求来自于api文档时不记录登录日志，其余情况则记录
                if request_from_swagger or request_from_redoc:
                    pass
                else:
                    user = kwargs.get('form_data')
                    user_name = user.username
                    login_log['loginTime'] = oper_time
                    login_log['userName'] = user_name
                    login_log['status'] = str(status)
                    login_log['msg'] = result_dict.get('msg')

                    await LoginLogService.add_login_log_services(query_db, LogininforModel(**login_log))
            else:
                current_user = await LoginService.get_current_user(request, token, query_db)
                oper_name = current_user.user.user_name
                dept_name = current_user.user.dept.dept_name if current_user.user.dept else None
                operation_log = OperLogModel(
                    title=title,
                    businessType=business_type,
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

    return decorator


@lru_cache()
def get_ip_location(oper_ip: str):
    """
    查询ip归属区域

    :param oper_ip: 需要查询的ip
    :return: ip归属区域
    """
    oper_location = '内网IP'
    try:
        if oper_ip != '127.0.0.1' and oper_ip != 'localhost':
            oper_location = '未知'
            ip_result = requests.get(f'https://qifu-api.baidubce.com/ip/geo/v1/district?ip={oper_ip}')
            if ip_result.status_code == 200:
                prov = ip_result.json().get('data').get('prov')
                city = ip_result.json().get('data').get('city')
                if prov or city:
                    oper_location = f'{prov}-{city}'
    except Exception as e:
        oper_location = '未知'
        print(e)
    return oper_location
