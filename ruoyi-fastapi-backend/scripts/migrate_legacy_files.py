import argparse
import asyncio
import hashlib
import mimetypes
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiofiles
from pydantic import ValidationError

from config.database import AsyncSessionLocal
from config.env import UploadConfig
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.vo.file_vo import FileInfoModel
from utils.log_util import logger
from utils.upload_util import UploadUtil

FILE_NAME_MAX_LENGTH = 255
STORAGE_KEY_MAX_LENGTH = 500
EXTENSION_MAX_LENGTH = 20
CONTENT_TYPE_MAX_LENGTH = 255


@dataclass(frozen=True)
class FileSignature:
    """
    文件稳定性签名
    """

    file_size: int
    modified_time_ns: int
    changed_time_ns: int
    device_id: int
    inode: int


@dataclass(frozen=True)
class LegacyFileInfo:
    """
    历史文件信息
    """

    filepath: Path
    storage_key: str
    filename: str
    extension: str
    content_type: str | None
    file_size: int
    file_time: datetime
    signature: FileSignature


def get_file_signature(filepath: Path) -> FileSignature:
    """
    获取普通文件的稳定性签名

    :param filepath: 文件路径
    :return: 文件稳定性签名
    """
    file_stat = filepath.lstat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError('文件不是普通文件')
    return FileSignature(
        file_size=file_stat.st_size,
        modified_time_ns=file_stat.st_mtime_ns,
        changed_time_ns=file_stat.st_ctime_ns,
        device_id=file_stat.st_dev,
        inode=file_stat.st_ino,
    )


def get_legacy_file_skip_reason(
    storage_key: str,
    filename: str,
    extension: str,
    content_type: str | None,
    file_size: int,
) -> str | None:
    """
    获取历史文件跳过原因

    :param storage_key: 存储相对路径
    :param filename: 存储文件名
    :param extension: 文件扩展名
    :param content_type: 文件内容类型
    :param file_size: 文件大小
    :return: 跳过原因
    """
    if extension not in UploadConfig.DEFAULT_ALLOWED_EXTENSION:
        return '文件扩展名不在允许列表'
    if file_size > UploadConfig.MAX_FILE_SIZE:
        return f'文件大小超过{UploadConfig.MAX_FILE_SIZE // 1024 // 1024}MB'
    if len(filename) > FILE_NAME_MAX_LENGTH:
        return f'文件名超过{FILE_NAME_MAX_LENGTH}个字符'
    if len(storage_key) > STORAGE_KEY_MAX_LENGTH:
        return f'存储相对路径超过{STORAGE_KEY_MAX_LENGTH}个字符'
    if len(extension) > EXTENSION_MAX_LENGTH:
        return f'文件扩展名超过{EXTENSION_MAX_LENGTH}个字符'
    if content_type and len(content_type) > CONTENT_TYPE_MAX_LENGTH:
        return f'文件内容类型超过{CONTENT_TYPE_MAX_LENGTH}个字符'
    return None


def collect_legacy_files() -> tuple[list[LegacyFileInfo], int]:
    """
    收集待迁移的历史文件

    :return: 符合要求的文件信息和跳过数量
    """
    upload_root = Path(UploadConfig.UPLOAD_PATH).resolve()
    legacy_files = []
    skipped_count = 0
    for filepath in upload_root.rglob('*'):
        try:
            signature = get_file_signature(filepath)
        except ValueError:
            continue
        except OSError as exc:
            logger.warning(f'跳过无法读取的历史文件路径: {filepath}，原因: {exc.__class__.__name__}')
            skipped_count += 1
            continue

        storage_key = filepath.relative_to(upload_root).as_posix()
        filename = filepath.name
        extension = UploadUtil.get_file_extension(filename)
        content_type = mimetypes.guess_type(filename)[0]
        skip_reason = get_legacy_file_skip_reason(
            storage_key,
            filename,
            extension,
            content_type,
            signature.file_size,
        )
        if skip_reason:
            logger.warning(f'跳过历史文件: {storage_key}，原因: {skip_reason}')
            skipped_count += 1
            continue

        legacy_files.append(
            LegacyFileInfo(
                filepath=filepath,
                storage_key=storage_key,
                filename=filename,
                extension=extension,
                content_type=content_type,
                file_size=signature.file_size,
                file_time=datetime.fromtimestamp(signature.modified_time_ns / 1_000_000_000),
                signature=signature,
            )
        )
    return legacy_files, skipped_count


