import json
from datetime import datetime
from typing import Any, Literal

from fastapi import Request
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel
from exceptions.exception import ServiceException
from middlewares.trace_middleware.ctx import TraceCtx
from module_admin.dao.file_access_dao import FileAccessLogDao, FileAclDao
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileAcl
from module_admin.entity.vo.dept_vo import DeptTreeModel
from module_admin.entity.vo.file_vo import (
    BatchSaveFileAclModel,
    FileAccessLogModel,
    FileAclListModel,
    FileAclModel,
    FileAclSubjectOptionModel,
    SaveFileAclModel,
)
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.dept_service import DeptService
from module_admin.service.log_service import LogQueueService
from utils.client_ip_util import ClientIPUtil
from utils.file_util import FileUtil
from utils.log_util import LogSanitizer, logger


class FileAclService:
    @classmethod
    async def get_file_acl_list_services(
        cls,
        query_db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
    ) -> FileAclListModel:
        """
        获取文件访问控制列表service

        :param query_db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 文件访问控制列表及版本
        """
        file_info = await FileInfoDao.get_file_info_detail_by_id(query_db, file_id, file_data_scope_sql)
        if file_info is None:
            raise ServiceException(message='文件信息不存在或超出数据权限')
        file_acl_list = await FileAclDao.get_file_acl_list(query_db, file_id)
        subject_name_map = await FileAclDao.get_acl_subject_name_map(
            query_db,
            cls._group_acl_subject_ids(file_acl_list),
            user_data_scope_sql,
            dept_data_scope_sql,
        )
        return FileAclListModel(
            aclVersion=file_info.acl_version,
            entries=[
                FileAclModel(
                    aclId=file_acl.acl_id,
                    fileId=file_acl.file_id,
                    subjectType=file_acl.subject_type,
                    subjectId=file_acl.subject_id,
                    subjectName=subject_name_map.get(
                        (file_acl.subject_type, file_acl.subject_id),
                        f'不可用或无权查看主体（{file_acl.subject_id}）',
                    ),
                    permission=file_acl.permission,
                    effect=file_acl.effect,
                    includeChildren=file_acl.include_children == '1',
                    expireTime=file_acl.expire_time,
                    createBy=file_acl.create_by,
                    createTime=file_acl.create_time,
                )
                for file_acl in file_acl_list
            ],
        )

    @classmethod
    async def search_file_acl_subjects_services(
        cls,
        query_db: AsyncSession,
        subject_type: str,
        keyword: str | None,
        limit: int,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
    ) -> list[FileAclSubjectOptionModel]:
        """
        查询文件访问控制主体选项service

        :param query_db: orm对象
        :param subject_type: 主体类型
        :param keyword: 查询关键字
        :param limit: 返回数量限制
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 主体选项列表
        """
        subject_list = await FileAclDao.search_acl_subjects(
            query_db,
            subject_type,
            keyword,
            limit,
            user_data_scope_sql,
            dept_data_scope_sql,
        )
        return [FileAclSubjectOptionModel.model_validate(item, by_name=True) for item in subject_list]

    @classmethod
    async def get_file_acl_dept_tree_services(
        cls,
        query_db: AsyncSession,
        dept_data_scope_sql: ColumnElement,
    ) -> list[DeptTreeModel]:
        """
        获取文件授权部门树service

        :param query_db: orm对象
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :return: 部门树
        """
        dept_list = await FileAclDao.get_acl_dept_list(query_db, dept_data_scope_sql)
        return DeptService.list_to_tree(dept_list)

    @classmethod
    async def save_file_acl_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        file_id: str,
        save_file_acl: SaveFileAclModel,
        file_data_scope_sql: ColumnElement,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        保存文件访问控制service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param file_id: 文件ID
        :param save_file_acl: 文件访问控制参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :param request: Request对象
        :return: 保存结果
        """
        file_info = await FileInfoDao.get_file_info_by_id_for_update(query_db, file_id, file_data_scope_sql)
        if file_info is None:
            raise ServiceException(message='文件信息不存在、已删除或超出数据权限')
        if file_info.access_type != 'private':
            raise ServiceException(message='公开文件不支持配置访问权限')
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')
        current_acl_version = file_info.acl_version or 0
        if save_file_acl.acl_version != current_acl_version:
            await query_db.rollback()
            raise ServiceException(message='文件权限已被其他用户修改，请刷新后重试')

        current_time = datetime.now()
        unique_subjects = set()
        subject_ids: dict[str, set[int]] = {'user': set(), 'role': set(), 'dept': set()}
        normalized_expire_times = []
        for entry in save_file_acl.entries:
            subject_key = (entry.subject_type, entry.subject_id)
            if subject_key in unique_subjects:
                raise ServiceException(message='同一授权主体不能重复配置')
            unique_subjects.add(subject_key)
            subject_ids[entry.subject_type].add(entry.subject_id)
            expire_time = entry.expire_time
            if expire_time and expire_time.tzinfo:
                expire_time = expire_time.astimezone().replace(tzinfo=None)
            normalized_expire_times.append(expire_time)
            if expire_time and expire_time <= current_time:
                raise ServiceException(message='授权过期时间必须晚于当前时间')

        subject_name_map = await FileAclDao.get_acl_subject_name_map(
            query_db,
            subject_ids,
            user_data_scope_sql,
            dept_data_scope_sql,
        )
        if len(subject_name_map) != len(unique_subjects):
            raise ServiceException(message='部分授权主体不存在、已停用或超出数据权限')

        file_acl_list = [
            SysFileAcl(
                file_id=file_id,
                subject_type=entry.subject_type,
                subject_id=entry.subject_id,
                permission='download',
                effect=entry.effect,
                include_children='1' if entry.subject_type == 'dept' and entry.include_children else '0',
                expire_time=expire_time,
                create_by=user.user_name,
                create_time=current_time,
                del_flag='0',
            )
            for entry, expire_time in zip(save_file_acl.entries, normalized_expire_times, strict=True)
        ]
        try:
            await FileAclDao.replace_file_acl_list(query_db, file_id, file_acl_list)
            file_info.acl_version = current_acl_version + 1
            file_info.update_by = user.user_name
            file_info.update_time = current_time
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_id,
                'acl_update',
                'failed',
                error_message=exc.__class__.__name__,
                operation_detail={'previousAclVersion': current_acl_version},
            )
            raise
        subject_type_counts = {
            subject_type: len(subject_ids[subject_type]) for subject_type in ('user', 'role', 'dept')
        }
        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            file_id,
            'acl_update',
            'completed',
            operation_detail={
                'previousAclVersion': current_acl_version,
                'newAclVersion': current_acl_version + 1,
                'entryCount': len(save_file_acl.entries),
                'allowCount': sum(entry.effect == 'allow' for entry in save_file_acl.entries),
                'denyCount': sum(entry.effect == 'deny' for entry in save_file_acl.entries),
                'subjectTypeCounts': subject_type_counts,
            },
        )
        return CrudResponseModel(is_success=True, message='文件权限保存成功')

    @classmethod
    async def batch_save_file_acl_services(
        cls,
        query_db: AsyncSession,
        current_user: CurrentUserModel,
        batch_save_file_acl: BatchSaveFileAclModel,
        file_data_scope_sql: ColumnElement,
        user_data_scope_sql: ColumnElement,
        dept_data_scope_sql: ColumnElement,
        request: Request | None = None,
    ) -> CrudResponseModel:
        """
        批量保存文件访问控制service

        :param query_db: orm对象
        :param current_user: 当前用户对象
        :param batch_save_file_acl: 批量文件访问控制参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param user_data_scope_sql: 用户数据权限对应的查询sql语句
        :param dept_data_scope_sql: 部门数据权限对应的查询sql语句
        :param request: Request对象
        :return: 保存结果
        """
        file_ids = FileUtil.parse_file_ids(batch_save_file_acl.file_ids)
        user = current_user.user
        if user is None or not user.user_name:
            raise ServiceException(message='无法获取当前用户信息')
        file_infos = await FileInfoDao.get_file_infos_by_ids_for_update(query_db, file_ids, file_data_scope_sql)
        if len(file_infos) != len(file_ids):
            await query_db.rollback()
            raise ServiceException(message='部分文件不存在、已删除或超出数据权限')
        if any(file_info.access_type != 'private' for file_info in file_infos):
            await query_db.rollback()
            raise ServiceException(message='批量授权仅支持受保护文件')

        current_time = datetime.now()
        unique_subjects = set()
        subject_ids: dict[str, set[int]] = {'user': set(), 'role': set(), 'dept': set()}
        normalized_entries = []
        for entry in batch_save_file_acl.entries:
            subject_key = (entry.subject_type, entry.subject_id)
            if subject_key in unique_subjects:
                raise ServiceException(message='同一授权主体不能重复配置')
            unique_subjects.add(subject_key)
            subject_ids[entry.subject_type].add(entry.subject_id)
            expire_time = entry.expire_time
            if expire_time and expire_time.tzinfo:
                expire_time = expire_time.astimezone().replace(tzinfo=None)
            if expire_time and expire_time <= current_time:
                raise ServiceException(message='授权过期时间必须晚于当前时间')
            normalized_entries.append((entry, expire_time))

        subject_name_map = await FileAclDao.get_acl_subject_name_map(
            query_db,
            subject_ids,
            user_data_scope_sql,
            dept_data_scope_sql,
        )
        if len(subject_name_map) != len(unique_subjects):
            raise ServiceException(message='部分授权主体不存在、已停用或超出数据权限')

        acl_versions = {file_info.file_id: file_info.acl_version or 0 for file_info in file_infos}
        file_acl_list = [
            SysFileAcl(
                file_id=file_id,
                subject_type=entry.subject_type,
                subject_id=entry.subject_id,
                permission='download',
                effect=entry.effect,
                include_children='1' if entry.subject_type == 'dept' and entry.include_children else '0',
                expire_time=expire_time,
                create_by=user.user_name,
                create_time=current_time,
                del_flag='0',
            )
            for file_id in file_ids
            for entry, expire_time in normalized_entries
        ]
        try:
            await FileAclDao.replace_file_acl_lists(query_db, file_ids, file_acl_list)
            for file_info in file_infos:
                file_info.acl_version = acl_versions[file_info.file_id] + 1
                file_info.update_by = user.user_name
                file_info.update_time = current_time
            await query_db.commit()
        except Exception as exc:
            await query_db.rollback()
            for file_id in file_ids:
                await FileAuditService.enqueue_file_audit(
                    request,
                    current_user,
                    file_id,
                    'acl_update',
                    'failed',
                    error_message=exc.__class__.__name__,
                    operation_detail={'batch': True, 'previousAclVersion': acl_versions[file_id]},
                )
            raise

        subject_type_counts = {
            subject_type: len(subject_ids[subject_type]) for subject_type in ('user', 'role', 'dept')
        }
        for file_id in file_ids:
            await FileAuditService.enqueue_file_audit(
                request,
                current_user,
                file_id,
                'acl_update',
                'completed',
                operation_detail={
                    'batch': True,
                    'previousAclVersion': acl_versions[file_id],
                    'newAclVersion': acl_versions[file_id] + 1,
                    'entryCount': len(batch_save_file_acl.entries),
                    'allowCount': sum(entry.effect == 'allow' for entry in batch_save_file_acl.entries),
                    'denyCount': sum(entry.effect == 'deny' for entry in batch_save_file_acl.entries),
                    'subjectTypeCounts': subject_type_counts,
                },
            )
        return CrudResponseModel(is_success=True, message='文件权限批量保存成功')

    @staticmethod
    def _group_acl_subject_ids(file_acl_list: list[SysFileAcl]) -> dict[str, set[int]]:
        """
        按类型分组文件访问控制主体ID

        :param file_acl_list: 文件访问控制列表
        :return: 主体ID分组
        """
        subject_ids: dict[str, set[int]] = {'user': set(), 'role': set(), 'dept': set()}
        for file_acl in file_acl_list:
            if file_acl.subject_type in subject_ids:
                subject_ids[file_acl.subject_type].add(file_acl.subject_id)
        return subject_ids


class FileAuditService:
    """
    文件审计服务层
    """

    @classmethod
    async def enqueue_file_audit(
        cls,
        request: Request | None,
        current_user: CurrentUserModel,
        file_id: str,
        action: Literal['upload', 'download', 'acl_update', 'transfer', 'delete', 'restore', 'purge', 'reconcile'],
        result: Literal['allowed', 'denied', 'completed', 'failed'],
        bytes_sent: int = 0,
        error_message: str = '',
        operation_detail: dict[str, Any] | None = None,
    ) -> None:
        """
        将文件审计事件写入日志队列

        :param request: Request对象
        :param current_user: 当前用户对象
        :param file_id: 文件ID
        :param action: 操作类型
        :param result: 操作结果
        :param bytes_sent: 已发送字节数
        :param error_message: 失败原因
        :param operation_detail: 操作详情
        :return: None
        """
        if request is None:
            return
        try:
            user = current_user.user
            file_access_log = FileAccessLogModel(
                fileId=file_id,
                action=action,
                actorUserId=user.user_id if user else None,
                actorName=user.user_name if user else '',
                result=result,
                requestId=TraceCtx.get_request_id(),
                traceId=TraceCtx.get_trace_id(),
                ipAddress=ClientIPUtil.get_client_ip(request),
                userAgent=(request.headers.get('User-Agent') or '')[:500],
                bytesSent=bytes_sent,
                errorMessage=error_message[:500],
                operationDetail=cls._serialize_operation_detail(operation_detail),
                accessTime=datetime.now(),
            )
            await LogQueueService.enqueue_file_access_log(
                request,
                file_access_log,
                source=f'file:{file_id}:{action}:{result}',
            )
        except Exception as exc:
            logger.error(f'文件审计写入队列失败: {exc}')

    @classmethod
    async def add_system_file_audit(
        cls,
        query_db: AsyncSession,
        file_id: str,
        action: Literal['purge'],
        result: Literal['completed', 'failed'],
        error_message: str = '',
        operation_detail: dict[str, Any] | None = None,
    ) -> None:
        """
        在后台任务事务内写入文件审计记录

        :param query_db: orm对象
        :param file_id: 文件ID
        :param action: 操作类型
        :param result: 操作结果
        :param error_message: 失败原因
        :param operation_detail: 操作详情
        :return: None
        """
        file_access_log = FileAccessLogModel(
            fileId=file_id,
            action=action,
            actorName='system',
            result=result,
            errorMessage=error_message[:500],
            operationDetail=cls._serialize_operation_detail(operation_detail),
            accessTime=datetime.now(),
        )
        await FileAccessLogDao.add_file_access_log_dao(query_db, file_access_log)

    @staticmethod
    def _serialize_operation_detail(operation_detail: dict[str, Any] | None) -> str:
        """
        序列化文件操作详情

        :param operation_detail: 操作详情
        :return: 序列化后的操作详情
        """
        if not operation_detail:
            return ''
        sanitized_detail = LogSanitizer.sanitize_data(operation_detail)
        return json.dumps(sanitized_detail, ensure_ascii=False, default=str, separators=(',', ':'))
