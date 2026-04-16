import base64
import json
import os
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, Request
from redis import asyncio as aioredis

from config.env import AppConfig, TransportCryptoConfig
from utils.log_util import logger


# 通用编码辅助
def _urlsafe_b64encode(data: bytes) -> str:
    """
    将字节串编码为URL安全的Base64字符串

    :param data: 原始字节串
    :return: URL安全的Base64字符串
    """
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def _urlsafe_b64decode(data: str) -> bytes:
    """
    将URL安全的Base64字符串解码为字节串

    :param data: URL安全的Base64字符串
    :return: 解码后的字节串
    """
    padding_length = (-len(data)) % 4
    return base64.urlsafe_b64decode(f'{data}{"=" * padding_length}'.encode())


@dataclass(frozen=True)
class TransportKeyPair:
    """
    传输层密钥对载体

    kid: 密钥版本标识
    private_key_pem: PEM格式私钥
    public_key_pem: PEM格式公钥
    """

    kid: str
    private_key_pem: str
    public_key_pem: str


# 传输层数据载体
@dataclass(frozen=True)
class DecryptedTransportEnvelope:
    """
    请求信封解密结果

    kid: 请求使用的密钥版本标识
    nonce: 请求随机数
    timestamp: 请求时间戳
    aes_key: 当前请求协商出的AES会话密钥
    aad: 通过校验后的AAD上下文
    plaintext: 解密得到的原始请求载荷
    """

    kid: str
    nonce: str
    timestamp: int
    aes_key: bytes
    aad: dict[str, str]
    plaintext: bytes


# 传输层密钥管理
class TransportKeyProvider:
    """
    传输层密钥提供者
    """

    _lock = Lock()
    _key_pairs: dict[str, TransportKeyPair] | None = None
    _MIN_RSA_KEY_SIZE = 2048
    _RSA_KEY_SIZE_STEP = 256

    @classmethod
    def validate_runtime_configuration(cls) -> None:
        """
        校验传输层加解密运行配置，确保启用时显式配置密钥对

        :return: None
        """
        if not TransportCryptoConfig.transport_crypto_enabled or TransportCryptoConfig.transport_crypto_mode == 'off':
            return

        configured_private_key = cls._normalize_pem(TransportCryptoConfig.transport_crypto_private_key)
        configured_public_key = cls._normalize_pem(TransportCryptoConfig.transport_crypto_public_key)
        rsa_key_size = TransportCryptoConfig.transport_crypto_rsa_key_size

        if rsa_key_size < cls._MIN_RSA_KEY_SIZE or rsa_key_size % cls._RSA_KEY_SIZE_STEP != 0:
            raise ValueError('TRANSPORT_CRYPTO_RSA_KEY_SIZE必须大于等于2048，且为256的整数倍')

        if not configured_private_key or not configured_public_key:
            raise ValueError(
                '启用传输层加解密时，必须显式配置TRANSPORT_CRYPTO_PUBLIC_KEY和TRANSPORT_CRYPTO_PRIVATE_KEY'
            )

        private_key = serialization.load_pem_private_key(configured_private_key.encode('utf-8'), password=None)
        derived_public_key = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode('utf-8')
        )
        if cls._normalize_pem(derived_public_key) != configured_public_key:
            raise ValueError('TRANSPORT_CRYPTO_PUBLIC_KEY与TRANSPORT_CRYPTO_PRIVATE_KEY不匹配')

        if TransportCryptoConfig.transport_crypto_legacy_key_pairs:
            cls._build_legacy_key_pairs()

    @classmethod
    def get_current_key_pair(cls) -> TransportKeyPair:
        """
        获取当前启用的密钥对

        :return: 当前启用的密钥对
        """
        if cls._key_pairs is None:
            with cls._lock:
                if cls._key_pairs is None:
                    cls._key_pairs = cls._build_key_pairs()

        return cls._key_pairs[TransportCryptoConfig.transport_crypto_kid]

    @classmethod
    def get_current_kid(cls) -> str:
        """
        获取当前启用的密钥标识

        :return: 当前启用的密钥标识
        """
        return cls.get_current_key_pair().kid

    @classmethod
    def get_public_key_pem(cls, kid: str | None = None) -> str:
        """
        获取公钥PEM

        :param kid: 密钥版本标识，未传入时默认使用当前版本
        :return: PEM格式公钥字符串
        """
        return cls.get_key_pair(kid).public_key_pem

    @classmethod
    def get_private_key_pem(cls, kid: str | None = None) -> str:
        """
        获取私钥PEM

        :param kid: 密钥版本标识，未传入时默认使用当前版本
        :return: PEM格式私钥字符串
        """
        return cls.get_key_pair(kid).private_key_pem

    @classmethod
    def get_key_pair(cls, kid: str | None = None) -> TransportKeyPair:
        """
        根据kid获取密钥对，未传入时返回当前密钥对

        :param kid: 密钥版本标识，未传入时默认使用当前版本
        :return: 匹配到的密钥对
        """
        target_kid = kid or cls.get_current_kid()
        if cls._key_pairs is None:
            with cls._lock:
                if cls._key_pairs is None:
                    cls._key_pairs = cls._build_key_pairs()
        key_pair = cls._key_pairs.get(target_kid)
        if key_pair is None:
            raise ValueError('密钥版本不存在')
        return key_pair

    @classmethod
    def get_supported_kids(cls) -> tuple[str, ...]:
        """
        获取当前支持解密的全部密钥版本

        :return: 当前支持解密的密钥版本元组
        """
        if cls._key_pairs is None:
            cls.get_current_key_pair()
        return tuple(cls._key_pairs.keys())

    @classmethod
    def _build_key_pairs(cls) -> dict[str, TransportKeyPair]:
        """
        构建当前进程可用的全部密钥对映射

        :return: 以kid为键的密钥对映射
        """
        configured_private_key = cls._normalize_pem(TransportCryptoConfig.transport_crypto_private_key)
        configured_public_key = cls._normalize_pem(TransportCryptoConfig.transport_crypto_public_key)
        kid = TransportCryptoConfig.transport_crypto_kid

        if not configured_private_key or not configured_public_key:
            raise ValueError(
                '启用传输层加解密时，必须显式配置TRANSPORT_CRYPTO_PUBLIC_KEY和TRANSPORT_CRYPTO_PRIVATE_KEY'
            )

        key_pairs = {
            kid: TransportKeyPair(kid=kid, private_key_pem=configured_private_key, public_key_pem=configured_public_key)
        }
        key_pairs.update(cls._build_legacy_key_pairs())
        return key_pairs

    @classmethod
    def _build_legacy_key_pairs(cls) -> dict[str, TransportKeyPair]:
        """
        构建历史密钥对映射，用于密钥轮换窗口内的兼容解密

        :return: 以kid为键的历史密钥对映射
        """
        legacy_key_pairs: dict[str, TransportKeyPair] = {}
        configured_legacy_key_pairs = TransportCryptoConfig.transport_crypto_legacy_key_pairs
        if not configured_legacy_key_pairs:
            return legacy_key_pairs

        try:
            parsed_key_pairs = json.loads(configured_legacy_key_pairs)
        except json.JSONDecodeError as exc:
            raise ValueError('传输层历史密钥配置不是合法JSON') from exc

        if not isinstance(parsed_key_pairs, list):
            raise ValueError('传输层历史密钥配置必须是JSON数组')

        for item in parsed_key_pairs:
            if not isinstance(item, dict):
                raise ValueError('传输层历史密钥项必须是JSON对象')
            item_kid = item.get('kid')
            private_key_pem = cls._normalize_pem(item.get('privateKey') or item.get('private_key') or '')
            public_key_pem = cls._normalize_pem(item.get('publicKey') or item.get('public_key') or '')
            if not item_kid or not private_key_pem:
                raise ValueError('传输层历史密钥项必须包含kid和privateKey')
            if not public_key_pem:
                private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
                public_key_pem = (
                    private_key.public_key()
                    .public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    .decode('utf-8')
                )
            legacy_key_pairs[str(item_kid)] = TransportKeyPair(
                kid=str(item_kid),
                private_key_pem=private_key_pem,
                public_key_pem=public_key_pem,
            )

        return legacy_key_pairs

    @staticmethod
    def _normalize_pem(pem_value: str) -> str:
        """
        兼容环境变量中的换行转义

        :param pem_value: 原始PEM字符串
        :return: 标准化后的PEM字符串
        """
        return pem_value.replace('\\n', '\n').strip() if pem_value else ''


