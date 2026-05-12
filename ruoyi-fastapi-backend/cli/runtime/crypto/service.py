from datetime import datetime
from typing import Any

from .gateway import CryptoInfrastructureGateway
from .support import CryptoDomainSupport, CryptoResultSupport


class CryptoRuntimeService:
    """
    传输加密运行时服务。

    该服务作为传输加密运行时 facade，对外统一暴露配置校验、
    公钥导出、密钥生成和轮换辅助方案构建入口。

    :param infrastructure_gateway: 传输加密基础设施网关
    :param domain_support: 传输加密领域支持对象
    :param result_support: 传输加密结果支持对象
    """

    def __init__(
        self,
        *,
        infrastructure_gateway: CryptoInfrastructureGateway | None = None,
        domain_support: CryptoDomainSupport | None = None,
        result_support: CryptoResultSupport | None = None,
    ) -> None:
        """
        初始化传输加密运行时服务。

        :param infrastructure_gateway: 传输加密基础设施网关
        :param domain_support: 传输加密领域支持对象
        :param result_support: 传输加密结果支持对象
        :return: None
        """
        self.infrastructure_gateway = infrastructure_gateway or CryptoInfrastructureGateway()
        self.domain_support = domain_support or CryptoDomainSupport(self.infrastructure_gateway)
        self.result_support = result_support or CryptoResultSupport()

    def generate_crypto_key_pair(self, kid: str, key_size: int) -> dict[str, Any]:
        """
        生成新的传输加密密钥对。

        :param kid: 目标密钥版本标识
        :param key_size: RSA 密钥长度
        :return: 密钥生成结果
        """

        def _operation() -> dict[str, Any]:
            self.domain_support.validate_rsa_key_size(key_size)
            private_key_pem, public_key_pem = self.domain_support.generate_rsa_key_pair(key_size)
            return {
                'ok': True,
                'message': '传输加密密钥生成完成',
                'kid': kid,
                'keySize': key_size,
                'privateKey': private_key_pem,
                'publicKey': public_key_pem,
                'envPatch': self.domain_support.build_key_pair_env_patch(kid, private_key_pem, public_key_pem),
            }

        return self.result_support.run_argument_guarded(_operation, failure_message='生成传输加密密钥失败')

    def validate_crypto_config(self) -> dict[str, Any]:
        """
        校验传输加密运行配置。

        :return: 传输加密配置校验结果
        """
        transport_key_provider = self.infrastructure_gateway.get_transport_key_provider()

        def _operation() -> dict[str, Any]:
            transport_key_provider.validate_runtime_configuration()
            return {'ok': True, 'message': '传输加密配置校验通过'}

        return self.result_support.run_runtime_guarded(_operation, failure_message='传输加密配置校验失败')

    def export_public_key(self) -> dict[str, Any]:
        """
        导出当前运行环境的传输加密公钥信息。

        :return: 公钥导出结果
        """
        transport_key_provider = self.infrastructure_gateway.get_transport_key_provider()
        transport_crypto_util = self.infrastructure_gateway.get_transport_crypto_util()

        def _operation() -> dict[str, Any]:
            transport_key_provider.validate_runtime_configuration()
            return {'ok': True, 'publicKey': transport_crypto_util.build_public_key_payload()}

        return self.result_support.run_runtime_guarded(_operation, failure_message='导出传输加密公钥失败')

    def build_rotation_payload(self, next_kid: str, key_size: int) -> dict[str, Any]:
        """
        生成传输加密密钥轮换辅助结果。

        :param next_kid: 新密钥版本标识
        :param key_size: 新密钥的 RSA 长度
        :return: 轮换辅助结果
        """
        transport_key_provider = self.infrastructure_gateway.get_transport_key_provider()

        def _operation() -> dict[str, Any]:
            self.domain_support.validate_rsa_key_size(key_size)
            transport_key_provider.validate_runtime_configuration()
            current_key_pair = transport_key_provider.get_current_key_pair()
            if next_kid == current_key_pair.kid:
                raise ValueError('新密钥版本不能与当前版本相同')

            private_key_pem, public_key_pem = self.domain_support.generate_rsa_key_pair(key_size)
            legacy_key_pairs = self.domain_support.load_existing_legacy_key_pairs()
            merged_legacy_key_pairs = self.domain_support.merge_rotation_legacy_key_pairs(
                legacy_key_pairs,
                current_key_pair,
                next_kid,
            )
            return {
                'ok': True,
                'message': '传输加密密钥轮换方案已生成',
                'currentKid': current_key_pair.kid,
                'nextKid': next_kid,
                'keySize': key_size,
                'generatedAt': datetime.now().isoformat(),
                'nextKeyPair': {
                    'kid': next_kid,
                    'privateKey': private_key_pem,
                    'publicKey': public_key_pem,
                },
                'legacyKeyPairs': merged_legacy_key_pairs,
                'envPatch': self.domain_support.build_rotation_env_patch(
                    next_kid,
                    private_key_pem,
                    public_key_pem,
                    merged_legacy_key_pairs,
                ),
                'applySteps': self.result_support.build_rotation_apply_steps(),
            }

        return self.result_support.run_argument_guarded(_operation, failure_message='生成密钥轮换方案失败')


CRYPTO_RUNTIME = CryptoRuntimeService()
