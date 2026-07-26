import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, true
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import CrudResponseModel, PageModel
from exceptions.exception import ServiceException
from module_admin.dao.file_business_dao import (
    FileReferenceDao,
    FileRetentionNoticeDao,
    FileRetentionPolicyDao,
)
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import (
    SysFileInfo,
    SysFileReference,
    SysFileRetentionNotice,
    SysFileRetentionPolicy,
)
from module_admin.entity.vo.file_vo import (
    FileReferenceModel,
    FileRetentionNoticePageQueryModel,
    FileRetentionPolicyModel,
    FileRetentionScanModel,
)
from utils.common_util import CamelCaseUtil


class FileReferenceService:
    """
    文件业务引用服务层
    """

    MAX_REFERENCE_FILES = 100

    @classmethod
    async def get_file_reference_list_services(
        cls,
        query_db: AsyncSession,
        file_id: str,
        file_data_scope_sql: ColumnElement,
    ) -> list[FileReferenceModel]:
        """
        获取文件业务引用列表service

        :param query_db: orm对象
        :param file_id: 文件ID
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 文件业务引用列表
        """
        file_info = await FileInfoDao.get_file_management_detail_by_id(query_db, file_id, file_data_scope_sql)
        if file_info is None:
            raise ServiceException(message='文件信息不存在或超出数据权限')
        file_reference_list = await FileReferenceDao.get_file_reference_list(query_db, file_id)
        result = [FileReferenceModel(**CamelCaseUtil.transform_result(item)) for item in file_reference_list]
        business_type = file_info.get('business_type')
        business_id = file_info.get('business_id')
        reference_keys = {(item.business_type, item.business_id) for item in file_reference_list}
        if business_type and business_id and (business_type, business_id) not in reference_keys:
            result.insert(
                0,
                FileReferenceModel(
                    fileId=file_id,
                    businessType=business_type,
                    businessId=business_id,
                    legacy=True,
                ),
            )
        return result

    @classmethod
    async def replace_business_file_references_services(
        cls,
        query_db: AsyncSession,
        business_type: str,
        business_id: str,
        file_ids: list[str],
        create_by: str,
        file_data_scope_sql: ColumnElement,
        business_name: str | None = None,
    ) -> None:
        """
        在调用方业务事务内全量替换文件引用service

        :param query_db: orm对象
        :param business_type: 业务类型
        :param business_id: 业务ID
        :param file_ids: 文件ID列表
        :param create_by: 创建者
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param business_name: 业务名称
        :return: None
        """
        normalized_business_type = cls._normalize_text(business_type, '业务类型', 50, required=True)
        normalized_business_id = cls._normalize_text(business_id, '业务ID', 64, required=True)
        normalized_business_name = cls._normalize_text(business_name, '业务名称', 255)
        normalized_create_by = cls._normalize_text(create_by, '创建者', 64) or ''
        normalized_file_ids = cls._normalize_file_ids(file_ids)
        file_infos = []
        if normalized_file_ids:
            file_infos = await FileInfoDao.get_file_infos_by_ids_for_update(
                query_db,
                normalized_file_ids,
                file_data_scope_sql,
            )
            if len(file_infos) != len(normalized_file_ids):
                raise ServiceException(message='部分引用文件不存在或已失效')
        create_time = datetime.now()
        retention_policy = await FileRetentionPolicyService.get_enabled_file_retention_policy_services(
            query_db,
            normalized_business_type,
        )
        if retention_policy and any(
            getattr(file_info, 'access_type', 'private') != 'private' for file_info in file_infos
        ):
            raise ServiceException(message='配置保留策略的业务只能引用受保护文件')
        retention_expire_time = (
            create_time + timedelta(days=retention_policy.retention_days) if retention_policy else None
        )
        file_reference_list = [
            SysFileReference(
                file_id=file_id,
                business_type=normalized_business_type,
                business_id=normalized_business_id,
                business_name=normalized_business_name,
                retention_expire_time=retention_expire_time,
                create_by=normalized_create_by,
                create_time=create_time,
            )
            for file_id in normalized_file_ids
        ]
        await FileReferenceDao.replace_business_file_references(
            query_db,
            normalized_business_type,
            normalized_business_id,
            file_reference_list,
        )

    @classmethod
    async def remove_business_file_references_services(
        cls,
        query_db: AsyncSession,
        business_type: str,
        business_id: str,
    ) -> None:
        """
        在调用方业务事务内解除业务对象的全部文件引用service

        :param query_db: orm对象
        :param business_type: 业务类型
        :param business_id: 业务ID
        :return: None
        """
        await cls.replace_business_file_references_services(
            query_db,
            business_type,
            business_id,
            [],
            create_by='',
            file_data_scope_sql=true(),
        )

    @classmethod
    async def get_file_reference_count_map_services(
        cls,
        query_db: AsyncSession,
        file_infos: list[SysFileInfo] | list[dict],
    ) -> dict[str, int]:
        """
        获取包含兼容字段的文件业务引用数量映射service

        :param query_db: orm对象
        :param file_infos: 文件信息列表
        :return: 文件ID和业务引用数量映射
        """
        file_ids = [str(cls._get_value(item, 'file_id', 'fileId')) for item in file_infos]
        reference_count_map = await FileReferenceDao.get_file_reference_count_map(query_db, file_ids)
        for file_info in file_infos:
            file_id = str(cls._get_value(file_info, 'file_id', 'fileId'))
            business_type = cls._get_value(file_info, 'business_type', 'businessType')
            business_id = cls._get_value(file_info, 'business_id', 'businessId')
            if business_type and business_id:
                reference_count_map[file_id] = reference_count_map.get(file_id, 0) + 1
        return reference_count_map

    @classmethod
    def _normalize_file_ids(cls, file_ids: list[str]) -> list[str]:
        """校验并标准化文件ID列表。"""
        if len(file_ids) > cls.MAX_REFERENCE_FILES:
            raise ServiceException(message=f'单个业务对象最多引用{cls.MAX_REFERENCE_FILES}个文件')
        try:
            normalized_file_ids = [str(uuid.UUID(str(file_id))) for file_id in file_ids]
        except (AttributeError, TypeError, ValueError) as exc:
            raise ServiceException(message='文件ID格式错误') from exc
        return list(dict.fromkeys(normalized_file_ids))

    @staticmethod
    def _normalize_text(value: str | None, field_name: str, max_length: int, required: bool = False) -> str | None:
        """校验并标准化业务引用文本字段。"""
        normalized_value = value.strip() if value else None
        if required and not normalized_value:
            raise ServiceException(message=f'{field_name}不能为空')
        if normalized_value and (len(normalized_value) > max_length or not normalized_value.isprintable()):
            raise ServiceException(message=f'{field_name}格式错误')
        return normalized_value

    @staticmethod
    def _get_value(item: SysFileInfo | dict, snake_name: str, camel_name: str) -> Any:
        """兼容读取ORM对象和查询字典。"""
        if isinstance(item, dict):
            return item.get(snake_name) if snake_name in item else item.get(camel_name)
        return getattr(item, snake_name)


