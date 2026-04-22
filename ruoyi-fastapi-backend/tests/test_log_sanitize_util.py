import asyncio
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Request
from loguru import logger as _logger

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common.annotation.log_annotation import Log, RequestLogFieldRoot, ResponseLogFieldRoot
from common.enums import BusinessType
from config.env import LogConfig
from utils.log_util import LoggerInitializer, LogSanitizer, _build_text_assignment_patterns, _build_text_key_pattern


def test_sanitize_nested_log_payload() -> None:
    payload = {
        'jsonBody': {
            'password': 'plain-password',
            'apiKey': 'sk-123456',
            'systemPrompt': 'top secret prompt',
            'phonenumber': '13812345678',
            'email': 'admin@example.com',
            'ipaddr': '192.168.1.10',
        }
    }

    sanitized = LogSanitizer.sanitize_data(payload)

    assert sanitized['jsonBody']['password'] == '******'
    assert sanitized['jsonBody']['apiKey'] == '******'
    assert sanitized['jsonBody']['systemPrompt'] == '******'
    assert sanitized['jsonBody']['phonenumber'] == '138****5678'
    assert sanitized['jsonBody']['email'] == 'a***n@example.com'
    assert sanitized['jsonBody']['ipaddr'] == '192.168.1.10'


def test_ip_masking_can_be_enabled_by_partial_mask_field_configuration() -> None:
    payload = {
        'jsonBody': {
            'ipaddr': '192.168.1.10',
            'login_ip': '192.168.1.11',
        }
    }

    with patch.object(
        LogSanitizer,
        '_PARTIAL_MASK_FIELDS',
        LogSanitizer._PARTIAL_MASK_FIELDS | {'ip', 'ipaddr', 'operip', 'loginip'},
    ):
        sanitized = LogSanitizer.sanitize_data(payload)

    assert sanitized['jsonBody']['ipaddr'] == '192.168.1.*'
    assert sanitized['jsonBody']['login_ip'] == '192.168.1.*'


def test_sanitize_config_value_by_config_key() -> None:
    payload = {
        'configKey': 'sys.transport.privateKey',
        'configValue': '-----BEGIN PRIVATE KEY-----abc',
    }

    sanitized = LogSanitizer.sanitize_data(payload)

    assert sanitized['configValue'] == '******'


def test_sanitize_text_message() -> None:
    text = 'Authorization=Bearer abc.def password=123456 api_key=sk-test'
    expected_mask_count = 3

    sanitized = LogSanitizer.sanitize_text(text)

    assert 'abc.def' not in sanitized
    assert '123456' not in sanitized
    assert 'sk-test' not in sanitized
    assert sanitized.count('******') >= expected_mask_count


def test_sanitize_text_masks_configured_secret_fields() -> None:
    text = (
        'secret_key=my-secret private_key="-----BEGIN PRIVATE KEY-----abc" '
        "credential='cred-123' credentials=cred-list"
    )
    expected_mask_count = 4

    sanitized = LogSanitizer.sanitize_text(text)

    assert 'my-secret' not in sanitized
    assert '-----BEGIN PRIVATE KEY-----abc' not in sanitized
    assert 'cred-123' not in sanitized
    assert 'cred-list' not in sanitized
    assert sanitized.count('******') >= expected_mask_count


def test_sanitize_stringified_json_preserves_newlines_after_masking() -> None:
    text = '{\n  "password": "123456",\n  "userName": "admin"\n}'

    sanitized = LogSanitizer.sanitize_data({'operParam': text})

    assert sanitized['operParam'] == '{\n  "password": "******",\n  "userName": "admin"\n}'


def test_sanitize_text_masks_configured_partial_fields() -> None:
    text = 'email=admin@example.com phonenumber=13812345678 mobile="13812345679"'

    sanitized = LogSanitizer.sanitize_text(text)

    assert 'admin@example.com' not in sanitized
    assert '13812345678' not in sanitized
    assert '13812345679' not in sanitized
    assert 'a***n@example.com' in sanitized
    assert '138****5678' in sanitized
    assert '138****5679' in sanitized