# 传输层安全校验
class TransportSecurityUtil:
    """
    传输层安全校验工具
    """

    @classmethod
    def validate_timestamp(cls, timestamp: int) -> None:
        """
        校验请求时间窗

        :param timestamp: 请求信封中的时间戳
        :return: None
        """
        now_timestamp = int(time.time())
        if abs(now_timestamp - timestamp) > TransportCryptoConfig.transport_crypto_clock_skew_seconds:
            logger.warning(
                '传输层加密请求时间窗校验失败，request_ts={}, now_ts={}, allowed_skew={}',
                timestamp,
                now_timestamp,
                TransportCryptoConfig.transport_crypto_clock_skew_seconds,
            )
            raise ValueError('加密请求已过期，请刷新页面后重试')

    @classmethod
    async def validate_replay(cls, request: Request, kid: str, nonce: str) -> None:
        """
        使用Redis进行防重放校验

        :param request: 当前请求对象
        :param kid: 当前密钥版本标识
        :param nonce: 当前请求随机数
        :return: None
        """
        redis = getattr(request.app.state, 'redis', None)
        if redis is None:
            if cls._should_fail_closed_when_replay_check_unavailable(request):
                logger.error('Redis未初始化，当前请求要求严格防重放校验，已拒绝请求')
                raise ValueError('服务端防重放校验不可用，请稍后重试')
            logger.warning('Redis未初始化，已跳过传输层防重放校验')
            return

        replay_key = f'transport:replay:{kid}:{nonce}'
        try:
            is_success = await redis.set(
                replay_key, '1', ex=TransportCryptoConfig.transport_crypto_replay_ttl_seconds, nx=True
            )
        except Exception as exc:
            if cls._should_fail_closed_when_replay_check_unavailable(request):
                logger.error('Redis防重放校验执行失败，当前请求要求严格校验，error={}', exc)
                raise ValueError('服务端防重放校验不可用，请稍后重试') from exc
            logger.warning('Redis防重放校验执行失败，已跳过当前请求的防重放校验，error={}', exc)
            return
        if not is_success:
            logger.warning('传输层加密请求检测到重放，kid={}, nonce={}', kid, nonce)
            raise ValueError('检测到重复请求，请勿重放加密报文')

    @classmethod
    def _should_fail_closed_when_replay_check_unavailable(cls, request: Request) -> bool:
        """
        判断当前请求在防重放能力不可用时是否需要直接拒绝

        :param request: 当前请求对象
        :return: 是否需要失败关闭
        """
        if TransportCryptoConfig.transport_crypto_mode == 'required':
            return True
        current_path = cls._normalize_path(str(request.scope.get('path', '')))
        return cls._is_required_path(current_path)

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

    @staticmethod
    def _is_required_path(path: str) -> bool:
        """
        判断当前路径是否命中强制加密路径配置

        :param path: 当前请求路径
        :return: 是否命中强制加密路径
        """
        required_paths = [
            required_path.strip()
            for required_path in TransportCryptoConfig.transport_crypto_required_paths.split(',')
            if required_path.strip()
        ]
        if not required_paths:
            return False
        return any(path == required_path or path.startswith(f'{required_path}/') for required_path in required_paths)


