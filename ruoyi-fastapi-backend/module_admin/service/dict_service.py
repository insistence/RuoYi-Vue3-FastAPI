from fastapi import Request
import json
from config.env import RedisInitKeyConfig
from module_admin.dao.dict_dao import *
from module_admin.entity.vo.common_vo import CrudResponseModel
from utils.common_util import export_list2excel, CamelCaseUtil


class DictTypeService:
    """
    字典类型管理模块服务层
    """

    @classmethod
    def get_dict_type_list_services(cls, query_db: Session, query_object: DictTypePageQueryModel, is_page: bool = False):
        """
        获取字典类型列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典类型列表信息对象
        """
        dict_type_list_result = DictTypeDao.get_dict_type_list(query_db, query_object, is_page)

        return dict_type_list_result

    @classmethod
    async def add_dict_type_services(cls, request: Request, query_db: Session, page_object: DictTypeModel):
        """
        新增字典类型信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 新增岗位对象
        :return: 新增字典类型校验结果
        """
        dict_type = DictTypeDao.get_dict_type_detail_by_info(query_db, DictTypeModel(dictType=page_object.dict_type))
        if dict_type:
            result = dict(is_success=False, message='字典类型已存在')
        else:
            try:
                DictTypeDao.add_dict_type_dao(query_db, page_object)
                query_db.commit()
                await DictDataService.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    async def edit_dict_type_services(cls, request: Request, query_db: Session, page_object: DictTypeModel):
        """
        编辑字典类型信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 编辑字典类型对象
        :return: 编辑字典类型校验结果
        """
        edit_dict_type = page_object.model_dump(exclude_unset=True)
        dict_type_info = cls.dict_type_detail_services(query_db, edit_dict_type.get('dict_id'))
        if dict_type_info:
            if dict_type_info.dict_type != page_object.dict_type or dict_type_info.dict_name != page_object.dict_name:
                dict_type = DictTypeDao.get_dict_type_detail_by_info(query_db, DictTypeModel(dictType=page_object.dict_type))
                if dict_type:
                    result = dict(is_success=False, message='字典类型已存在')
                    return CrudResponseModel(**result)
            try:
                if dict_type_info.dict_type != page_object.dict_type:
                    query_dict_data = DictDataModel(dictType=dict_type_info.dict_type)
                    dict_data_list = DictDataDao.get_dict_data_list(query_db, query_dict_data)
                    for dict_data in dict_data_list:
                        edit_dict_data = DictDataModel(dictCode=dict_data.dict_code, dictType=page_object.dict_type, updateBy=page_object.update_by).model_dump(exclude_unset=True)
                        DictDataDao.edit_dict_data_dao(query_db, edit_dict_data)
                DictTypeDao.edit_dict_type_dao(query_db, edit_dict_type)
                query_db.commit()
                await DictDataService.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='字典类型不存在')

        return CrudResponseModel(**result)

    @classmethod
    async def delete_dict_type_services(cls, request: Request, query_db: Session, page_object: DeleteDictTypeModel):
        """
        删除字典类型信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 删除字典类型对象
        :return: 删除字典类型校验结果
        """
        if page_object.dict_ids.split(','):
            dict_id_list = page_object.dict_ids.split(',')
            try:
                for dict_id in dict_id_list:
                    DictTypeDao.delete_dict_type_dao(query_db, DictTypeModel(dictId=dict_id))
                query_db.commit()
                await DictDataService.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入字典类型id为空')
        return CrudResponseModel(**result)

    @classmethod
    def dict_type_detail_services(cls, query_db: Session, dict_id: int):
        """
        获取字典类型详细信息service
        :param query_db: orm对象
        :param dict_id: 字典类型id
        :return: 字典类型id对应的信息
        """
        dict_type = DictTypeDao.get_dict_type_detail_by_id(query_db, dict_id=dict_id)
        result = DictTypeModel(**CamelCaseUtil.transform_result(dict_type))

        return result

    @staticmethod
    def export_dict_type_list_services(dict_type_list: List):
        """
        导出字典类型信息service
        :param dict_type_list: 字典信息列表
        :return: 字典信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "dictId": "字典编号",
            "dictName": "字典名称",
            "dictType": "字典类型",
            "status": "状态",
            "createBy": "创建者",
            "createTime": "创建时间",
            "updateBy": "更新者",
            "updateTime": "更新时间",
            "remark": "备注",
        }

        data = dict_type_list

        for item in data:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in data]
        binary_data = export_list2excel(new_data)

        return binary_data

    @classmethod
    async def refresh_sys_dict_services(cls, request: Request, query_db: Session):
        """
        刷新字典缓存信息service
        :param request: Request对象
        :param query_db: orm对象
        :return: 刷新字典缓存校验结果
        """
        await DictDataService.init_cache_sys_dict_services(query_db, request.app.state.redis)
        result = dict(is_success=True, message='刷新成功')

        return CrudResponseModel(**result)


class DictDataService:
    """
    字典数据管理模块服务层
    """

    @classmethod
    def get_dict_data_list_services(cls, query_db: Session, query_object: DictDataPageQueryModel, is_page: bool = False):
        """
        获取字典数据列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典数据列表信息对象
        """
        dict_data_list_result = DictDataDao.get_dict_data_list(query_db, query_object, is_page)

        return dict_data_list_result

    @classmethod
    def query_dict_data_list_services(cls, query_db: Session, dict_type: str):
        """
        获取字典数据列表信息service
        :param query_db: orm对象
        :param dict_type: 字典类型
        :return: 字典数据列表信息对象
        """
        dict_data_list_result = DictDataDao.query_dict_data_list(query_db, dict_type)

        return dict_data_list_result

    @classmethod
    async def init_cache_sys_dict_services(cls, query_db: Session, redis):
        """
        应用初始化：获取所有字典类型对应的字典数据信息并缓存service
        :param query_db: orm对象
        :param redis: redis对象
        :return:
        """
        # 获取以sys_dict:开头的键列表
        keys = await redis.keys(f"{RedisInitKeyConfig.SYS_DICT.get('key')}:*")
        # 删除匹配的键
        if keys:
            await redis.delete(*keys)
        dict_type_all = DictTypeDao.get_all_dict_type(query_db)
        for dict_type_obj in [item for item in dict_type_all if item.status == '0']:
            dict_type = dict_type_obj.dict_type
            dict_data_list = DictDataDao.query_dict_data_list(query_db, dict_type)
            dict_data = [CamelCaseUtil.transform_result(row) for row in dict_data_list if row]
            await redis.set(f"{RedisInitKeyConfig.SYS_DICT.get('key')}:{dict_type}", json.dumps(dict_data, ensure_ascii=False, default=str))

    @classmethod
    async def query_dict_data_list_from_cache_services(cls, redis, dict_type: str):
        """
        从缓存获取字典数据列表信息service
        :param redis: redis对象
        :param dict_type: 字典类型
        :return: 字典数据列表信息对象
        """
        result = []
        dict_data_list_result = await redis.get(f"{RedisInitKeyConfig.SYS_DICT.get('key')}:{dict_type}")
        if dict_data_list_result:
            result = json.loads(dict_data_list_result)

        return CamelCaseUtil.transform_result(result)

    @classmethod
    async def add_dict_data_services(cls, request: Request, query_db: Session, page_object: DictDataModel):
        """
        新增字典数据信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 新增岗位对象
        :return: 新增字典数据校验结果
        """
        dict_data = DictDataDao.get_dict_data_detail_by_info(query_db, page_object)
        if dict_data:
            result = dict(is_success=False, message='字典数据已存在')
        else:
            try:
                DictDataDao.add_dict_data_dao(query_db, page_object)
                query_db.commit()
                await cls.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    async def edit_dict_data_services(cls, request: Request, query_db: Session, page_object: DictDataModel):
        """
        编辑字典数据信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 编辑字典数据对象
        :return: 编辑字典数据校验结果
        """
        edit_data_type = page_object.model_dump(exclude_unset=True)
        dict_data_info = cls.dict_data_detail_services(query_db, edit_data_type.get('dict_code'))
        if dict_data_info:
            if dict_data_info.dict_type != page_object.dict_type or dict_data_info.dict_label != page_object.dict_label or dict_data_info.dict_value != page_object.dict_value:
                dict_data = DictDataDao.get_dict_data_detail_by_info(query_db, page_object)
                if dict_data:
                    result = dict(is_success=False, message='字典数据已存在')
                    return CrudResponseModel(**result)
            try:
                DictDataDao.edit_dict_data_dao(query_db, edit_data_type)
                query_db.commit()
                await cls.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='字典数据不存在')

        return CrudResponseModel(**result)

    @classmethod
    async def delete_dict_data_services(cls, request: Request, query_db: Session, page_object: DeleteDictDataModel):
        """
        删除字典数据信息service
        :param request: Request对象
        :param query_db: orm对象
        :param page_object: 删除字典数据对象
        :return: 删除字典数据校验结果
        """
        if page_object.dict_codes.split(','):
            dict_code_list = page_object.dict_codes.split(',')
            try:
                for dict_code in dict_code_list:
                    DictDataDao.delete_dict_data_dao(query_db, DictDataModel(dictCode=dict_code))
                query_db.commit()
                await cls.init_cache_sys_dict_services(query_db, request.app.state.redis)
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入字典数据id为空')
        return CrudResponseModel(**result)

    @classmethod
    def dict_data_detail_services(cls, query_db: Session, dict_code: int):
        """
        获取字典数据详细信息service
        :param query_db: orm对象
        :param dict_code: 字典数据id
        :return: 字典数据id对应的信息
        """
        dict_data = DictDataDao.get_dict_data_detail_by_id(query_db, dict_code=dict_code)
        result = DictDataModel(**CamelCaseUtil.transform_result(dict_data))

        return result

    @staticmethod
    def export_dict_data_list_services(dict_data_list: List):
        """
        导出字典数据信息service
        :param dict_data_list: 字典数据信息列表
        :return: 字典数据信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "dictCode": "字典编码",
            "dictSort": "字典标签",
            "dictLabel": "字典键值",
            "dictValue": "字典排序",
            "dictType": "字典类型",
            "cssClass": "样式属性",
            "listClass": "表格回显样式",
            "isDefault": "是否默认",
            "status": "状态",
            "createBy": "创建者",
            "createTime": "创建时间",
            "updateBy": "更新者",
            "updateTime": "更新时间",
            "remark": "备注",
        }

        data = dict_data_list

        for item in data:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
            if item.get('isDefault') == 'Y':
                item['isDefault'] = '是'
            else:
                item['isDefault'] = '否'
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in data]
        binary_data = export_list2excel(new_data)

        return binary_data