def test_sanitize_text_can_enable_ip_masking_by_partial_mask_field_configuration() -> None:
    text = 'login_ip=192.168.1.10 ipaddr="192.168.1.11"'
    ip_fields = LogSanitizer._PARTIAL_MASK_FIELDS | {'ip', 'ipaddr', 'operip', 'loginip'}
    ip_key_pattern = '|'.join(
        sorted(
            {
                _build_text_key_pattern(field_name)
                for field_name in (*LogSanitizer._TEXT_PARTIAL_FIELDS, 'ip', 'ipaddr', 'oper_ip', 'login_ip')
            },
            key=len,
            reverse=True,
        )
    )

    with (
        patch.object(LogSanitizer, '_PARTIAL_MASK_FIELDS', ip_fields),
        patch.object(LogSanitizer, '_PARTIAL_KV_PATTERNS', _build_text_assignment_patterns(ip_key_pattern)),
    ):
        sanitized = LogSanitizer.sanitize_text(text)

    assert '192.168.1.10' not in sanitized
    assert '192.168.1.11' not in sanitized
    assert '192.168.1.*' in sanitized


def test_sanitize_text_masks_python_repr_like_payload() -> None:
    text = "ValueError({'secret_key': 'abc', 'password': '123456', 'api_key': 'sk-123'})"
    expected_mask_count = 3

    sanitized = LogSanitizer.sanitize_text(text)

    assert 'abc' not in sanitized
    assert '123456' not in sanitized
    assert 'sk-123' not in sanitized
    assert sanitized.count('******') >= expected_mask_count


def test_sanitize_text_masks_alphanumeric_verification_code() -> None:
    text = '短信验证码为A1B2'

    sanitized = LogSanitizer.sanitize_text(text)

    assert 'A1B2' not in sanitized
    assert '******' in sanitized


def test_sanitize_text_returns_original_when_mask_disabled() -> None:
    text = 'Authorization=Bearer abc.def password=123456 api_key=sk-test'

    with patch.object(LogConfig, 'log_mask_enabled', False):
        sanitized = LogSanitizer.sanitize_text(text)

    assert sanitized == text


def test_build_json_payload_sanitizes_exception_and_extra() -> None:
    initializer = LoggerInitializer()
    try:
        raise ValueError('token=abc.def')
    except ValueError as exc:
        exception = SimpleNamespace(
            type=type(exc),
            value=exc,
            traceback=exc.__traceback__,
        )
    record = {
        'time': datetime(2026, 4, 20, 12, 0, 0),
        'level': SimpleNamespace(name='ERROR'),
        'message': 'password=123456',
        'name': 'test_logger',
        'module': 'test_module',
        'function': 'test_function',
        'line': 1,
        'extra': {'authorization': 'Bearer abc.def', 'trace_id': 'trace-1'},
        'exception': exception,
    }

    initializer._patch_record(record)
    initializer._filter(record)
    payload = initializer._build_json_payload(record)

    assert '123456' not in payload['message']
    assert 'abc.def' not in payload['exception']['value']
    assert 'abc.def' not in payload['exception']['traceback']
    assert 'ValueError' in payload['exception']['traceback']
    assert payload['extra']['authorization'] == '******'


def test_plain_log_formatter_sanitizes_exception_traceback() -> None:
    initializer = LoggerInitializer()
    outputs = []
    test_logger = _logger.patch(initializer._patch_record)
    test_logger.remove()
    test_logger.add(
        lambda message: outputs.append(str(message)),
        format=initializer._plain_log_formatter,
        filter=initializer._filter,
        backtrace=False,
        diagnose=False,
    )

    try:
        raise ValueError('password=123456 token=abc.def')
    except ValueError:
        test_logger.exception('boom password=123456')

    output = outputs[0]

    assert '123456' not in output
    assert 'abc.def' not in output
    assert 'ValueError' in output
    assert '******' in output


def test_get_request_params_returns_structured_payload() -> None:
    async def receive() -> dict:
        return {
            'type': 'http.request',
            'body': b'{"password":"plain-password","phonenumber":"13812345678"}',
            'more_body': False,
        }

    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/test',
            'headers': [(b'content-type', b'application/json')],
            'path_params': {},
            'query_string': b'page=1',
        },
        receive=receive,
    )

    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)
    params = asyncio.run(log_decorator._get_request_params(request))

    assert params['query_params']['page'] == '1'
    assert params['json_body']['password'] == 'plain-password'


