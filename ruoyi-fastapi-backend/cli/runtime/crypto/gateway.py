from importlib import import_module
from typing import Any


class CryptoInfrastructureGateway:
    """
    传输加密基础设施网关。

    该对象负责延迟加载 cryptography、环境配置和传输加密工具依赖，
    供传输加密运行时 facade 与其协作对象统一复用。
    """

    @staticmethod
    def get_serialization_module() -> Any:
        """
        获取 cryptography 序列化模块。

        :return: 序列化模块
        """
        return import_module('cryptography.hazmat.primitives.serialization')

    @staticmethod
    def get_rsa_module() -> Any:
        """
        获取 RSA 非对称算法模块。

        :return: RSA 模块
        """
        return import_module('cryptography.hazmat.primitives.asymmetric.rsa')

    @staticmethod
    def get_transport_crypto_config() -> Any:
        """
        获取传输加密配置对象。

        :return: 传输加密配置对象
        """
        return import_module('config.env').TransportCryptoConfig

    @staticmethod
    def get_transport_crypto_util() -> Any:
        """
        获取传输加密工具类。

        :return: 传输加密工具类
        """
        return import_module('utils.transport_crypto_util').TransportCryptoUtil

    @staticmethod
    def get_transport_key_provider() -> Any:
        """
        获取传输加密密钥提供者。

        :return: 传输加密密钥提供者
        """
        return import_module('utils.transport_crypto_util').TransportKeyProvider
