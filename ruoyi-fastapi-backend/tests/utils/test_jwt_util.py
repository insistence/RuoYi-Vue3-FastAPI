from unittest.mock import patch

import pytest
from jwt.exceptions import DecodeError, InvalidAlgorithmError, InvalidKeyError

from exceptions.exception import AuthException
from utils.jwt_util import JwtUtil


@pytest.mark.parametrize('jwt_error', [DecodeError(), InvalidAlgorithmError(), InvalidKeyError()])
def test_decode_converts_pyjwt_errors_to_auth_exception(jwt_error: Exception) -> None:
    with (
        patch('utils.jwt_util.jwt.decode', side_effect=jwt_error),
        pytest.raises(AuthException) as exc_info,
    ):
        JwtUtil.decode('invalid-token')

    assert exc_info.value.message == '用户token已失效，请重新登录'


@pytest.mark.parametrize('jwt_error', [InvalidAlgorithmError(), InvalidKeyError()])
def test_encode_converts_pyjwt_errors_to_auth_exception(jwt_error: Exception) -> None:
    with (
        patch('utils.jwt_util.jwt.encode', side_effect=jwt_error),
        pytest.raises(AuthException) as exc_info,
    ):
        JwtUtil.encode({'user_id': '1'})

    assert exc_info.value.message == '用户token生成失败'