def test_get_request_params_falls_back_to_raw_body_when_json_invalid() -> None:
    async def receive() -> dict:
        return {
            'type': 'http.request',
            'body': b'{bad json',
            'more_body': False,
        }

    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/test',
            'headers': [(b'content-type', b'application/json')],
            'path_params': {},
            'query_string': b'',
        },
        receive=receive,
    )

    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        params = asyncio.run(log_decorator._get_request_params(request))

    assert params['raw_body'] == '{bad json'
    mock_warning.assert_called_once()
    assert '解析失败' in mock_warning.call_args.args[0]


def test_get_request_params_decodes_non_utf8_body_without_raising() -> None:
    async def receive() -> dict:
        return {
            'type': 'http.request',
            'body': b'\xff\xfeabc',
            'more_body': False,
        }

    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/test',
            'headers': [(b'content-type', b'text/plain')],
            'path_params': {},
            'query_string': b'',
        },
        receive=receive,
    )

    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)
    params = asyncio.run(log_decorator._get_request_params(request))

    assert params['raw_body'].endswith('abc')
    assert '\ufffd' in params['raw_body']


def test_log_handles_missing_user_agent_without_error() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER, log_type='login')

    assert log_decorator._get_oper_type(None) == 0

    login_log = log_decorator._get_login_log(
        None,
        oper_ip='127.0.0.1',
        oper_location='内网IP',
        oper_time=datetime(2026, 4, 20, 12, 0, 0),
        origin_kwargs={},
    )

    assert login_log['ipaddr'] == '127.0.0.1'
    assert login_log['loginLocation'] == '内网IP'
    assert login_log['browser'] == 'Other'
    assert login_log['os'] == 'Other'


def test_build_log_text_with_summary_mode() -> None:
    log_decorator = Log(
        title='测试日志',
        business_type=BusinessType.OTHER,
        request_log_mode='summary',
    )

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'query_params': {'page': '1'},
                'json_body': {'password': 'plain-password', 'modelName': 'demo-model'},
            }
        ),
        mode='summary',
        include_fields=(),
        exclude_fields=(),
        payload_kind='request',
    )
    log_payload = json.loads(log_text)

    assert log_payload['mode'] == 'summary'
    assert log_payload['query_param_keys'] == ['page']
    assert log_payload['json_body_keys'] == ['password', 'modelName']


def test_build_log_text_with_include_mode() -> None:
    log_decorator = Log(
        title='测试日志',
        business_type=BusinessType.OTHER,
        response_log_mode='include',
        response_include_fields=('data.token', 'data.userName'),
    )

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'code': 200,
                'msg': 'success',
                'data': {'token': 'abc.def', 'userName': 'admin', 'extra': 'ignored'},
            }
        ),
        mode='include',
        include_fields=('data.token', 'data.userName'),
        exclude_fields=(),
        payload_kind='response',
    )
    log_payload = json.loads(log_text)

    assert log_payload['mode'] == 'include'
    assert log_payload['selected']['data.token'] == '******'
    assert log_payload['selected']['data.userName'] == 'admin'
    assert 'data.extra' not in log_payload['selected']


def test_include_fields_support_snake_case_matching_camel_case_payload() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'json_body': {
                    'modelCode': 'deepseek-chat',
                    'supportReasoning': 'Y',
                }
            }
        ),
        mode='include',
        include_fields=('json_body.model_code', 'json_body.support_reasoning'),
        exclude_fields=(),
        payload_kind='request',
    )
    log_payload = json.loads(log_text)

    assert log_payload['selected']['json_body.model_code'] == 'deepseek-chat'
    assert log_payload['selected']['json_body.support_reasoning'] == 'Y'


def test_include_fields_support_camel_case_matching_snake_case_payload() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'data': {
                    'user_name': 'admin',
                    'login_ip': '192.168.1.10',
                }
            }
        ),
        mode='include',
        include_fields=('data.userName', 'data.loginIp'),
        exclude_fields=(),
        payload_kind='response',
    )
    log_payload = json.loads(log_text)

    assert log_payload['selected']['data.userName'] == 'admin'
    assert log_payload['selected']['data.loginIp'] == '192.168.1.10'


