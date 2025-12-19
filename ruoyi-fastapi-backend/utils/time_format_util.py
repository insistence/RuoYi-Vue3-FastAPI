from copy import deepcopy
from datetime import date, datetime
from typing import Any, Union

from dateutil.parser import parse


def object_format_datetime(obj: Any) -> Any:
    """
    :param obj: 输入一个对象
    :return:对目标对象所有datetime类型的属性格式化
    """
    for attr in dir(obj):
        value = getattr(obj, attr)
        if isinstance(value, datetime):
            setattr(obj, attr, value.strftime('%Y-%m-%d %H:%M:%S'))
    return obj


def list_format_datetime(lst: list[Any]) -> list[Any]:
    """
    :param lst: 输入一个嵌套对象的列表
    :return: 对目标列表中所有对象的datetime类型的属性格式化
    """
    for obj in lst:
        for attr in dir(obj):
            value = getattr(obj, attr)
            if isinstance(value, datetime):
                setattr(obj, attr, value.strftime('%Y-%m-%d %H:%M:%S'))
    return lst


def format_datetime_dict_list(dicts: list[dict]) -> list[dict]:
    """
    递归遍历嵌套字典，并将 datetime 值转换为字符串格式

    :param dicts: 输入一个嵌套字典的列表
    :return: 对目标列表中所有字典的datetime类型的属性格式化
    """
    result = []

    for item in dicts:
        new_item = {}
        for k, v in item.items():
            if isinstance(v, dict):
                # 递归遍历子字典
                new_item[k] = format_datetime_dict_list([v])[0]
            elif isinstance(v, datetime):
                # 如果值是 datetime 类型，则格式化为字符串
                new_item[k] = v.strftime('%Y-%m-%d %H:%M:%S')
            else:
                # 否则保留原始值
                new_item[k] = v
        result.append(new_item)

    return result


class TimeFormatUtil:
    """
    时间格式化工具类
    """

    @classmethod
    def format_time(cls, time_info: Union[str, datetime], fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
        """
        格式化时间字符串或datetime对象为指定格式

        :param time_info: 时间字符串或datetime对象
        :param fmt: 格式化格式，默认为'%Y-%m-%d %H:%M:%S'
        :return: 格式化后的时间字符串
        """
        if isinstance(time_info, datetime):
            format_date = time_info.strftime(fmt)
        else:
            try:
                date = parse(time_info)
                format_date = date.strftime(fmt)
            except Exception:
                format_date = time_info

        return format_date

    @classmethod
    def parse_date(cls, time_str: str) -> Union[date, str]:
        """
        解析时间字符串提取日期部分

        :param time_str: 时间字符串
        :return: 日期部分
        """
        try:
            dt = parse(time_str)
            return dt.date()
        except Exception:
            return time_str

    @classmethod
    def format_time_dict(cls, time_dict: dict, fmt: str = '%Y-%m-%d %H:%M:%S') -> dict:
        """
        格式化时间字典

        :param time_dict: 时间字典
        :param fmt: 格式化格式，默认为'%Y-%m-%d %H:%M:%S'
        :return: 格式化后的时间字典
        """
        copy_time_dict = deepcopy(time_dict)
        for k, v in copy_time_dict.items():
            if isinstance(v, (str, datetime)):
                copy_time_dict[k] = cls.format_time(v, fmt)
            elif isinstance(v, dict):
                copy_time_dict[k] = cls.format_time_dict(v, fmt)
            elif isinstance(v, list):
                copy_time_dict[k] = cls.format_time_list(v, fmt)
            else:
                copy_time_dict[k] = v

        return copy_time_dict

    @classmethod
    def format_time_list(cls, time_list: list, fmt: str = '%Y-%m-%d %H:%M:%S') -> list:
        """
        格式化时间列表

        :param time_list: 时间列表
        :param fmt: 格式化格式，默认为'%Y-%m-%d %H:%M:%S'
        :return: 格式化后的时间列表
        """
        format_time_list = []
        for item in time_list:
            if isinstance(item, (str, datetime)):
                format_item = cls.format_time(item, fmt)
            elif isinstance(item, dict):
                format_item = cls.format_time_dict(item, fmt)
            elif isinstance(item, list):
                format_item = cls.format_time_list(item, fmt)
            else:
                format_item = item

            format_time_list.append(format_item)

        return format_time_list
