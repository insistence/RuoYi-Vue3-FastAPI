from fastapi import Request
from config.env import AppConfig

from common.enums import RedisInitKeyConfig
from common.vo import CrudResponseModel
from config.get_redis import RedisUtil
from module_admin.entity.vo.cache_vo import CacheInfoModel, CacheMonitorModel


class CacheService:
    """
    缓存监控模块服务层
    """

    @classmethod
    async def get_cache_monitor_statistical_info_services(cls, request: Request) -> CacheMonitorModel:
        """
        获取缓存监控信息service

        :param request: Request对象
        :return: 缓存监控信息
        """
        info = await request.app.state.redis.info()
        db_size = await request.app.state.redis.dbsize()
        command_stats_dict = await request.app.state.redis.info('commandstats')
        command_stats = [
            {'name': key.split('_')[1], 'value': str(value.get('calls'))} for key, value in command_stats_dict.items()
        ]
        result = CacheMonitorModel(commandStats=command_stats, dbSize=db_size, info=info)

        return result

    @classmethod
    async def get_cache_monitor_cache_name_services(cls) -> list[CacheInfoModel]:
        """
        获取缓存名称列表信息service

        :return: 缓存名称列表信息
        """
        name_list = [
            CacheInfoModel(
                cacheKey='',
                cacheName=key_config.key,
                cacheValue='',
                remark=key_config.remark,
            )
            for key_config in RedisInitKeyConfig
        ]

        return name_list

    @classmethod
    async def get_cache_monitor_cache_key_services(cls, request: Request, cache_name: str) -> list[str]:
        """
        获取缓存键名列表信息service

        :param request: Request对象
        :param cache_name: 缓存名称
        :return: 缓存键名列表信息
        """
        cache_keys: list[str] = await request.app.state.redis.keys(f'{cache_name}*')
        cache_key_list = [key.split(':', 1)[1] for key in cache_keys if key.startswith(f'{cache_name}:')]

        return cache_key_list

    @classmethod
    async def get_cache_monitor_cache_value_services(
        cls, request: Request, cache_name: str, cache_key: str
    ) -> CacheInfoModel:
        """
        获取缓存内容信息service

        :param request: Request对象
        :param cache_name: 缓存名称
        :param cache_key: 缓存键名
        :return: 缓存内容信息
        """
        cache_value = await request.app.state.redis.get(f'{cache_name}:{cache_key}')

        return CacheInfoModel(cacheKey=cache_key, cacheName=cache_name, cacheValue=cache_value, remark='')

    @classmethod
    async def clear_cache_monitor_cache_name_services(cls, request: Request, cache_name: str) -> CrudResponseModel:
        """
        清除缓存名称对应所有键值service

        :param request: Request对象
        :param cache_name: 缓存名称
        :return: 操作缓存响应信息
        """
        cache_keys = await request.app.state.redis.keys(f'{cache_name}*')
        if cache_keys:
            await request.app.state.redis.delete(*cache_keys)

        return CrudResponseModel(is_success=True, message=f'{cache_name}对应键值清除成功')

    @classmethod
    async def clear_cache_monitor_cache_key_services(cls, request: Request, cache_key: str) -> CrudResponseModel:
        """
        清除缓存名称对应所有键值service

        :param request: Request对象
        :param cache_key: 缓存键名
        :return: 操作缓存响应信息
        """
        cache_keys = await request.app.state.redis.keys(f'*{cache_key}')
        if cache_keys:
            await request.app.state.redis.delete(*cache_keys)

        return CrudResponseModel(is_success=True, message=f'{cache_key}清除成功')

    @classmethod
    async def clear_cache_monitor_all_services(cls, request: Request) -> CrudResponseModel:
        """
        清除所有缓存service

        :param request: Request对象
        :return: 操作缓存响应信息
        """
        cache_keys = await request.app.state.redis.keys()
        if cache_keys:
            await request.app.state.redis.delete(*cache_keys)

        await RedisUtil.init_sys_dict(request.app.state.redis)
        await RedisUtil.init_sys_config(request.app.state.redis)

        return CrudResponseModel(is_success=True, message='所有缓存清除成功')

    @classmethod
    async def clear_usercache_by_id(cls, request: Request, user_id: int):
        """
        根据用户ID清除用户信息缓存service

        :param request: Request对象
        :param user_id: 用户ID
        :return: 操作缓存响应信息
        """
        if not AppConfig.app_enable_user_cache:
            return False
        
        cache_key = f'{RedisInitKeyConfig.USER_INFO.key}:{user_id}'
        await request.app.state.redis.delete(cache_key)

        return True

    @classmethod
    async def clear_usercache_all(cls, request: Request):
        """
        清除所有用户信息缓存service

        :param request: Request对象
        :return: 操作缓存响应信息
        """
        if not AppConfig.app_enable_user_cache:
            return False

        pattern = f'{RedisInitKeyConfig.USER_INFO.key}:*'
        batch_size = 1000

        try:
            cursor = 0
            deleted_count = 0
            while True:
                cursor, keys = await request.app.state.redis.scan(cursor=cursor, match=pattern, count=batch_size)
                if keys:
                    await request.app.state.redis.unlink(*keys)
                    deleted_count += len(keys)
                # 游标为 0 表示迭代完成
                if cursor == 0:
                    break

            print(f'✅ 已删除 {deleted_count} 个用户缓存键')
        except Exception as e:
            print(f'❌ 删除失败: {e}')
            return False

        return True
