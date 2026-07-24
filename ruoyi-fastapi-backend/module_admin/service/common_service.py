import asyncio
import hashlib
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Literal

import aiofiles
from fastapi import BackgroundTasks, Request, UploadFile
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel
from config.env import UploadConfig
from exceptions.exception import ServiceException
from module_admin.dao.file_access_dao import FileAclDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.vo.common_vo import UploadResponseModel
from module_admin.entity.vo.file_vo import FileInfoModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.file_access_service import FileAuditService
from utils.upload_util import FilePathUtil, UploadUtil


class CommonService:
    """
    通用模块服务层
    """

    @classmethod
    async def upload_service(
        cls,
        request: Request,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file: UploadFile,
        access_type: Literal['public', 'private'] = 'public',
    ) -> CrudResponseModel:
        """
        通用上传service

        :param request: Request对象
        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file: 上传文件对象
        :param access_type: 文件访问类型
        :return: 上传结果
        """
        if access_type not in {'public', 'private'}:
            raise ServiceException(message='文件访问类型不合法')
        if not UploadUtil.check_file_extension(file):
            raise ServiceException(message='文件类型不合法')
        if file.size is not None and file.size > UploadConfig.MAX_FILE_SIZE:
            raise ServiceException(message=f'文件大小不能超过{UploadConfig.MAX_FILE_SIZE // 1024 // 1024}MB')

        now = datetime.now()
        relative_path = Path('upload', now.strftime('%Y'), now.strftime('%m'), now.strftime('%d'))
        storage_root = UploadConfig.UPLOAD_PATH if access_type == 'public' else UploadConfig.PRIVATE_UPLOAD_PATH
        dir_path = Path(storage_root, relative_path)
        UploadUtil.ensure_directory(dir_path)
        file_id = str(uuid.uuid4())
        extension = UploadUtil.get_file_extension(file.filename)
        original_filename = UploadUtil.get_original_filename(file.filename)
        file_stem = UploadUtil.get_safe_file_stem(file.filename)
        for _ in range(10):
            filename = f'{file_stem}_{now.strftime("%Y%m%d%H%M%S")}{UploadConfig.UPLOAD_MACHINE}{UploadUtil.generate_random_number()}.{extension}'
            filepath = dir_path / filename
            try:
                total_size, file_hash = await cls._write_uploaded_file(file, filepath)
                break
            except FileExistsError:
                continue
        else:
            raise ServiceException(message='文件名生成冲突，请重新上传')

        relative_path_url = relative_path.as_posix()
        storage_key = f'{relative_path_url}/{filename}'
        user = current_user.user
        if user is None:
            UploadUtil.delete_file(filepath)
            raise ServiceException(message='无法获取当前用户信息')

        try:
            file_info = FileInfoModel(
                fileId=file_id,
                originalName=original_filename,
                storedName=filename,
                storageKey=storage_key,
                accessType=access_type,
                uploadUserId=user.user_id,
                ownerUserId=user.user_id,
                deptId=user.dept_id,
                extension=extension,
                contentType=file.content_type,
                fileSize=total_size,
                fileHash=file_hash,
                createBy=user.user_name,
                createTime=now,
                updateBy=user.user_name,
                updateTime=now,
            )
            await FileInfoDao.add_file_info_dao(query_db, file_info)
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            if UploadUtil.check_file_exists(filepath):
                UploadUtil.delete_file(filepath)
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='upload',
                result='failed',
                error_message='文件信息写入失败',
            )
            raise

        download_path = f'/common/files/{file_id}/download/{filename}'
        if access_type == 'public':
            file_name = f'{UploadConfig.UPLOAD_PREFIX}/{storage_key}'
            file_url = f'{request.base_url}{UploadConfig.UPLOAD_PREFIX[1:]}/{storage_key}'
        else:
            file_name = download_path
            file_url = f'{request.base_url}{download_path.lstrip("/")}'

        await cls._enqueue_file_access_log(
            request,
            current_user,
            file_id,
            action='upload',
            result='completed',
            bytes_sent=total_size,
        )

        return CrudResponseModel(
            is_success=True,
            result=UploadResponseModel(
                fileName=file_name,
                newFileName=filename,
                originalFilename=original_filename,
                url=file_url,
                fileId=file_id,
                accessType=access_type,
                downloadUrl=download_path,
            ),
            message='上传成功',
        )

    @classmethod
    async def _write_uploaded_file(cls, file: UploadFile, filepath: Path) -> tuple[int, str]:
        """
        将上传文件写入目标路径并计算摘要

        :param file: 上传文件对象
        :param filepath: 文件目标路径
        :return: 文件大小和SHA-256
        """
        total_size = 0
        file_hasher = hashlib.sha256()
        file_created = False
        try:
            async with aiofiles.open(filepath, 'xb') as target_file:
                file_created = True
                while chunk := await file.read(1024 * 1024):
                    total_size += len(chunk)
                    if total_size > UploadConfig.MAX_FILE_SIZE:
                        raise ServiceException(
                            message=f'文件大小不能超过{UploadConfig.MAX_FILE_SIZE // 1024 // 1024}MB'
                        )
                    file_hasher.update(chunk)
                    await target_file.write(chunk)
        except Exception:
            if file_created and UploadUtil.check_file_exists(filepath):
                UploadUtil.delete_file(filepath)
            raise
        return total_size, file_hasher.hexdigest()

    @classmethod
    async def download_managed_file_services(
        cls,
        request: Request,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_id: str,
        enforce_owner_permission: bool = True,
        file_data_scope_sql: ColumnElement | None = None,
    ) -> tuple[AsyncGenerator[bytes, None], str]:
        """
        下载已登记文件service

        :param request: Request对象
        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_id: 文件ID
        :param enforce_owner_permission: 是否校验文件所有者权限
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件流和下载文件名
        """
        file_info = await FileInfoDao.get_file_info_by_id(query_db, file_id, file_data_scope_sql)
        user = current_user.user
        if file_info is None or user is None:
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='download',
                result='denied',
                error_message='文件不存在或无权访问',
            )
            raise ServiceException(message='文件不存在或无权访问')
        if file_info.storage_type != 'local' or file_info.access_type not in {'public', 'private'}:
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='download',
                result='failed',
                error_message='文件存储类型或访问类型异常',
            )
            raise ServiceException(message='文件不存在或无权访问')

        current_time = datetime.now()
        is_expired = (
            file_info.access_type == 'private' and file_info.expire_time and file_info.expire_time < current_time
        )
        if is_expired:
            is_allowed = False
        elif not enforce_owner_permission or file_info.access_type == 'public':
            is_allowed = True
        else:
            is_allowed = await cls._has_private_file_download_permission(
                query_db,
                current_user,
                file_info,
                file_id,
                current_time,
            )
        if not is_allowed:
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='download',
                result='denied',
                error_message='文件不存在或无权访问',
            )
            raise ServiceException(message='文件不存在或无权访问')

        storage_root = (
            UploadConfig.UPLOAD_PATH if file_info.access_type == 'public' else UploadConfig.PRIVATE_UPLOAD_PATH
        )
        try:
            filepath = FilePathUtil.resolve_file_within_root(storage_root, file_info.storage_key)
        except (FileNotFoundError, ValueError) as exc:
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='download',
                result='failed',
                error_message='文件不存在或存储路径异常',
            )
            raise ServiceException(message='文件不存在或无权访问') from exc

        original_name = file_info.original_name
        await query_db.rollback()
        await cls._enqueue_file_access_log(
            request,
            current_user,
            file_id,
            action='download',
            result='allowed',
        )
        stream = cls._generate_audited_file(request, current_user, file_id, filepath)
        return stream, original_name

    @classmethod
    async def _has_private_file_download_permission(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_info: SysFileInfo,
        file_id: str,
        current_time: datetime,
    ) -> bool:
        """
        校验私有文件下载权限

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_info: 文件信息
        :param file_id: 文件ID
        :param current_time: 当前时间
        :return: 是否允许下载
        """
        user = current_user.user
        if user is None or user.user_id is None:
            return False
        if bool(getattr(user, 'admin', False)) or user.user_id == file_info.owner_user_id:
            return True

        file_acl_list = await FileAclDao.get_effective_file_acl_list(query_db, file_id, current_time)
        role_ids = cls._get_current_user_role_ids(user)
        dept_id, ancestor_dept_ids = cls._get_current_user_dept_ids(user)
        matched_effects = []
        for file_acl in file_acl_list:
            is_matched = False
            if file_acl.subject_type == 'user':
                is_matched = file_acl.subject_id == user.user_id
            elif file_acl.subject_type == 'role':
                is_matched = file_acl.subject_id in role_ids
            elif file_acl.subject_type == 'dept':
                is_matched = file_acl.subject_id == dept_id or (
                    file_acl.include_children in {'1', True} and file_acl.subject_id in ancestor_dept_ids
                )
            if is_matched:
                matched_effects.append(file_acl.effect)

        if 'deny' in matched_effects:
            return False
        if user.user_id == file_info.upload_user_id:
            return True
        return 'allow' in matched_effects

    @staticmethod
    def _get_current_user_role_ids(user: object) -> set[int]:
        """
        获取当前用户角色ID集合

        :param user: 当前用户对象
        :return: 角色ID集合
        """
        role_ids = {
            role.role_id
            for role in (getattr(user, 'role', None) or [])
            if role is not None and getattr(role, 'role_id', None) is not None
        }
        role_ids_text = getattr(user, 'role_ids', None)
        if role_ids_text:
            role_ids.update(int(role_id) for role_id in role_ids_text.split(',') if role_id.strip().isdigit())
        return role_ids

    @staticmethod
    def _get_current_user_dept_ids(user: object) -> tuple[int | None, set[int]]:
        """
        获取当前用户部门及祖级部门ID

        :param user: 当前用户对象
        :return: 当前部门ID和祖级部门ID集合
        """
        dept = getattr(user, 'dept', None)
        dept_id = getattr(user, 'dept_id', None) or getattr(dept, 'dept_id', None)
        ancestors = getattr(dept, 'ancestors', None) or ''
        ancestor_dept_ids = {int(ancestor_id) for ancestor_id in ancestors.split(',') if ancestor_id.strip().isdigit()}
        return dept_id, ancestor_dept_ids

    @classmethod
    async def _generate_audited_file(
        cls,
        request: Request,
        current_user: CurrentUserModel,
        file_id: str,
        filepath: Path,
    ) -> AsyncGenerator[bytes, None]:
        """
        生成带有完成审计的文件流

        :param request: Request对象
        :param current_user: 当前用户对象
        :param file_id: 文件ID
        :param filepath: 文件路径
        :yield: 文件二进制数据
        """
        bytes_sent = 0
        audit_result: Literal['completed', 'failed'] = 'failed'
        error_message = 'StreamClosed'
        try:
            async for chunk in UploadUtil.generate_file(filepath):
                bytes_sent += len(chunk)
                yield chunk
        except asyncio.CancelledError:
            error_message = 'CancelledError'
            raise
        except Exception as exc:
            error_message = exc.__class__.__name__
            raise
        else:
            audit_result = 'completed'
            error_message = ''
        finally:
            await cls._enqueue_file_access_log(
                request,
                current_user,
                file_id,
                action='download',
                result=audit_result,
                bytes_sent=bytes_sent,
                error_message=error_message,
            )

    @classmethod
    async def _enqueue_file_access_log(
        cls,
        request: Request,
        current_user: CurrentUserModel,
        file_id: str,
        action: Literal['upload', 'download'],
        result: Literal['allowed', 'denied', 'completed', 'failed'],
        bytes_sent: int = 0,
        error_message: str = '',
    ) -> None:
        """
        将文件访问审计写入日志队列

        :param request: Request对象
        :param current_user: 当前用户对象
        :param file_id: 文件ID
        :param action: 操作类型
        :param result: 操作结果
        :param bytes_sent: 已发送字节数
        :param error_message: 失败原因
        :return: None
        """
        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            file_id,
            action,
            result,
            bytes_sent=bytes_sent,
            error_message=error_message,
        )

    @classmethod
    async def download_services(
        cls, background_tasks: BackgroundTasks, file_name: str, delete: bool
    ) -> CrudResponseModel:
        """
        下载下载目录文件service

        :param background_tasks: 后台任务对象
        :param file_name: 下载的文件名称
        :param delete: 是否在下载完成后删除文件
        :return: 上传结果
        """
        try:
            filepath = FilePathUtil.resolve_file_within_root(UploadConfig.DOWNLOAD_PATH, file_name)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceException(message='文件名称不合法或文件不存在') from exc
        if delete:
            background_tasks.add_task(UploadUtil.delete_file, filepath)
        return CrudResponseModel(is_success=True, result=UploadUtil.generate_file(filepath), message='下载成功')

    @classmethod
    async def download_resource_services(cls, resource: str) -> CrudResponseModel:
        """
        下载上传目录文件service

        :param resource: 下载的文件名称
        :return: 上传结果
        """
        resource_prefix = f'{UploadConfig.UPLOAD_PREFIX.rstrip("/")}/'
        if not resource.startswith(resource_prefix):
            raise ServiceException(message='资源路径不合法')
        relative_resource = resource[len(resource_prefix) :]
        try:
            filepath = FilePathUtil.resolve_file_within_root(UploadConfig.UPLOAD_PATH, relative_resource)
        except (FileNotFoundError, ValueError) as exc:
            raise ServiceException(message='资源路径不合法或文件不存在') from exc
        filename = filepath.name
        if (
            '..' in filename
            or not UploadUtil.check_file_timestamp(filename)
            or not UploadUtil.check_file_machine(filename)
            or not UploadUtil.check_file_random_code(filename)
            or UploadUtil.get_file_extension(filename) not in UploadConfig.DEFAULT_ALLOWED_EXTENSION
        ):
            raise ServiceException(message='资源文件名称不合法')
        return CrudResponseModel(is_success=True, result=UploadUtil.generate_file(filepath), message='下载成功')
