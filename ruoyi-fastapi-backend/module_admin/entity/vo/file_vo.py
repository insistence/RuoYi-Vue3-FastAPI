from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class FileInfoModel(BaseModel):
    """
    文件信息表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    file_id: str = Field(max_length=36, description='文件ID')
    original_name: str = Field(max_length=255, description='原始文件名')
    stored_name: str = Field(max_length=255, description='存储文件名')
    storage_key: str = Field(max_length=500, description='存储相对路径')
    storage_type: str = Field(default='local', max_length=20, description='存储类型')
    access_type: Literal['public', 'private'] = Field(description='访问类型')
    upload_user_id: int | None = Field(default=None, description='上传用户ID')
    owner_user_id: int | None = Field(default=None, description='所有者用户ID')
    dept_id: int | None = Field(default=None, description='所属部门ID')
    acl_version: int = Field(default=0, ge=0, description='访问控制版本')
    business_type: str | None = Field(default=None, max_length=50, description='业务类型')
    business_id: str | None = Field(default=None, max_length=64, description='业务ID')
    extension: str = Field(max_length=20, description='文件扩展名')
    content_type: str | None = Field(default=None, max_length=255, description='内容类型')
    file_size: int = Field(default=0, ge=0, description='文件大小')
    file_hash: str = Field(min_length=64, max_length=64, description='文件SHA-256')
    status: Literal['active', 'deleted', 'purging'] = Field(default='active', description='文件状态')
    create_by: str | None = Field(default=None, max_length=64, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, max_length=64, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    expire_time: datetime | None = Field(default=None, description='过期时间')
    deleted_time: datetime | None = Field(default=None, description='移入回收站时间')
    del_flag: Literal['0', '1'] = Field(default='0', description='删除标志')


class FileInfoDisplayModel(FileInfoModel):
    """
    文件信息展示模型
    """

    owner_name: str | None = Field(default=None, description='所有者用户名称')
    dept_name: str | None = Field(default=None, description='所属部门名称')
    acl_nearest_expire_time: datetime | None = Field(default=None, description='最近ACL过期时间')
    acl_entry_count: int = Field(default=0, ge=0, description='ACL配置数量')
    reference_count: int = Field(default=0, ge=0, description='业务引用数量')
    storage_status: Literal['normal', 'missing', 'quarantined', 'invalid'] = Field(
        default='normal', description='物理存储状态'
    )


class FileReferenceModel(BaseModel):
    """
    文件业务引用表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    reference_id: int | None = Field(default=None, description='引用ID')
    file_id: str = Field(description='文件ID')
    business_type: str = Field(description='业务类型')
    business_id: str = Field(description='业务ID')
    business_name: str | None = Field(default=None, description='业务名称')
    retention_expire_time: datetime | None = Field(default=None, description='保留期限到期时间')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    legacy: bool = Field(default=False, description='是否为文件主表兼容引用')


class FileRetentionPolicyModel(BaseModel):
    """
    文件业务保留策略模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, str_strip_whitespace=True)

    business_type: str = Field(min_length=1, max_length=50, description='业务类型')
    retention_days: int = Field(ge=1, le=36500, description='保留天数')
    status: Literal['0', '1'] = Field(default='0', description='状态（0启用 1停用）')
    remark: str | None = Field(default=None, max_length=500, description='备注')
    create_by: str | None = Field(default=None, max_length=64, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, max_length=64, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')


class FileRetentionNoticeModel(BaseModel):
    """
    文件保留期限提醒展示模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    notice_id: int = Field(description='提醒ID')
    file_id: str = Field(description='文件ID')
    original_name: str = Field(description='原始文件名')
    owner_name: str | None = Field(default=None, description='所有者用户名称')
    dept_name: str | None = Field(default=None, description='所属部门名称')
    notice_type: Literal['expiring', 'expired'] = Field(description='提醒类型')
    expire_time: datetime = Field(description='文件过期时间')
    status: Literal['0', '1'] = Field(description='状态（0未读 1已读）')
    create_time: datetime = Field(description='创建时间')
    read_by: str | None = Field(default=None, description='读取者')
    read_time: datetime | None = Field(default=None, description='读取时间')


class FileRetentionNoticeQueryModel(BaseModel):
    """
    文件保留期限提醒不分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    original_name: str | None = Field(default=None, description='原始文件名')
    notice_type: Literal['expiring', 'expired'] | None = Field(default=None, description='提醒类型')
    status: Literal['0', '1'] | None = Field(default=None, description='提醒状态')


class FileRetentionNoticePageQueryModel(FileRetentionNoticeQueryModel):
    """
    文件保留期限提醒分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class FileRetentionScanModel(BaseModel):
    """
    文件保留期限提醒扫描结果模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    expiring_count: int = Field(default=0, ge=0, description='新增即将到期提醒数')
    expired_count: int = Field(default=0, ge=0, description='新增已到期提醒数')


class FileAccessLogModel(BaseModel):
    """
    文件访问审计表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    audit_id: int | None = Field(default=None, description='审计ID')
    file_id: str = Field(description='文件ID')
    action: Literal['upload', 'download', 'acl_update', 'transfer', 'delete', 'restore', 'purge'] = Field(
        description='操作类型'
    )
    actor_user_id: int | None = Field(default=None, description='操作用户ID')
    actor_name: str | None = Field(default=None, description='操作用户名称')
    result: Literal['allowed', 'denied', 'completed', 'failed'] = Field(description='操作结果')
    request_id: str | None = Field(default=None, description='请求ID')
    trace_id: str | None = Field(default=None, description='链路ID')
    ip_address: str | None = Field(default=None, description='客户端地址')
    user_agent: str | None = Field(default=None, description='用户代理')
    bytes_sent: int = Field(default=0, description='发送字节数')
    error_message: str | None = Field(default=None, description='失败原因')
    operation_detail: str | None = Field(default=None, description='操作详情')
    access_time: datetime | None = Field(default=None, description='访问时间')