class FileRetentionPolicyService:
    """
    文件业务保留策略服务层
    """

    @classmethod
    async def get_file_retention_policy_list_services(
        cls,
        query_db: AsyncSession,
    ) -> list[FileRetentionPolicyModel]:
        """
        获取文件业务保留策略列表service

        :param query_db: orm对象
        :return: 文件业务保留策略列表
        """
        policy_list = await FileRetentionPolicyDao.get_file_retention_policy_list(query_db)
        return [FileRetentionPolicyModel(**CamelCaseUtil.transform_result(policy)) for policy in policy_list]

    @classmethod
    async def get_enabled_file_retention_policy_services(
        cls,
        query_db: AsyncSession,
        business_type: str,
    ) -> FileRetentionPolicyModel | None:
        """
        获取已启用的文件业务保留策略service

        :param query_db: orm对象
        :param business_type: 业务类型
        :return: 文件业务保留策略
        """
        policy = await FileRetentionPolicyDao.get_file_retention_policy_by_business_type(
            query_db,
            business_type,
            enabled_only=True,
        )
        return FileRetentionPolicyModel(**CamelCaseUtil.transform_result(policy)) if policy else None

    @classmethod
    async def add_file_retention_policy_services(
        cls,
        query_db: AsyncSession,
        policy: FileRetentionPolicyModel,
        operator_name: str,
    ) -> CrudResponseModel:
        """
        新增文件业务保留策略service

        :param query_db: orm对象
        :param policy: 文件业务保留策略
        :param operator_name: 操作人名称
        :return: 操作结果
        """
        cls._validate_business_type(policy.business_type)
        exists_policy = await FileRetentionPolicyDao.get_file_retention_policy_by_business_type(
            query_db,
            policy.business_type,
        )
        if exists_policy:
            raise ServiceException(message=f'业务类型{policy.business_type}的保留策略已存在')
        current_time = datetime.now()
        db_policy = SysFileRetentionPolicy(
            **policy.model_dump(
                exclude={
                    'create_by',
                    'create_time',
                    'update_by',
                    'update_time',
                }
            ),
            create_by=operator_name,
            create_time=current_time,
            update_by=operator_name,
            update_time=current_time,
        )
        try:
            await FileRetentionPolicyDao.add_file_retention_policy(query_db, db_policy)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception:
            await query_db.rollback()
            raise

    @classmethod
    async def edit_file_retention_policy_services(
        cls,
        query_db: AsyncSession,
        policy: FileRetentionPolicyModel,
        operator_name: str,
    ) -> CrudResponseModel:
        """
        修改文件业务保留策略service

        :param query_db: orm对象
        :param policy: 文件业务保留策略
        :param operator_name: 操作人名称
        :return: 操作结果
        """
        cls._validate_business_type(policy.business_type)
        exists_policy = await FileRetentionPolicyDao.get_file_retention_policy_by_business_type(
            query_db,
            policy.business_type,
        )
        if exists_policy is None:
            raise ServiceException(message='文件业务保留策略不存在')
        policy_data = policy.model_dump(
            exclude={
                'business_type',
                'create_by',
                'create_time',
                'update_by',
                'update_time',
            }
        )
        policy_data.update(update_by=operator_name, update_time=datetime.now())
        try:
            await FileRetentionPolicyDao.edit_file_retention_policy(
                query_db,
                policy.business_type,
                policy_data,
            )
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='修改成功')
        except Exception:
            await query_db.rollback()
            raise

    @classmethod
    async def delete_file_retention_policy_services(
        cls,
        query_db: AsyncSession,
        business_type: str,
    ) -> CrudResponseModel:
        """
        删除文件业务保留策略service

        :param query_db: orm对象
        :param business_type: 业务类型
        :return: 操作结果
        """
        normalized_business_type = business_type.strip()
        cls._validate_business_type(normalized_business_type)
        exists_policy = await FileRetentionPolicyDao.get_file_retention_policy_by_business_type(
            query_db,
            normalized_business_type,
        )
        if exists_policy is None:
            raise ServiceException(message='文件业务保留策略不存在')
        try:
            await FileRetentionPolicyDao.delete_file_retention_policy(query_db, normalized_business_type)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='删除成功')
        except Exception:
            await query_db.rollback()
            raise

    @staticmethod
    def _validate_business_type(business_type: str) -> None:
        """校验业务类型。"""
        if not business_type.isprintable():
            raise ServiceException(message='业务类型格式错误')