def test_request_field_helper_builds_canonical_path() -> None:
    assert RequestLogFieldRoot.JSON_BODY.field('model_code') == 'json_body.model_code'
    assert ResponseLogFieldRoot.DATA.field('userName') == 'data.userName'


def test_code_field_masking_only_applies_to_login_like_verification_code() -> None:
    login_payload = {
        'uuid': 'captcha-session',
        'code': 'A1B2',
        'msg': 'login',
    }
    business_payload = {
        'code': '200',
        'msg': 'ok',
    }

    sanitized_login_payload = LogSanitizer.sanitize_data(login_payload)
    sanitized_business_payload = LogSanitizer.sanitize_data(business_payload)

    assert sanitized_login_payload['code'] == '******'
    assert sanitized_business_payload['code'] == '200'


def test_build_log_text_with_exclude_mode() -> None:
    log_decorator = Log(
        title='测试日志',
        business_type=BusinessType.OTHER,
        request_log_mode='exclude',
        request_exclude_fields=('json_body.api_key',),
    )

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'json_body': {
                    'modelCode': 'deepseek-chat',
                    'apiKey': 'sk-test',
                    'baseUrl': 'https://api.example.com',
                }
            }
        ),
        mode='exclude',
        include_fields=(),
        exclude_fields=('json_body.api_key',),
        payload_kind='request',
    )
    log_payload = json.loads(log_text)

    assert 'apiKey' not in log_payload['json_body']
    assert log_payload['json_body']['modelCode'] == 'deepseek-chat'
    assert log_payload['json_body']['baseUrl'] == 'https://api.example.com'


def test_exclude_fields_support_snake_case_matching_camel_case_payload() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'data': {
                    'apiKey': '******',
                    'baseUrl': 'https://api.example.com',
                }
            }
        ),
        mode='exclude',
        include_fields=(),
        exclude_fields=('data.api_key',),
        payload_kind='response',
    )
    log_payload = json.loads(log_text)

    assert 'apiKey' not in log_payload['data']
    assert log_payload['data']['baseUrl'] == 'https://api.example.com'


def test_exclude_fields_remove_multiple_list_indexes_without_shift() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    log_text = log_decorator._build_log_text(
        LogSanitizer.sanitize_data(
            {
                'rows': [
                    {'id': 1},
                    {'id': 2},
                    {'id': 3},
                ]
            }
        ),
        mode='exclude',
        include_fields=(),
        exclude_fields=('rows.0', 'rows.1'),
        payload_kind='response',
    )
    log_payload = json.loads(log_text)

    assert log_payload['rows'] == [{'id': 3}]


def test_collect_field_path_warnings_for_invalid_root() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    warnings = log_decorator._collect_field_path_warnings(
        mode='include',
        include_fields=('body.modelCode',),
        exclude_fields=(),
        payload_kind='request',
    )

    assert len(warnings) == 1
    assert 'body.modelCode' in warnings[0]
    assert 'json_body' in warnings[0]


def test_collect_field_path_warnings_accepts_normalized_root() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    warnings = log_decorator._collect_field_path_warnings(
        mode='include',
        include_fields=('jsonBody.modelCode',),
        exclude_fields=(),
        payload_kind='request',
    )

    assert warnings == []


def test_collect_field_path_warnings_for_missing_include_fields() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    warnings = log_decorator._collect_field_path_warnings(
        mode='include',
        include_fields=(),
        exclude_fields=(),
        payload_kind='response',
    )

    assert len(warnings) == 1
    assert 'include模式' in warnings[0]
    assert 'data' in warnings[0]


def test_collect_field_path_warnings_for_missing_exclude_fields() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    warnings = log_decorator._collect_field_path_warnings(
        mode='exclude',
        include_fields=(),
        exclude_fields=(),
        payload_kind='request',
    )

    assert len(warnings) == 1
    assert 'exclude模式' in warnings[0]
    assert 'json_body' in warnings[0]


def test_log_warns_when_include_fields_do_not_match_mode() -> None:
    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        Log(
            title='测试日志',
            business_type=BusinessType.OTHER,
            request_log_mode='summary',
            request_include_fields=('json_body.modelCode',),
        )

    mock_warning.assert_called_once()
    assert '不会生效' in mock_warning.call_args.args[0]


