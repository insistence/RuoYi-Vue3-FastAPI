import json
from collections.abc import Callable
from typing import Any

from cli.exit_codes import ARGUMENT_ERROR, RUNTIME_ERROR

from .gateway import CryptoInfrastructureGateway

MIN_RSA_KEY_SIZE = 2048
RSA_KEY_SIZE_STEP = 256


class CryptoDomainSupport:
    """
    传输加密领域支持对象。

    该对象负责 RSA 密钥规则校验、密钥对生成和历史密钥规整，
    避免主运行时服务继续承载局部安全规则和数据拼装细节。

    :param infrastructure_gateway: 传输加密基础设施网关
    """

    def __init__(self, infrastructure_gateway: CryptoInfrastructureGateway) -> None:
        """
        初始化传输加密领域支持对象。

        :param infrastructure_gateway: 传输加密基础设施网关
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway

    @staticmethod
    def validate_rsa_key_size(key_size: int) -> None:
        """
        校验 RSA 密钥长度是否合法。

        :param key_size: RSA 密钥长度
        :return: None
        :raises ValueError: 密钥长度不满足约束时抛出异常
        """
        if key_size < MIN_RSA_KEY_SIZE or key_size % RSA_KEY_SIZE_STEP != 0:
            raise ValueError('RSA 密钥长度必须大于等于 2048，且为 256 的整数倍')

    def generate_rsa_key_pair(self, key_size: int) -> tuple[str, str]:
        """
        生成 PEM 格式的 RSA 密钥对。

        :param key_size: RSA 密钥长度
        :return: 私钥与公钥 PEM 字符串
        """
        rsa_module = self.infrastructure_gateway.get_rsa_module()
        serialization_module = self.infrastructure_gateway.get_serialization_module()
        private_key = rsa_module.generate_private_key(public_exponent=65537, key_size=key_size)
        private_key_pem = private_key.private_bytes(
            encoding=serialization_module.Encoding.PEM,
            format=serialization_module.PrivateFormat.PKCS8,
            encryption_algorithm=serialization_module.NoEncryption(),
        ).decode('utf-8')
        public_key_pem = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization_module.Encoding.PEM,
                format=serialization_module.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode('utf-8')
        )
        return private_key_pem, public_key_pem

    def load_existing_legacy_key_pairs(self) -> list[dict[str, str]]:
        """
        解析当前配置中的历史密钥列表。

        :return: 历史密钥列表
        :raises ValueError: 历史密钥配置非法时抛出异常
        """
        transport_crypto_config = self.infrastructure_gateway.get_transport_crypto_config()
        raw_legacy_key_pairs = transport_crypto_config.transport_crypto_legacy_key_pairs or '[]'
        parsed_legacy_key_pairs = json.loads(raw_legacy_key_pairs)
        if not isinstance(parsed_legacy_key_pairs, list):
            raise ValueError('TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS 必须为 JSON 数组')
        return [item for item in parsed_legacy_key_pairs if isinstance(item, dict)]

    @staticmethod
    def merge_rotation_legacy_key_pairs(
        legacy_key_pairs: list[dict[str, str]],
        current_key_pair: Any,
        next_kid: str,
    ) -> list[dict[str, str]]:
        """
        合并轮换后的历史密钥列表。

        :param legacy_key_pairs: 当前历史密钥列表
        :param current_key_pair: 当前生效密钥对对象
        :param next_kid: 即将切换的新密钥版本
        :return: 合并后的历史密钥列表
        """
        normalized_legacy_key_pairs: dict[str, dict[str, str]] = {
            str(item.get('kid')): item for item in legacy_key_pairs if item.get('kid')
        }
        normalized_legacy_key_pairs[current_key_pair.kid] = {
            'kid': current_key_pair.kid,
            'privateKey': current_key_pair.private_key_pem,
            'publicKey': current_key_pair.public_key_pem,
        }
        normalized_legacy_key_pairs.pop(next_kid, None)
        return list(normalized_legacy_key_pairs.values())

    @staticmethod
    def build_key_pair_env_patch(kid: str, private_key_pem: str, public_key_pem: str) -> dict[str, str]:
        """
        构建密钥对写回环境变量所需的补丁数据。

        :param kid: 密钥版本标识
        :param private_key_pem: 私钥 PEM 文本
        :param public_key_pem: 公钥 PEM 文本
        :return: 环境变量补丁数据
        """
        return {
            'TRANSPORT_CRYPTO_KID': kid,
            'TRANSPORT_CRYPTO_PRIVATE_KEY': private_key_pem,
            'TRANSPORT_CRYPTO_PUBLIC_KEY': public_key_pem,
        }

    def build_rotation_env_patch(
        self,
        next_kid: str,
        private_key_pem: str,
        public_key_pem: str,
        merged_legacy_key_pairs: list[dict[str, str]],
    ) -> dict[str, str]:
        """
        构建密钥轮换写回环境变量所需的补丁数据。

        :param next_kid: 新密钥版本标识
        :param private_key_pem: 新私钥 PEM 文本
        :param public_key_pem: 新公钥 PEM 文本
        :param merged_legacy_key_pairs: 合并后的历史密钥列表
        :return: 环境变量补丁数据
        """
        env_patch = self.build_key_pair_env_patch(next_kid, private_key_pem, public_key_pem)
        env_patch['TRANSPORT_CRYPTO_LEGACY_KEY_PAIRS'] = json.dumps(merged_legacy_key_pairs, ensure_ascii=False)
        return env_patch


class CryptoResultSupport:
    """
    传输加密结果支持对象。

    该对象负责参数错误/运行时错误结果翻译，以及固定轮换提示文案构建，
    避免主运行时服务继续承载重复异常映射与静态 payload 片段。
    """

    @staticmethod
    def build_argument_error_result(message: str, exc: Exception) -> dict[str, Any]:
        """
        构建参数错误结果。

        :param message: 失败消息
        :param exc: 原始异常
        :return: 标准参数错误结果
        """
        return {
            'ok': False,
            'message': message,
            'error': str(exc),
            'exit_code': ARGUMENT_ERROR,
        }

    @staticmethod
    def build_runtime_error_result(message: str, exc: Exception) -> dict[str, Any]:
        """
        构建运行时错误结果。

        :param message: 失败消息
        :param exc: 原始异常
        :return: 标准运行时错误结果
        """
        return {
            'ok': False,
            'message': message,
            'error': str(exc),
            'exit_code': RUNTIME_ERROR,
        }

    def run_argument_guarded(
        self,
        operation: Callable[[], dict[str, Any]],
        *,
        failure_message: str,
    ) -> dict[str, Any]:
        """
        以统一参数/运行时错误翻译执行操作。

        :param operation: 待执行操作
        :param failure_message: 失败消息
        :return: 操作结果
        """
        try:
            return operation()
        except ValueError as exc:
            return self.build_argument_error_result(failure_message, exc)
        except Exception as exc:
            return self.build_runtime_error_result(failure_message, exc)

    def run_runtime_guarded(
        self,
        operation: Callable[[], dict[str, Any]],
        *,
        failure_message: str,
    ) -> dict[str, Any]:
        """
        以统一运行时错误翻译执行操作。

        :param operation: 待执行操作
        :param failure_message: 失败消息
        :return: 操作结果
        """
        try:
            return operation()
        except Exception as exc:
            return self.build_runtime_error_result(failure_message, exc)

    @staticmethod
    def build_rotation_apply_steps() -> list[str]:
        """
        构建密钥轮换后的应用步骤说明。

        :return: 轮换应用步骤列表
        """
        return [
            '将 envPatch 中的新密钥写入目标环境配置',
            '发布后保留 legacyKeyPairs，确保旧请求在轮换窗口内可解密',
            '确认前端已刷新到 nextKid 后，再移除不再需要的历史密钥',
        ]