async def calculate_file_hash(filepath: Path, expected_signature: FileSignature | None = None) -> str:
    """
    计算稳定文件的SHA-256

    :param filepath: 文件路径
    :param expected_signature: 扫描阶段记录的文件签名
    :return: 文件SHA-256
    """
    before_signature = await asyncio.to_thread(get_file_signature, filepath)
    if expected_signature is not None and before_signature != expected_signature:
        raise ValueError('文件在扫描后发生变化')

    file_hasher = hashlib.sha256()
    async with aiofiles.open(filepath, 'rb') as source_file:
        while chunk := await source_file.read(1024 * 1024):
            file_hasher.update(chunk)

    after_signature = await asyncio.to_thread(get_file_signature, filepath)
    if before_signature != after_signature:
        raise ValueError('文件在哈希计算期间发生变化')
    return file_hasher.hexdigest()


async def build_legacy_file_info(legacy_file: LegacyFileInfo) -> FileInfoModel:
    """
    构造历史文件信息模型

    :param legacy_file: 历史文件信息
    :return: 文件信息模型
    """
    return FileInfoModel(
        fileId=str(uuid.uuid4()),
        originalName=legacy_file.filename,
        storedName=legacy_file.filename,
        storageKey=legacy_file.storage_key,
        accessType='public',
        extension=legacy_file.extension,
        contentType=legacy_file.content_type,
        fileSize=legacy_file.file_size,
        fileHash=await calculate_file_hash(legacy_file.filepath, legacy_file.signature),
        createBy='migration',
        createTime=legacy_file.file_time,
        updateBy='migration',
        updateTime=legacy_file.file_time,
    )


async def migrate_legacy_files(
    dry_run: bool = False,
    batch_size: int = 100,
    maintenance_confirmed: bool = False,
) -> tuple[int, int]:
    """
    将公开目录中的历史文件登记到文件信息表

    :param dry_run: 是否仅扫描不写入数据库
    :param batch_size: 每批提交数量
    :param maintenance_confirmed: 是否已确认停止公开文件上传
    :return: 新增数量和跳过数量
    """
    if batch_size < 1:
        raise ValueError('每批提交数量必须大于0')
    if not dry_run and not maintenance_confirmed:
        raise ValueError('正式迁移前必须停止公开文件上传并确认维护窗口')

    legacy_files, skipped_count = await asyncio.to_thread(collect_legacy_files)
    added_count = 0
    pending_count = 0
    async with AsyncSessionLocal() as session:
        for legacy_file in legacy_files:
            if await FileInfoDao.get_file_info_by_storage_key(session, legacy_file.storage_key):
                skipped_count += 1
                continue

            try:
                file_info = await build_legacy_file_info(legacy_file)
            except (OSError, ValidationError, ValueError) as exc:
                logger.warning(f'跳过无法稳定迁移的历史文件: {legacy_file.storage_key}，原因: {exc.__class__.__name__}')
                skipped_count += 1
                continue

            if await FileInfoDao.get_file_info_by_storage_key(session, legacy_file.storage_key):
                skipped_count += 1
                continue
            if dry_run:
                logger.info(f'待登记历史文件: {legacy_file.storage_key}')
                added_count += 1
                continue

            await FileInfoDao.add_file_info_dao(session, file_info)
            pending_count += 1
            if pending_count == batch_size:
                await session.commit()
                added_count += pending_count
                pending_count = 0

        if not dry_run and pending_count:
            await session.commit()
            added_count += pending_count
    return added_count, skipped_count


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数

    :return: 命令行参数
    """
    parser = argparse.ArgumentParser(description='登记公开目录中的历史文件')
    parser.add_argument('--env', type=str, default='', help='运行环境')
    parser.add_argument('--dry-run', action='store_true', help='执行完整预检但不写入数据库')
    parser.add_argument('--batch-size', type=int, default=100, help='每批提交数量')
    parser.add_argument(
        '--confirm-maintenance',
        action='store_true',
        help='确认正式迁移期间已经停止公开文件上传',
    )
    args = parser.parse_args()
    if not args.dry_run and not args.confirm_maintenance:
        parser.error('正式迁移必须指定--confirm-maintenance并停止公开文件上传')
    return args


if __name__ == '__main__':
    args = parse_args()
    added, skipped = asyncio.run(
        migrate_legacy_files(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            maintenance_confirmed=args.confirm_maintenance,
        )
    )
    logger.info(f'历史文件登记完成，新增{added}个，跳过{skipped}个')
