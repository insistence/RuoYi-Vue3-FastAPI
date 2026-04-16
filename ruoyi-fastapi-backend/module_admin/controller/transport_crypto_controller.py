from fastapi import Request, Response

from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.constant import ApiNamespace
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.transport_crypto_vo import (
    TransportCryptoFrontendConfigModel,
    TransportCryptoMonitorModel,
    TransportCryptoPublicKeyModel,
)
from module_admin.service.transport_crypto_service import TransportCryptoService
from utils.log_util import logger
from utils.response_util import ResponseUtil

transport_crypto_controller = APIRouterPro(prefix='/transport/crypto', order_num=15, tags=['传输加密模块'])


@transport_crypto_controller.get(
    '/frontend-config',
    summary='获取前端传输加密配置接口',
    description='公开接口，用于向前端下发当前传输层加解密启用状态与运行模式，供前端统一跟随后端策略',
    response_model=DataResponseModel[TransportCryptoFrontendConfigModel],
)
@ApiRateLimit(namespace=ApiNamespace.TRANSPORT_CRYPTO_FRONTEND_CONFIG, preset=ApiRateLimitPreset.ANON_PUBLIC_METADATA)
async def get_transport_frontend_config(request: Request) -> Response:
    """
    获取当前前端传输层加解密运行配置

    :param request: 当前请求对象
    :return: 前端传输层加解密运行配置响应
    """
    transport_frontend_config = await TransportCryptoService.get_transport_frontend_config_services()
    logger.info('获取成功')

    return ResponseUtil.success(data=transport_frontend_config)


@transport_crypto_controller.get(
    '/public-key',
    summary='获取传输加密公钥接口',
    description='公开接口，用于向前端下发当前可用的传输层加密公钥，已配置匿名限流保护',
    response_model=DataResponseModel[TransportCryptoPublicKeyModel],
)
@ApiRateLimit(namespace=ApiNamespace.TRANSPORT_CRYPTO_PUBLIC_KEY, preset=ApiRateLimitPreset.ANON_PUBLIC_METADATA)
async def get_transport_public_key(request: Request) -> Response:
    """
    获取当前传输层加密公钥

    :param request: 当前请求对象
    :return: 公钥下发响应
    """
    transport_public_key = await TransportCryptoService.get_transport_public_key_services()
    logger.info('获取成功')

    return ResponseUtil.success(data=transport_public_key)


@transport_crypto_controller.get(
    '/monitor',
    summary='获取传输层加解密监控信息接口',
    description='用于获取基于Redis聚合的传输层加解密运行状态与统计信息',
    response_model=DataResponseModel[TransportCryptoMonitorModel],
    dependencies=[PreAuthDependency(), UserInterfaceAuthDependency('monitor:transportCrypto:list')],
)
async def get_transport_crypto_monitor_info(request: Request) -> Response:
    """
    获取基于Redis聚合的传输层加解密监控信息

    :param request: 当前请求对象
    :return: 传输层加解密监控信息响应
    """
    transport_crypto_monitor_info = await TransportCryptoService.get_transport_crypto_monitor_info_services(request)
    logger.info('获取成功')

    return ResponseUtil.success(data=transport_crypto_monitor_info)