def test_request_include_fields_invalid_root_raises_value_error() -> None:
    try:
        Log(
            title='测试日志',
            business_type=BusinessType.OTHER,
            request_log_mode='include',
            request_include_fields=('body.modelCode',),
        )
    except ValueError as exc:
        assert 'body.modelCode' in str(exc)
    else:
        raise AssertionError('expected ValueError for invalid request include root')


def test_request_exclude_fields_invalid_root_raises_value_error() -> None:
    try:
        Log(
            title='测试日志',
            business_type=BusinessType.OTHER,
            request_log_mode='exclude',
            request_exclude_fields=('body.apiKey',),
        )
    except ValueError as exc:
        assert 'body.apiKey' in str(exc)
    else:
        raise AssertionError('expected ValueError for invalid request exclude root')


def test_build_log_text_warns_for_missing_include_field() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        log_text = log_decorator._build_log_text(
            LogSanitizer.sanitize_data(
                {
                    'json_body': {
                        'modelCode': 'deepseek-chat',
                    }
                }
            ),
            mode='include',
            include_fields=('json_body.modleCode',),
            exclude_fields=(),
            payload_kind='request',
        )

    log_payload = json.loads(log_text)

    assert log_payload['selected'] == {}
    mock_warning.assert_called_once()
    assert '未命中' in mock_warning.call_args.args[0]
    assert 'modleCode' in mock_warning.call_args.args[0]


def test_missing_include_field_warning_only_emitted_once() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)
    payload = LogSanitizer.sanitize_data({'data': {'userName': 'admin'}})

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        log_decorator._build_log_text(
            payload,
            mode='include',
            include_fields=('data.userNmae',),
            exclude_fields=(),
            payload_kind='response',
        )
        log_decorator._build_log_text(
            payload,
            mode='include',
            include_fields=('data.userNmae',),
            exclude_fields=(),
            payload_kind='response',
        )

    mock_warning.assert_called_once()


def test_include_fields_keep_explicit_none_value() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        log_text = log_decorator._build_log_text(
            LogSanitizer.sanitize_data(
                {
                    'data': {
                        'userName': None,
                    }
                }
            ),
            mode='include',
            include_fields=('data.userName',),
            exclude_fields=(),
            payload_kind='response',
        )

    log_payload = json.loads(log_text)

    assert 'data.userName' in log_payload['selected']
    assert log_payload['selected']['data.userName'] is None
    mock_warning.assert_not_called()


def test_include_field_warning_reports_ambiguous_normalized_match() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        log_text = log_decorator._build_log_text(
            LogSanitizer.sanitize_data(
                {
                    'data': {
                        'user_name': 'admin',
                        'userName': 'root',
                    }
                }
            ),
            mode='include',
            include_fields=('data.username',),
            exclude_fields=(),
            payload_kind='response',
        )

    log_payload = json.loads(log_text)

    assert log_payload['selected'] == {}
    mock_warning.assert_called_once()
    assert '命名冲突' in mock_warning.call_args.args[0]
    assert 'user_name' in mock_warning.call_args.args[0]
    assert 'userName' in mock_warning.call_args.args[0]


def test_build_log_text_warns_for_missing_exclude_field() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    with patch('common.annotation.log_annotation.logger.warning') as mock_warning:
        log_text = log_decorator._build_log_text(
            LogSanitizer.sanitize_data(
                {
                    'json_body': {
                        'modelCode': 'deepseek-chat',
                    }
                }
            ),
            mode='exclude',
            include_fields=(),
            exclude_fields=('json_body.apiKey',),
            payload_kind='request',
        )

    log_payload = json.loads(log_text)

    assert log_payload['json_body']['modelCode'] == 'deepseek-chat'
    mock_warning.assert_called_once()
    assert '排除路径未命中' in mock_warning.call_args.args[0]


def test_build_summary_payload_supports_message_field_fallback() -> None:
    log_decorator = Log(title='测试日志', business_type=BusinessType.OTHER)

    summary_payload = log_decorator._build_summary_payload({'code': 200, 'message': '获取成功'}, 'response')
    status, error_msg = log_decorator._get_status_and_error_msg({'code': 500, 'message': '获取失败'})

    assert summary_payload['msg'] == '获取成功'
    assert status == 1
    assert error_msg == '获取失败'
