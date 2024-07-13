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
    def is_http(cls, link: str):
        """
        判断是否为http(s)://开头

        :param link: 链接
        :return: 是否为http(s)://开头
        """
        return link.startswith(CommonConstant.HTTP) or link.startswith(CommonConstant.HTTPS)
