from fastapi import Request
from config.env import RedisInitKeyConfig
from module_admin.dao.config_dao import *
from module_admin.entity.vo.common_vo import CrudResponseModel
from utils.common_util import export_list2excel, CamelCaseUtil


class ConfigService:
    """
    参数配置管理模块服务层
    """

    @classmethod
    def get_config_list_services(cls, query_db: Session, query_object: ConfigPageQueryModel, is_page: bool = False):
        """
        获取参数配置列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 参数配置列表信息对象
        """
        config_list_result = ConfigDao.get_config_list(query_db, query_object, is_page)

        return config_list_result

    @classmethod
    async def init_cache_sys_config_services(cls, query_db: Session, redis):
        """
        应用初始化：获取所有参数配置对应的键值对信息并缓存service
        :param query_db: orm对象
        :param redis: redis对象
        :return:
        """
        # 获取以sys_config:开头的键列表
        keys = await redis.keys(f"{RedisInitKeyConfig.SYS_CONFIG.get('key')}:*")
        # 删除匹配的键
        if keys:
            await redis.delete(*keys)
        config_all = ConfigDao.get_config_list(query_db, ConfigPageQueryModel(**dict()), is_page=False)
        for config_obj in config_all:
            if config_obj.get('configType') == 'Y':
                await redis.set(f"{RedisInitKeyConfig.SYS_CONFIG.get('key')}:{config_obj.get('configKey')}", config_obj.get('configValue'))

    @classmethod
    async def query_config_list_from_cache_services(cls, redis, config_key: str):
        """
        从缓存获取参数键名对应值service
        :param redis: redis对象
        :param config_key: 参数键名
        :return: 参数键名对应值
        """
        result = await redis.get(f"{RedisInitKeyConfig.SYS_CONFIG.get('key')}:{config_key}")

        return result

    @classmethod
    async def add_config_services(cls, request: Request, query_db: Session, page_object: ConfigModel):
        """
        新增参数配置信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 新增参数配置对象
        :return: 新增参数配置校验结果
        """
        config = ConfigDao.get_config_detail_by_info(query_db, ConfigModel(configKey=page_object.config_key))
        if config:
            result = dict(is_success=False, message='参数键名已存在')
        else:
            try:
                ConfigDao.add_config_dao(query_db, page_object)
                query_db.commit()
                await cls.init_cache_sys_config_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    async def edit_config_services(cls, request: Request, query_db: Session, page_object: ConfigModel):
        """
        编辑参数配置信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 编辑参数配置对象
        :return: 编辑参数配置校验结果
        """
        edit_config = page_object.model_dump(exclude_unset=True)
        config_info = cls.config_detail_services(query_db, edit_config.get('config_id'))
        if config_info:
            if config_info.config_key != page_object.config_key or config_info.config_value != page_object.config_value:
                config = ConfigDao.get_config_detail_by_info(query_db, page_object)
                if config:
                    result = dict(is_success=False, message='参数配置已存在')
                    return CrudResponseModel(**result)
            try:
                ConfigDao.edit_config_dao(query_db, edit_config)
                query_db.commit()
                await cls.init_cache_sys_config_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='参数配置不存在')

        return CrudResponseModel(**result)

    @classmethod
    async def delete_config_services(cls, request: Request, query_db: Session, page_object: DeleteConfigModel):
        """
        删除参数配置信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 删除参数配置对象
        :return: 删除参数配置校验结果
        """
        if page_object.config_ids.split(','):
            config_id_list = page_object.config_ids.split(',')
            try:
                for config_id in config_id_list:
                    ConfigDao.delete_config_dao(query_db, ConfigModel(configId=config_id))
                query_db.commit()
                await cls.init_cache_sys_config_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入字典数据id为空')
        return CrudResponseModel(**result)

    @classmethod
    def config_detail_services(cls, query_db: Session, config_id: int):
        """
        获取参数配置详细信息service
        :param query_db: orm对象
        :param config_id: 参数配置id
        :return: 参数配置id对应的信息
        """
        config = ConfigDao.get_config_detail_by_id(query_db, config_id=config_id)
        result = ConfigModel(**CamelCaseUtil.transform_result(config))

        return result

    @staticmethod
    def export_config_list_services(config_list: List):
        """
        导出参数配置信息service
        :param config_list: 参数配置信息列表
        :return: 参数配置信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "configId": "参数主键",
            "configName": "参数名称",
            "configKey": "参数键名",
            "configValue": "参数键值",
            "configType": "系统内置",
            "createBy": "创建者",
            "createTime": "创建时间",
            "updateBy": "更新者",
            "updateTime": "更新时间",
            "remark": "备注",
        }

        data = config_list

        for item in data:
            if item.get('configType') == 'Y':
                item['configType'] = '是'
            else:
                item['configType'] = '否'
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in data]
        binary_data = export_list2excel(new_data)

        return binary_data

    @classmethod
    async def refresh_sys_config_services(cls, request: Request, query_db: Session):
        """
        刷新字典缓存信息service
        :param request: Request对象
        :param query_db: orm对象
        :return: 刷新字典缓存校验结果
        """
        await cls.init_cache_sys_config_services(query_db, request.app.state.redis)
        result = dict(is_success=True, message='刷新成功')

        return CrudResponseModel(**result)
