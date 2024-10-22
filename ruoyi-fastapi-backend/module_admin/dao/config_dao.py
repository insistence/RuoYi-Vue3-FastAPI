from datetime import datetime, time
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.config_do import SysConfig
from module_admin.entity.vo.config_vo import ConfigModel, ConfigPageQueryModel
from utils.page_util import PageUtil


class ConfigDao:
    """
    参数配置管理模块数据库操作层
    """

    @classmethod
    async def get_config_detail_by_id(cls, db: AsyncSession, config_id: int):
        """
        根据参数配置id获取参数配置详细信息

        :param db: orm对象
        :param config_id: 参数配置id
        :return: 参数配置信息对象
        """
        config_info = (await db.execute(select(SysConfig).where(SysConfig.config_id == config_id))).scalars().first()

        return config_info

    @classmethod
    async def get_config_detail_by_info(cls, db: AsyncSession, config: ConfigModel):
        """
        根据参数配置参数获取参数配置信息

        :param db: orm对象
        :param config: 参数配置参数对象
        :return: 参数配置信息对象
        """
        config_info = (
            (
                await db.execute(
                    select(SysConfig).where(
                        SysConfig.config_key == config.config_key if config.config_key else True,
                        SysConfig.config_value == config.config_value if config.config_value else True,
                    )
                )
            )
            .scalars()
            .first()
        )

        return config_info

    @classmethod
    async def get_config_list(cls, db: AsyncSession, query_object: ConfigPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取参数配置列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 参数配置列表信息对象
        """
        query = (
            select(SysConfig)
            .where(
                SysConfig.config_name.like(f'%{query_object.config_name}%') if query_object.config_name else True,
                SysConfig.config_key.like(f'%{query_object.config_key}%') if query_object.config_key else True,
                SysConfig.config_type == query_object.config_type if query_object.config_type else True,
                SysConfig.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
            )
            .order_by(SysConfig.config_id)
            .distinct()
        )
        config_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return config_list

    @classmethod
    async def add_config_dao(cls, db: AsyncSession, config: ConfigModel):
        """
        新增参数配置数据库操作

        :param db: orm对象
        :param config: 参数配置对象
        :return:
        """
        db_config = SysConfig(**config.model_dump())
        db.add(db_config)
        await db.flush()

        return db_config

    @classmethod
    async def edit_config_dao(cls, db: AsyncSession, config: dict):
        """
        编辑参数配置数据库操作

        :param db: orm对象
        :param config: 需要更新的参数配置字典
        :return:
        """
        await db.execute(update(SysConfig), [config])

    @classmethod
    async def delete_config_dao(cls, db: AsyncSession, config: ConfigModel):
        """
        删除参数配置数据库操作

        :param db: orm对象
        :param config: 参数配置对象
        :return:
        """
        await db.execute(delete(SysConfig).where(SysConfig.config_id.in_([config.config_id])))
