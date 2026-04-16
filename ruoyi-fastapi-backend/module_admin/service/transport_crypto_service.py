from fastapi import Request

from module_admin.entity.vo.transport_crypto_vo import (
    TransportCryptoFrontendConfigModel,
    TransportCryptoMonitorModel,
    TransportCryptoPublicKeyModel,
)
from utils.transport_crypto_util import TransportCryptoMonitorUtil, TransportCryptoUtil


class TransportCryptoService:
    """
    传输加密模块服务层
    """

    @classmethod
    async def get_transport_frontend_config_services(cls) -> TransportCryptoFrontendConfigModel:
        """
        获取前端传输加密运行配置service

        :return: 前端传输加密运行配置
        """
        return TransportCryptoFrontendConfigModel.model_validate(TransportCryptoUtil.build_frontend_config_payload())

    @classmethod
    async def get_transport_public_key_services(cls) -> TransportCryptoPublicKeyModel:
        """
        获取传输加密公钥service

        :return: 传输加密公钥信息
        """
        return TransportCryptoPublicKeyModel.model_validate(TransportCryptoUtil.build_public_key_payload())

    @classmethod
    async def get_transport_crypto_monitor_info_services(cls, request: Request) -> TransportCryptoMonitorModel:
        """
        获取传输加密监控信息service

        :param request: Request对象
        :return: 传输加密监控信息
        """
        transport_crypto_monitor_info = await TransportCryptoMonitorUtil.get_snapshot(request.app)

        return TransportCryptoMonitorModel.model_validate(transport_crypto_monitor_info)
