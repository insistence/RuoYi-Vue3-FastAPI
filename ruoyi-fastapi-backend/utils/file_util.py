import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from config.env import UploadConfig
from exceptions.exception import ServiceException
from utils.log_util import logger
from utils.upload_util import FilePathUtil, UploadUtil


class FileStorageInfo(Protocol):
    """
    文件存储信息协议
    """

    file_id: str
    storage_type: str
    access_type: str
    storage_key: str
    stored_name: str


@dataclass(frozen=True)
class StagedFile:
    """
    待删除文件暂存信息
    """

    source_path: Path
    trash_path: Path


class FileUtil:
    """
    文件工具类
    """

    @classmethod
    def parse_file_ids(cls, file_ids: str) -> list[str]:
        """
        解析并校验文件ID

        :param file_ids: 文件ID字符串
        :return: 文件ID列表
        """
        if not file_ids:
            raise ServiceException(message='文件ID不能为空')
        try:
            parsed_file_ids = list(
                dict.fromkeys(str(uuid.UUID(item.strip())) for item in file_ids.split(',') if item.strip())
            )
        except ValueError as exc:
            raise ServiceException(message='文件ID格式不正确') from exc
        if not parsed_file_ids:
            raise ServiceException(message='文件ID不能为空')
        return parsed_file_ids

    @classmethod
    def enrich_storage_status(cls, file_rows: list[dict[str, Any]]) -> None:
        """
        补充文件物理存储状态

        :param file_rows: 文件信息列表
        :return: None
        """
        for file_row in file_rows:
            file_row['storageStatus'] = cls.get_storage_status(file_row)

    @classmethod
    def get_storage_status(cls, file_info: dict[str, Any]) -> str:
        """
        获取文件物理存储状态

        :param file_info: 文件信息
        :return: 文件物理存储状态
        """

        def get_value(snake_name: str, camel_name: str) -> Any:
            return file_info.get(snake_name) if snake_name in file_info else file_info.get(camel_name)

        try:
            file_id = get_value('file_id', 'fileId')
            storage_type = get_value('storage_type', 'storageType')
            access_type = get_value('access_type', 'accessType')
            storage_key = get_value('storage_key', 'storageKey')
            stored_name = get_value('stored_name', 'storedName')
            status = get_value('status', 'status')
            if storage_type != 'local' or access_type not in {'public', 'private'}:
                return 'invalid'
            storage_root = UploadConfig.UPLOAD_PATH if access_type == 'public' else UploadConfig.PRIVATE_UPLOAD_PATH
            source_path = FilePathUtil.resolve_path_within_root(storage_root, storage_key)
            trash_path = FilePathUtil.resolve_path_within_root(
                UploadConfig.FILE_TRASH_PATH,
                f'{file_id}/{stored_name}',
            )
            source_exists = source_path.exists()
            trash_exists = trash_path.exists()
            if source_exists and not source_path.is_file():
                return 'invalid'
            if trash_exists and not trash_path.is_file():
                return 'invalid'
            if status in {'deleted', 'purging'}:
                if trash_exists and not source_exists:
                    return 'quarantined'
                return 'invalid' if source_exists else 'missing'
            if source_exists and not trash_exists:
                return 'normal'
            if trash_exists and not source_exists:
                return 'quarantined'
            return 'invalid' if source_exists and trash_exists else 'missing'
        except (AttributeError, OSError, TypeError, ValueError):
            return 'invalid'

    @classmethod
    def stage_file_deletions(cls, file_infos: list[FileStorageInfo]) -> list[StagedFile]:
        """
        将待删除文件移入回收区

        :param file_infos: 文件信息列表
        :return: 暂存文件列表
        """
        staged_files = []
        try:
            for file_info in file_infos:
                staged_file = cls._get_staged_file_paths(file_info)
                if not staged_file.source_path.exists():
                    if staged_file.trash_path.exists():
                        if not staged_file.trash_path.is_file():
                            raise ValueError('回收区路径不是普通文件')
                        staged_files.append(staged_file)
                    continue
                if not staged_file.source_path.is_file():
                    raise ValueError('待删除路径不是普通文件')
                if staged_file.trash_path.exists():
                    raise FileExistsError('回收区目标文件已存在')
                UploadUtil.move_file(staged_file.source_path, staged_file.trash_path)
                staged_files.append(staged_file)
        except Exception:
            cls.restore_staged_files(staged_files)
            raise
        return staged_files

    @classmethod
    def _get_staged_file_paths(cls, file_info: FileStorageInfo) -> StagedFile:
        """
        获取文件原路径和回收区路径

        :param file_info: 文件信息
        :return: 文件暂存信息
        """
        if file_info.storage_type != 'local' or file_info.access_type not in {'public', 'private'}:
            raise ValueError('文件存储类型或访问类型异常')
        storage_root = (
            UploadConfig.UPLOAD_PATH if file_info.access_type == 'public' else UploadConfig.PRIVATE_UPLOAD_PATH
        )
        source_path = FilePathUtil.resolve_path_within_root(storage_root, file_info.storage_key)
        trash_path = FilePathUtil.resolve_path_within_root(
            UploadConfig.FILE_TRASH_PATH,
            f'{file_info.file_id}/{file_info.stored_name}',
        )
        return StagedFile(source_path=source_path, trash_path=trash_path)

    @classmethod
    def restore_staged_files(cls, staged_files: list[StagedFile]) -> None:
        """
        将隔离区文件恢复到原路径

        :param staged_files: 暂存文件列表
        :return: None
        """
        for staged_file in reversed(staged_files):
            try:
                if staged_file.trash_path.exists():
                    if staged_file.source_path.exists():
                        logger.error(f'文件删除回滚失败，原路径已存在: {staged_file.source_path}')
                        continue
                    UploadUtil.move_file(staged_file.trash_path, staged_file.source_path)
                    UploadUtil.remove_empty_directory(staged_file.trash_path.parent)
            except OSError as exc:
                logger.error(f'文件删除回滚失败: {exc}')

    @classmethod
    def prepare_deleted_files_for_restore(cls, file_infos: list[FileStorageInfo]) -> list[StagedFile]:
        """
        校验待恢复文件并生成暂存信息

        :param file_infos: 文件信息列表
        :return: 暂存文件列表
        """
        staged_files = []
        for file_info in file_infos:
            staged_file = cls._get_staged_file_paths(file_info)
            if not staged_file.trash_path.exists() or not staged_file.trash_path.is_file():
                raise FileNotFoundError('回收区文件不存在')
            if staged_file.source_path.exists():
                raise FileExistsError('文件原路径已存在')
            staged_files.append(staged_file)
        return staged_files

    @classmethod
    def prepare_deleted_files_for_purge(cls, file_infos: list[FileStorageInfo]) -> list[StagedFile]:
        """
        校验待永久清理文件并生成暂存信息

        :param file_infos: 文件信息列表
        :return: 暂存文件列表
        """
        staged_files = []
        for file_info in file_infos:
            staged_file = cls._get_staged_file_paths(file_info)
            if staged_file.source_path.exists():
                raise FileExistsError('待清理文件仍存在于正式存储目录')
            if staged_file.trash_path.exists() and not staged_file.trash_path.is_file():
                raise ValueError('回收区路径不是普通文件')
            staged_files.append(staged_file)
        return staged_files

    @classmethod
    def purge_deleted_files(cls, staged_files: list[StagedFile]) -> None:
        """
        永久删除回收区文件

        :param staged_files: 暂存文件列表
        :return: None
        """
        for staged_file in staged_files:
            if staged_file.source_path.exists():
                raise FileExistsError('待清理文件仍存在于正式存储目录')
            if staged_file.trash_path.exists():
                if not staged_file.trash_path.is_file():
                    raise ValueError('回收区路径不是普通文件')
                staged_file.trash_path.unlink()
            UploadUtil.remove_empty_directory(staged_file.trash_path.parent)

    @classmethod
    def restore_deleted_files(cls, staged_files: list[StagedFile]) -> None:
        """
        将已删除文件从回收区恢复到原路径

        :param staged_files: 暂存文件列表
        :return: None
        """
        restored_files = []
        try:
            for staged_file in staged_files:
                if not staged_file.trash_path.exists() or not staged_file.trash_path.is_file():
                    raise FileNotFoundError('回收区文件不存在')
                if staged_file.source_path.exists():
                    raise FileExistsError('文件原路径已存在')
                UploadUtil.move_file(staged_file.trash_path, staged_file.source_path)
                restored_files.append(staged_file)
        except Exception:
            cls._restage_restored_files(restored_files)
            raise

    @classmethod
    def _restage_restored_files(cls, staged_files: list[StagedFile]) -> None:
        """
        将恢复失败的文件重新移入回收区

        :param staged_files: 暂存文件列表
        :return: None
        """
        for staged_file in reversed(staged_files):
            try:
                if staged_file.source_path.exists():
                    if staged_file.trash_path.exists():
                        logger.error(f'文件恢复回滚失败，回收区路径已存在: {staged_file.trash_path}')
                        continue
                    UploadUtil.move_file(staged_file.source_path, staged_file.trash_path)
            except OSError as exc:
                logger.error(f'文件恢复回滚失败: {exc}')

    @classmethod
    def cleanup_trash_directories(cls, staged_files: list[StagedFile]) -> None:
        """
        清理恢复后留下的空回收区目录

        :param staged_files: 暂存文件列表
        :return: None
        """
        for staged_file in staged_files:
            UploadUtil.remove_empty_directory(staged_file.trash_path.parent)
