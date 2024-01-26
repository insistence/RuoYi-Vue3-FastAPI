from fastapi import Request
from fastapi.exceptions import HTTPException
from server import app
from exceptions.auth_exception import AuthException
from exceptions.permission_exception import PermissionException
from utils.response_util import ResponseUtil, JSONResponse, jsonable_encoder


# 自定义token检验异常
@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return ResponseUtil.unauthorized(data=exc.data, msg=exc.message)


# 自定义权限检验异常
@app.exception_handler(PermissionException)
async def permission_exception_handler(request: Request, exc: PermissionException):
    return ResponseUtil.forbidden(data=exc.data, msg=exc.message)


# 处理其他http请求异常
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        content=jsonable_encoder({"code": exc.status_code, "msg": exc.detail}),
        status_code=exc.status_code
    )