class FileRetentionNoticeService:
    """
    文件保留期限提醒服务层
    """

    DEFAULT_REMIND_DAYS = 7
    MAX_REMIND_DAYS = 365
    MAX_BATCH_SIZE = 1000

    @classmethod
    async def scan_file_retention_notices_services(
        cls,
        query_db: AsyncSession,
        remind_days: int = DEFAULT_REMIND_DAYS,
        batch_size: int = 500,
        file_data_scope_sql: ColumnElement | None = None,
    ) -> FileRetentionScanModel:
        """
        扫描并生成文件保留期限提醒service

        :param query_db: orm对象
        :param remind_days: 提前提醒天数
        :param batch_size: 单类提醒单批处理数量
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 扫描结果
        """
        cls._validate_scan_parameters(remind_days, batch_size)
        current_time = datetime.now()
        reminder_deadline = current_time + timedelta(days=remind_days)
        data_scope_sql = file_data_scope_sql if file_data_scope_sql is not None else true()
        try:
            expired_files = await FileRetentionNoticeDao.get_missing_notice_candidates(
                query_db,
                'expired',
                current_time,
                reminder_deadline,
                batch_size,
                data_scope_sql,
            )
            expiring_files = await FileRetentionNoticeDao.get_missing_notice_candidates(
                query_db,
                'expiring',
                current_time,
                reminder_deadline,
                batch_size,
                data_scope_sql,
            )
            await FileRetentionNoticeDao.invalidate_expiring_notices(
                query_db,
                [file_info.file_id for file_info in expired_files],
            )
            notice_list = [
                SysFileRetentionNotice(
                    file_id=file_info.file_id,
                    notice_type=notice_type,
                    expire_time=file_info.expire_time,
                    status='0',
                    create_time=current_time,
                )
                for notice_type, file_infos in (
                    ('expired', expired_files),
                    ('expiring', expiring_files),
                )
                for file_info in file_infos
            ]
            await FileRetentionNoticeDao.add_file_retention_notices(query_db, notice_list)
            await query_db.commit()
            return FileRetentionScanModel(
                expiringCount=len(expiring_files),
                expiredCount=len(expired_files),
            )
        except Exception:
            await query_db.rollback()
            raise

    @classmethod
    async def get_file_retention_notice_list_services(
        cls,
        query_db: AsyncSession,
        query_object: FileRetentionNoticePageQueryModel,
        file_data_scope_sql: ColumnElement,
        is_page: bool = True,
    ) -> PageModel | list[dict]:
        """
        获取文件保留期限提醒列表service

        :param query_db: orm对象
        :param query_object: 查询参数
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: 文件保留期限提醒列表
        """
        return await FileRetentionNoticeDao.get_file_retention_notice_list(
            query_db,
            query_object,
            file_data_scope_sql,
            is_page,
        )

    @classmethod
    async def mark_file_retention_notices_read_services(
        cls,
        query_db: AsyncSession,
        notice_ids: str,
        read_by: str,
        file_data_scope_sql: ColumnElement,
    ) -> CrudResponseModel:
        """
        标记文件保留期限提醒为已读service

        :param query_db: orm对象
        :param notice_ids: 提醒ID字符串
        :param read_by: 读取者
        :param file_data_scope_sql: 文件数据权限对应的查询sql语句
        :return: 操作结果
        """
        parsed_notice_ids = cls._parse_notice_ids(notice_ids)
        scoped_notice_ids = await FileRetentionNoticeDao.get_notice_ids_in_data_scope_for_update(
            query_db,
            parsed_notice_ids,
            file_data_scope_sql,
        )
        if len(scoped_notice_ids) != len(parsed_notice_ids):
            await query_db.rollback()
            raise ServiceException(message='部分提醒不存在、已失效或超出数据权限')
        try:
            await FileRetentionNoticeDao.mark_file_retention_notices_read(
                query_db,
                parsed_notice_ids,
                read_by,
                datetime.now(),
            )
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='提醒已标记为已读')
        except Exception:
            await query_db.rollback()
            raise

    @classmethod
    def _validate_scan_parameters(cls, remind_days: int, batch_size: int) -> None:
        """校验提醒扫描参数。"""
        if remind_days < 1 or remind_days > cls.MAX_REMIND_DAYS:
            raise ServiceException(message=f'提前提醒天数必须在1到{cls.MAX_REMIND_DAYS}之间')
        if batch_size < 1 or batch_size > cls.MAX_BATCH_SIZE:
            raise ServiceException(message=f'单批处理数量必须在1到{cls.MAX_BATCH_SIZE}之间')

    @staticmethod
    def _parse_notice_ids(notice_ids: str) -> list[int]:
        """解析并校验提醒ID。"""
        try:
            parsed_notice_ids = list(dict.fromkeys(int(item.strip()) for item in notice_ids.split(',') if item.strip()))
        except (AttributeError, ValueError) as exc:
            raise ServiceException(message='提醒ID格式不正确') from exc
        if not parsed_notice_ids or any(notice_id <= 0 for notice_id in parsed_notice_ids):
            raise ServiceException(message='提醒ID格式不正确')
        return parsed_notice_ids
