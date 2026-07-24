import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from exceptions.exception import ServiceException
from module_admin.dao.file_access_dao import FileAccessLogDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.vo.file_vo import (
    DeleteFileModel,
    FileAccessLogPageQueryModel,
    FileInfoDisplayModel,
    FileInfoPageQueryModel,
    FileStatsModel,
    TransferFileModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.file_access_service import FileAuditService
from module_admin.service.file_business_service import FileReferenceService
from utils.file_util import FileUtil
from utils.log_util import logger


@dataclass(frozen=True)
class FileAuditSnapshot:
    """文件审计快照。"""

    file_id: str
    original_name: str
    access_type: str


class FileLifecycleService:
    MAX_PURGE_RETENTION_DAYS = 36500
    MAX_PURGE_BATCH_SIZE = 1000

    @classmethod
    async def delete_file_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        delete_file: DeleteFileModel,
        file_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        删除文件service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param delete_file: 删除文件参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param request: Request对象
        :return: 删除结果
        """
        file_ids = FileUtil.parse_file_ids(delete_file.file_ids)
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')

        file_infos = await FileInfoDao.get_file_infos_by_ids_for_update(query_db, file_ids, file_data_scope_sql)
        if len(file_infos) != len(file_ids):
            await query_db.rollback()
            raise ServiceException(message='部分文件不存在、已删除或超出数据权限')
        file_audit_snapshots = cls._build_file_audit_snapshots(file_infos)
        reference_count_map = await FileReferenceService.get_file_reference_count_map_services(query_db, file_infos)
        referenced_file_ids = [file_id for file_id in file_ids if reference_count_map.get(file_id, 0) > 0]
        if referenced_file_ids:
            await query_db.rollback()
            snapshot_map = {item.file_id: item for item in file_audit_snapshots}
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'delete',
                    'denied',
                    error_message='BusinessReferenceExists',
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                        'referenceCount': reference_count_map.get(file_audit_snapshot.file_id, 0),
                    },
                )
            referenced_names = [snapshot_map[file_id].original_name for file_id in referenced_file_ids[:3]]
            referenced_name_text = '、'.join(f'“{name}”' for name in referenced_names)
            if len(referenced_file_ids) > len(referenced_names):
                referenced_name_text += f'等{len(referenced_file_ids)}个文件'
            raise ServiceException(message=f'文件{referenced_name_text}仍被业务引用，请先解除引用后再删除')

        try:
            staged_files = await asyncio.to_thread(FileUtil.stage_file_deletions, file_infos)
        except (OSError, ValueError) as exc:
            await query_db.rollback()
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'delete',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                    },
                )
            raise ServiceException(message='文件移入回收区失败') from exc

        try:
            await FileInfoDao.soft_delete_file_infos(query_db, file_ids, user.user_name, datetime.now())
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            await asyncio.to_thread(FileUtil.restore_staged_files, staged_files)
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'delete',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                    },
                )
            raise

        for file_audit_snapshot in file_audit_snapshots:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_audit_snapshot.file_id,
                'delete',
                'completed',
                operation_detail={
                    'originalName': file_audit_snapshot.original_name,
                    'accessType': file_audit_snapshot.access_type,
                    'previousStatus': 'active',
                    'newStatus': 'deleted',
                },
            )
        return CrudResponseModel(is_success=True, message='文件已移入回收站')

    @classmethod
    async def purge_file_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_ids: str,
        file_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        永久清理回收站文件service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_ids: 文件ID字符串
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param request: Request对象
        :return: 永久清理结果
        """
        parsed_file_ids = FileUtil.parse_file_ids(file_ids)
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')
        file_infos = await FileInfoDao.get_purgeable_file_infos_by_ids_for_update(
            query_db,
            parsed_file_ids,
            file_data_scope_sql,
        )
        if len(file_infos) != len(parsed_file_ids):
            await query_db.rollback()
            raise ServiceException(message='部分文件不存在、未进入回收站或超出数据权限')
        file_audit_snapshots = cls._build_file_audit_snapshots(file_infos)
        reference_count_map = await FileReferenceService.get_file_reference_count_map_services(query_db, file_infos)
        if any(reference_count_map.get(file_id, 0) > 0 for file_id in parsed_file_ids):
            await query_db.rollback()
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'purge',
                    'denied',
                    error_message='BusinessReferenceExists',
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                        'referenceCount': reference_count_map.get(file_audit_snapshot.file_id, 0),
                    },
                )
            raise ServiceException(message='部分文件仍被业务引用，不能永久清理')
        try:
            staged_files = await asyncio.to_thread(FileUtil.prepare_deleted_files_for_purge, file_infos)
        except (OSError, ValueError) as exc:
            await query_db.rollback()
            await cls._enqueue_purge_audits(
                request,
                current_user,
                file_audit_snapshots,
                'failed',
                error_message=exc.__class__.__name__,
            )
            raise ServiceException(message='回收区文件校验失败，未执行永久清理') from exc

        try:
            await FileInfoDao.mark_file_infos_purging(
                query_db,
                parsed_file_ids,
                user.user_name,
                datetime.now(),
            )
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            raise

        try:
            await asyncio.to_thread(FileUtil.purge_deleted_files, staged_files)
        except (OSError, ValueError) as exc:
            await cls._enqueue_purge_audits(
                request,
                current_user,
                file_audit_snapshots,
                'failed',
                error_message=exc.__class__.__name__,
            )
            raise ServiceException(message='永久清理物理文件失败，文件已保留为清理中状态，可重试') from exc

        try:
            await FileInfoDao.purge_file_infos(query_db, parsed_file_ids)
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            await cls._enqueue_purge_audits(
                request,
                current_user,
                file_audit_snapshots,
                'failed',
                error_message=exc.__class__.__name__,
            )
            raise

        await cls._enqueue_purge_audits(
            request,
            current_user,
            file_audit_snapshots,
            'completed',
        )
        return CrudResponseModel(is_success=True, message='文件已永久清理')

    @classmethod
    async def purge_recycle_bin_services(
        cls,
        query_db: AsyncSession,
        retention_days: int = 30,
        batch_size: int = 100,
    ) -> int:
        """
        按回收站保留天数自动永久清理文件service

        :param query_db: orm对象
        :param retention_days: 回收站保留天数
        :param batch_size: 单批处理数量
        :return: 永久清理文件数量
        """
        cls._validate_purge_parameters(retention_days, batch_size)
        deleted_before = datetime.now() - timedelta(days=retention_days)
        file_infos = await FileInfoDao.get_recycle_bin_purge_candidates(
            query_db,
            deleted_before,
            batch_size,
        )
        if not file_infos:
            await query_db.rollback()
            return 0
        file_ids = [file_info.file_id for file_info in file_infos]
        file_audit_snapshots = cls._build_file_audit_snapshots(file_infos)
        reference_count_map = await FileReferenceService.get_file_reference_count_map_services(query_db, file_infos)
        if any(reference_count_map.get(file_id, 0) > 0 for file_id in file_ids):
            await query_db.rollback()
            raise ServiceException(message='自动清理候选文件仍存在业务引用')
        try:
            staged_files = await asyncio.to_thread(FileUtil.prepare_deleted_files_for_purge, file_infos)
            await FileInfoDao.mark_file_infos_purging(query_db, file_ids, 'system', datetime.now())
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            raise

        try:
            await asyncio.to_thread(FileUtil.purge_deleted_files, staged_files)
        except (OSError, ValueError) as exc:
            await query_db.rollback()
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.add_system_file_audit(
                    query_db,
                    file_audit_snapshot.file_id,
                    'purge',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                        'automatic': True,
                        'retentionDays': retention_days,
                    },
                )
            await query_db.commit()
            raise

        try:
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.add_system_file_audit(
                    query_db,
                    file_audit_snapshot.file_id,
                    'purge',
                    'completed',
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                        'automatic': True,
                        'retentionDays': retention_days,
                    },
                )
            await FileInfoDao.purge_file_infos(query_db, file_ids)
            await query_db.commit()
        except Exception:
            await query_db.rollback()
            raise
        return len(file_ids)

    @classmethod
    async def restore_file_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_ids: str,
        file_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        恢复文件service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_ids: 文件ID字符串
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param request: Request对象
        :return: 恢复结果
        """
        parsed_file_ids = FileUtil.parse_file_ids(file_ids)
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')

        file_infos = await FileInfoDao.get_deleted_file_infos_by_ids_for_update(
            query_db,
            parsed_file_ids,
            file_data_scope_sql,
        )
        if len(file_infos) != len(parsed_file_ids):
            await query_db.rollback()
            raise ServiceException(message='部分文件不存在、未删除或超出数据权限')
        file_audit_snapshots = cls._build_file_audit_snapshots(file_infos)

        try:
            staged_files = await asyncio.to_thread(FileUtil.prepare_deleted_files_for_restore, file_infos)
        except (OSError, ValueError) as exc:
            await query_db.rollback()
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'restore',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                    },
                )
            raise ServiceException(message='文件从回收区恢复失败') from exc

        try:
            await FileInfoDao.restore_file_infos(
                query_db,
                parsed_file_ids,
                user.user_name,
                datetime.now(),
            )
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'restore',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                    },
                )
            raise

        try:
            await asyncio.to_thread(FileUtil.restore_deleted_files, staged_files)
        except (OSError, ValueError) as exc:
            try:
                await FileInfoDao.soft_delete_file_infos(
                    query_db,
                    parsed_file_ids,
                    user.user_name,
                    datetime.now(),
                )
                await query_db.commit()
            except Exception as compensation_exc:
                await query_db.rollback()
                logger.error(f'文件恢复状态补偿失败: {compensation_exc}')
            for file_audit_snapshot in file_audit_snapshots:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_audit_snapshot.file_id,
                    'restore',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        'originalName': file_audit_snapshot.original_name,
                        'accessType': file_audit_snapshot.access_type,
                    },
                )
            raise ServiceException(message='文件从回收区恢复失败') from exc

        await asyncio.to_thread(FileUtil.cleanup_trash_directories, staged_files)
        for file_audit_snapshot in file_audit_snapshots:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_audit_snapshot.file_id,
                'restore',
                'completed',
                operation_detail={
                    'originalName': file_audit_snapshot.original_name,
                    'accessType': file_audit_snapshot.access_type,
                    'previousStatus': 'deleted',
                    'newStatus': 'active',
                },
            )
        return CrudResponseModel(is_success=True, message='文件恢复成功')

    @staticmethod
    def _build_file_audit_snapshots(file_infos: list[SysFileInfo]) -> list[FileAuditSnapshot]:
        """
        在事务结束前固化文件审计字段

        :param file_infos: 文件信息列表
        :return: 文件审计快照列表
        """
        return [
            FileAuditSnapshot(
                file_id=file_info.file_id,
                original_name=file_info.original_name,
                access_type=file_info.access_type,
            )
            for file_info in file_infos
        ]

    @classmethod
    async def _enqueue_purge_audits(
        cls,
        request: Request | None,
        current_user: CurrentUserModel,
        file_audit_snapshots: list[FileAuditSnapshot],
        result: str,
        error_message: str = '',
    ) -> None:
        """批量写入永久清理审计。"""
        for file_audit_snapshot in file_audit_snapshots:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_audit_snapshot.file_id,
                'purge',
                result,
                error_message=error_message,
                operation_detail={
                    'originalName': file_audit_snapshot.original_name,
                    'accessType': file_audit_snapshot.access_type,
                    'automatic': False,
                },
            )

    @classmethod
    def _validate_purge_parameters(cls, retention_days: int, batch_size: int) -> None:
        """校验自动清理参数。"""
        if retention_days < 1 or retention_days > cls.MAX_PURGE_RETENTION_DAYS:
            raise ServiceException(message=f'回收站保留天数必须在1到{cls.MAX_PURGE_RETENTION_DAYS}之间')
        if batch_size < 1 or batch_size > cls.MAX_PURGE_BATCH_SIZE:
            raise ServiceException(message=f'单批处理数量必须在1到{cls.MAX_PURGE_BATCH_SIZE}之间')


class FileQueryService:
    @classmethod
    async def get_file_list_services(
        cls,
        query_db: AsyncSession,
        query_object: FileInfoPageQueryModel,
        file_data_scope_sql: ColumnElement,
        is_page: bool = True,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取文件信息列表service

        :param query_db: orm对象
        :param query_object: 文件信息查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 文件信息列表
        """
        file_list = await FileInfoDao.get_file_info_list(query_db, query_object, file_data_scope_sql, is_page)
        file_rows = file_list.rows if isinstance(file_list, PageModel) else file_list
        reference_count_map = await FileReferenceService.get_file_reference_count_map_services(query_db, file_rows)
        cls._enrich_file_reference_counts(file_rows, reference_count_map)
        await asyncio.to_thread(FileUtil.enrich_storage_status, file_rows)
        return file_list

    @classmethod
    async def get_file_stats_services(
        cls,
        query_db: AsyncSession,
        query_object: FileInfoPageQueryModel,
        file_data_scope_sql: ColumnElement,
    ) -> FileStatsModel:
        """
        获取文件管理统计信息service

        :param query_db: orm对象
        :param query_object: 文件信息查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件管理统计信息
        """
        return await FileInfoDao.get_file_stats(query_db, query_object, file_data_scope_sql)

    @classmethod
    async def file_detail_services(
        cls,
        query_db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement,
    ) -> FileInfoDisplayModel:
        """
        获取文件详细信息service

        :param query_db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件详细信息
        """
        file_info = await FileInfoDao.get_file_management_detail_by_id(query_db, file_id, file_data_scope_sql)
        if file_info is None:
            raise ServiceException(message='文件信息不存在或超出数据权限')
        reference_count_map = await FileReferenceService.get_file_reference_count_map_services(query_db, [file_info])
        file_info['reference_count'] = reference_count_map.get(file_id, 0)
        file_info['storage_status'] = await asyncio.to_thread(FileUtil.get_storage_status, file_info)
        return FileInfoDisplayModel.model_validate(file_info, by_name=True)

    @classmethod
    async def get_file_access_log_list_services(
        cls,
        query_db: AsyncSession,
        file_id: str,
        query_object: FileAccessLogPageQueryModel,
        file_data_scope_sql: ColumnElement,
        is_page: bool = True,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取文件访问审计列表service

        :param query_db: orm对象
        :param file_id: 文件ID
        :param query_object: 文件访问审计查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 文件访问审计列表
        """
        if await FileInfoDao.get_file_info_detail_by_id(query_db, file_id, file_data_scope_sql) is None:
            raise ServiceException(message='文件信息不存在或超出数据权限')
        return await FileAccessLogDao.get_file_access_log_list(query_db, file_id, query_object, is_page)

    @staticmethod
    def _enrich_file_reference_counts(file_rows: list[dict[str, Any]], reference_count_map: dict[str, int]) -> None:
        """
        补充文件业务引用数量

        :param file_rows: 文件信息列表
        :param reference_count_map: 文件ID和业务引用数量映射
        :return: None
        """
        for file_row in file_rows:
            file_id = str(file_row.get('file_id') or file_row.get('fileId'))
            file_row['referenceCount'] = reference_count_map.get(file_id, 0)


class FileTransferService:
    @classmethod
    async def transfer_file_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_ids: str,
        transfer_file: TransferFileModel,
        file_data_scope_sql: ColumnElement,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        批量转移文件service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_ids: 文件ID字符串
        :param transfer_file: 文件转移参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :param request: Request对象
        :return: 转移结果
        """
        parsed_file_ids = FileUtil.parse_file_ids(file_ids)
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')

        target_user = await FileInfoDao.get_transfer_user_by_id(
            query_db,
            transfer_file.owner_user_id,
            user_data_scope_sql,
        )
        target_dept = await FileInfoDao.get_transfer_dept_by_id(
            query_db,
            transfer_file.dept_id,
            dept_data_scope_sql,
        )
        if target_user is None or target_dept is None:
            await query_db.rollback()
            raise ServiceException(message='目标用户或部门不存在、已停用或超出数据权限')
        if target_user.dept_id != target_dept.dept_id:
            await query_db.rollback()
            raise ServiceException(message='目标用户不属于所选部门')
        target_user_id = target_user.user_id
        target_user_name = getattr(target_user, 'user_name', '')
        target_dept_id = target_dept.dept_id

        file_infos = await FileInfoDao.get_file_infos_by_ids_for_update(
            query_db,
            parsed_file_ids,
            file_data_scope_sql,
        )
        if len(file_infos) != len(parsed_file_ids):
            await query_db.rollback()
            raise ServiceException(message='部分文件不存在、已删除或超出数据权限')

        ownership_snapshots = {
            file_info.file_id: {
                'previousOwnerUserId': getattr(file_info, 'owner_user_id', None),
                'previousDeptId': getattr(file_info, 'dept_id', None),
            }
            for file_info in file_infos
        }

        try:
            await FileInfoDao.transfer_file_infos(
                query_db,
                parsed_file_ids,
                target_user_id,
                target_dept_id,
                user.user_name,
                datetime.now(),
            )
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            for file_id in parsed_file_ids:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_id,
                    'transfer',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={
                        **ownership_snapshots[file_id],
                        'newOwnerUserId': target_user_id,
                        'newDeptId': target_dept_id,
                        'reason': transfer_file.reason,
                    },
                )
            raise
        for file_id in parsed_file_ids:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_id,
                'transfer',
                'completed',
                operation_detail={
                    **ownership_snapshots[file_id],
                    'newOwnerUserId': target_user_id,
                    'newOwnerName': target_user_name,
                    'newDeptId': target_dept_id,
                    'reason': transfer_file.reason,
                },
            )
        return CrudResponseModel(is_success=True, message='文件转移成功')
