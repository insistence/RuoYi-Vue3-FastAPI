import os
import random
from datetime import datetime
from fastapi import UploadFile
from config.env import UploadConfig


class UploadUtil:
    """
    上传工具类
    """

    @classmethod
    def generate_random_number(cls):
        """
        生成3位数字构成的字符串

        :return: 3位数字构成的字符串
        """
        random_number = random.randint(1, 999)

        return f'{random_number:03}'

    @classmethod
    def check_file_exists(cls, filepath: str):
        """
        检查文件是否存在

        :param filepath: 文件路径
        :return: 校验结果
        """
        return os.path.exists(filepath)

    @classmethod
    def check_file_extension(cls, file: UploadFile):
        """
        检查文件后缀是否合法

        :param file: 文件对象
        :return: 校验结果
        """
        file_extension = file.filename.rsplit('.', 1)[-1]
        if file_extension in UploadConfig.DEFAULT_ALLOWED_EXTENSION:
            return True
        return False

    @classmethod
    def check_file_timestamp(cls, filename: str):
        """
        校验文件时间戳是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        timestamp = filename.rsplit('.', 1)[0].split('_')[-1].split(UploadConfig.UPLOAD_MACHINE)[0]
        try:
            datetime.strptime(timestamp, '%Y%m%d%H%M%S')
            return True
        except ValueError:
            return False

    @classmethod
    def check_file_machine(cls, filename: str):
        """
        校验文件机器码是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        if filename.rsplit('.', 1)[0][-4] == UploadConfig.UPLOAD_MACHINE:
            return True
        return False

    @classmethod
    def check_file_random_code(cls, filename: str):
        """
        校验文件随机码是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        valid_code_list = [f'{i:03}' for i in range(1, 999)]
        if filename.rsplit('.', 1)[0][-3:] in valid_code_list:
            return True
        return False

    @classmethod
    def generate_file(cls, filepath: str):
        """
        根据文件生成二进制数据

        :param filepath: 文件路径
        :yield: 二进制数据
        """
        with open(filepath, 'rb') as response_file:
            yield from response_file

    @classmethod
    def delete_file(cls, filepath: str):
        """
        根据文件路径删除对应文件

        :param filepath: 文件路径
        """
        os.remove(filepath)
