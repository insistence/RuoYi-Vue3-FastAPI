from sqlalchemy import and_
from sqlalchemy.orm import Session
from module_admin.entity.do.dict_do import SysDictType, SysDictData
from module_admin.entity.vo.dict_vo import *
from utils.time_format_util import list_format_datetime
from utils.page_util import PageUtil
from datetime import datetime, time


class DictTypeDao:
    """
    字典类型管理模块数据库操作层
    """

    @classmethod
    def get_dict_type_detail_by_id(cls, db: Session, dict_id: int):
        """
        根据字典类型id获取字典类型详细信息
        :param db: orm对象
        :param dict_id: 字典类型id
        :return: 字典类型信息对象
        """
        dict_type_info = db.query(SysDictType) \
            .filter(SysDictType.dict_id == dict_id) \
            .first()

        return dict_type_info

    @classmethod
    def get_dict_type_detail_by_info(cls, db: Session, dict_type: DictTypeModel):
        """
        根据字典类型参数获取字典类型信息
        :param db: orm对象
        :param dict_type: 字典类型参数对象
        :return: 字典类型信息对象
        """
        dict_type_info = db.query(SysDictType) \
            .filter(SysDictType.dict_type == dict_type.dict_type if dict_type.dict_type else True,
                    SysDictType.dict_name == dict_type.dict_name if dict_type.dict_name else True) \
            .first()

        return dict_type_info

    @classmethod
    def get_all_dict_type(cls, db: Session):
        """
        获取所有的字典类型信息
        :param db: orm对象
        :return: 字典类型信息列表对象
        """
        dict_type_info = db.query(SysDictType).all()

        return list_format_datetime(dict_type_info)

    @classmethod
    def get_dict_type_list(cls, db: Session, query_object: DictTypePageQueryModel, is_page: bool = False):
        """
        根据查询参数获取字典类型列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典类型列表信息对象
        """
        query = db.query(SysDictType) \
            .filter(SysDictType.dict_name.like(f'%{query_object.dict_name}%') if query_object.dict_name else True,
                    SysDictType.dict_type.like(f'%{query_object.dict_type}%') if query_object.dict_type else True,
                    SysDictType.status == query_object.status if query_object.status else True,
                    SysDictType.create_time.between(
                        datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                        datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)))
                    if query_object.begin_time and query_object.end_time else True
                    ) \
            .distinct()
        dict_type_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return dict_type_list

    @classmethod
    def add_dict_type_dao(cls, db: Session, dict_type: DictTypeModel):
        """
        新增字典类型数据库操作
        :param db: orm对象
        :param dict_type: 字典类型对象
        :return:
        """
        db_dict_type = SysDictType(**dict_type.dict())
        db.add(db_dict_type)
        db.flush()

        return db_dict_type

    @classmethod
    def edit_dict_type_dao(cls, db: Session, dict_type: dict):
        """
        编辑字典类型数据库操作
        :param db: orm对象
        :param dict_type: 需要更新的字典类型字典
        :return:
        """
        db.query(SysDictType) \
            .filter(SysDictType.dict_id == dict_type.get('dict_id')) \
            .update(dict_type)

    @classmethod
    def delete_dict_type_dao(cls, db: Session, dict_type: DictTypeModel):
        """
        删除字典类型数据库操作
        :param db: orm对象
        :param dict_type: 字典类型对象
        :return:
        """
        db.query(SysDictType) \
            .filter(SysDictType.dict_id == dict_type.dict_id) \
            .delete()


class DictDataDao:
    """
    字典数据管理模块数据库操作层
    """

    @classmethod
    def get_dict_data_detail_by_id(cls, db: Session, dict_code: int):
        """
        根据字典数据id获取字典数据详细信息
        :param db: orm对象
        :param dict_code: 字典数据id
        :return: 字典数据信息对象
        """
        dict_data_info = db.query(SysDictData) \
            .filter(SysDictData.dict_code == dict_code) \
            .first()

        return dict_data_info

    @classmethod
    def get_dict_data_detail_by_info(cls, db: Session, dict_data: DictDataModel):
        """
        根据字典数据参数获取字典数据信息
        :param db: orm对象
        :param dict_data: 字典数据参数对象
        :return: 字典数据信息对象
        """
        dict_data_info = db.query(SysDictData) \
            .filter(SysDictData.dict_type == dict_data.dict_type if dict_data.dict_type else True,
                    SysDictData.dict_label == dict_data.dict_label if dict_data.dict_label else True,
                    SysDictData.dict_value == dict_data.dict_value if dict_data.dict_value else True) \
            .first()

        return dict_data_info

    @classmethod
    def get_dict_data_list(cls, db: Session, query_object: DictDataPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取字典数据列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典数据列表信息对象
        """
        query = db.query(SysDictData) \
            .filter(SysDictData.dict_type == query_object.dict_type if query_object.dict_type else True,
                    SysDictData.dict_label.like(f'%{query_object.dict_label}%') if query_object.dict_label else True,
                    SysDictData.status == query_object.status if query_object.status else True
                    ) \
            .order_by(SysDictData.dict_sort) \
            .distinct()
        dict_data_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return dict_data_list

    @classmethod
    def query_dict_data_list(cls, db: Session, dict_type: str):
        """
        根据查询参数获取字典数据列表信息
        :param db: orm对象
        :param dict_type: 字典类型
        :return: 字典数据列表信息对象
        """
        dict_data_list = db.query(SysDictData).select_from(SysDictType) \
            .filter(SysDictType.dict_type == dict_type if dict_type else True, SysDictType.status == 0) \
            .outerjoin(SysDictData, and_(SysDictType.dict_type == SysDictData.dict_type, SysDictData.status == 0)) \
            .order_by(SysDictData.dict_sort) \
            .distinct().all()

        return dict_data_list

    @classmethod
    def add_dict_data_dao(cls, db: Session, dict_data: DictDataModel):
        """
        新增字典数据数据库操作
        :param db: orm对象
        :param dict_data: 字典数据对象
        :return:
        """
        db_data_type = SysDictData(**dict_data.dict())
        db.add(db_data_type)
        db.flush()

        return db_data_type

    @classmethod
    def edit_dict_data_dao(cls, db: Session, dict_data: dict):
        """
        编辑字典数据数据库操作
        :param db: orm对象
        :param dict_data: 需要更新的字典数据字典
        :return:
        """
        db.query(SysDictData) \
            .filter(SysDictData.dict_code == dict_data.get('dict_code')) \
            .update(dict_data)

    @classmethod
    def delete_dict_data_dao(cls, db: Session, dict_data: DictDataModel):
        """
        删除字典数据数据库操作
        :param db: orm对象
        :param dict_data: 字典数据对象
        :return:
        """
        db.query(SysDictData) \
            .filter(SysDictData.dict_code == dict_data.dict_code) \
            .delete()