# 传输层加解密核心能力
class TransportCryptoUtil:
    """
    传输层加解密工具
    """

    _ENVELOPE_VERSION = '1'
    _RESPONSE_ENVELOPE_ALGORITHM = 'AES_256_GCM'
    _REQUIRED_ENVELOPE_FIELDS = ('kid', 'ts', 'nonce', 'ek', 'iv', 'ct', 'aad')

    @classmethod
    def get_response_envelope_algorithm(cls) -> str:
        """
        获取响应信封算法标识

        :return: 响应信封算法标识
        """
        return cls._RESPONSE_ENVELOPE_ALGORITHM

    @classmethod
    def decrypt_envelope(
        cls,
        envelope: dict[str, Any],
        expected_method: str,
        expected_path: str,
    ) -> DecryptedTransportEnvelope:
        """
        解密请求信封

        :param envelope: 请求加密信封
        :param expected_method: 当前请求预期HTTP方法
        :param expected_path: 当前请求预期路径
        :return: 解密后的请求信封对象
        """
        cls._validate_envelope(envelope)
        kid = str(envelope['kid'])
        aad = cls._extract_and_validate_aad(envelope, expected_method, expected_path)
        aes_key = cls.decrypt_request_key(envelope)
        iv = _urlsafe_b64decode(str(envelope['iv']))
        ciphertext = _urlsafe_b64decode(str(envelope['ct']))
        plaintext = AESGCM(aes_key).decrypt(iv, ciphertext, cls._build_aad_bytes(aad))

        return DecryptedTransportEnvelope(
            kid=kid,
            nonce=str(envelope['nonce']),
            timestamp=int(envelope['ts']),
            aes_key=aes_key,
            aad=aad,
            plaintext=plaintext,
        )

    @classmethod
    def decrypt_request_key(cls, envelope: dict[str, Any]) -> bytes:
        """
        仅解出请求中的AES会话密钥，用于异常场景构造加密错误响应

        :param envelope: 请求加密信封
        :return: 请求协商出的AES会话密钥
        """
        kid = str(envelope['kid'])
        private_key_pem = TransportKeyProvider.get_private_key_pem(kid)
        private_key = serialization.load_pem_private_key(private_key_pem.encode('utf-8'), password=None)
        encrypted_key = _urlsafe_b64decode(str(envelope['ek']))
        return private_key.decrypt(
            encrypted_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )

    @classmethod
    def encrypt_response_body(
        cls,
        aes_key: bytes,
        payload: bytes,
        kid: str,
        method: str,
        path: str,
    ) -> bytes:
        """
        使用请求协商出的AES密钥加密响应体

        :param aes_key: 请求协商出的AES会话密钥
        :param payload: 需要加密的响应体字节串
        :param kid: 当前使用的密钥版本标识
        :param method: 当前HTTP请求方法
        :param path: 当前HTTP请求路径
        :return: 加密后的响应体字节串
        """
        iv = os.urandom(12)
        aad = {'method': method.upper(), 'path': path, 'direction': 'response'}
        ciphertext = AESGCM(aes_key).encrypt(iv, payload, cls._build_aad_bytes(aad))
        encrypted_payload = {
            'v': cls._ENVELOPE_VERSION,
            'kid': kid,
            'alg': cls._RESPONSE_ENVELOPE_ALGORITHM,
            'aad': aad,
            'iv': _urlsafe_b64encode(iv),
            'ct': _urlsafe_b64encode(ciphertext),
        }
        return json.dumps(encrypted_payload, ensure_ascii=False).encode('utf-8')

    @classmethod
    def decode_query_envelope(cls, encrypted_query: str) -> dict[str, Any]:
        """
        解码查询参数中的加密信封

        :param encrypted_query: 查询参数中的加密信封字符串
        :return: 解码后的信封字典
        """
        decoded_query = _urlsafe_b64decode(encrypted_query).decode('utf-8')
        return json.loads(decoded_query)

    @classmethod
    def build_public_key_payload(cls) -> dict[str, Any]:
        """
        构建公钥下发载荷

        :return: 公钥下发载荷字典
        """
        return {
            'kid': TransportKeyProvider.get_current_kid(),
            'envelopeVersion': cls._ENVELOPE_VERSION,
            'alg': TransportCryptoConfig.transport_crypto_algorithm,
            'publicKey': TransportKeyProvider.get_public_key_pem(),
            'supportedKids': TransportKeyProvider.get_supported_kids(),
            'expireAt': int(time.time()) + TransportCryptoConfig.transport_crypto_public_key_ttl_seconds,
        }

    @classmethod
    def build_frontend_config_payload(cls) -> dict[str, Any]:
        """
        构建前端传输层加解密运行配置载荷

        :return: 前端传输层加解密运行配置载荷字典
        """
        transport_crypto_active = (
            TransportCryptoConfig.transport_crypto_enabled and TransportCryptoConfig.transport_crypto_mode != 'off'
        )
        return {
            'transportCryptoEnabled': TransportCryptoConfig.transport_crypto_enabled,
            'transportCryptoMode': TransportCryptoConfig.transport_crypto_mode,
            'transportCryptoActive': transport_crypto_active,
            'envelopeVersion': cls._ENVELOPE_VERSION,
            'publicKeyUrl': '/transport/crypto/public-key',
            'requestEnvelopeAlgorithm': TransportCryptoConfig.transport_crypto_algorithm,
            'responseEnvelopeAlgorithm': cls.get_response_envelope_algorithm(),
            'enabledPaths': cls._split_paths(TransportCryptoConfig.transport_crypto_enabled_paths),
            'requiredPaths': cls._split_paths(TransportCryptoConfig.transport_crypto_required_paths),
            'excludePaths': cls._split_paths(TransportCryptoConfig.transport_crypto_exclude_paths),
            'maxEncryptedGetUrlLength': TransportCryptoConfig.transport_crypto_max_get_url_length,
            'configExpireAt': int(time.time()) + TransportCryptoConfig.transport_crypto_frontend_config_ttl_seconds,
        }

    @classmethod
    def _validate_envelope(cls, envelope: dict[str, Any]) -> None:
        """
        校验请求加密信封的结构、协议版本与算法是否有效

        :param envelope: 请求加密信封
        :return: None
        """
        if not isinstance(envelope, dict):
            raise ValueError('加密请求信封格式不合法')

        missing_fields = [field_name for field_name in cls._REQUIRED_ENVELOPE_FIELDS if not envelope.get(field_name)]
        if missing_fields:
            raise ValueError(f'加密请求缺少必要字段: {",".join(missing_fields)}')

        if str(envelope.get('v', '')) != cls._ENVELOPE_VERSION:
            raise ValueError('加密请求协议版本不受支持')

        if str(envelope.get('alg', '')) != TransportCryptoConfig.transport_crypto_algorithm:
            raise ValueError('加密请求算法不受支持')

    @classmethod
    def _extract_and_validate_aad(
        cls,
        envelope: dict[str, Any],
        expected_method: str,
        expected_path: str,
    ) -> dict[str, str]:
        """
        提取并校验请求AAD，确保密文与当前接口绑定

        :param envelope: 请求加密信封
        :param expected_method: 当前请求预期HTTP方法
        :param expected_path: 当前请求预期路径
        :return: 归一化后的AAD字典
        """
        aad = envelope.get('aad')
        if not isinstance(aad, dict):
            raise ValueError('加密请求缺少合法的aad')

        method = str(aad.get('method', '')).upper()
        path = str(aad.get('path', ''))
        if method != expected_method.upper() or path != expected_path:
            raise ValueError('加密请求的method/path与当前接口不匹配')

        return {'method': method, 'path': path}

    @staticmethod
    def _build_aad_bytes(aad: dict[str, str]) -> bytes:
        """
        将AAD字典序列化为AES-GCM additionalData所需字节串

        :param aad: AAD字典
        :return: 序列化后的AAD字节串
        """
        return json.dumps(aad, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    @staticmethod
    def _split_paths(path_value: str) -> list[str]:
        """
        将逗号分隔的路径配置拆分为列表

        :param path_value: 原始路径配置
        :return: 路径列表
        """
        return [path.strip() for path in path_value.split(',') if path.strip()]


# 传输层监控读写与聚合
class TransportCryptoMonitorUtil:
    """
    传输层加解密监控工具
    """

    _REDIS_KEY_PREFIX = 'transport:monitor'
    _META_STARTED_AT_KEY = f'{_REDIS_KEY_PREFIX}:started_at'
    _COUNTERS_KEY = f'{_REDIS_KEY_PREFIX}:counters'
    _FAILURE_REASONS_KEY = f'{_REDIS_KEY_PREFIX}:failure_reasons'
    _KIDS_KEY = f'{_REDIS_KEY_PREFIX}:kids'
    _RECENT_FAILURES_KEY = f'{_REDIS_KEY_PREFIX}:recent_failures'
    _RECENT_FAILURE_LIMIT = 20
    _REDIS_WARNING_INTERVAL_SECONDS = 60
    _lock = Lock()
    _started_at = datetime.now()
    _counters: Counter[str] = Counter()
    _failure_reasons: Counter[str] = Counter()
    _kid_counters: defaultdict[str, Counter[str]] = defaultdict(Counter)
    _recent_failures: deque[dict[str, Any]] = deque(maxlen=_RECENT_FAILURE_LIMIT)
    _last_redis_warning_at = 0.0

    # 对外暴露的监控记录与查询入口
    @classmethod
    async def record_plain_request(cls, app: FastAPI | None = None) -> None:
        """
        记录明文请求

        :param app: FastAPI应用对象
        :return: None
        """
        if await cls._write_redis_counters(
            app,
            counter_updates={
                'requests_total': 1,
                'plain_requests_total': 1,
            },
        ):
            return
        cls._record_plain_request_local()

    @classmethod
    async def record_encrypted_request(cls, app: FastAPI | None = None, kid: str | None = None) -> None:
        """
        记录加密请求

        :param app: FastAPI应用对象
        :param kid: 当前请求使用的密钥版本
        :return: None
        """
        if await cls._write_redis_counters(
            app,
            counter_updates={
                'requests_total': 1,
                'encrypted_requests_total': 1,
            },
            kid=kid,
            kid_counter_updates={'encrypted_requests_total': 1},
        ):
            return
        cls._record_encrypted_request_local(kid)

    @classmethod
    async def record_required_rejected(cls, app: FastAPI | None = None, method: str = '', path: str = '') -> None:
        """
        记录强制加密接口被明文访问的拒绝事件

        :param app: FastAPI应用对象
        :param method: 请求方法
        :param path: 请求路径
        :return: None
        """
        if await cls._write_redis_failure(
            app,
            method=method,
            path=path,
            reason='required_missing',
            include_decrypt_failure=False,
        ):
            return
        cls._record_failure_local(method, path, 'required_missing', include_decrypt_failure=False)

    @classmethod
    async def record_decrypt_success(cls, app: FastAPI | None = None, kid: str | None = None) -> None:
        """
        记录请求解密成功事件

        :param app: FastAPI应用对象
        :param kid: 当前请求使用的密钥版本
        :return: None
        """
        if await cls._write_redis_counters(
            app,
            counter_updates={'decrypt_success_total': 1},
            kid=kid,
            kid_counter_updates={'decrypt_success_total': 1},
        ):
            return
        cls._record_decrypt_success_local(kid)

    @classmethod
    async def record_decrypt_failure(
        cls,
        app: FastAPI | None = None,
        method: str = '',
        path: str = '',
        reason: str = '',
        kid: str | None = None,
    ) -> None:
        """
        记录请求解密失败事件

        :param app: FastAPI应用对象
        :param method: 请求方法
        :param path: 请求路径
        :param reason: 失败原因分类
        :param kid: 当前请求使用的密钥版本
        :return: None
        """
        if await cls._write_redis_failure(app, method=method, path=path, reason=reason, kid=kid):
            return
        cls._record_failure_local(method, path, reason, kid=kid)

    @classmethod
    async def record_plain_response(cls, app: FastAPI | None = None) -> None:
        """
        记录明文响应

        :param app: FastAPI应用对象
        :return: None
        """
        if await cls._write_redis_counters(app, counter_updates={'plain_responses_total': 1}):
            return
        cls._record_plain_response_local()

    @classmethod
    async def record_encrypted_response(
        cls,
        app: FastAPI | None = None,
        kid: str | None = None,
        is_error: bool = False,
    ) -> None:
        """
        记录加密响应

        :param app: FastAPI应用对象
        :param kid: 当前响应使用的密钥版本
        :param is_error: 是否为错误响应
        :return: None
        """
        counter_updates = {'encrypted_responses_total': 1}
        if is_error:
            counter_updates['encrypted_error_responses_total'] = 1
        if await cls._write_redis_counters(
            app,
            counter_updates=counter_updates,
            kid=kid,
            kid_counter_updates={'encrypted_responses_total': 1},
        ):
            return
        cls._record_encrypted_response_local(kid, is_error)

    @classmethod
    async def get_snapshot(cls, app: FastAPI | None = None) -> dict[str, Any]:
        """
        获取传输层加解密监控快照

        :param app: FastAPI应用对象
        :return: 监控快照字典
        """
        redis_snapshot = await cls._get_redis_snapshot(app)
        local_snapshot = cls._get_local_snapshot_parts()
        snapshot_parts = cls._merge_snapshot_parts(redis_snapshot, local_snapshot)
        return cls._build_snapshot(snapshot_parts)

    # Redis 聚合写入与读取
    @classmethod
    async def _write_redis_counters(
        cls,
        app: FastAPI | None,
        counter_updates: dict[str, int],
        kid: str | None = None,
        kid_counter_updates: dict[str, int] | None = None,
    ) -> bool:
        """
        将监控计数写入Redis

        :param app: FastAPI应用对象
        :param counter_updates: 全局计数增量
        :param kid: 当前密钥版本
        :param kid_counter_updates: 按密钥版本统计的增量
        :return: 是否写入成功
        """
        redis = cls._get_redis_client(app)
        if redis is None:
            return False
        try:
            async with redis.pipeline(transaction=False) as pipe:
                pipe.set(cls._META_STARTED_AT_KEY, cls._started_at.isoformat(), nx=True)
                for counter_name, delta in counter_updates.items():
                    pipe.hincrby(cls._COUNTERS_KEY, counter_name, delta)
                if kid and kid_counter_updates:
                    pipe.sadd(cls._KIDS_KEY, kid)
                    kid_counter_key = cls._build_kid_counter_key(kid)
                    for counter_name, delta in kid_counter_updates.items():
                        pipe.hincrby(kid_counter_key, counter_name, delta)
                await pipe.execute()
            return True
        except Exception as exc:
            cls._log_redis_warning('write_counters', exc)
            return False

    @classmethod
    async def _write_redis_failure(
        cls,
        app: FastAPI | None,
        method: str,
        path: str,
        reason: str,
        kid: str | None = None,
        include_decrypt_failure: bool = True,
    ) -> bool:
        """
        将失败事件写入Redis

        :param app: FastAPI应用对象
        :param method: 请求方法
        :param path: 请求路径
        :param reason: 失败原因分类
        :param kid: 当前请求使用的密钥版本
        :param include_decrypt_failure: 是否计入解密失败次数
        :return: 是否写入成功
        """
        redis = cls._get_redis_client(app)
        if redis is None:
            return False
        try:
            recent_failure = json.dumps(
                {
                    'time': datetime.now().isoformat(),
                    'method': method,
                    'path': path,
                    'reason': reason,
                    'kid': kid,
                },
                ensure_ascii=False,
            )
            async with redis.pipeline(transaction=False) as pipe:
                pipe.set(cls._META_STARTED_AT_KEY, cls._started_at.isoformat(), nx=True)
                if include_decrypt_failure:
                    pipe.hincrby(cls._COUNTERS_KEY, 'decrypt_failure_total', 1)
                if reason == 'required_missing':
                    pipe.hincrby(cls._COUNTERS_KEY, 'required_rejected_total', 1)
                pipe.hincrby(cls._FAILURE_REASONS_KEY, reason, 1)
                pipe.lpush(cls._RECENT_FAILURES_KEY, recent_failure)
                pipe.ltrim(cls._RECENT_FAILURES_KEY, 0, cls._RECENT_FAILURE_LIMIT - 1)
                if kid:
                    pipe.sadd(cls._KIDS_KEY, kid)
                    pipe.hincrby(cls._build_kid_counter_key(kid), 'decrypt_failure_total', 1)
                await pipe.execute()
            return True
        except Exception as exc:
            cls._log_redis_warning('write_failure', exc)
            return False

    @classmethod
    async def _get_redis_snapshot(cls, app: FastAPI | None) -> dict[str, Any]:
        """
        从Redis中读取监控快照

        :param app: FastAPI应用对象
        :return: Redis监控快照字典
        """
        redis = cls._get_redis_client(app)
        if redis is None:
            return {
                'monitor_scope': 'process-local-fallback',
                'started_at': cls._started_at,
                'counters': {},
                'failure_reasons': {},
                'kid_stats': [],
                'recent_failures': [],
            }
        try:
            async with redis.pipeline(transaction=False) as pipe:
                pipe.set(cls._META_STARTED_AT_KEY, cls._started_at.isoformat(), nx=True)
                pipe.get(cls._META_STARTED_AT_KEY)
                pipe.hgetall(cls._COUNTERS_KEY)
                pipe.hgetall(cls._FAILURE_REASONS_KEY)
                pipe.lrange(cls._RECENT_FAILURES_KEY, 0, cls._RECENT_FAILURE_LIMIT - 1)
                pipe.smembers(cls._KIDS_KEY)
                _, started_at_raw, counters_raw, failure_reasons_raw, recent_failures_raw, kids = await pipe.execute()
            kid_stats = await cls._get_redis_kid_stats(redis, sorted(kids))
            return {
                'monitor_scope': 'redis-aggregated',
                'started_at': cls._parse_datetime(started_at_raw) or cls._started_at,
                'counters': cls._to_int_mapping(counters_raw),
                'failure_reasons': cls._to_int_mapping(failure_reasons_raw),
                'kid_stats': kid_stats,
                'recent_failures': cls._parse_recent_failures(recent_failures_raw),
            }
        except Exception as exc:
            cls._log_redis_warning('read_snapshot', exc)
            return {
                'monitor_scope': 'process-local-fallback',
                'started_at': cls._started_at,
                'counters': {},
                'failure_reasons': {},
                'kid_stats': [],
                'recent_failures': [],
            }

    @classmethod
    async def _get_redis_kid_stats(cls, redis: aioredis.Redis, kids: list[str]) -> list[dict[str, Any]]:
        """
        获取Redis中的按密钥版本聚合统计

        :param redis: Redis客户端
        :param kids: 密钥版本列表
        :return: 按密钥版本统计列表
        """
        if not kids:
            return []
        async with redis.pipeline(transaction=False) as pipe:
            for kid in kids:
                pipe.hgetall(cls._build_kid_counter_key(kid))
            kid_counter_rows = await pipe.execute()
        return [
            {
                'kid': kid,
                'encryptedRequests': cls._to_int_mapping(kid_counter).get('encrypted_requests_total', 0),
                'decryptSuccess': cls._to_int_mapping(kid_counter).get('decrypt_success_total', 0),
                'decryptFailure': cls._to_int_mapping(kid_counter).get('decrypt_failure_total', 0),
                'encryptedResponses': cls._to_int_mapping(kid_counter).get('encrypted_responses_total', 0),
            }
            for kid, kid_counter in zip(kids, kid_counter_rows, strict=False)
        ]

    # 进程内回退统计
    @classmethod
    def _record_plain_request_local(cls) -> None:
        """
        在本地内存中记录明文请求

        :return: None
        """
        with cls._lock:
            cls._counters['requests_total'] += 1
            cls._counters['plain_requests_total'] += 1

    @classmethod
    def _record_encrypted_request_local(cls, kid: str | None = None) -> None:
        """
        在本地内存中记录加密请求

        :param kid: 当前请求使用的密钥版本
        :return: None
        """
        with cls._lock:
            cls._counters['requests_total'] += 1
            cls._counters['encrypted_requests_total'] += 1
            cls._increase_kid_counter_local(kid, 'encrypted_requests_total')

    @classmethod
    def _record_decrypt_success_local(cls, kid: str | None = None) -> None:
        """
        在本地内存中记录解密成功事件

        :param kid: 当前请求使用的密钥版本
        :return: None
        """
        with cls._lock:
            cls._counters['decrypt_success_total'] += 1
            cls._increase_kid_counter_local(kid, 'decrypt_success_total')

    @classmethod
    def _record_plain_response_local(cls) -> None:
        """
        在本地内存中记录明文响应

        :return: None
        """
        with cls._lock:
            cls._counters['plain_responses_total'] += 1

    @classmethod
    def _record_encrypted_response_local(cls, kid: str | None = None, is_error: bool = False) -> None:
        """
        在本地内存中记录加密响应

        :param kid: 当前响应使用的密钥版本
        :param is_error: 是否为错误响应
        :return: None
        """
        with cls._lock:
            cls._counters['encrypted_responses_total'] += 1
            if is_error:
                cls._counters['encrypted_error_responses_total'] += 1
            cls._increase_kid_counter_local(kid, 'encrypted_responses_total')

    @classmethod
    def _record_failure_local(
        cls,
        method: str,
        path: str,
        reason: str,
        kid: str | None = None,
        include_decrypt_failure: bool = True,
    ) -> None:
        """
        在本地内存中记录失败事件

        :param method: 请求方法
        :param path: 请求路径
        :param reason: 失败原因分类
        :param kid: 当前请求使用的密钥版本
        :param include_decrypt_failure: 是否计入解密失败次数
        :return: None
        """
        with cls._lock:
            if include_decrypt_failure:
                cls._counters['decrypt_failure_total'] += 1
            if reason == 'required_missing':
                cls._counters['required_rejected_total'] += 1
            cls._failure_reasons[reason] += 1
            cls._increase_kid_counter_local(kid, 'decrypt_failure_total')
            cls._recent_failures.appendleft(
                {
                    'time': datetime.now(),
                    'method': method,
                    'path': path,
                    'reason': reason,
                    'kid': kid,
                }
            )

    @classmethod
    def _get_local_snapshot_parts(cls) -> dict[str, Any]:
        """
        获取本地内存中的监控快照片段

        :return: 本地监控快照片段
        """
        with cls._lock:
            return {
                'monitor_scope': 'process-local-fallback',
                'started_at': cls._started_at,
                'counters': dict(cls._counters),
                'failure_reasons': dict(cls._failure_reasons),
                'kid_stats': [
                    {
                        'kid': kid,
                        'encryptedRequests': kid_counter.get('encrypted_requests_total', 0),
                        'decryptSuccess': kid_counter.get('decrypt_success_total', 0),
                        'decryptFailure': kid_counter.get('decrypt_failure_total', 0),
                        'encryptedResponses': kid_counter.get('encrypted_responses_total', 0),
                    }
                    for kid, kid_counter in sorted(cls._kid_counters.items(), key=lambda item: item[0])
                ],
                'recent_failures': list(cls._recent_failures),
            }

    @classmethod
    def _merge_snapshot_parts(cls, redis_snapshot: dict[str, Any], local_snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        合并Redis统计与本地回退统计

        :param redis_snapshot: Redis监控快照片段
        :param local_snapshot: 本地监控快照片段
        :return: 合并后的监控快照片段
        """
        merged_counters = Counter(redis_snapshot['counters'])
        merged_counters.update(local_snapshot['counters'])

        merged_failure_reasons = Counter(redis_snapshot['failure_reasons'])
        merged_failure_reasons.update(local_snapshot['failure_reasons'])

        merged_kid_stats: dict[str, dict[str, Any]] = {}
        for kid_stat in redis_snapshot['kid_stats'] + local_snapshot['kid_stats']:
            kid = kid_stat.get('kid')
            if not kid:
                continue
            merged_kid_stat = merged_kid_stats.setdefault(
                kid,
                {
                    'kid': kid,
                    'encryptedRequests': 0,
                    'decryptSuccess': 0,
                    'decryptFailure': 0,
                    'encryptedResponses': 0,
                },
            )
            merged_kid_stat['encryptedRequests'] += int(kid_stat.get('encryptedRequests', 0) or 0)
            merged_kid_stat['decryptSuccess'] += int(kid_stat.get('decryptSuccess', 0) or 0)
            merged_kid_stat['decryptFailure'] += int(kid_stat.get('decryptFailure', 0) or 0)
            merged_kid_stat['encryptedResponses'] += int(kid_stat.get('encryptedResponses', 0) or 0)

        combined_failures = redis_snapshot['recent_failures'] + local_snapshot['recent_failures']
        combined_failures.sort(
            key=lambda item: cls._coerce_datetime_for_sort(item.get('time')),
            reverse=True,
        )

        monitor_scope = redis_snapshot['monitor_scope']
        if monitor_scope == 'redis-aggregated' and cls._has_local_fallback_data(local_snapshot):
            monitor_scope = 'redis-aggregated+local-fallback'

        return {
            'monitor_scope': monitor_scope,
            'started_at': min(redis_snapshot['started_at'], local_snapshot['started_at']),
            'counters': dict(merged_counters),
            'failure_reasons': dict(merged_failure_reasons),
            'kid_stats': sorted(merged_kid_stats.values(), key=lambda item: item['kid']),
            'recent_failures': combined_failures[: cls._RECENT_FAILURE_LIMIT],
        }

    # 快照构建与通用辅助
    @classmethod
    def _build_snapshot(cls, snapshot_parts: dict[str, Any]) -> dict[str, Any]:
        """
        基于监控片段构建最终快照

        :param snapshot_parts: 监控快照片段
        :return: 最终监控快照
        """
        try:
            current_kid = TransportKeyProvider.get_current_kid()
            supported_kids = TransportKeyProvider.get_supported_kids()
        except Exception:
            current_kid = ''
            supported_kids = []

        counters = snapshot_parts['counters']
        return {
            'monitorScope': snapshot_parts['monitor_scope'],
            'startedAt': snapshot_parts['started_at'],
            'appEnv': AppConfig.app_env,
            'transportCryptoEnabled': TransportCryptoConfig.transport_crypto_enabled,
            'transportCryptoMode': TransportCryptoConfig.transport_crypto_mode,
            'currentKid': current_kid,
            'supportedKids': supported_kids,
            'enabledPaths': TransportCryptoUtil._split_paths(TransportCryptoConfig.transport_crypto_enabled_paths),
            'requiredPaths': TransportCryptoUtil._split_paths(TransportCryptoConfig.transport_crypto_required_paths),
            'excludePaths': TransportCryptoUtil._split_paths(TransportCryptoConfig.transport_crypto_exclude_paths),
            'requestsTotal': counters.get('requests_total', 0),
            'plainRequestsTotal': counters.get('plain_requests_total', 0),
            'encryptedRequestsTotal': counters.get('encrypted_requests_total', 0),
            'requiredRejectedTotal': counters.get('required_rejected_total', 0),
            'decryptSuccessTotal': counters.get('decrypt_success_total', 0),
            'decryptFailureTotal': counters.get('decrypt_failure_total', 0),
            'plainResponsesTotal': counters.get('plain_responses_total', 0),
            'encryptedResponsesTotal': counters.get('encrypted_responses_total', 0),
            'encryptedErrorResponsesTotal': counters.get('encrypted_error_responses_total', 0),
            'failureReasons': snapshot_parts['failure_reasons'],
            'kidStats': snapshot_parts['kid_stats'],
            'recentFailures': snapshot_parts['recent_failures'],
        }

    @classmethod
    def _get_redis_client(cls, app: FastAPI | None) -> aioredis.Redis | None:
        """
        获取当前应用中的Redis客户端

        :param app: FastAPI应用对象
        :return: Redis客户端，不存在时返回None
        """
        if app is None:
            return None
        return getattr(app.state, 'redis', None)

    @classmethod
    def _increase_kid_counter_local(cls, kid: str | None, counter_name: str) -> None:
        """
        在本地内存中按密钥版本累加统计值

        :param kid: 当前密钥版本
        :param counter_name: 统计项名称
        :return: None
        """
        if not kid:
            return
        cls._kid_counters[kid][counter_name] += 1

    @classmethod
    def _log_redis_warning(cls, action: str, exc: Exception) -> None:
        """
        记录Redis监控降级日志，并限制日志频率

        :param action: 当前执行动作
        :param exc: 异常对象
        :return: None
        """
        now = time.monotonic()
        with cls._lock:
            if now - cls._last_redis_warning_at < cls._REDIS_WARNING_INTERVAL_SECONDS:
                return
            cls._last_redis_warning_at = now
        logger.warning('传输层加解密监控Redis操作失败，已回退为进程内统计，action={}, error={}', action, exc)

    @classmethod
    def _has_local_fallback_data(cls, local_snapshot: dict[str, Any]) -> bool:
        """
        判断本地回退统计中是否存在有效数据

        :param local_snapshot: 本地监控快照片段
        :return: 是否存在有效数据
        """
        if local_snapshot['counters']:
            return True
        if local_snapshot['failure_reasons']:
            return True
        if local_snapshot['kid_stats']:
            return True
        return bool(local_snapshot['recent_failures'])

    @classmethod
    def _build_kid_counter_key(cls, kid: str) -> str:
        """
        构建按密钥版本统计的Redis键名

        :param kid: 密钥版本
        :return: Redis键名
        """
        return f'{cls._REDIS_KEY_PREFIX}:kid:{kid}:counters'

    @classmethod
    def _parse_recent_failures(cls, recent_failures: list[str]) -> list[dict[str, Any]]:
        """
        解析Redis中的最近失败记录

        :param recent_failures: Redis中存储的失败记录列表
        :return: 失败记录对象列表
        """
        parsed_failures: list[dict[str, Any]] = []
        for recent_failure in recent_failures:
            try:
                recent_failure_item = json.loads(recent_failure)
            except json.JSONDecodeError:
                continue
            if not isinstance(recent_failure_item, dict):
                continue
            recent_failure_item['time'] = cls._parse_datetime(recent_failure_item.get('time'))
            parsed_failures.append(recent_failure_item)
        return parsed_failures

    @staticmethod
    def _to_int_mapping(mapping: dict[str, Any]) -> dict[str, int]:
        """
        将Redis返回的字符串字典转换为整数字典

        :param mapping: Redis原始字典
        :return: 转换后的整数字典
        """
        return {str(key): int(value) for key, value in mapping.items()}

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """
        将字符串时间解析为datetime对象

        :param value: 原始时间值
        :return: datetime对象，解析失败时返回None
        """
        if isinstance(value, datetime):
            return value
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @classmethod
    def _coerce_datetime_for_sort(cls, value: Any) -> datetime:
        """
        将任意时间值转换为可排序的datetime对象

        :param value: 原始时间值
        :return: datetime对象
        """
        parsed_datetime = cls._parse_datetime(value)
        if parsed_datetime:
            return parsed_datetime
        return datetime.min
