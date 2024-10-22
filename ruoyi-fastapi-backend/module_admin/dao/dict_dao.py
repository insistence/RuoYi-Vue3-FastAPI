from datetime import datetime, time
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.dict_do import SysDictType, SysDictData
from module_admin.entity.vo.dict_vo import DictDataModel, DictDataPageQueryModel, DictTypeModel, DictTypePageQueryModel
from utils.page_util import PageUtil
from utils.time_format_util import list_format_datetime


class DictTypeDao:
    """
    字典类型管理模块数据库操作层
    """

    @classmethod
    async def get_dict_type_detail_by_id(cls, db: AsyncSession, dict_id: int):
        """
        根据字典类型id获取字典类型详细信息

        :param db: orm对象
        :param dict_id: 字典类型id
        :return: 字典类型信息对象
        """
        dict_type_info = (await db.execute(select(SysDictType).where(SysDictType.dict_id == dict_id))).scalars().first()

        return dict_type_info

    @classmethod
    async def get_dict_type_detail_by_info(cls, db: AsyncSession, dict_type: DictTypeModel):
        """
        根据字典类型参数获取字典类型信息

        :param db: orm对象
        :param dict_type: 字典类型参数对象
        :return: 字典类型信息对象
        """
        dict_type_info = (
            (
                await db.execute(
                    select(SysDictType).where(
                        SysDictType.dict_type == dict_type.dict_type if dict_type.dict_type else True,
                        SysDictType.dict_name == dict_type.dict_name if dict_type.dict_name else True,
                    )
                )
            )
            .scalars()
            .first()
        )

        return dict_type_info

    @classmethod
    async def get_all_dict_type(cls, db: AsyncSession):
        """
        获取所有的字典类型信息

        :param db: orm对象
        :return: 字典类型信息列表对象
        """
        dict_type_info = (await db.execute(select(SysDictType))).scalars().all()

        return list_format_datetime(dict_type_info)

    @classmethod
    async def get_dict_type_list(cls, db: AsyncSession, query_object: DictTypePageQueryModel, is_page: bool = False):
        """
        根据查询参数获取字典类型列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典类型列表信息对象
        """
        query = (
            select(SysDictType)
            .where(
                SysDictType.dict_name.like(f'%{query_object.dict_name}%') if query_object.dict_name else True,
                SysDictType.dict_type.like(f'%{query_object.dict_type}%') if query_object.dict_type else True,
                SysDictType.status == query_object.status if query_object.status else True,
                SysDictType.create_time.between(
                    datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                    datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)),
                )
                if query_object.begin_time and query_object.end_time
                else True,
            )
            .order_by(SysDictType.dict_id)
            .distinct()
        )
        dict_type_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return dict_type_list

    @classmethod
    async def add_dict_type_dao(cls, db: AsyncSession, dict_type: DictTypeModel):
        """
        新增字典类型数据库操作

        :param db: orm对象
        :param dict_type: 字典类型对象
        :return:
        """
        db_dict_type = SysDictType(**dict_type.model_dump())
        db.add(db_dict_type)
        await db.flush()

        return db_dict_type

    @classmethod
    async def edit_dict_type_dao(cls, db: AsyncSession, dict_type: dict):
        """
        编辑字典类型数据库操作

        :param db: orm对象
        :param dict_type: 需要更新的字典类型字典
        :return:
        """
        await db.execute(update(SysDictType), [dict_type])

    @classmethod
    async def delete_dict_type_dao(cls, db: AsyncSession, dict_type: DictTypeModel):
        """
        删除字典类型数据库操作

        :param db: orm对象
        :param dict_type: 字典类型对象
        :return:
        """
        await db.execute(delete(SysDictType).where(SysDictType.dict_id.in_([dict_type.dict_id])))


class DictDataDao:
    """
    字典数据管理模块数据库操作层
    """

    @classmethod
    async def get_dict_data_detail_by_id(cls, db: AsyncSession, dict_code: int):
        """
        根据字典数据id获取字典数据详细信息

        :param db: orm对象
        :param dict_code: 字典数据id
        :return: 字典数据信息对象
        """
        dict_data_info = (
            (await db.execute(select(SysDictData).where(SysDictData.dict_code == dict_code))).scalars().first()
        )

        return dict_data_info

    @classmethod
    async def get_dict_data_detail_by_info(cls, db: AsyncSession, dict_data: DictDataModel):
        """
        根据字典数据参数获取字典数据信息

        :param db: orm对象
        :param dict_data: 字典数据参数对象
        :return: 字典数据信息对象
        """
        dict_data_info = (
            (
                await db.execute(
                    select(SysDictData).where(
                        SysDictData.dict_type == dict_data.dict_type,
                        SysDictData.dict_label == dict_data.dict_label,
                        SysDictData.dict_value == dict_data.dict_value,
                    )
                )
            )
            .scalars()
            .first()
        )

        return dict_data_info

    @classmethod
    async def get_dict_data_list(cls, db: AsyncSession, query_object: DictDataPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取字典数据列表信息

        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 字典数据列表信息对象
        """
        query = (
            select(SysDictData)
            .where(
                SysDictData.dict_type == query_object.dict_type if query_object.dict_type else True,
                SysDictData.dict_label.like(f'%{query_object.dict_label}%') if query_object.dict_label else True,
                SysDictData.status == query_object.status if query_object.status else True,
            )
            .order_by(SysDictData.dict_sort)
            .distinct()
        )
        dict_data_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)

        return dict_data_list

    @classmethod
    async def query_dict_data_list(cls, db: AsyncSession, dict_type: str):
        """
        根据查询参数获取字典数据列表信息

        :param db: orm对象
        :param dict_type: 字典类型
        :return: 字典数据列表信息对象
        """
        dict_data_list = (
            (
                await db.execute(
                    select(SysDictData)
                    .select_from(SysDictType)
                    .where(SysDictType.dict_type == dict_type if dict_type else True, SysDictType.status == '0')
                    .join(
                        SysDictData,
                        and_(SysDictType.dict_type == SysDictData.dict_type, SysDictData.status == '0'),
                        isouter=True,
                    )
                    .order_by(SysDictData.dict_sort)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        return dict_data_list

    @classmethod
    async def add_dict_data_dao(cls, db: AsyncSession, dict_data: DictDataModel):
        """
        新增字典数据数据库操作

        :param db: orm对象
        :param dict_data: 字典数据对象
        :return:
        """
        db_data_type = SysDictData(**dict_data.model_dump())
        db.add(db_data_type)
        await db.flush()

        return db_data_type

    @classmethod
    async def edit_dict_data_dao(cls, db: AsyncSession, dict_data: dict):
        """
        编辑字典数据数据库操作

        :param db: orm对象
        :param dict_data: 需要更新的字典数据字典
        :return:
        """
        await db.execute(update(SysDictData), [dict_data])

    @classmethod
    async def delete_dict_data_dao(cls, db: AsyncSession, dict_data: DictDataModel):
        """
        删除字典数据数据库操作

        :param db: orm对象
        :param dict_data: 字典数据对象
        :return:
        """
        await db.execute(delete(SysDictData).where(SysDictData.dict_code.in_([dict_data.dict_code])))

    @classmethod
    async def count_dict_data_dao(cls, db: AsyncSession, dict_type: str):
        """
        根据字典类型查询字典类型关联的字典数据数量

        :param db: orm对象
        :param dict_type: 字典类型
        :return: 字典类型关联的字典数据数量
        """
        dict_data_count = (
            await db.execute(select(func.count('*')).select_from(SysDictData).where(SysDictData.dict_type == dict_type))
        ).scalar()

        return dict_data_count
