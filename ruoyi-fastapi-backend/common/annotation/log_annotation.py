import inspect
import json
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Literal, TypeVar

import httpx
from async_lru import alru_cache
from fastapi import Request
from fastapi.responses import JSONResponse, ORJSONResponse, UJSONResponse
from starlette.status import HTTP_200_OK
from typing_extensions import ParamSpec
from user_agents import parse

from common.context import RequestContext
from common.enums import BusinessType
from config.env import AppConfig
from exceptions.exception import LoginException, ServiceException, ServiceWarning
from module_admin.entity.vo.log_vo import LogininforModel, OperLogModel
from module_admin.service.log_service import LogQueueService
from utils.client_ip_util import ClientIPUtil
from utils.dependency_util import DependencyUtil
from utils.log_util import LogSanitizer, logger
from utils.response_util import ResponseUtil

P = ParamSpec('P')
R = TypeVar('R')


class _LogFieldRoot(str, Enum):
    """
    日志字段路径根节点
    """

    def field(self, *parts: str) -> str:
        """
        生成 include 字段路径

        :param parts: 后续字段路径片段
        :return: 完整字段路径
        """
        return '.'.join((self.value, *parts)) if parts else self.value


class RequestLogFieldRoot(_LogFieldRoot):
    """
    请求日志字段路径支持的根节点
    """

    PATH_PARAMS = 'path_params'
    QUERY_PARAMS = 'query_params'
    JSON_BODY = 'json_body'
    FORM_DATA = 'form_data'
    FILES = 'files'
    RAW_BODY = 'raw_body'


class ResponseLogFieldRoot(_LogFieldRoot):
    """
    响应日志字段路径推荐的根节点
    """

    CODE = 'code'
    MSG = 'msg'
    DATA = 'data'
    ROWS = 'rows'
    SUCCESS = 'success'
    TIME = 'time'


