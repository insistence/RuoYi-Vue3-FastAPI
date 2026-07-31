from typing import Any

import jwt
from jwt.exceptions import PyJWTError

from config.env import JwtConfig
from exceptions.exception import AuthException
from utils.log_util import logger


class JwtUtil:
    """
    JWT编解码工具类。
    """

    @classmethod
    def encode(cls, payload: dict[str, Any]) -> str:
        """
        生成JWT并将PyJWT异常转换为认证异常。

        :param payload: JWT载荷
        :return: 编码后的JWT
        """
        try:
            return jwt.encode(payload, JwtConfig.jwt_secret_key, algorithm=JwtConfig.jwt_algorithm)
        except PyJWTError as exc:
            logger.warning(f'JWT生成失败：{type(exc).__name__}')
            raise AuthException(data='', message='用户token生成失败') from exc

    @classmethod
    def decode(cls, token: str | bytes, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        解析JWT并将PyJWT异常转换为认证异常。

        :param token: 待解析的JWT
        :param options: PyJWT解析选项
        :return: JWT载荷
        """
        try:
            return jwt.decode(
                token,
                JwtConfig.jwt_secret_key,
                algorithms=[JwtConfig.jwt_algorithm],
                options=options,
            )
        except PyJWTError as exc:
            logger.warning(f'JWT校验失败：{type(exc).__name__}')
            raise AuthException(data='', message='用户token已失效，请重新登录') from exc
