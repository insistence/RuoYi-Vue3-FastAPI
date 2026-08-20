import asyncio
import mimetypes
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from config.database import DataSourceRegistry
from config.env import UploadConfig
from exceptions.exception import ServiceException
from module_admin.dao.file_access_dao import FileAccessLogDao
from module_admin.dao.file_business_dao import FileReferenceDao, FileRetentionNoticeDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo, SysFileReconcileIssue, SysFileReconcileRun, SysFileReference
from module_admin.entity.vo.file_vo import (
    DeleteFileModel,
    DisposeExpiredFileModel,
    ExtendFileRetentionModel,
    FileAccessLogPageQueryModel,
    FileInfoDisplayModel,
    FileInfoModel,
    FileInfoPageQueryModel,
    FileReconcileAction,
    FileReconcileHandleModel,
    FileReconcileIssueModel,
    FileReconcileIssuePageQueryModel,
    FileReconcileRunModel,
    FileReconcileRunPageQueryModel,
    FileReconcileStatsModel,
    FileStatsModel,
    TransferFileModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.file_access_service import FileAuditService
from module_admin.service.file_business_service import FileReferenceService
from utils.file_util import FileReconcileUtil, FileUtil
from utils.log_util import logger
from utils.upload_util import UploadUtil


@dataclass(frozen=True)
class FileAuditSnapshot:
    """文件审计快照。"""

    file_id: str
    original_name: str
    access_type: str


class FileRetentionDispositionService:
    """
    文件到期处置服务层
    """

    @classmethod
    async def extend_file_retention_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        notice_id: int,
        extend_retention: ExtendFileRetentionModel,
        file_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        延长文件保留期限service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param notice_id: 提醒ID
        :param extend_retention: 延期参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param request: Request对象
        :return: 延期结果
        """
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')
        context = await FileRetentionNoticeDao.get_file_retention_notice_context_for_update(
            query_db,
            notice_id,
            file_data_scope_sql,
        )
        if context is None:
            await query_db.rollback()
            raise ServiceException(message='提醒不存在、已失效或超出数据权限')
        _, file_info = context
        file_snapshot = FileAuditSnapshot(
            file_id=file_info.file_id,
            original_name=file_info.original_name,
            access_type=file_info.access_type,
        )
        current_time = datetime.now()
        new_expire_time = extend_retention.expire_time
        if new_expire_time.tzinfo:
            new_expire_time = new_expire_time.astimezone().replace(tzinfo=None)
        previous_expire_time = file_info.expire_time
        if previous_expire_time is None:
            await query_db.rollback()
            raise ServiceException(message='文件未配置保留期限')
        if new_expire_time <= current_time or new_expire_time <= previous_expire_time:
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_extend',
                'denied',
                extend_retention.reason,
                previous_expire_time,
                new_expire_time,
                error_message='InvalidExpireTime',
            )
            await query_db.rollback()
            raise ServiceException(message='新的到期时间必须晚于当前时间和原到期时间')

        reference_list = await FileReferenceDao.get_file_reference_list_for_update(query_db, file_info.file_id)
        if not reference_list:
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_extend',
                'denied',
                extend_retention.reason,
                previous_expire_time,
                new_expire_time,
                error_message='TimedBusinessReferenceNotFound',
            )
            await query_db.rollback()
            raise ServiceException(message='文件不存在可延期的限时业务引用，请先重新关联业务')
        if (file_info.business_type and file_info.business_id) or any(
            reference.retention_expire_time is None for reference in reference_list
        ):
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_extend',
                'denied',
                extend_retention.reason,
                previous_expire_time,
                new_expire_time,
                error_message='PermanentBusinessReferenceExists',
            )
            await query_db.rollback()
            raise ServiceException(message='文件存在永久业务引用，不能通过到期提醒延期')

        terminal_references = [
            reference for reference in reference_list if reference.retention_expire_time == previous_expire_time
        ]
        if reference_list and not terminal_references:
            await query_db.rollback()
            raise ServiceException(message='文件到期时间与业务引用不一致，请先检查业务引用')

        for reference in terminal_references:
            reference.retention_expire_time = new_expire_time
        file_info.expire_time = new_expire_time
        file_info.update_by = user.user_name
        file_info.update_time = current_time
        await FileRetentionNoticeDao.invalidate_file_retention_notices(query_db, file_info.file_id)
        try:
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_extend',
                'failed',
                extend_retention.reason,
                previous_expire_time,
                new_expire_time,
                reference_count=len(terminal_references),
                error_message=exc.__class__.__name__,
            )
            raise

        await cls._enqueue_retention_audit(
            request,
            current_user,
            file_snapshot,
            'retention_extend',
            'completed',
            extend_retention.reason,
            previous_expire_time,
            new_expire_time,
            reference_count=len(terminal_references),
        )
        return CrudResponseModel(is_success=True, message='文件保留期限已延长')

    @classmethod
    async def dispose_expired_file_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        notice_id: int,
        dispose_file: DisposeExpiredFileModel,
        file_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        将到期文件移入回收站service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param notice_id: 提醒ID
        :param dispose_file: 处置参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param request: Request对象
        :return: 处置结果
        """
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')
        context = await FileRetentionNoticeDao.get_file_retention_notice_context_for_update(
            query_db,
            notice_id,
            file_data_scope_sql,
        )
        if context is None:
            await query_db.rollback()
            raise ServiceException(message='提醒不存在、已失效或超出数据权限')
        _, file_info = context
        file_snapshot = FileAuditSnapshot(
            file_id=file_info.file_id,
            original_name=file_info.original_name,
            access_type=file_info.access_type,
        )
        current_time = datetime.now()
        expire_time = file_info.expire_time
        if expire_time is None or expire_time > current_time:
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_dispose',
                'denied',
                dispose_file.reason,
                expire_time,
                error_message='FileNotExpired',
            )
            await query_db.rollback()
            raise ServiceException(message='文件尚未到期，不能执行到期处置')

        reference_list = await FileReferenceDao.get_file_reference_list_for_update(query_db, file_info.file_id)
        blocking_references = [
            reference
            for reference in reference_list
            if reference.retention_expire_time is None or reference.retention_expire_time > current_time
        ]
        if (file_info.business_type and file_info.business_id) or blocking_references:
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_dispose',
                'denied',
                dispose_file.reason,
                expire_time,
                reference_count=len(reference_list),
                error_message='ActiveBusinessReferenceExists',
            )
            await query_db.rollback()
            raise ServiceException(message='文件存在永久或尚未到期的业务引用，不能执行到期处置')

        reference_snapshots = cls._build_reference_snapshots(reference_list)
        try:
            staged_files = await asyncio.to_thread(FileUtil.stage_file_deletions, [file_info])
        except (OSError, ValueError) as exc:
            await query_db.rollback()
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_dispose',
                'failed',
                dispose_file.reason,
                expire_time,
                reference_count=len(reference_list),
                error_message=exc.__class__.__name__,
            )
            raise ServiceException(message='到期文件移入回收区失败') from exc

        try:
            await FileReferenceDao.delete_file_references(query_db, file_info.file_id)
            await FileInfoDao.soft_delete_file_infos(
                query_db,
                [file_info.file_id],
                user.user_name,
                current_time,
            )
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            await asyncio.to_thread(FileUtil.restore_staged_files, staged_files)
            await cls._enqueue_retention_audit(
                request,
                current_user,
                file_snapshot,
                'retention_dispose',
                'failed',
                dispose_file.reason,
                expire_time,
                reference_count=len(reference_list),
                error_message=exc.__class__.__name__,
            )
            raise

        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            file_snapshot.file_id,
            'retention_dispose',
            'completed',
            operation_detail={
                'originalName': file_snapshot.original_name,
                'accessType': file_snapshot.access_type,
                'reason': dispose_file.reason,
                'expireTime': expire_time,
                'releasedReferenceCount': len(reference_snapshots),
                'releasedReferences': reference_snapshots,
                'previousStatus': 'active',
                'newStatus': 'deleted',
            },
        )
        return CrudResponseModel(is_success=True, message='到期文件已移入回收站')

    @classmethod
    async def _enqueue_retention_audit(
        cls,
        request: Request | None,
        current_user: CurrentUserModel,
        file_snapshot: FileAuditSnapshot,
        action: Literal['retention_extend', 'retention_dispose'],
        result: Literal['denied', 'completed', 'failed'],
        reason: str,
        previous_expire_time: datetime | None,
        new_expire_time: datetime | None = None,
        reference_count: int | None = None,
        error_message: str = '',
    ) -> None:
        """写入文件到期处置审计。"""
        operation_detail = {
            'originalName': file_snapshot.original_name,
            'accessType': file_snapshot.access_type,
            'reason': reason,
            'previousExpireTime': previous_expire_time,
        }
        if new_expire_time is not None:
            operation_detail['newExpireTime'] = new_expire_time
        if reference_count is not None:
            operation_detail['referenceCount'] = reference_count
        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            file_snapshot.file_id,
            action,
            result,
            error_message=error_message,
            operation_detail=operation_detail,
        )

    @staticmethod
    def _build_reference_snapshots(reference_list: list[SysFileReference]) -> list[dict[str, Any]]:
        """构建释放业务引用的审计快照。"""
        return [
            {
                'referenceId': reference.reference_id,
                'businessType': reference.business_type,
                'businessId': reference.business_id,
                'businessName': reference.business_name,
                'retentionExpireTime': reference.retention_expire_time,
            }
            for reference in reference_list
        ]


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
                'previousUploaderAccessEnabled': getattr(file_info, 'uploader_access_enabled', '1') in {'1', True},
            }
            for file_info in file_infos
        }

        try:
            await FileInfoDao.transfer_file_infos(
                query_db,
                parsed_file_ids,
                target_user_id,
                target_dept_id,
                transfer_file.retain_uploader_access,
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
                        'newUploaderAccessEnabled': transfer_file.retain_uploader_access,
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
                    'newUploaderAccessEnabled': transfer_file.retain_uploader_access,
                    'reason': transfer_file.reason,
                },
            )
        return CrudResponseModel(is_success=True, message='文件转移成功')