class Log:
    """
    日志装饰器

    支持的日志模式:
    - `full`: 记录脱敏后的完整载荷
    - `none`: 不记录对应方向的载荷
    - `summary`: 仅记录摘要信息，如顶层键、状态码、rows数量等
    - `include`: 仅记录白名单字段，适合高敏感接口
    - `exclude`: 记录完整载荷后排除少数字段，适合中敏感接口

    模式建议:
    - 普通后台管理接口可使用`full`
    - 包含大量字段但只关心结构时使用`summary`
    - 包含密钥、密码、提示词、配置项等高敏感字段时优先使用`include`
    - 字段较多但只需排除极少数字段时可使用`exclude`
    - 完全无需保留请求体或响应体时使用`none`

    include / exclude 模式字段路径规则:
    - 使用`.`分隔路径，如`json_body.modelCode`、`data.userId`
    - 请求日志推荐根节点：`path_params`、`query_params`、`json_body`、`form_data`、`files`、`raw_body`
    - 响应日志推荐根节点：`code`、`msg`、`data`、`rows`、`success`、`time`
    - 字段名优先按原样精确匹配，若未命中会自动尝试 snake_case、camelCase、kebab-case 归一化匹配
    - 数组使用数字下标，如`rows.0.userName`
    - 当前不支持通配符
    - 推荐优先使用`RequestLogFieldRoot.JSON_BODY.field(...)`和`ResponseLogFieldRoot.DATA.field(...)`构造字段路径

    示例:
    - `request_include_fields=(RequestLogFieldRoot.JSON_BODY.field('model_code'),)`
    - `response_include_fields=(ResponseLogFieldRoot.DATA.field('userName'),)`
    - `request_exclude_fields=('json_body.api_key',)`
    """

    _REQUEST_INCLUDE_ROOTS = tuple(item.value for item in RequestLogFieldRoot)
    _RESPONSE_INCLUDE_ROOTS = tuple(item.value for item in ResponseLogFieldRoot)
    _MISSING = object()
    _AMBIGUOUS = object()

    def __init__(
        self,
        title: str,
        business_type: BusinessType,
        log_type: Literal['login', 'operation'] | None = 'operation',
        request_log_mode: Literal['full', 'none', 'summary', 'include', 'exclude'] = 'full',
        response_log_mode: Literal['full', 'none', 'summary', 'include', 'exclude'] = 'full',
        request_include_fields: tuple[str, ...] | None = None,
        response_include_fields: tuple[str, ...] | None = None,
        request_exclude_fields: tuple[str, ...] | None = None,
        response_exclude_fields: tuple[str, ...] | None = None,
    ) -> None:
        """
        日志装饰器

        :param title: 当前日志装饰器装饰的模块标题
        :param business_type: 业务类型（OTHER其它 INSERT新增 UPDATE修改 DELETE删除 GRANT授权 EXPORT导出 IMPORT导入 FORCE强退 GENCODE生成代码 CLEAN清空数据）
        :param log_type: 日志类型；`login`表示登录日志，仅落登录信息，`operation`表示操作日志，会落请求/响应摘要与操作人信息
        :param request_log_mode: 请求日志记录模式；`full`记录脱敏后的完整请求，`none`不记录请求体，`summary`记录请求摘要，`include`仅记录request_include_fields指定的字段，`exclude`记录完整请求后排除request_exclude_fields指定的字段
        :param response_log_mode: 响应日志记录模式；`full`记录脱敏后的完整响应，`none`不记录响应体，`summary`记录响应摘要，`include`仅记录response_include_fields指定的字段，`exclude`记录完整响应后排除response_exclude_fields指定的字段
        :param request_include_fields: 请求日志白名单字段路径，仅在request_log_mode='include'时生效；推荐从path_params/query_params/json_body/form_data/files/raw_body开始，字段名支持 snake_case 与 camelCase 自动兼容
        :param response_include_fields: 响应日志白名单字段路径，仅在response_log_mode='include'时生效；推荐从code/msg/data/rows/success/time开始，字段名支持 snake_case 与 camelCase 自动兼容
        :param request_exclude_fields: 请求日志排除字段路径，仅在request_log_mode='exclude'时生效；推荐从path_params/query_params/json_body/form_data/files/raw_body开始，字段名支持 snake_case 与 camelCase 自动兼容
        :param response_exclude_fields: 响应日志排除字段路径，仅在response_log_mode='exclude'时生效；推荐从code/msg/data/rows/success/time开始，字段名支持 snake_case 与 camelCase 自动兼容
        :return:
        """
        self.title = title
        self.business_type = business_type.value
        self.log_type = log_type
        self.request_log_mode = request_log_mode
        self.response_log_mode = response_log_mode
        self.request_include_fields = request_include_fields or ()
        self.response_include_fields = response_include_fields or ()
        self.request_exclude_fields = request_exclude_fields or ()
        self.response_exclude_fields = response_exclude_fields or ()
        self._oper_param_len = 2000
        self._warned_field_path_warnings: set[str] = set()
        self._validate_request_field_paths_strict()
        self._warn_invalid_field_path_config()

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
            request_method = request.method
            user_agent = request.headers.get('User-Agent') or ''
            # 获取操作类型
            operator_type = self._get_oper_type(user_agent)
            # 获取请求的url
            oper_url = request.url.path
            # 获取请求ip
            oper_ip = ClientIPUtil.get_client_ip(request)
            # 获取请求ip归属区域
            oper_location = await self._get_oper_location(oper_ip)
            # 获取请求参数
            oper_param_payload = LogSanitizer.sanitize_data(await self._get_request_params(request))
            oper_param = self._build_log_text(
                oper_param_payload,
                self.request_log_mode,
                self.request_include_fields,
                self.request_exclude_fields,
                payload_kind='request',
            )
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
            sanitized_result_dict = LogSanitizer.sanitize_data(
                self._get_result_dict(result, request_from_swagger, request_from_redoc)
            )
            json_result = self._build_log_text(
                sanitized_result_dict,
                self.response_log_mode,
                self.response_include_fields,
                self.response_exclude_fields,
                payload_kind='response',
            )
            # 根据响应结果获取响应状态及异常信息
            status, error_msg = self._get_status_and_error_msg(sanitized_result_dict)
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
                            'msg': sanitized_result_dict.get('msg') or '',
                        }
                    )

                    await LogQueueService.enqueue_login_log(request, LogininforModel(**login_log), func_path)
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
                await LogQueueService.enqueue_operation_log(request, operation_log, func_path)

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
        user_agent_text = user_agent or ''
        operator_type = 0
        if 'Windows' in user_agent_text or 'Macintosh' in user_agent_text or 'Linux' in user_agent_text:
            operator_type = 1
        if 'Mobile' in user_agent_text or 'Android' in user_agent_text or 'iPhone' in user_agent_text:
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

    async def _get_request_params(self, request: Request) -> dict[str, Any]:
        """
        获取请求参数

        :param request: Request对象
        :return: 结构化请求参数
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
            params.update(await self._get_json_request_params(request, content_type))

        # 表单数据
        elif 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            params.update(await self._get_form_request_params(request, content_type))

        # 其他文本请求
        elif 'application/octet-stream' not in content_type:
            params.update(await self._get_raw_request_params(request))

        return params

    async def _get_json_request_params(self, request: Request, content_type: str) -> dict[str, Any]:
        """
        获取 JSON 请求参数，解析失败时自动降级为原始文本

        :param request: Request对象
        :param content_type: 请求头中的 content-type
        :return: 结构化请求参数
        """
        params = {}
        try:
            json_body = await request.json()
        except Exception as exc:
            logger.warning(
                'Log装饰器请求体解析失败，已降级为raw_body记录，path={}, content_type={}, error_type={}',
                request.url.path,
                content_type,
                type(exc).__name__,
            )
            params.update(await self._get_raw_request_params(request))
        else:
            if json_body:
                params['json_body'] = json_body
        return params

    async def _get_form_request_params(self, request: Request, content_type: str) -> dict[str, Any]:
        """
        获取表单请求参数

        :param request: Request对象
        :param content_type: 请求头中的 content-type
        :return: 结构化请求参数
        """
        params = {}
        form_data = await request.form()
        if not form_data:
            return params

        # 过滤掉文件对象，只保留普通表单字段
        form_dict = {key: value for key, value in form_data.items() if not hasattr(value, 'filename')}
        if form_dict:
            params['form_data'] = form_dict

        # 仅在multipart时尝试处理文件
        if 'multipart/form-data' not in content_type:
            return params

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
        return params

    async def _get_raw_request_params(self, request: Request) -> dict[str, Any]:
        """
        获取原始文本请求参数

        :param request: Request对象
        :return: 原始文本请求参数
        """
        body = await request.body()
        if not body:
            return {}
        return {'raw_body': self._decode_request_body(body)}

    @staticmethod
    def _decode_request_body(body: bytes) -> str:
        """
        安全解码请求体，避免日志采集影响主流程

        :param body: 原始请求体字节
        :return: 解码后的请求体文本
        """
        return body.decode('utf-8', errors='replace')

    def _build_log_text(
        self,
        payload: Any,
        mode: Literal['full', 'none', 'summary', 'include', 'exclude'],
        include_fields: tuple[str, ...],
        exclude_fields: tuple[str, ...],
        payload_kind: Literal['request', 'response'],
    ) -> str:
        """
        根据日志策略构建日志文本

        :param payload: 已完成脱敏的日志载荷
        :param mode: 日志记录模式
        :param include_fields: 白名单字段路径
        :param exclude_fields: 排除字段路径
        :param payload_kind: 载荷类型
        :return: 日志文本
        """
        if mode == 'none' or not payload:
            return ''
        if mode == 'summary':
            log_payload = self._build_summary_payload(payload, payload_kind)
        elif mode == 'include':
            log_payload = self._extract_include_fields(payload, include_fields, payload_kind)
        elif mode == 'exclude':
            log_payload = self._exclude_fields(payload, exclude_fields, payload_kind)
        else:
            log_payload = payload
        return json.dumps(log_payload, ensure_ascii=False, indent=2) if log_payload else ''

    def _build_summary_payload(self, payload: Any, payload_kind: Literal['request', 'response']) -> dict[str, Any]:
        """
        构建摘要日志载荷

        :param payload: 原始载荷
        :param payload_kind: 载荷类型
        :return: 摘要日志载荷
        """
        summary_payload: dict[str, Any] = {
            'mode': 'summary',
            'kind': payload_kind,
        }
        if not isinstance(payload, dict):
            summary_payload['type'] = type(payload).__name__
            return summary_payload
        summary_payload['keys'] = list(payload.keys())
        if payload_kind == 'request':
            summary_payload.update(
                {
                    'path_param_keys': self._get_mapping_keys(payload.get('path_params')),
                    'query_param_keys': self._get_mapping_keys(payload.get('query_params')),
                    'json_body_keys': self._get_mapping_keys(payload.get('json_body')),
                    'form_data_keys': self._get_mapping_keys(payload.get('form_data')),
                    'file_fields': self._get_mapping_keys(payload.get('files')),
                    'raw_body_length': len(payload.get('raw_body', '')) if payload.get('raw_body') else 0,
                }
            )
        else:
            summary_payload.update(
                {
                    'code': payload.get('code'),
                    'msg': self._get_result_message(payload),
                    'data_keys': self._get_mapping_keys(payload.get('data')),
                    'rows_count': len(payload.get('rows')) if isinstance(payload.get('rows'), list) else 0,
                }
            )
        return summary_payload

    def _extract_include_fields(
        self,
        payload: Any,
        include_fields: tuple[str, ...],
        payload_kind: Literal['request', 'response'],
    ) -> dict[str, Any]:
        """
        提取白名单字段日志载荷

        :param payload: 原始载荷
        :param include_fields: 白名单字段路径
        :param payload_kind: 载荷类型
        :return: 提取后的日志载荷
        """
        selected_fields = {}
        for field_path in include_fields:
            field_value = self._get_field_value_by_path(payload, field_path)
            if field_value is not self._MISSING:
                selected_fields[field_path] = field_value
            else:
                self._warn_missing_field_path(payload, field_path, payload_kind, strategy='include')
        return {
            'mode': 'include',
            'selected': selected_fields,
        }

    def _exclude_fields(
        self,
        payload: Any,
        exclude_fields: tuple[str, ...],
        payload_kind: Literal['request', 'response'],
    ) -> Any:
        """
        排除指定字段后返回日志载荷

        :param payload: 原始载荷
        :param exclude_fields: 排除字段路径
        :param payload_kind: 载荷类型
        :return: 排除后的日志载荷
        """
        if not exclude_fields or not isinstance(payload, (dict, list)):
            return payload
        filtered_payload = deepcopy(payload)
        for field_path in self._sort_field_paths_for_exclude(exclude_fields):
            if not self._remove_field_by_path(filtered_payload, field_path):
                self._warn_missing_field_path(payload, field_path, payload_kind, strategy='exclude')
        return filtered_payload

    def _warn_missing_field_path(
        self,
        payload: Any,
        field_path: str,
        payload_kind: Literal['request', 'response'],
        strategy: Literal['include', 'exclude'],
    ) -> None:
        """
        记录未命中的字段路径告警，同一路径仅提示一次

        :param payload: 原始载荷
        :param field_path: 字段路径
        :param payload_kind: 载荷类型
        :param strategy: 当前字段路径策略
        :return: None
        """
        warning_key = f'{strategy}:{payload_kind}:{field_path}'
        if warning_key in self._warned_field_path_warnings:
            return
        self._warned_field_path_warnings.add(warning_key)
        kind_text = '请求' if payload_kind == 'request' else '响应'
        reason = self._describe_missing_field_path(payload, field_path)
        if strategy == 'include':
            logger.warning(
                f'Log装饰器字段白名单未命中：{kind_text}日志字段路径`{field_path}`已忽略。'
                f'{reason}若该字段为可选字段，可忽略此提示。'
            )
        else:
            logger.warning(
                f'Log装饰器字段排除路径未命中：{kind_text}日志字段路径`{field_path}`未生效。'
                f'{reason}若该字段为可选字段，可忽略此提示。'
            )

    def _describe_missing_field_path(self, payload: Any, field_path: str) -> str:
        """
        描述字段路径未命中的原因

        :param payload: 原始载荷
        :param field_path: 字段路径
        :return: 原因描述
        """
        current_value = payload
        traversed_parts: list[str] = []
        for part in field_path.split('.'):
            traversed_path = '.'.join(traversed_parts) or '<root>'
            if isinstance(current_value, dict):
                mapping_value = self._get_mapping_value_by_part(current_value, part)
                if mapping_value is self._MISSING:
                    available_keys = ', '.join(map(str, current_value.keys())) if current_value else '无'
                    return f'在`{traversed_path}`下未找到字段`{part}`，可用字段：{available_keys}。'
                if mapping_value is self._AMBIGUOUS:
                    ambiguous_keys = ', '.join(
                        str(key)
                        for key in current_value
                        if self._normalize_include_key(str(key)) == self._normalize_include_key(part)
                    )
                    return (
                        f'在`{traversed_path}`下字段`{part}`存在命名冲突，'
                        f'可匹配字段：{ambiguous_keys}；请改用精确字段名。'
                    )
                current_value = mapping_value
            elif isinstance(current_value, list):
                if not part.isdigit():
                    return f'在`{traversed_path}`处当前值为列表，字段片段`{part}`应为数字下标。'
                current_index = int(part)
                if current_index >= len(current_value):
                    return f'在`{traversed_path}`处列表长度为{len(current_value)}，下标`{part}`越界。'
                current_value = current_value[current_index]
            else:
                current_type = type(current_value).__name__ if current_value is not None else 'None'
                return f'在`{traversed_path}`处当前值类型为`{current_type}`，无法继续匹配后续路径。'
            traversed_parts.append(part)
        return ''

    def _warn_invalid_field_path_config(self) -> None:
        """
        记录字段路径配置告警，帮助开发者发现路径误配

        :return: None
        """
        warnings = [
            *self._collect_field_path_warnings(
                mode=self.request_log_mode,
                include_fields=self.request_include_fields,
                exclude_fields=self.request_exclude_fields,
                payload_kind='request',
            ),
            *self._collect_field_path_warnings(
                mode=self.response_log_mode,
                include_fields=self.response_include_fields,
                exclude_fields=self.response_exclude_fields,
                payload_kind='response',
            ),
        ]
        for warning in warnings:
            logger.warning(f'Log装饰器字段路径配置提示：{warning}')

    def _validate_request_field_paths_strict(self) -> None:
        """
        严格校验请求日志字段路径根节点

        :return: None
        """
        field_paths = ()
        if self.request_log_mode == 'include':
            field_paths = self.request_include_fields
        elif self.request_log_mode == 'exclude':
            field_paths = self.request_exclude_fields
        for field_path in field_paths:
            if not field_path:
                continue
            root_part = field_path.split('.', 1)[0]
            if self._resolve_include_root(root_part, self._REQUEST_INCLUDE_ROOTS) is None:
                raise ValueError(
                    f'请求日志字段路径`{field_path}`使用了不支持的根节点`{root_part}`；'
                    f'仅支持：{", ".join(self._REQUEST_INCLUDE_ROOTS)}'
                )

    def _collect_field_path_warnings(
        self,
        mode: Literal['full', 'none', 'summary', 'include', 'exclude'],
        include_fields: tuple[str, ...],
        exclude_fields: tuple[str, ...],
        payload_kind: Literal['request', 'response'],
    ) -> list[str]:
        """
        收集字段路径配置告警信息

        :param mode: 日志记录模式
        :param include_fields: 白名单字段路径列表
        :param exclude_fields: 排除字段路径列表
        :param payload_kind: 载荷类型
        :return: 告警信息列表
        """
        warnings = []
        kind_text = '请求' if payload_kind == 'request' else '响应'
        recommended_roots = self._REQUEST_INCLUDE_ROOTS if payload_kind == 'request' else self._RESPONSE_INCLUDE_ROOTS
        if mode == 'include' and not include_fields:
            warnings.append(
                f'{kind_text}日志已启用include模式，但未配置白名单字段；推荐根节点：{", ".join(recommended_roots)}'
            )
        if mode == 'exclude' and not exclude_fields:
            warnings.append(
                f'{kind_text}日志已启用exclude模式，但未配置排除字段；推荐根节点：{", ".join(recommended_roots)}'
            )
        if mode != 'include' and include_fields:
            warnings.append(f'{kind_text}日志配置了白名单字段，但当前模式为{mode}，这些字段不会生效')
        if mode != 'exclude' and exclude_fields:
            warnings.append(f'{kind_text}日志配置了排除字段，但当前模式为{mode}，这些字段不会生效')
        for field_path in include_fields:
            path_warning = self._validate_field_path(field_path, payload_kind, strategy='include')
            if path_warning:
                warnings.append(path_warning)
        for field_path in exclude_fields:
            path_warning = self._validate_field_path(field_path, payload_kind, strategy='exclude')
            if path_warning:
                warnings.append(path_warning)

        return warnings

    def _validate_field_path(
        self,
        field_path: str,
        payload_kind: Literal['request', 'response'],
        strategy: Literal['include', 'exclude'],
    ) -> str | None:
        """
        校验单个字段路径

        :param field_path: 字段路径
        :param payload_kind: 载荷类型
        :param strategy: 当前字段路径策略
        :return: 告警信息
        """
        kind_text = '请求' if payload_kind == 'request' else '响应'
        recommended_roots = self._REQUEST_INCLUDE_ROOTS if payload_kind == 'request' else self._RESPONSE_INCLUDE_ROOTS
        strategy_text = '白名单字段路径' if strategy == 'include' else '排除字段路径'
        if not field_path:
            return f'{kind_text}日志存在空{strategy_text}；推荐根节点：{", ".join(recommended_roots)}'
        parts = field_path.split('.')
        if any(not part for part in parts):
            return f'{kind_text}日志{strategy_text}`{field_path}`格式不合法，请使用`.`分隔的完整路径'
        canonical_root = self._resolve_include_root(parts[0], recommended_roots)
        if canonical_root is None:
            return (
                f'{kind_text}日志{strategy_text}`{field_path}`未使用推荐根节点`{parts[0]}`；'
                f'推荐根节点：{", ".join(recommended_roots)}'
            )
        return None

    def _get_field_value_by_path(self, payload: Any, field_path: str) -> Any:
        """
        通过字段路径获取字段值

        :param payload: 原始载荷
        :param field_path: 字段路径
        :return: 字段值
        """
        current_value = payload
        for part in field_path.split('.'):
            if isinstance(current_value, dict):
                mapping_value = self._get_mapping_value_by_part(current_value, part)
                if mapping_value is self._MISSING or mapping_value is self._AMBIGUOUS:
                    return self._MISSING
                current_value = mapping_value
            elif isinstance(current_value, list) and part.isdigit():
                current_index = int(part)
                if current_index >= len(current_value):
                    return self._MISSING
                current_value = current_value[current_index]
            else:
                return self._MISSING
        return current_value

    def _get_mapping_value_by_part(self, payload: dict[str, Any], part: str) -> Any:
        """
        从字典中按字段片段获取值，支持 snake_case / camelCase / kebab-case 自动兼容

        :param payload: 当前字典载荷
        :param part: 当前路径片段
        :return: 字段值
        """
        if part in payload:
            return payload[part]
        normalized_part = self._normalize_include_key(part)
        matched_keys = [key for key in payload if self._normalize_include_key(str(key)) == normalized_part]
        if len(matched_keys) == 1:
            return payload[matched_keys[0]]
        if len(matched_keys) > 1:
            return self._AMBIGUOUS
        return self._MISSING

    @staticmethod
    def _sort_field_paths_for_exclude(field_paths: tuple[str, ...]) -> list[str]:
        """
        对 exclude 字段路径排序，优先处理更深层路径和更大的列表下标，避免列表删除时发生索引位移

        :param field_paths: 原始字段路径
        :return: 排序后的字段路径列表
        """
        return sorted(field_paths, key=Log._build_exclude_sort_key, reverse=True)

    @staticmethod
    def _build_exclude_sort_key(field_path: str) -> tuple[int, tuple[tuple[int, int | str], ...]]:
        """
        构建 exclude 字段路径排序键

        :param field_path: 字段路径
        :return: 排序键
        """
        parts = field_path.split('.')
        normalized_parts: tuple[tuple[int, int | str], ...] = tuple(
            (1, int(part)) if part.isdigit() else (0, part) for part in parts
        )
        return len(parts), normalized_parts

    def _remove_field_by_path(self, payload: Any, field_path: str) -> bool:
        """
        按路径移除字段

        :param payload: 原始载荷
        :param field_path: 字段路径
        :return: 是否移除成功
        """
        if not field_path:
            return False
        current_value = payload
        parts = field_path.split('.')
        for part in parts[:-1]:
            if isinstance(current_value, dict):
                mapping_value = self._get_mapping_value_by_part(current_value, part)
                if mapping_value is self._MISSING or mapping_value is self._AMBIGUOUS:
                    return False
                current_value = mapping_value
            elif isinstance(current_value, list) and part.isdigit():
                current_index = int(part)
                if current_index >= len(current_value):
                    return False
                current_value = current_value[current_index]
            else:
                return False

        target_part = parts[-1]
        if isinstance(current_value, dict):
            resolved_key = self._resolve_mapping_key_by_part(current_value, target_part)
            if resolved_key is self._MISSING or resolved_key is self._AMBIGUOUS:
                return False
            del current_value[resolved_key]
            return True
        if isinstance(current_value, list) and target_part.isdigit():
            current_index = int(target_part)
            if current_index >= len(current_value):
                return False
            current_value.pop(current_index)
            return True
        return False

    def _resolve_mapping_key_by_part(self, payload: dict[str, Any], part: str) -> str | object:
        """
        解析字段片段在字典中的真实键名

        :param payload: 当前字典载荷
        :param part: 当前路径片段
        :return: 真实键名或哨兵值
        """
        if part in payload:
            return part
        normalized_part = self._normalize_include_key(part)
        matched_keys = [key for key in payload if self._normalize_include_key(str(key)) == normalized_part]
        if len(matched_keys) == 1:
            return matched_keys[0]
        if len(matched_keys) > 1:
            return self._AMBIGUOUS
        return self._MISSING

    @staticmethod
    def _resolve_include_root(
        root: RequestLogFieldRoot | ResponseLogFieldRoot | str, candidates: tuple[str, ...]
    ) -> str | None:
        """
        解析 include 根节点到标准写法

        :param root: 原始根节点
        :param candidates: 候选根节点
        :return: 标准根节点
        """
        normalized_root = Log._normalize_include_key(str(root))
        for candidate in candidates:
            if Log._normalize_include_key(candidate) == normalized_root:
                return candidate
        return None

    @staticmethod
    def _normalize_include_key(field_name: str) -> str:
        """
        标准化 include 字段名

        :param field_name: 原始字段名
        :return: 标准化后的字段名
        """
        return ''.join(char.lower() for char in field_name if char.isalnum())

    @staticmethod
    def _get_mapping_keys(payload: Any) -> list[str]:
        """
        获取字典载荷的键列表

        :param payload: 原始载荷
        :return: 键列表
        """
        if isinstance(payload, dict):
            return list(payload.keys())
        return []

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
            user_agent_info = parse(user_agent or '')
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
            error_msg = self._get_result_message(result_dict)

        return status, error_msg

    @staticmethod
    def _get_result_message(result_dict: dict[str, Any]) -> Any:
        """
        获取响应结果中的消息字段，兼容 msg / message 两种写法

        :param result_dict: 操作结果字典
        :return: 消息内容
        """
        return result_dict.get('msg') if result_dict.get('msg') is not None else result_dict.get('message')

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
