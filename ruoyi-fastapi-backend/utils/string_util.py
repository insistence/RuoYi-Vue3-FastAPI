from typing import Dict, List
from config.constant import CommonConstant


class StringUtil:
    """
    字符串工具类
    """

    @classmethod
    def is_blank(cls, string: str) -> bool:
        """
        校验字符串是否为''或全空格

        :param string: 需要校验的字符串
        :return: 校验结果
        """
        if string is None:
            return False
        str_len = len(string)
        if str_len == 0:
            return True
        else:
            for i in range(str_len):
                if string[i] != ' ':
                    return False
            return True

    @classmethod
    def is_empty(cls, string) -> bool:
        """
        校验字符串是否为''或None

        :param string: 需要校验的字符串
        :return: 校验结果
        """
        return string is None or len(string) == 0

    @classmethod
    def is_not_empty(cls, string: str) -> bool:
        """
        校验字符串是否不是''和None

        :param string: 需要校验的字符串
        :return: 校验结果
        """
        return not cls.is_empty(string)

    @classmethod
    def is_http(cls, link: str):
        """
        判断是否为http(s)://开头

        :param link: 链接
        :return: 是否为http(s)://开头
        """
        return link.startswith(CommonConstant.HTTP) or link.startswith(CommonConstant.HTTPS)

    @classmethod
    def contains_ignore_case(cls, search_str: str, compare_str: str):
        """
        查找指定字符串是否包含指定字符串同时忽略大小写

        :param search_str: 查找的字符串
        :param compare_str: 比对的字符串
        :return: 查找结果
        """
        if compare_str and search_str:
            return compare_str.lower() in search_str.lower()
        return False

    @classmethod
    def contains_any_ignore_case(cls, search_str: str, compare_str_list: List[str]):
        """
        查找指定字符串是否包含指定字符串列表中的任意一个字符串同时忽略大小写

        :param search_str: 查找的字符串
        :param compare_str_list: 比对的字符串列表
        :return: 查找结果
        """
        if search_str and compare_str_list:
            return any([cls.contains_ignore_case(search_str, compare_str) for compare_str in compare_str_list])
        return False

    @classmethod
    def equals_ignore_case(cls, search_str: str, compare_str: str):
        """
        比较两个字符串是否相等同时忽略大小写

        :param search_str: 查找的字符串
        :param compare_str: 比对的字符串
        :return: 比较结果
        """
        if search_str and compare_str:
            return search_str.lower() == compare_str.lower()
        return False

    @classmethod
    def equals_any_ignore_case(cls, search_str: str, compare_str_list: List[str]):
        """
        比较指定字符串是否与指定字符串列表中的任意一个字符串相等同时忽略大小写

        :param search_str: 查找的字符串
        :param compare_str_list: 比对的字符串列表
        :return: 比较结果
        """
        if search_str and compare_str_list:
            return any([cls.equals_ignore_case(search_str, compare_str) for compare_str in compare_str_list])
        return False

    @classmethod
    def startswith_case(cls, search_str: str, compare_str: str):
        """
        查找指定字符串是否以指定字符串开头

        :param search_str: 查找的字符串
        :param compare_str: 比对的字符串
        :return: 查找结果
        """
        if compare_str and search_str:
            return search_str.startswith(compare_str)
        return False

    @classmethod
    def startswith_any_case(cls, search_str: str, compare_str_list: List[str]):
        """
        查找指定字符串是否以指定字符串列表中的任意一个字符串开头

        :param search_str: 查找的字符串
        :param compare_str_list: 比对的字符串列表
        :return: 查找结果
        """
        if search_str and compare_str_list:
            return any([cls.startswith_case(search_str, compare_str) for compare_str in compare_str_list])
        return False

    @classmethod
    def convert_to_camel_case(cls, name: str) -> str:
        """
        将下划线大写方式命名的字符串转换为驼峰式。如果转换前的下划线大写方式命名的字符串为空，则返回空字符串

        :param name: 转换前的下划线大写方式命名的字符串
        :return: 转换后的驼峰式命名的字符串
        """
        if not name:
            return ''
        if '_' not in name:
            return name[0].upper() + name[1:]
        parts = name.split('_')
        result = []
        for part in parts:
            if not part:
                continue
            result.append(part[0].upper() + part[1:].lower())
        return ''.join(result)

    @classmethod
    def get_mapping_value_by_key_ignore_case(cls, mapping: Dict[str, str], key: str) -> str:
        """
        根据忽略大小写的键获取字典中的对应的值

        param mapping: 字典
        param key: 字典的键
        :return: 字典键对应的值
        """
        for k, v in mapping.items():
            if key.lower() == k.lower():
                return v
        
        return ''