class FileAclModel(BaseModel):
    """
    文件访问控制表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    acl_id: int | None = Field(default=None, description='访问控制ID')
    file_id: str = Field(description='文件ID')
    subject_type: Literal['user', 'role', 'dept'] = Field(description='主体类型')
    subject_id: int = Field(description='主体ID')
    subject_name: str | None = Field(default=None, description='主体名称')
    permission: Literal['download'] = Field(default='download', description='权限类型')
    effect: Literal['allow', 'deny'] = Field(description='授权效果')
    include_children: bool = Field(default=False, description='部门是否包含下级')
    expire_time: datetime | None = Field(default=None, description='授权过期时间')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')


class FileAclItemModel(BaseModel):
    """
    文件访问控制配置项模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    subject_type: Literal['user', 'role', 'dept'] = Field(description='主体类型')
    subject_id: int = Field(gt=0, description='主体ID')
    effect: Literal['allow', 'deny'] = Field(description='授权效果')
    include_children: bool = Field(default=False, description='部门是否包含下级')
    expire_time: datetime | None = Field(default=None, description='授权过期时间')


class FileAclListModel(BaseModel):
    """
    文件访问控制列表模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    acl_version: int = Field(ge=0, description='访问控制版本')
    entries: list[FileAclModel] = Field(default_factory=list, description='访问控制配置项')


class SaveFileAclModel(BaseModel):
    """
    保存文件访问控制模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    acl_version: int = Field(ge=0, description='访问控制版本')
    entries: list[FileAclItemModel] = Field(default_factory=list, max_length=100, description='访问控制配置项')


class BatchSaveFileAclModel(BaseModel):
    """
    批量保存文件访问控制模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    file_ids: str = Field(description='需要授权的文件ID')
    entries: list[FileAclItemModel] = Field(default_factory=list, max_length=100, description='访问控制配置项')


class FileAclSubjectOptionModel(BaseModel):
    """
    文件访问控制主体选项模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    subject_id: int = Field(description='主体ID')
    subject_name: str = Field(description='主体名称')
    dept_id: int | None = Field(default=None, description='所属部门ID')


class FileInfoQueryModel(BaseModel):
    """
    文件信息管理不分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    original_name: str | None = Field(default=None, description='原始文件名')
    access_type: Literal['public', 'private'] | None = Field(default=None, description='访问类型')
    status: Literal['active', 'deleted', 'purging'] | None = Field(default=None, description='文件状态')
    create_by: str | None = Field(default=None, description='上传用户名称')
    owner_name: str | None = Field(default=None, description='所有者用户名称')
    dept_id: int | None = Field(default=None, gt=0, description='所属部门ID')
    expiration_status: Literal['permanent', 'valid', 'expiring', 'expired'] | None = Field(
        default=None, description='文件过期状态'
    )
    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class FileInfoPageQueryModel(FileInfoQueryModel):
    """
    文件信息管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class FileStatsModel(BaseModel):
    """
    文件管理统计模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    total_count: int = Field(default=0, ge=0, description='文件总数')
    total_size: int = Field(default=0, ge=0, description='文件总大小')
    public_size: int = Field(default=0, ge=0, description='公开文件总大小')
    private_size: int = Field(default=0, ge=0, description='受保护文件总大小')
    active_count: int = Field(default=0, ge=0, description='有效文件数')
    deleted_count: int = Field(default=0, ge=0, description='回收站文件数')
    expired_count: int = Field(default=0, ge=0, description='已过期文件数')
    retention_expiring_count: int = Field(default=0, ge=0, description='保留期限即将到期文件数')
    acl_expiring_count: int = Field(default=0, ge=0, description='ACL即将过期文件数')


class FileAccessLogQueryModel(BaseModel):
    """
    文件访问审计不分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    action: Literal['upload', 'download', 'acl_update', 'transfer', 'delete', 'restore', 'purge'] | None = Field(
        default=None, description='操作类型'
    )
    result: Literal['allowed', 'denied', 'completed', 'failed'] | None = Field(default=None, description='操作结果')
    actor_name: str | None = Field(default=None, description='操作用户名称')
    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class FileAccessLogPageQueryModel(FileAccessLogQueryModel):
    """
    文件访问审计分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteFileModel(BaseModel):
    """
    删除文件模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    file_ids: str = Field(description='需要删除的文件ID')


class TransferFileModel(BaseModel):
    """
    转移文件模型
    """

    model_config = ConfigDict(alias_generator=to_camel, str_strip_whitespace=True)

    owner_user_id: int = Field(gt=0, description='新所有者用户ID')
    dept_id: int = Field(gt=0, description='新所属部门ID')
    reason: str = Field(min_length=1, max_length=500, description='转移原因')
