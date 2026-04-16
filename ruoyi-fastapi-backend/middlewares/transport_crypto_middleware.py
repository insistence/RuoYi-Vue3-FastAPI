import json
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.datastructures import Headers, QueryParams
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from common.constant import HttpStatusConstant
from config.env import AppConfig, TransportCryptoConfig
from utils.transport_crypto_util import (
    DecryptedTransportEnvelope,
    TransportCryptoMonitorUtil,
    TransportCryptoUtil,
    TransportSecurityUtil,
)


class TransportCryptoMiddleware:
    """
    传输层请求解密与响应加密中间件
    """

    _ENCRYPT_REQUEST_HEADER = 'x-transport-encrypt'
    _ENCRYPT_RESPONSE_HEADER = 'x-body-encrypted'
    _ENCRYPT_ALG_HEADER = 'x-encrypt-alg'
    _ENCRYPT_KID_HEADER = 'x-key-id'
    _MONITOR_REQUEST_MODE_HEADER = 'x-transport-request-mode'
    _MONITOR_RESPONSE_MODE_HEADER = 'x-transport-response-mode'
    _MONITOR_STATUS_HEADER = 'x-transport-crypto-status'
    _MONITOR_KID_HEADER = 'x-transport-key-id'

    def __init__(self, app: ASGIApp) -> None:
        """
        初始化传输层加解密中间件

        :param app: FastAPI/Starlette应用对象
        :return: None
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        拦截HTTP请求，按配置执行请求解密与响应加密

        :param scope: 当前ASGI请求作用域
        :param receive: ASGI receive函数
        :param send: ASGI send函数
        :return: None
        """
        if scope['type'] != 'http' or not TransportCryptoConfig.transport_crypto_enabled:
            await self.app(scope, receive, send)
            return

        current_app = scope.get('app')
        path = self._normalize_path(str(scope.get('path', '')))
        if (
            self._is_excluded_path(path)
            or TransportCryptoConfig.transport_crypto_mode == 'off'
            or not self._is_enabled_path(path)
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_encrypted = headers.get(self._ENCRYPT_REQUEST_HEADER) == '1'
        request_required = TransportCryptoConfig.transport_crypto_mode == 'required' or self._is_required_path(path)

        if request_required and not request_encrypted:
            await TransportCryptoMonitorUtil.record_plain_request(current_app)
            await TransportCryptoMonitorUtil.record_required_rejected(
                current_app, str(scope.get('method', '')).upper(), path
            )
            await TransportCryptoMonitorUtil.record_plain_response(current_app)
            await self._send_error_response(
                scope,
                receive,
                send,
                '当前接口要求使用加密传输',
                headers=self._build_monitor_headers(
                    request_mode='plain',
                    response_mode='plain',
                    crypto_status='required_missing',
                ),
            )
            return

        if not request_encrypted:
            await TransportCryptoMonitorUtil.record_plain_request(current_app)
            response_observer = self._build_passthrough_response_observer(
                app=current_app,
                send=send,
                request_mode='plain',
                crypto_status='pass_through',
            )
            await self.app(scope, receive, response_observer)
            return

        body = await self._read_body(receive)
        request = Request(scope, receive=self._build_receive(body))
        try:
            decrypted_scope, decrypted_body, crypto_context = await self._decrypt_request(scope, request, headers, body)
            await TransportCryptoMonitorUtil.record_encrypted_request(current_app, str(crypto_context['kid']))
            await TransportCryptoMonitorUtil.record_decrypt_success(current_app, str(crypto_context['kid']))
        except Exception as exc:
            error_crypto_context = self._build_error_crypto_context(scope, headers, body)
            error_kid = (
                str(error_crypto_context['kid'])
                if error_crypto_context
                else self._extract_request_kid(scope, headers, body)
            )
            await TransportCryptoMonitorUtil.record_encrypted_request(current_app, error_kid)
            failure_reason = self._classify_failure_reason(str(exc))
            await TransportCryptoMonitorUtil.record_decrypt_failure(
                current_app,
                method=str(scope.get('method', '')).upper(),
                path=path,
                reason=failure_reason,
                kid=error_kid,
            )
            if error_crypto_context:
                await TransportCryptoMonitorUtil.record_encrypted_response(current_app, error_kid, is_error=True)
            else:
                await TransportCryptoMonitorUtil.record_plain_response(current_app)
            await self._send_error_response(
                scope,
                receive,
                send,
                str(exc) or '加密请求解析失败',
                error_crypto_context,
                headers=self._build_monitor_headers(
                    request_mode='encrypted',
                    response_mode='encrypted' if error_crypto_context else 'plain',
                    crypto_status=failure_reason,
                    kid=error_kid,
                ),
            )
            return

        async def send_wrapper(message: Message) -> None:
            await response_encryptor(message)

        response_encryptor = self._build_response_encryptor(
            app=current_app,
            scope=decrypted_scope,
            send=send,
            crypto_context=crypto_context,
        )
        await self.app(decrypted_scope, self._build_receive(decrypted_body), send_wrapper)

    async def _decrypt_request(
        self,
        scope: Scope,
        request: Request,
        headers: Headers,
        body: bytes,
    ) -> tuple[Scope, bytes, dict[str, str | bytes | bool]]:
        """
        解密请求并回写解密后的headers、query和body

        :param scope: 当前ASGI请求作用域
        :param request: FastAPI请求对象
        :param headers: 当前请求头对象
        :param body: 原始请求体字节串
        :return: 解密后的scope、请求体与加密上下文
        """
        new_scope = dict(scope)
        new_scope['state'] = dict(scope.get('state', {}))
        new_scope['headers'] = self._remove_header(new_scope.get('headers', []), b'accept-encoding')
        content_type = headers.get('content-type', '')

        query_envelope = self._extract_query_envelope(new_scope)
        body_envelope = self._extract_body_envelope(content_type, body)

        if query_envelope is None and body_envelope is None:
            raise ValueError('未找到可解密的请求载荷')

        crypto_context: dict[str, str | bytes | bool] | None = None
        if query_envelope is not None:
            decrypted_query = await self._decrypt_envelope(request, scope, query_envelope)
            query_payload = self._loads_json_mapping(decrypted_query.plaintext.decode('utf-8'))
            new_scope['query_string'] = urlencode(query_payload, doseq=True).encode('utf-8')
            crypto_context = self._build_crypto_context(decrypted_query)

        decrypted_body = body
        if body_envelope is not None:
            decrypted_body_payload = await self._decrypt_envelope(request, scope, body_envelope)
            if crypto_context and crypto_context['kid'] != decrypted_body_payload.kid:
                raise ValueError('请求中存在不一致的密钥版本')
            if crypto_context and crypto_context['aes_key'] != decrypted_body_payload.aes_key:
                raise ValueError('请求中存在不一致的会话密钥')
            if crypto_context is None:
                crypto_context = self._build_crypto_context(decrypted_body_payload)

            if 'application/x-www-form-urlencoded' in content_type:
                form_payload = self._loads_json_mapping(decrypted_body_payload.plaintext.decode('utf-8'))
                decrypted_body = urlencode(form_payload, doseq=True).encode('utf-8')
            else:
                decrypted_body = decrypted_body_payload.plaintext
            new_scope['headers'] = self._replace_header(
                new_scope.get('headers', []), b'content-length', str(len(decrypted_body)).encode('utf-8')
            )

        if crypto_context is None:
            raise ValueError('加密请求缺少可用的密钥上下文')

        new_scope['state']['transport_crypto_context'] = crypto_context
        return new_scope, decrypted_body, crypto_context

    async def _decrypt_envelope(
        self,
        request: Request,
        scope: Scope,
        envelope: dict[str, str],
    ) -> DecryptedTransportEnvelope:
        """
        解密单个请求信封并执行时间窗、防重放校验

        :param request: 当前请求对象
        :param scope: 当前ASGI请求作用域
        :param envelope: 请求信封字典
        :return: 解密后的请求信封对象
        """
        decrypted_payload = TransportCryptoUtil.decrypt_envelope(
            envelope,
            expected_method=str(scope.get('method', '')).upper(),
            expected_path=self._normalize_path(str(scope.get('path', ''))),
        )
        TransportSecurityUtil.validate_timestamp(decrypted_payload.timestamp)
        await TransportSecurityUtil.validate_replay(request, decrypted_payload.kid, decrypted_payload.nonce)
        return decrypted_payload

    def _extract_query_envelope(self, scope: Scope) -> dict[str, str] | None:
        """
        从查询参数中提取加密信封

        :param scope: 当前ASGI请求作用域
        :return: 查询参数中的信封字典，不存在时返回None
        """
        query_params = QueryParams(scope.get('query_string', b'').decode('utf-8'))
        encrypted_query = query_params.get('__enc')
        if not encrypted_query:
            return None
        return TransportCryptoUtil.decode_query_envelope(encrypted_query)

    def _extract_body_envelope(self, content_type: str, body: bytes) -> dict[str, str] | None:
        """
        根据内容类型从请求体中提取加密信封

        :param content_type: 当前请求内容类型
        :param body: 原始请求体字节串
        :return: 请求体中的信封字典，不存在时返回None
        """
        if not body or 'multipart/form-data' in content_type:
            return None

        if 'application/json' in content_type:
            body_payload = json.loads(body.decode('utf-8'))
            if not isinstance(body_payload, dict):
                raise ValueError('加密请求体格式不合法')
            return body_payload

        if 'application/x-www-form-urlencoded' in content_type:
            parsed_form = parse_qs(body.decode('utf-8'), keep_blank_values=True)
            body_envelope = {
                key: values[-1] if isinstance(values, list) else values for key, values in parsed_form.items()
            }
            aad = body_envelope.get('aad')
            if isinstance(aad, str) and aad:
                try:
                    parsed_aad = json.loads(aad)
                    if isinstance(parsed_aad, dict):
                        body_envelope['aad'] = parsed_aad
                except json.JSONDecodeError:
                    pass
            return body_envelope

        return None

    def _build_response_encryptor(
        self,
        app: FastAPI | None,
        scope: Scope,
        send: Send,
        crypto_context: dict[str, str | bytes | bool],
    ) -> Callable[[Message], Awaitable[None]]:
        """
        构建响应加密发送器，仅对JSON响应执行加密

        :param scope: 当前ASGI请求作用域
        :param send: ASGI send函数
        :param crypto_context: 当前请求加密上下文
        :return: 包装后的ASGI send函数
        """
        response_start_message: Message | None = None
        buffered_json_body: list[bytes] = []
        should_buffer_json = False

        async def _encrypt_response(message: Message) -> None:
            nonlocal response_start_message, should_buffer_json

            if message['type'] == 'http.response.start':
                response_start_message = message
                headers = Headers(raw=message.get('headers', []))
                content_type = headers.get('content-type', '')
                should_buffer_json = 'application/json' in content_type
                if not should_buffer_json:
                    await TransportCryptoMonitorUtil.record_plain_response(app)
                    await send(
                        {
                            **message,
                            'headers': self._merge_response_headers(
                                message.get('headers', []),
                                self._build_monitor_headers(
                                    request_mode='encrypted',
                                    response_mode='plain',
                                    crypto_status='ok',
                                    kid=str(crypto_context['kid']),
                                ),
                            ),
                        }
                    )
                return

            if message['type'] != 'http.response.body':
                await send(message)
                return

            if not should_buffer_json or response_start_message is None:
                await send(message)
                return

            buffered_json_body.append(message.get('body', b''))
            if message.get('more_body', False):
                return

            encrypted_body = TransportCryptoUtil.encrypt_response_body(
                aes_key=crypto_context['aes_key'],
                payload=b''.join(buffered_json_body),
                kid=str(crypto_context['kid']),
                method=str(scope.get('method', '')),
                path=self._normalize_path(str(scope.get('path', ''))),
            )
            response_headers = self._replace_header(
                response_start_message.get('headers', []),
                b'content-length',
                str(len(encrypted_body)).encode('utf-8'),
            )
            response_headers = self._replace_header(response_headers, b'content-type', b'application/json')
            response_headers = self._replace_header(
                response_headers, self._ENCRYPT_RESPONSE_HEADER.encode('utf-8'), b'1'
            )
            response_headers = self._replace_header(
                response_headers,
                self._ENCRYPT_ALG_HEADER.encode('utf-8'),
                TransportCryptoUtil.get_response_envelope_algorithm().encode('utf-8'),
            )
            response_headers = self._replace_header(
                response_headers,
                self._ENCRYPT_KID_HEADER.encode('utf-8'),
                str(crypto_context['kid']).encode('utf-8'),
            )
            response_headers = self._merge_response_headers(
                response_headers,
                self._build_monitor_headers(
                    request_mode='encrypted',
                    response_mode='encrypted',
                    crypto_status='ok',
                    kid=str(crypto_context['kid']),
                ),
            )
            await TransportCryptoMonitorUtil.record_encrypted_response(app, str(crypto_context['kid']))
            await send({**response_start_message, 'headers': response_headers})
            await send({'type': 'http.response.body', 'body': encrypted_body, 'more_body': False})

        return _encrypt_response

    def _build_passthrough_response_observer(
        self,
        app: FastAPI | None,
        send: Send,
        request_mode: str,
        crypto_status: str,
        kid: str | None = None,
    ) -> Callable[[Message], Awaitable[None]]:
        """
        构建明文响应观察器，为响应追加监控诊断头

        :param send: ASGI send函数
        :param request_mode: 请求传输模式
        :param crypto_status: 当前传输层处理状态
        :param kid: 可选的密钥版本
        :return: 包装后的ASGI send函数
        """
        has_recorded_response = False

        async def _observe_response(message: Message) -> None:
            nonlocal has_recorded_response

            if message['type'] == 'http.response.start':
                if not has_recorded_response:
                    await TransportCryptoMonitorUtil.record_plain_response(app)
                    has_recorded_response = True
                await send(
                    {
                        **message,
                        'headers': self._merge_response_headers(
                            message.get('headers', []),
                            self._build_monitor_headers(
                                request_mode=request_mode,
                                response_mode='plain',
                                crypto_status=crypto_status,
                                kid=kid,
                            ),
                        ),
                    }
                )
                return

            await send(message)

        return _observe_response

    def _build_crypto_context(self, decrypted_payload: DecryptedTransportEnvelope) -> dict[str, str | bytes | bool]:
        """
        从解密结果构建请求生命周期内的加密上下文

        :param decrypted_payload: 解密后的请求信封对象
        :return: 请求加密上下文字典
        """
        return {
            'active': True,
            'kid': decrypted_payload.kid,
            'aes_key': decrypted_payload.aes_key,
        }

    def _build_error_crypto_context(
        self,
        scope: Scope,
        headers: Headers,
        body: bytes,
    ) -> dict[str, str | bytes | bool] | None:
        """
        尝试在解密失败场景下提取AES会话密钥，以便返回加密错误响应

        :param scope: 当前ASGI请求作用域
        :param headers: 当前请求头对象
        :param body: 原始请求体字节串
        :return: 可用于构造加密错误响应的上下文字典，失败时返回None
        """
        content_type = headers.get('content-type', '')
        try:
            query_envelope = self._extract_query_envelope(scope)
            body_envelope = self._extract_body_envelope(content_type, body)
            envelope = body_envelope or query_envelope
            if envelope is None:
                return None
            TransportCryptoUtil._extract_and_validate_aad(
                envelope,
                expected_method=str(scope.get('method', '')).upper(),
                expected_path=self._normalize_path(str(scope.get('path', ''))),
            )
            return {
                'active': True,
                'kid': str(envelope['kid']),
                'aes_key': TransportCryptoUtil.decrypt_request_key(envelope),
            }
        except Exception:
            return None

    def _extract_request_kid(self, scope: Scope, headers: Headers, body: bytes) -> str | None:
        """
        尝试从原始请求信封中提取密钥版本

        :param scope: 当前ASGI请求作用域
        :param headers: 当前请求头对象
        :param body: 原始请求体字节串
        :return: 密钥版本，不存在时返回None
        """
        content_type = headers.get('content-type', '')
        try:
            query_envelope = self._extract_query_envelope(scope)
            body_envelope = self._extract_body_envelope(content_type, body)
            envelope = body_envelope or query_envelope
        except Exception:
            return None
        if envelope is None or not envelope.get('kid'):
            return None
        return str(envelope['kid'])

    @staticmethod
    def _loads_json_mapping(payload: str) -> dict:
        """
        将JSON字符串解析为字典，并限制结果必须为JSON对象

        :param payload: JSON字符串
        :return: 解析后的字典对象
        """
        json_payload = json.loads(payload)
        if not isinstance(json_payload, dict):
            raise ValueError('解密后的请求载荷必须为JSON对象')
        return json_payload

    @staticmethod
    async def _read_body(receive: Receive) -> bytes:
        """
        从ASGI receive中读取完整请求体

        :param receive: ASGI receive函数
        :return: 完整请求体字节串
        """
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message['type'] != 'http.request':
                continue
            body_chunks.append(message.get('body', b''))
            more_body = message.get('more_body', False)
        return b''.join(body_chunks)

    @staticmethod
    def _build_receive(body: bytes) -> Receive:
        """
        根据指定请求体重建一次性可消费的ASGI receive函数

        :param body: 需要回放的请求体字节串
        :return: 重建后的ASGI receive函数
        """
        has_been_called = False

        async def _receive() -> Message:
            nonlocal has_been_called
            if has_been_called:
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            has_been_called = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        return _receive

    @staticmethod
    def _replace_header(headers: list[tuple[bytes, bytes]], key: bytes, value: bytes) -> list[tuple[bytes, bytes]]:
        """
        替换或新增指定响应头

        :param headers: 原始请求/响应头列表
        :param key: 头名称
        :param value: 头值
        :return: 替换后的头列表
        """
        normalized_key = key.lower()
        filtered_headers = [
            (header_key, header_value) for header_key, header_value in headers if header_key.lower() != normalized_key
        ]
        filtered_headers.append((key, value))
        return filtered_headers

    @staticmethod
    def _remove_header(headers: list[tuple[bytes, bytes]], key: bytes) -> list[tuple[bytes, bytes]]:
        """
        删除指定请求头

        :param headers: 原始请求头列表
        :param key: 头名称
        :return: 删除后的头列表
        """
        normalized_key = key.lower()
        return [
            (header_key, header_value) for header_key, header_value in headers if header_key.lower() != normalized_key
        ]

    @staticmethod
    def _normalize_path(path: str) -> str:
        """
        标准化请求路径，剥离应用根路径前缀

        :param path: 原始请求路径
        :return: 标准化后的业务路径
        """
        app_root_path = AppConfig.app_root_path
        if app_root_path and path.startswith(app_root_path):
            normalized_path = path[len(app_root_path) :]
            return normalized_path or '/'
        return path or '/'

    @classmethod
    def _merge_response_headers(
        cls,
        headers: list[tuple[bytes, bytes]],
        extra_headers: dict[str, str],
    ) -> list[tuple[bytes, bytes]]:
        """
        将字符串响应头批量写回到原始headers列表

        :param headers: 原始请求/响应头列表
        :param extra_headers: 需要追加的响应头
        :return: 合并后的响应头列表
        """
        merged_headers = headers
        for header_key, header_value in extra_headers.items():
            merged_headers = cls._replace_header(
                merged_headers, header_key.encode('utf-8'), header_value.encode('utf-8')
            )
        return merged_headers

    @classmethod
    def _build_monitor_headers(
        cls,
        request_mode: str,
        response_mode: str,
        crypto_status: str,
        kid: str | None = None,
    ) -> dict[str, str]:
        """
        构建传输层加解密监控响应头

        :param request_mode: 请求传输模式
        :param response_mode: 响应传输模式
        :param crypto_status: 当前传输层处理状态
        :param kid: 可选的密钥版本
        :return: 监控响应头字典
        """
        headers = {
            cls._MONITOR_REQUEST_MODE_HEADER: request_mode,
            cls._MONITOR_RESPONSE_MODE_HEADER: response_mode,
            cls._MONITOR_STATUS_HEADER: crypto_status,
        }
        if kid:
            headers[cls._MONITOR_KID_HEADER] = kid
        return headers

    @classmethod
    async def _send_error_response(
        cls,
        scope: Scope,
        receive: Receive,
        send: Send,
        message: str,
        crypto_context: dict[str, str | bytes | bool] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        发送错误响应，在存在AES会话密钥时优先返回加密错误响应

        :param scope: 当前ASGI请求作用域
        :param receive: ASGI receive函数
        :param send: ASGI send函数
        :param message: 错误信息
        :param crypto_context: 可选的请求加密上下文
        :param headers: 需要追加的诊断响应头
        :return: None
        """
        response_content = {'code': HttpStatusConstant.BAD_REQUEST, 'msg': message, 'success': False}
        response = JSONResponse(status_code=HttpStatusConstant.BAD_REQUEST, content=response_content)
        if crypto_context:
            encrypted_body = TransportCryptoUtil.encrypt_response_body(
                aes_key=crypto_context['aes_key'],
                payload=json.dumps(response_content, ensure_ascii=False).encode('utf-8'),
                kid=str(crypto_context['kid']),
                method=str(scope.get('method', '')),
                path=cls._normalize_path(str(scope.get('path', ''))),
            )
            response.body = encrypted_body
            response.init_headers()
            response.headers[cls._ENCRYPT_RESPONSE_HEADER] = '1'
            response.headers[cls._ENCRYPT_ALG_HEADER] = TransportCryptoUtil.get_response_envelope_algorithm()
            response.headers[cls._ENCRYPT_KID_HEADER] = str(crypto_context['kid'])
        if headers:
            response.headers.update(headers)
        await response(scope, receive, send)

    @staticmethod
    def _classify_failure_reason(message: str) -> str:
        """
        根据异常信息归类传输层失败原因

        :param message: 原始异常信息
        :return: 失败原因分类编码
        """
        if not message or message == '加密请求解析失败':
            return 'decrypt_failed'
        failure_reason_mapping = (
            ('method/path与当前接口不匹配', 'aad_mismatch'),
            ('缺少合法的aad', 'aad_invalid'),
            ('已过期', 'timestamp_expired'),
            ('缺少必要字段', 'envelope_fields_missing'),
            ('协议版本不受支持', 'protocol_version_invalid'),
            ('算法不受支持', 'algorithm_invalid'),
            ('未找到可解密的请求载荷', 'envelope_missing'),
            ('密钥版本', 'kid_mismatch'),
        )
        for reason_keyword, reason_code in failure_reason_mapping:
            if reason_keyword in message:
                return reason_code
        if '重复请求' in message or '重放' in message:
            return 'replay_detected'
        return 'decrypt_failed'

    @classmethod
    def _is_excluded_path(cls, path: str) -> bool:
        """
        判断当前路径是否在传输加密排除列表内

        :param path: 当前请求路径
        :return: 是否命中排除列表
        """
        excluded_paths = [
            excluded_path.strip()
            for excluded_path in TransportCryptoConfig.transport_crypto_exclude_paths.split(',')
            if excluded_path.strip()
        ]
        return any(path == excluded_path or path.startswith(f'{excluded_path}/') for excluded_path in excluded_paths)

    @classmethod
    def _is_required_path(cls, path: str) -> bool:
        """
        判断当前路径是否在强制加密列表内

        :param path: 当前请求路径
        :return: 是否命中强制加密列表
        """
        required_paths = [
            required_path.strip()
            for required_path in TransportCryptoConfig.transport_crypto_required_paths.split(',')
            if required_path.strip()
        ]
        if not required_paths:
            return False
        return any(path == required_path or path.startswith(f'{required_path}/') for required_path in required_paths)

    @classmethod
    def _is_enabled_path(cls, path: str) -> bool:
        """
        判断当前路径是否在启用传输加密的列表内

        :param path: 当前请求路径
        :return: 当前路径是否启用传输加密
        """
        enabled_paths = [
            enabled_path.strip()
            for enabled_path in TransportCryptoConfig.transport_crypto_enabled_paths.split(',')
            if enabled_path.strip()
        ]
        if not enabled_paths:
            return True
        return any(path == enabled_path or path.startswith(f'{enabled_path}/') for enabled_path in enabled_paths)


def add_transport_crypto_middleware(app: ASGIApp) -> None:
    """
    添加传输层加解密中间件

    :param app: FastAPI/Starlette应用对象
    :return: None
    """
    app.add_middleware(TransportCryptoMiddleware)
