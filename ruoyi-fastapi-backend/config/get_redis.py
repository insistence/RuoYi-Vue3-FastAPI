from redis import asyncio as aioredis
from redis.cluster import ClusterNode
from redis.exceptions import AuthenticationError, TimeoutError, RedisError
from config.database import AsyncSessionLocal
from config.env import RedisConfig
from module_admin.service.config_service import ConfigService
from module_admin.service.dict_service import DictDataService
from utils.log_util import logger


def create_cluster_nodes(node_string):
    """
    创建集群节点列表。

    根据传入的节点字符串，生成一个包含多个ClusterNode对象的列表。
    节点字符串的格式为"host1:port1,host2:port2,...",每个节点的主机名和端口号用冒号分隔，
    不同节点之间用逗号分隔。

    参数:
    - node_string (str): 节点字符串，格式为"host1:port1,host2:port2,..."

    返回:
    - list: 包含多个ClusterNode对象的列表，每个ClusterNode对象表示一个集群节点。
    """
    # 初始化节点列表
    nodes = []

    # 遍历节点字符串，生成ClusterNode对象，并添加到节点列表中
    for node in node_string.split(','):
        # 分割节点字符串，获取主机名和端口号
        host, port = node.split(':')

        # 将主机名和端口号转换为ClusterNode对象，并添加到节点列表中
        nodes.append(ClusterNode(host=host, port=int(port)))

    # 返回节点列表
    return nodes


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
        logger.info('开始连接redis...')
        if RedisConfig.redis_cluster:
            logger.info(f'redis集群模式,集群地址：{RedisConfig.redis_host}')
            # 创建 ClusterNode 实例列表
            startup_nodes = create_cluster_nodes(RedisConfig.redis_host)
            redis = await aioredis.RedisCluster(
                startup_nodes=startup_nodes,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                encoding='utf-8',
                decode_responses=True,
            )
        else:
            logger.info(f'redis单机模式,单机地址：{RedisConfig.redis_host}:{RedisConfig.redis_port}')
            redis = await aioredis.from_url(
                url=f'redis://{RedisConfig.redis_host}',
                port=RedisConfig.redis_port,
                username=RedisConfig.redis_username,
                password=RedisConfig.redis_password,
                db=RedisConfig.redis_database,
                encoding='utf-8',
                decode_responses=True,
            )
        try:
            connection = await redis.ping()
            if connection:
                logger.info('redis连接成功')
            else:
                logger.error('redis连接失败')
        except AuthenticationError as e:
            logger.error(f'redis用户名或密码错误，详细错误信息：{e}')
        except TimeoutError as e:
            logger.error(f'redis连接超时，详细错误信息：{e}')
        except RedisError as e:
            logger.error(f'redis连接错误，详细错误信息：{e}')
        return redis

    @classmethod
    async def close_redis_pool(cls, app):
        """
        应用关闭时关闭redis连接

        :param app: fastapi对象
        :return:
        """
        await app.state.redis.close()
        logger.info('关闭redis连接成功')

    @classmethod
    async def init_sys_dict(cls, redis):
        """
        应用启动时缓存字典表

        :param redis: redis对象
        :return:
        """
        async with AsyncSessionLocal() as session:
            await DictDataService.init_cache_sys_dict_services(session, redis)

    @classmethod
    async def init_sys_config(cls, redis):
        """
        应用启动时缓存参数配置表

        :param redis: redis对象
        :return:
        """
        async with AsyncSessionLocal() as session:
            await ConfigService.init_cache_sys_config_services(session, redis)
