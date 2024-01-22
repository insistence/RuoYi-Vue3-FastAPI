from fastapi import APIRouter
from fastapi import Depends
from module_admin.service.login_service import LoginService
from module_admin.service.cache_service import *
from utils.response_util import *
from utils.log_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth


cacheController = APIRouter(prefix='/monitor/cache', dependencies=[Depends(LoginService.get_current_user)])


@cacheController.get("", response_model=CacheMonitorModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def get_monitor_cache_info(request: Request):
    try:
        # 获取全量数据
        cache_info_query_result = await CacheService.get_cache_monitor_statistical_info_services(request)
        logger.info('获取成功')
        return ResponseUtil.success(data=cache_info_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.get("/getNames", response_model=List[CacheInfoModel], dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def get_monitor_cache_name(request: Request):
    try:
        # 获取全量数据
        cache_name_list_result = CacheService.get_cache_monitor_cache_name_services()
        logger.info('获取成功')
        return ResponseUtil.success(data=cache_name_list_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.get("/getKeys/{cache_name}", response_model=List[str], dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def get_monitor_cache_key(request: Request, cache_name: str):
    try:
        # 获取全量数据
        cache_key_list_result = await CacheService.get_cache_monitor_cache_key_services(request, cache_name)
        logger.info('获取成功')
        return ResponseUtil.success(data=cache_key_list_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.get("/getValue/{cache_name}/{cache_key}", response_model=CacheInfoModel, dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def get_monitor_cache_value(request: Request, cache_name: str, cache_key: str):
    try:
        # 获取全量数据
        cache_value_list_result = await CacheService.get_cache_monitor_cache_value_services(request, cache_name, cache_key)
        logger.info('获取成功')
        return ResponseUtil.success(data=cache_value_list_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.delete("/clearCacheName/{cache_name}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def clear_monitor_cache_name(request: Request, cache_name: str):
    try:
        clear_cache_name_result = await CacheService.clear_cache_monitor_cache_name_services(request, cache_name)
        if clear_cache_name_result.is_success:
            logger.info(clear_cache_name_result.message)
            return ResponseUtil.success(msg=clear_cache_name_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.delete("/clearCacheKey/{cache_key}", dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def clear_monitor_cache_key(request: Request, cache_key: str):
    try:
        clear_cache_key_result = await CacheService.clear_cache_monitor_cache_key_services(request, cache_key)
        if clear_cache_key_result.is_success:
            logger.info(clear_cache_key_result.message)
            return ResponseUtil.success(msg=clear_cache_key_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@cacheController.delete("/clearCacheAll", dependencies=[Depends(CheckUserInterfaceAuth('monitor:cache:list'))])
async def clear_monitor_cache_all(request: Request):
    try:
        clear_cache_all_result = await CacheService.clear_cache_monitor_all_services(request)
        if clear_cache_all_result.is_success:
            logger.info(clear_cache_all_result.message)
            return ResponseUtil.success(msg=clear_cache_all_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
