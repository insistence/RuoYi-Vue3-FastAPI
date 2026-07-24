import os
import random
import re
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote

import aiofiles
from fastapi import UploadFile

from config.env import UploadConfig


class FilePathUtil:
    """
    文件路径安全校验工具类
    """

    @classmethod
    def resolve_path_within_root(cls, root: str | os.PathLike[str], untrusted_path: str) -> Path:
        """
        将不可信相对路径解析为根目录内路径

        :param root: 文件根目录
        :param untrusted_path: 不可信文件路径
        :return: 根目录内的路径
        """
        if not untrusted_path or '\x00' in untrusted_path:
            raise ValueError('文件路径不能为空')

        normalized_path = untrusted_path.replace('\\', '/')
        windows_path = PureWindowsPath(untrusted_path)
        posix_path = PurePosixPath(normalized_path)
        path_parts = normalized_path.split('/')

        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or posix_path.is_absolute()
            or any(part in {'', '.', '..'} for part in path_parts)
        ):
            raise ValueError('文件路径不合法')

        root_path = Path(root).resolve()
        candidate_path = root_path.joinpath(*path_parts).resolve()
        try:
            candidate_path.relative_to(root_path)
        except ValueError as exc:
            raise ValueError('文件路径超出允许目录') from exc

        return candidate_path

    @classmethod
    def resolve_file_within_root(cls, root: str | os.PathLike[str], untrusted_path: str) -> Path:
        """
        将不可信相对路径解析为根目录内已存在的普通文件

        :param root: 文件根目录
        :param untrusted_path: 不可信文件路径
        :return: 根目录内的文件路径
        """
        candidate_path = cls.resolve_path_within_root(root, untrusted_path)

        if not candidate_path.is_file():
            raise FileNotFoundError('文件不存在')
        return candidate_path


class UploadUtil:
    """
    上传工具类
    """

    GENERATED_FILE_INFO_LENGTH = 18
    MAX_RANDOM_CODE = 999

    @classmethod
    def generate_random_number(cls) -> str:
        """
        生成3位数字构成的字符串

        :return: 3位数字构成的字符串
        """
        random_number = random.randint(1, 999)

        return f'{random_number:03}'

    @classmethod
    def check_file_exists(cls, filepath: str | os.PathLike[str]) -> bool:
        """
        检查文件是否存在

        :param filepath: 文件路径
        :return: 校验结果
        """
        return os.path.exists(filepath)

    @classmethod
    def ensure_directory(cls, directory: str | os.PathLike[str]) -> None:
        """
        创建文件目录

        :param directory: 文件目录
        """
        os.makedirs(directory, exist_ok=True)

    @classmethod
    def check_file_extension(cls, file: UploadFile) -> bool:
        """
        检查文件后缀是否合法

        :param file: 文件对象
        :return: 校验结果
        """
        file_extension = cls.get_file_extension(file.filename)

        return file_extension in UploadConfig.DEFAULT_ALLOWED_EXTENSION

    @classmethod
    def get_file_extension(cls, filename: str | None) -> str:
        """
        获取文件名的小写扩展名

        :param filename: 文件名称
        :return: 小写文件扩展名
        """
        if not filename:
            return ''
        safe_name = PurePosixPath(filename.replace('\\', '/')).name
        return Path(safe_name).suffix.lower().removeprefix('.')

    @classmethod
    def get_original_filename(cls, filename: str | None) -> str:
        """
        获取移除目录信息后的原始文件名

        :param filename: 文件名称
        :return: 原始文件名
        """
        if not filename:
            return ''
        return PurePosixPath(filename.replace('\\', '/')).name

    @classmethod
    def get_safe_file_stem(cls, filename: str | None) -> str:
        """
        获取移除路径和非法字符后的文件名前缀

        :param filename: 文件名称
        :return: 安全文件名前缀
        """
        original_filename = cls.get_original_filename(filename)
        file_stem = original_filename.rsplit('.', 1)[0]
        safe_file_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', file_stem)
        while '..' in safe_file_stem:
            safe_file_stem = safe_file_stem.replace('..', '_')
        safe_file_stem = safe_file_stem.strip(' ._')[:100]
        return safe_file_stem or 'file'

    @classmethod
    def build_download_headers(cls, filename: str) -> dict[str, str]:
        """
        构造文件下载响应头

        :param filename: 文件名称
        :return: 文件下载响应头
        """
        safe_name = cls.get_original_filename(filename) or 'download'
        encoded_name = quote(safe_name)
        return {
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            'download-filename': encoded_name,
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': (
                "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
            'X-Frame-Options': 'DENY',
        }

    @classmethod
    def check_file_timestamp(cls, filename: str) -> bool:
        """
        校验文件时间戳是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        generated_file_info = filename.rsplit('.', 1)[0].rsplit('_', maxsplit=1)[-1]
        if len(generated_file_info) != cls.GENERATED_FILE_INFO_LENGTH:
            return False
        timestamp = generated_file_info[:14]
        try:
            datetime.strptime(timestamp, '%Y%m%d%H%M%S')
            return True
        except ValueError:
            return False

    @classmethod
    def check_file_machine(cls, filename: str) -> bool:
        """
        校验文件机器码是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        generated_file_info = filename.rsplit('.', 1)[0].rsplit('_', maxsplit=1)[-1]
        return (
            len(generated_file_info) == cls.GENERATED_FILE_INFO_LENGTH
            and generated_file_info[-4] == UploadConfig.UPLOAD_MACHINE
        )

    @classmethod
    def check_file_random_code(cls, filename: str) -> bool:
        """
        校验文件随机码是否合法

        :param filename: 文件名称
        :return: 校验结果
        """
        generated_file_info = filename.rsplit('.', 1)[0].rsplit('_', maxsplit=1)[-1]
        random_code = generated_file_info[-3:]
        return (
            len(generated_file_info) == cls.GENERATED_FILE_INFO_LENGTH
            and random_code.isdigit()
            and 1 <= int(random_code) <= cls.MAX_RANDOM_CODE
        )

    @classmethod
    async def generate_file(cls, filepath: str | os.PathLike[str]) -> AsyncGenerator[bytes, None]:
        """
        根据文件生成二进制数据

        :param filepath: 文件路径
        :yield: 二进制数据
        """
        async with aiofiles.open(filepath, 'rb') as response_file:
            while chunk := await response_file.read(1024 * 1024):
                yield chunk

    @classmethod
    def delete_file(cls, filepath: str | os.PathLike[str]) -> None:
        """
        根据文件路径删除对应文件

        :param filepath: 文件路径
        """
        os.remove(filepath)

    @classmethod
    def move_file(cls, source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        """
        移动文件到目标路径

        :param source: 原文件路径
        :param target: 目标文件路径
        """
        cls.ensure_directory(Path(target).parent)
        os.replace(source, target)

    @classmethod
    def remove_empty_directory(cls, directory: str | os.PathLike[str]) -> None:
        """
        删除空目录

        :param directory: 目录路径
        """
        try:
            os.rmdir(directory)
        except OSError:
            pass
