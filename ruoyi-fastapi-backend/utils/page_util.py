import math
from typing import Any

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from utils.common_util import CamelCaseUtil


class PageUtil:
    """
    分页工具类
    """

    @classmethod
    def get_page_obj(cls, data_list: list, page_num: int, page_size: int) -> PageModel:
        """
        输入数据列表data_list和分页信息，返回分页数据列表结果

        :param data_list: 原始数据列表
        :param page_num: 当前页码
        :param page_size: 当前页面数据量
        :return: 分页数据对象
        """
        # 计算起始索引和结束索引
        start = (page_num - 1) * page_size
        end = page_num * page_size

        # 根据计算得到的起始索引和结束索引对数据列表进行切片
        paginated_data = data_list[start:end]
        has_next = math.ceil(len(data_list) / page_size) > page_num

        result = PageModel[Any](
            rows=paginated_data, pageNum=page_num, pageSize=page_size, total=len(data_list), hasNext=has_next
        )

        return result

    @classmethod
    async def paginate(
        cls, db: AsyncSession, query: Select, page_num: int, page_size: int, is_page: bool = False
    ) -> PageModel | list[dict[str, Any] | list[dict[Any, Any]]]:
        """
        输入查询语句和分页信息，返回分页数据列表结果

        :param db: orm对象
        :param query: sqlalchemy查询语句
        :param page_num: 当前页码
        :param page_size: 当前页面数据量
        :param is_page: 是否开启分页
        :return: 分页数据对象
        """
        if is_page:
            total = (await db.execute(select(func.count('*')).select_from(query.subquery()))).scalar()
            query_result = await db.execute(query.offset((page_num - 1) * page_size).limit(page_size))
            paginated_data: list[Row] = []
            for row in query_result:
                if row and len(row) == 1:
                    paginated_data.append(row[0])
                else:
                    paginated_data.append(row)
            has_next = math.ceil(total / page_size) > page_num
            result = PageModel[Any](
                rows=CamelCaseUtil.transform_result(paginated_data),
                pageNum=page_num,
                pageSize=page_size,
                total=total,
                hasNext=has_next,
            )
        else:
            query_result = await db.execute(query)
            no_paginated_data: list[Row] = []
            for row in query_result:
                if row and len(row) == 1:
                    no_paginated_data.append(row[0])
                else:
                    no_paginated_data.append(row)
            result = CamelCaseUtil.transform_result(no_paginated_data)

        return result


def get_page_obj(data_list: list, page_num: int, page_size: int) -> PageModel:
    """
    输入数据列表data_list和分页信息，返回分页数据列表结果

    :param data_list: 原始数据列表
    :param page_num: 当前页码
    :param page_size: 当前页面数据量
    :return: 分页数据对象
    """
    # 计算起始索引和结束索引
    start = (page_num - 1) * page_size
    end = page_num * page_size

    # 根据计算得到的起始索引和结束索引对数据列表进行切片
    paginated_data = data_list[start:end]
    has_next = math.ceil(len(data_list) / page_size) > page_num

    result = PageModel[Any](
        rows=paginated_data, pageNum=page_num, pageSize=page_size, total=len(data_list), hasNext=has_next
    )

    return result
