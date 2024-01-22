from fastapi import status
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.encoders import jsonable_encoder
from typing import Any, Dict, Optional
from pydantic import BaseModel
from datetime import datetime


class ResponseUtil:
    """
    响应工具类
    """

    @classmethod
    def success(cls, msg: str = '操作成功', data: Optional[Any] = None, rows: Optional[Any] = None,
                dict_content: Optional[Dict] = None, model_content: Optional[BaseModel] = None) -> Response:
        """
        成功响应方法
        :param msg: 可选，自定义成功响应信息
        :param data: 可选，成功响应结果中属性为data的值
        :param rows: 可选，成功响应结果中属性为rows的值
        :param dict_content: 可选，dict类型，成功响应结果中自定义属性的值
        :param model_content: 可选，BaseModel类型，成功响应结果中自定义属性的值
        :return: 成功响应结果
        """
        result = {
            'code': 200,
            'msg': msg
        }

        if data is not None:
            result['data'] = data
        if rows is not None:
            result['rows'] = rows
        if dict_content is not None:
            result.update(dict_content)
        if model_content is not None:
            result.update(model_content.model_dump(by_alias=True))

        result.update({'success': True, 'time': datetime.now()})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(result)
        )

    @classmethod
    def failure(cls, msg: str = '操作失败', data: Optional[Any] = None, rows: Optional[Any] = None,
                dict_content: Optional[Dict] = None, model_content: Optional[BaseModel] = None) -> Response:
        """
        失败响应方法
        :param msg: 可选，自定义失败响应信息
        :param data: 可选，失败响应结果中属性为data的值
        :param rows: 可选，失败响应结果中属性为rows的值
        :param dict_content: 可选，dict类型，失败响应结果中自定义属性的值
        :param model_content: 可选，BaseModel类型，失败响应结果中自定义属性的值
        :return: 失败响应结果
        """
        result = {
            'code': 601,
            'msg': msg
        }

        if data is not None:
            result['data'] = data
        if rows is not None:
            result['rows'] = rows
        if dict_content is not None:
            result.update(dict_content)
        if model_content is not None:
            result.update(model_content.model_dump(by_alias=True))

        result.update({'success': False, 'time': datetime.now()})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(result)
        )

    @classmethod
    def unauthorized(cls, msg: str = '登录信息已过期，访问系统资源失败', data: Optional[Any] = None, rows: Optional[Any] = None,
                     dict_content: Optional[Dict] = None, model_content: Optional[BaseModel] = None) -> Response:
        """
        未认证响应方法
        :param msg: 可选，自定义未认证响应信息
        :param data: 可选，未认证响应结果中属性为data的值
        :param rows: 可选，未认证响应结果中属性为rows的值
        :param dict_content: 可选，dict类型，未认证响应结果中自定义属性的值
        :param model_content: 可选，BaseModel类型，未认证响应结果中自定义属性的值
        :return: 未认证响应结果
        """
        result = {
            'code': 401,
            'msg': msg
        }

        if data is not None:
            result['data'] = data
        if rows is not None:
            result['rows'] = rows
        if dict_content is not None:
            result.update(dict_content)
        if model_content is not None:
            result.update(model_content.model_dump(by_alias=True))

        result.update({'success': False, 'time': datetime.now()})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(result)
        )

    @classmethod
    def forbidden(cls, msg: str = '该用户无此接口权限', data: Optional[Any] = None, rows: Optional[Any] = None,
                  dict_content: Optional[Dict] = None, model_content: Optional[BaseModel] = None) -> Response:
        """
        未认证响应方法
        :param msg: 可选，自定义未认证响应信息
        :param data: 可选，未认证响应结果中属性为data的值
        :param rows: 可选，未认证响应结果中属性为rows的值
        :param dict_content: 可选，dict类型，未认证响应结果中自定义属性的值
        :param model_content: 可选，BaseModel类型，未认证响应结果中自定义属性的值
        :return: 未认证响应结果
        """
        result = {
            'code': 403,
            'msg': msg
        }

        if data is not None:
            result['data'] = data
        if rows is not None:
            result['rows'] = rows
        if dict_content is not None:
            result.update(dict_content)
        if model_content is not None:
            result.update(model_content.model_dump(by_alias=True))

        result.update({'success': False, 'time': datetime.now()})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(result)
        )

    @classmethod
    def error(cls, msg: str = '接口异常', data: Optional[Any] = None, rows: Optional[Any] = None,
              dict_content: Optional[Dict] = None, model_content: Optional[BaseModel] = None) -> Response:
        """
        错误响应方法
        :param msg: 可选，自定义错误响应信息
        :param data: 可选，错误响应结果中属性为data的值
        :param rows: 可选，错误响应结果中属性为rows的值
        :param dict_content: 可选，dict类型，错误响应结果中自定义属性的值
        :param model_content: 可选，BaseModel类型，错误响应结果中自定义属性的值
        :return: 错误响应结果
        """
        result = {
            'code': 500,
            'msg': msg
        }

        if data is not None:
            result['data'] = data
        if rows is not None:
            result['rows'] = rows
        if dict_content is not None:
            result.update(dict_content)
        if model_content is not None:
            result.update(model_content.model_dump(by_alias=True))

        result.update({'success': False, 'time': datetime.now()})

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(result)
        )

    @classmethod
    def streaming(cls, *, data: Any = None):
        """
        流式响应方法
        :param data: 流式传输的内容
        :return: 流式响应结果
        """
        return StreamingResponse(
            status_code=status.HTTP_200_OK,
            content=data
        )


def response_200(*, data: Any = None, message="获取成功") -> Response:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            {
                'code': 200,
                'message': message,
                'data': data,
                'success': 'true',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    )


def response_400(*, data: Any = None, message: str = "获取失败") -> Response:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=jsonable_encoder(
            {
                'code': 400,
                'message': message,
                'data': data,
                'success': 'false',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    )


def response_401(*, data: Any = None, message: str = "获取失败") -> Response:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=jsonable_encoder(
            {
                'code': 401,
                'message': message,
                'data': data,
                'success': 'false',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    )


def response_403(*, data: Any = None, message: str = "获取失败") -> Response:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=jsonable_encoder(
            {
                'code': 403,
                'message': message,
                'data': data,
                'success': 'false',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    )


def response_500(*, data: Any = None, message: str = "接口异常") -> Response:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(
            {
                'code': 500,
                'message': message,
                'data': data,
                'success': 'false',
                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    )


def streaming_response_200(*, data: Any = None):
    return StreamingResponse(
        status_code=status.HTTP_200_OK,
        content=data,
    )


class AuthException(Exception):
    """
    自定义令牌异常AuthException
    """

    def __init__(self, data: str = None, message: str = None):
        self.data = data
        self.message = message


class PermissionException(Exception):
    """
    自定义权限异常PermissionException
    """

    def __init__(self, data: str = None, message: str = None):
        self.data = data
        self.message = message


class LoginException(Exception):
    """
    自定义登录异常LoginException
    """

    def __init__(self, data: str = None, message: str = None):
        self.data = data
        self.message = message
