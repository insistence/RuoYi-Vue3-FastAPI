from typing import Annotated

from fastapi import APIRouter, Path, Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.vo import DataResponseModel, ResponseBaseModel
from module_admin.entity.vo.cache_vo import CacheInfoModel, CacheMonitorModel
from module_admin.service.cache_service import CacheService
from utils.log_util import logger
from utils.response_util import ResponseUtil

cache_controller = APIRouter(prefix='/monitor/cache', dependencies=[PreAuthDependency()])


@cache_controller.get(
    '',
    response_model=DataResponseModel[CacheMonitorModel],
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def get_monitor_cache_info(request: Request) -> Response:
    # 获取全量数据
    cache_info_query_result = await CacheService.get_cache_monitor_statistical_info_services(request)
    logger.info('获取成功')

    return ResponseUtil.success(data=cache_info_query_result)


@cache_controller.get(
    '/getNames',
    response_model=DataResponseModel[list[CacheInfoModel]],
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def get_monitor_cache_name(request: Request) -> Response:
    # 获取全量数据
    cache_name_list_result = await CacheService.get_cache_monitor_cache_name_services()
    logger.info('获取成功')

    return ResponseUtil.success(data=cache_name_list_result)


@cache_controller.get(
    '/getKeys/{cache_name}',
    response_model=DataResponseModel[list[str]],
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def get_monitor_cache_key(request: Request, cache_name: Annotated[str, Path(description='缓存名称')]) -> Response:
    # 获取全量数据
    cache_key_list_result = await CacheService.get_cache_monitor_cache_key_services(request, cache_name)
    logger.info('获取成功')

    return ResponseUtil.success(data=cache_key_list_result)


@cache_controller.get(
    '/getValue/{cache_name}/{cache_key}',
    response_model=DataResponseModel[CacheInfoModel],
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def get_monitor_cache_value(
    request: Request,
    cache_name: Annotated[str, Path(description='缓存名称')],
    cache_key: Annotated[str, Path(description='缓存键')],
) -> Response:
    # 获取全量数据
    cache_value_list_result = await CacheService.get_cache_monitor_cache_value_services(request, cache_name, cache_key)
    logger.info('获取成功')

    return ResponseUtil.success(data=cache_value_list_result)


@cache_controller.delete(
    '/clearCacheName/{cache_name}',
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def clear_monitor_cache_name(
    request: Request, cache_name: Annotated[str, Path(description='缓存名称')]
) -> Response:
    clear_cache_name_result = await CacheService.clear_cache_monitor_cache_name_services(request, cache_name)
    logger.info(clear_cache_name_result.message)

    return ResponseUtil.success(msg=clear_cache_name_result.message)


@cache_controller.delete(
    '/clearCacheKey/{cache_key}',
    response_model= ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def clear_monitor_cache_key(request: Request, cache_key: Annotated[str, Path(description='缓存键')]) -> Response:
    clear_cache_key_result = await CacheService.clear_cache_monitor_cache_key_services(request, cache_key)
    logger.info(clear_cache_key_result.message)

    return ResponseUtil.success(msg=clear_cache_key_result.message)


@cache_controller.delete(
    '/clearCacheAll',
    response_model= ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('monitor:cache:list')],
)
async def clear_monitor_cache_all(request: Request) -> Response:
    clear_cache_all_result = await CacheService.clear_cache_monitor_all_services(request)
    logger.info(clear_cache_all_result.message)

    return ResponseUtil.success(msg=clear_cache_all_result.message)