class FileReconcileService:
    """
    文件存储对账服务
    """

    RUN_LOCK_NAME = 'storage_reconcile'
    RUN_STALE_HOURS = 6
    ISSUE_ACTIONS: dict[str, list[FileReconcileAction]] = {
        'unexpected_trash': ['restore_source'],
        'unexpected_source': ['move_to_trash'],
        'wrong_storage_root': ['move_to_expected_root'],
        'duplicate_file': ['quarantine_file'],
        'orphan_file': ['quarantine_file', 'register_orphan'],
        'size_mismatch': ['accept_current'],
        'hash_mismatch': ['accept_current'],
    }

    @classmethod
    async def start_reconcile_run_services(
        cls,
        query_db: AsyncSession,
        *,
        check_hash: bool = False,
        trigger_type: str = 'manual',
        current_user: CurrentUserModel | None = None,
    ) -> FileReconcileRunModel:
        """
        创建文件存储对账任务

        :param query_db: orm对象
        :param check_hash: 是否校验文件摘要
        :param trigger_type: 触发类型
        :param current_user: 当前用户对象
        :return: 对账任务
        """
        if trigger_type not in {'manual', 'scheduled'}:
            raise ServiceException(message='对账任务触发类型不正确')
        started_by = 'system'
        if trigger_type == 'manual':
            user = cls._require_admin(current_user)
            started_by = user.user_name
        current_time = datetime.now()
        reconcile_run = SysFileReconcileRun(
            run_id=str(uuid.uuid4()),
            trigger_type=trigger_type,
            status='running',
            check_hash='1' if check_hash else '0',
            lock_name=cls.RUN_LOCK_NAME,
            started_by=started_by,
            started_time=current_time,
        )
        run_data = cls._build_run_data(reconcile_run)
        try:
            await FileInfoDao.release_stale_runs(
                query_db,
                current_time - timedelta(hours=cls.RUN_STALE_HOURS),
                current_time,
            )
            await FileInfoDao.add_reconcile_run(query_db, reconcile_run)
            await query_db.commit()
        except IntegrityError as exc:
            await query_db.rollback()
            raise ServiceException(message='已有文件存储对账任务正在运行') from exc
        except Exception:
            await query_db.rollback()
            raise
        return FileReconcileRunModel.model_validate(run_data, by_name=True)

    @classmethod
    async def execute_reconcile_run_services(cls, run_id: str) -> None:
        """
        在独立会话中执行文件存储对账任务

        :param run_id: 任务ID
        :return: None
        """
        try:
            async with DataSourceRegistry.session() as query_db:
                reconcile_run = await FileInfoDao.get_reconcile_run_by_id(query_db, run_id)
                if reconcile_run is None or reconcile_run.status != 'running':
                    return
                check_hash = reconcile_run.check_hash == '1'
                file_infos = await FileInfoDao.get_all_local_file_infos(query_db)
                scan_result = await asyncio.to_thread(
                    FileReconcileUtil.scan_storage,
                    file_infos,
                    check_hash,
                )
                current_time = datetime.now()
                new_issue_count = await FileInfoDao.upsert_reconcile_issues(
                    query_db,
                    run_id,
                    [asdict(finding) for finding in scan_result.findings],
                    current_time,
                )
                resolved_issue_count = await FileInfoDao.resolve_disappeared_issues(
                    query_db,
                    run_id,
                    current_time,
                )
                await FileInfoDao.finish_reconcile_run(
                    query_db,
                    run_id,
                    status='completed',
                    finished_time=current_time,
                    scanned_file_count=scan_result.scanned_file_count,
                    scanned_storage_count=scan_result.scanned_storage_count,
                    issue_count=len(scan_result.findings),
                    new_issue_count=new_issue_count,
                    resolved_issue_count=resolved_issue_count,
                )
                await query_db.commit()
                logger.info(
                    f'文件存储对账任务{run_id}完成，扫描文件记录{scan_result.scanned_file_count}条，'
                    f'物理文件{scan_result.scanned_storage_count}个，发现异常{len(scan_result.findings)}个'
                )
        except Exception as exc:
            logger.exception(f'文件存储对账任务{run_id}执行失败')
            async with DataSourceRegistry.session() as query_db:
                try:
                    await FileInfoDao.finish_reconcile_run(
                        query_db,
                        run_id,
                        status='failed',
                        finished_time=datetime.now(),
                        error_message=f'{exc.__class__.__name__}：对账任务执行失败',
                    )
                    await query_db.commit()
                except Exception:
                    await query_db.rollback()
                    logger.exception(f'文件存储对账任务{run_id}失败状态更新失败')

    @classmethod
    async def run_scheduled_reconcile_services(cls, check_hash: bool = False) -> None:
        """
        执行定时文件存储对账

        :param check_hash: 是否校验文件摘要
        :return: None
        """
        async with DataSourceRegistry.session() as query_db:
            try:
                reconcile_run = await cls.start_reconcile_run_services(
                    query_db,
                    check_hash=check_hash,
                    trigger_type='scheduled',
                )
            except ServiceException as exc:
                logger.warning(f'定时文件存储对账未启动：{exc.message}')
                return
        await cls.execute_reconcile_run_services(reconcile_run.run_id)

    @classmethod
    async def get_reconcile_run_list_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        query_object: FileReconcileRunPageQueryModel,
        is_page: bool = True,
    ) -> PageModel | list[FileReconcileRunModel]:
        """
        获取文件存储对账任务列表
        """
        cls._require_admin(current_user)
        run_list = await FileInfoDao.get_reconcile_run_list(query_db, query_object, is_page)
        if isinstance(run_list, PageModel):
            return PageModel.model_validate(
                {
                    'rows': [FileReconcileRunModel.model_validate(row, by_name=True) for row in run_list.rows],
                    'page_num': run_list.page_num,
                    'page_size': run_list.page_size,
                    'total': run_list.total,
                    'has_next': run_list.has_next,
                },
                by_name=True,
            )
        return [FileReconcileRunModel.model_validate(row, by_name=True) for row in run_list]

    @classmethod
    async def get_reconcile_issue_list_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        query_object: FileReconcileIssuePageQueryModel,
        is_page: bool = True,
    ) -> PageModel | list[FileReconcileIssueModel]:
        """
        获取文件存储对账异常列表
        """
        cls._require_admin(current_user)
        issue_list = await FileInfoDao.get_reconcile_issue_list(query_db, query_object, is_page)
        issue_rows = issue_list.rows if isinstance(issue_list, PageModel) else issue_list
        issue_models = []
        for issue_row in issue_rows:
            issue_model = FileReconcileIssueModel.model_validate(issue_row, by_name=True)
            issue_model.available_actions = cls._get_available_actions(issue_model)
            issue_models.append(issue_model)
        if isinstance(issue_list, PageModel):
            return PageModel.model_validate(
                {
                    'rows': issue_models,
                    'page_num': issue_list.page_num,
                    'page_size': issue_list.page_size,
                    'total': issue_list.total,
                    'has_next': issue_list.has_next,
                },
                by_name=True,
            )
        return issue_models

    @classmethod
    async def get_reconcile_stats_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
    ) -> FileReconcileStatsModel:
        """
        获取文件存储对账统计
        """
        cls._require_admin(current_user)
        stats = await FileInfoDao.get_reconcile_stats(query_db)
        latest_run = stats.pop('latest_run')
        stats['latest_run'] = (
            FileReconcileRunModel.model_validate(cls._build_run_data(latest_run), by_name=True) if latest_run else None
        )
        return FileReconcileStatsModel.model_validate(stats, by_name=True)

    @classmethod
    async def handle_reconcile_issue_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        issue_id: int,
        handle: FileReconcileHandleModel,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        处理文件存储对账异常

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param issue_id: 异常ID
        :param handle: 处理参数
        :param request: Request对象
        :return: 处理结果
        """
        cls._require_admin(current_user)
        if await FileInfoDao.has_running_reconcile_run(query_db):
            raise ServiceException(message='文件存储对账任务运行中，请等待扫描完成后再处理异常')
        issue = await FileInfoDao.get_reconcile_issue_for_update(query_db, issue_id)
        if issue is None:
            raise ServiceException(message='文件存储对账异常不存在')
        available_actions = cls._get_available_actions(issue)
        if handle.action not in available_actions:
            await query_db.rollback()
            raise ServiceException(message='当前异常状态不支持该处理动作')

        file_id = issue.file_id
        issue_type = issue.issue_type
        operation_location = {
            'actualRoot': issue.actual_root,
            'actualKey': issue.actual_key,
            'expectedRoot': issue.expected_root,
            'expectedKey': issue.expected_key,
        }
        performed_move: tuple[str, str, str, str] | None = None
        current_time = datetime.now()
        try:
            file_id, performed_move = await cls._apply_reconcile_action(
                query_db,
                issue,
                handle,
                current_user,
                current_time,
            )
            await query_db.commit()
        except ServiceException:
            await query_db.rollback()
            if performed_move:
                await cls._rollback_file_move(performed_move)
            raise
        except Exception as exc:
            await query_db.rollback()
            if performed_move:
                await cls._rollback_file_move(performed_move)
            if isinstance(exc, (FileExistsError, FileNotFoundError, OSError, ValueError)):
                raise ServiceException(message=f'文件存储异常处理失败：{exc}') from exc
            raise

        if file_id:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_id,
                'reconcile',
                'completed',
                operation_detail={
                    'issueId': issue_id,
                    'issueType': issue_type,
                    'action': handle.action,
                    'reason': handle.reason,
                    **operation_location,
                },
            )
        return CrudResponseModel(is_success=True, message='文件存储异常处理成功')

    @classmethod
    async def _apply_reconcile_action(
        cls,
        query_db: AsyncSession,
        issue: SysFileReconcileIssue,
        handle: FileReconcileHandleModel,
        current_user: CurrentUserModel,
        current_time: datetime,
    ) -> tuple[str | None, tuple[str, str, str, str] | None]:
        """执行已通过状态校验的对账处理动作。"""
        user = cls._require_admin(current_user)
        performed_move: tuple[str, str, str, str] | None = None
        file_id = issue.file_id
        if handle.action in {'ignore', 'reopen'}:
            status = 'ignored' if handle.action == 'ignore' else 'open'
            cls._mark_issue_handled(issue, status, handle, user.user_name, current_time)
        elif handle.action in {'restore_source', 'move_to_trash', 'move_to_expected_root'}:
            performed_move = await cls._move_issue_file(issue)
            cls._mark_issue_handled(issue, 'resolved', handle, user.user_name, current_time)
        elif handle.action == 'quarantine_file':
            performed_move = await cls._quarantine_issue_file(issue)
            cls._mark_issue_handled(issue, 'quarantined', handle, user.user_name, current_time)
        elif handle.action == 'restore_quarantine':
            performed_move = await cls._restore_quarantine_file(issue)
            cls._mark_issue_handled(issue, 'open', handle, user.user_name, current_time)
        elif handle.action == 'delete_quarantine':
            await cls._delete_quarantine_file(issue)
            cls._mark_issue_handled(issue, 'resolved', handle, user.user_name, current_time)
        elif handle.action == 'accept_current':
            file_id = await cls._accept_current_file(
                query_db,
                issue,
                user.user_name,
                handle.reason,
                current_time,
            )
        else:
            file_id = await cls._register_orphan_file(
                query_db,
                issue,
                handle,
                current_user,
                current_time,
            )
        return file_id, performed_move

    @classmethod
    async def _move_issue_file(
        cls,
        issue: SysFileReconcileIssue,
    ) -> tuple[str, str, str, str]:
        move = cls._get_issue_move_locations(issue)
        await asyncio.to_thread(FileReconcileUtil.move_regular_file, *move)
        return move

    @classmethod
    async def _quarantine_issue_file(
        cls,
        issue: SysFileReconcileIssue,
    ) -> tuple[str, str, str, str]:
        source_root, source_key = cls._require_location(issue.actual_root, issue.actual_key)
        quarantine_key = f'{issue.issue_id}/{source_root}/{source_key}'
        move = (source_root, source_key, 'quarantine', quarantine_key)
        await asyncio.to_thread(FileReconcileUtil.move_regular_file, *move)
        issue.quarantine_key = quarantine_key
        return move

    @classmethod
    async def _restore_quarantine_file(
        cls,
        issue: SysFileReconcileIssue,
    ) -> tuple[str, str, str, str]:
        if not issue.quarantine_key:
            raise ServiceException(message='隔离区文件路径不存在')
        target_root, target_key = cls._require_location(issue.actual_root, issue.actual_key)
        move = ('quarantine', issue.quarantine_key, target_root, target_key)
        await asyncio.to_thread(FileReconcileUtil.move_regular_file, *move)
        issue.quarantine_key = None
        return move

    @staticmethod
    async def _delete_quarantine_file(issue: SysFileReconcileIssue) -> None:
        if not issue.quarantine_key:
            raise ServiceException(message='隔离区文件路径不存在')
        await asyncio.to_thread(FileReconcileUtil.delete_quarantine_file, issue.quarantine_key)
        issue.quarantine_key = None

    @classmethod
    async def _accept_current_file(
        cls,
        query_db: AsyncSession,
        issue: SysFileReconcileIssue,
        handled_by: str,
        reason: str,
        current_time: datetime,
    ) -> str:
        if not issue.file_id:
            raise ServiceException(message='异常未关联文件信息')
        file_info = await FileInfoDao.get_file_info_for_reconcile(query_db, issue.file_id)
        if file_info is None:
            raise ServiceException(message='异常关联的文件信息不存在')
        root_name, relative_key = cls._require_location(
            issue.actual_root or issue.expected_root,
            issue.actual_key or issue.expected_key,
        )
        file_path = FileReconcileUtil.resolve_location(root_name, relative_key)
        file_size, file_hash = await asyncio.to_thread(
            FileReconcileUtil.calculate_file_integrity,
            file_path,
        )
        file_info.file_size = file_size
        file_info.file_hash = file_hash
        file_info.update_by = handled_by
        file_info.update_time = current_time
        await FileInfoDao.resolve_file_integrity_issues(
            query_db,
            issue.file_id,
            current_time,
            handled_by,
            reason,
        )
        return issue.file_id

    @classmethod
    async def _register_orphan_file(
        cls,
        query_db: AsyncSession,
        issue: SysFileReconcileIssue,
        handle: FileReconcileHandleModel,
        current_user: CurrentUserModel,
        current_time: datetime,
    ) -> str:
        user = cls._require_admin(current_user)
        access_type, storage_key = cls._require_location(issue.actual_root, issue.actual_key)
        if issue.issue_type != 'orphan_file' or access_type not in {'public', 'private'}:
            raise ServiceException(message='仅公开或受保护存储区的孤立文件可以登记')
        if await FileInfoDao.get_file_info_by_storage_key(query_db, storage_key, access_type) is not None:
            raise ServiceException(message='该物理文件已登记到文件信息表')
        stored_name = storage_key.rsplit('/', 1)[-1]
        extension = UploadUtil.get_file_extension(stored_name)
        if extension not in UploadConfig.DEFAULT_ALLOWED_EXTENSION:
            raise ServiceException(message='孤立文件扩展名不在允许范围内')
        original_name = UploadUtil.get_original_filename(handle.original_name or stored_name)
        if not original_name or UploadUtil.get_file_extension(original_name) != extension:
            raise ServiceException(message='原始文件名扩展名必须与物理文件一致')
        file_path = FileReconcileUtil.resolve_location(access_type, storage_key)
        file_size, file_hash = await asyncio.to_thread(
            FileReconcileUtil.calculate_file_integrity,
            file_path,
        )
        file_id = str(uuid.uuid4())
        await FileInfoDao.add_file_info_dao(
            query_db,
            FileInfoModel(
                fileId=file_id,
                originalName=original_name,
                storedName=stored_name,
                storageKey=storage_key,
                storageType='local',
                accessType=access_type,
                uploadUserId=user.user_id,
                ownerUserId=user.user_id,
                deptId=user.dept_id,
                extension=extension,
                contentType=mimetypes.guess_type(original_name)[0] or 'application/octet-stream',
                fileSize=file_size,
                fileHash=file_hash,
                status='active',
                createBy=user.user_name,
                createTime=current_time,
                updateBy=user.user_name,
                updateTime=current_time,
                delFlag='0',
            ),
        )
        issue.file_id = file_id
        cls._mark_issue_handled(issue, 'resolved', handle, user.user_name, current_time)
        return file_id

    @classmethod
    def _get_available_actions(
        cls,
        issue: SysFileReconcileIssue | FileReconcileIssueModel,
    ) -> list[FileReconcileAction]:
        if issue.quarantine_key or issue.status == 'quarantined':
            return ['restore_quarantine', 'delete_quarantine']
        if issue.status == 'ignored':
            return ['reopen']
        if issue.status != 'open':
            return []
        actions: list[FileReconcileAction] = ['ignore']
        actions.extend(cls.ISSUE_ACTIONS.get(issue.issue_type, []))
        if issue.issue_type == 'orphan_file' and issue.actual_root not in {'public', 'private'}:
            actions = [action for action in actions if action != 'register_orphan']
        return actions

    @classmethod
    def _get_issue_move_locations(
        cls,
        issue: SysFileReconcileIssue,
    ) -> tuple[str, str, str, str]:
        source_root, source_key = cls._require_location(issue.actual_root, issue.actual_key)
        target_root, target_key = cls._require_location(issue.expected_root, issue.expected_key)
        return source_root, source_key, target_root, target_key

    @staticmethod
    def _require_location(root_name: str | None, relative_key: str | None) -> tuple[str, str]:
        if not root_name or not relative_key:
            raise ServiceException(message='异常记录缺少可处理的存储位置')
        if root_name not in {'public', 'private', 'trash', 'quarantine'}:
            raise ServiceException(message='异常记录的存储区域不合法')
        return root_name, relative_key

    @staticmethod
    def _mark_issue_handled(
        issue: SysFileReconcileIssue,
        status: str,
        handle: FileReconcileHandleModel,
        handled_by: str,
        handled_time: datetime,
    ) -> None:
        issue.status = status
        issue.handle_action = handle.action
        issue.handle_reason = handle.reason
        issue.handled_by = handled_by
        issue.handled_time = handled_time

    @classmethod
    async def _rollback_file_move(cls, move: tuple[str, str, str, str]) -> None:
        source_root, source_key, target_root, target_key = move
        try:
            await asyncio.to_thread(
                FileReconcileUtil.move_regular_file,
                target_root,
                target_key,
                source_root,
                source_key,
            )
        except Exception:
            logger.exception('文件存储异常处理数据库回滚后，物理文件补偿失败')

    @staticmethod
    def _build_run_data(reconcile_run: SysFileReconcileRun) -> dict[str, Any]:
        return {
            'run_id': reconcile_run.run_id,
            'trigger_type': reconcile_run.trigger_type,
            'status': reconcile_run.status,
            'check_hash': reconcile_run.check_hash == '1',
            'scanned_file_count': reconcile_run.scanned_file_count or 0,
            'scanned_storage_count': reconcile_run.scanned_storage_count or 0,
            'issue_count': reconcile_run.issue_count or 0,
            'new_issue_count': reconcile_run.new_issue_count or 0,
            'resolved_issue_count': reconcile_run.resolved_issue_count or 0,
            'started_by': reconcile_run.started_by,
            'started_time': reconcile_run.started_time,
            'finished_time': reconcile_run.finished_time,
            'error_message': reconcile_run.error_message,
        }

    @staticmethod
    def _require_admin(current_user: CurrentUserModel | None) -> Any:
        user = current_user.user if current_user else None
        if user is None or not user.admin or not user.user_name:
            raise ServiceException(message='仅系统管理员可以使用文件存储对账功能')
        return user
