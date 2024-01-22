import aioredis
from module_admin.service.dict_service import DictDataService
from module_admin.service.config_service import ConfigService
from config.env import RedisConfig
from config.database import SessionLocal
from utils.log_util import logger


class RedisUtil:
    """
    Redis相关方法
    """

    @classmethod
    async def create_redis_pool(cls) -> aioredis.Redis:
        """
        应用启动时初始化redis连接
        :return: Redis连接对象
        """
        logger.info("开始连接redis...")
        redis = await aioredis.from_url(
            url=f"redis://{RedisConfig.HOST}",
            port=RedisConfig.PORT,
            username=RedisConfig.USERNAME,
            password=RedisConfig.PASSWORD,
            db=RedisConfig.DB,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("redis连接成功")
        return redis

    @classmethod
    async def close_redis_pool(cls, app):
        """
        应用关闭时关闭redis连接
        :param app: fastapi对象
        :return:
        """
        await app.state.redis.close()
        logger.info("关闭redis连接成功")

    @classmethod
    async def init_sys_dict(cls, redis):
        """
        应用启动时缓存字典表
        :param redis: redis对象
        :return:
        """
        session = SessionLocal()
        await DictDataService.init_cache_sys_dict_services(session, redis)

        session.close()

    @classmethod
    async def init_sys_config(cls, redis):
        """
        应用启动时缓存参数配置表
        :param redis: redis对象
        :return:
        """
        session = SessionLocal()
        await ConfigService.init_cache_sys_config_services(session, redis)

        session.close()
