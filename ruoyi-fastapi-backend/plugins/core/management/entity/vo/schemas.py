from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from plugins.core.state import PluginStatus
from plugins.core.types import PluginConfigValue

PluginEnabled = Literal['0', '1']


class PluginModel(BaseModel):
    """
    插件信息表对应 pydantic 模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str = Field(description='插件ID')
    plugin_name: str | None = Field(default=None, description='插件名称')
    version: str | None = Field(default=None, description='当前源码版本')
    installed_version: str | None = Field(default=None, description='已安装版本')
    enabled: PluginEnabled | None = Field(default=None, description='是否启用（0启用 1停用）')
    status: PluginStatus | None = Field(default=None, description='插件状态')
    source: str | None = Field(default=None, description='插件来源')
    backend_path: str | None = Field(default=None, description='后端插件相对路径')
    frontend_path: str | None = Field(default=None, description='前端插件相对路径')
    last_error: str | None = Field(default=None, description='最近一次错误信息')
    description: str | None = Field(default=None, description='插件说明')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    remark: str | None = Field(default=None, description='备注')
    capability: dict[str, Any] | None = Field(default=None, description='插件运行时操作能力')
    metadata: dict[str, Any] | None = Field(default=None, description='插件展示元数据')
    backend: dict[str, Any] | None = Field(default=None, description='插件后端声明摘要')
    frontend: dict[str, Any] | None = Field(default=None, description='插件前端声明摘要')
    permissions: list[dict[str, Any]] | None = Field(default=None, description='插件权限声明')
    config: list[dict[str, Any]] | None = Field(default=None, description='插件配置声明')
    dependencies: dict[str, Any] | None = Field(default=None, description='插件依赖声明')
    plugin_dependencies: list[dict[str, Any]] | None = Field(default=None, description='插件依赖声明')


class PluginQueryModel(BaseModel):
    """
    插件管理不分页查询模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str | None = Field(default=None, description='插件ID')
    plugin_name: str | None = Field(default=None, description='插件名称')
    enabled: PluginEnabled | None = Field(default=None, description='是否启用（0启用 1停用）')
    status: PluginStatus | None = Field(default=None, description='插件状态')
    source: str | None = Field(default=None, description='插件来源')


class PluginPageQueryModel(PluginQueryModel):
    """
    插件管理分页查询模型。

    模型字段说明通过 Field 的 description 声明。
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class PluginBatchActionModel(BaseModel):
    """
    插件批量执行请求体模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    operation: Literal['install', 'enable', 'upgrade'] = Field(description='批量操作类型：install、enable 或 upgrade')
    plugin_ids: list[str] | None = Field(default=None, description='插件ID列表')
    dry_run: bool = Field(default=True, description='是否仅预演操作')
    continue_on_error: bool = Field(default=False, description='失败后是否继续执行后续插件')


class PluginOperationLogModel(BaseModel):
    """
    插件批量操作审计日志表对应 pydantic 模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    operation_id: int | None = Field(default=None, description='操作日志ID')
    operation: str = Field(description='操作类型')
    plugin_ids: str | None = Field(default=None, description='目标插件ID JSON')
    dry_run: PluginEnabled = Field(default='1', description='是否预演（0是 1否）')
    continue_on_error: PluginEnabled = Field(default='1', description='失败后是否继续（0是 1否）')
    status: str = Field(description='执行状态')
    summary: str | None = Field(default=None, description='执行汇总JSON')
    result: str | None = Field(default=None, description='完整执行结果JSON')
    create_time: datetime | None = Field(default=None, description='创建时间')
    remark: str | None = Field(default=None, description='备注')


class PluginOperationLogQueryModel(BaseModel):
    """
    插件批量操作审计日志不分页查询模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str | None = Field(default=None, description='插件ID')
    operation: str | None = Field(default=None, description='操作类型')
    status: str | None = Field(default=None, description='执行状态')
    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class PluginOperationLogPageQueryModel(PluginOperationLogQueryModel):
    """
    插件批量操作审计日志分页查询模型。

    模型字段说明通过 Field 的 description 声明。
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class PluginOperationLogExportQueryModel(PluginOperationLogQueryModel):
    """
    插件批量操作审计日志导出查询模型。

    模型字段说明通过 Field 的 description 声明。
    """

    export_limit: int = Field(default=5000, ge=1, le=50000, description='导出最大记录数')


class PluginOperationLogDetailModel(BaseModel):
    """
    插件批量操作审计日志详情模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    operation_id: int | None = Field(default=None, description='操作日志ID')
    operation: str = Field(description='操作类型')
    plugin_ids: list[str] = Field(default_factory=list, description='目标插件ID列表')
    dry_run: bool = Field(default=False, description='是否预演')
    continue_on_error: bool = Field(default=False, description='失败后是否继续')
    status: str = Field(description='执行状态')
    summary: dict[str, object] = Field(default_factory=dict, description='执行汇总')
    result: dict[str, object] = Field(default_factory=dict, description='完整执行结果')
    create_time: datetime | None = Field(default=None, description='创建时间')
    remark: str | None = Field(default=None, description='备注')


class PluginOperationLogRetentionModel(BaseModel):
    """
    插件批量操作审计日志保留策略模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    retention_days: int = Field(default=180, ge=0, description='审计日志保留天数，0表示清理当前时间之前的全部日志')
    dry_run: bool = Field(default=True, description='是否仅预览清理结果')


class PluginOperationLogRetentionResultModel(BaseModel):
    """
    插件批量操作审计日志保留策略执行结果模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    retention_days: int = Field(description='审计日志保留天数')
    cutoff_time: datetime = Field(description='清理截止时间')
    matched_count: int = Field(description='匹配保留策略的日志数量')
    deleted_count: int = Field(description='已删除日志数量')
    dry_run: bool = Field(description='是否仅预览清理结果')


class PluginMenuModel(BaseModel):
    """
    插件和菜单关联表对应 pydantic 模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str = Field(description='插件ID')
    menu_id: int = Field(description='菜单ID')
    menu_key: str = Field(description='插件内菜单自然键')
    create_time: datetime | None = Field(default=None, description='创建时间')


class PluginMigrationModel(BaseModel):
    """
    插件 migration 执行历史表对应 pydantic 模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str = Field(description='插件ID')
    migration_path: str = Field(description='migration 相对路径')
    migration_checksum: str = Field(description='migration 内容校验值')
    version: str | None = Field(default=None, description='执行时插件版本')
    statement_count: int = Field(default=0, description='SQL 语句数量')
    status: str = Field(default='success', description='执行状态')
    error_message: str | None = Field(default=None, description='失败错误信息')
    attempt_count: int = Field(default=0, description='尝试次数')
    started_time: datetime | None = Field(default=None, description='最近开始时间')
    finished_time: datetime | None = Field(default=None, description='最近结束时间')
    create_time: datetime | None = Field(default=None, description='执行时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class PluginMigrationRecoveryModel(BaseModel):
    """
    插件 migration 人工恢复请求模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    migration_path: str = Field(description='migration 相对路径')
    note: str | None = Field(default=None, description='人工恢复备注')


class PluginConfigModel(BaseModel):
    """
    插件配置表对应 pydantic 模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    plugin_id: str = Field(description='插件ID')
    config_key: str = Field(description='配置键名')
    config_label: str | None = Field(default=None, description='配置展示名称')
    config_type: str = Field(default='string', description='配置值类型')
    config_value: str | None = Field(default=None, description='配置值')
    default_value: str | None = Field(default=None, description='默认配置值')
    required: PluginEnabled = Field(default='1', description='是否必填（0是 1否）')
    secret: PluginEnabled = Field(default='1', description='是否敏感（0是 1否）')
    options: str | None = Field(default=None, description='配置选项JSON')
    description: str | None = Field(default=None, description='配置说明')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class PluginConfigValueModel(BaseModel):
    """
    插件配置值模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    key: str = Field(description='配置键名')
    label: str | None = Field(default=None, description='配置展示名称')
    type: str = Field(default='string', description='配置值类型')
    value: PluginConfigValue = Field(default=None, description='配置值')
    default: PluginConfigValue = Field(default=None, description='默认配置值')
    required: bool = Field(default=False, description='是否必填')
    secret: bool = Field(default=False, description='是否敏感')
    group: str = Field(default='default', description='配置分组')
    order: int = Field(default=0, description='配置排序值')
    placeholder: str = Field(default='', description='配置输入占位提示')
    min: float | None = Field(default=None, description='数字配置最小值')
    max: float | None = Field(default=None, description='数字配置最大值')
    pattern: str | None = Field(default=None, description='字符串配置正则表达式')
    options: list[dict[str, PluginConfigValue]] = Field(default_factory=list, description='配置选项列表')
    description: str | None = Field(default=None, description='配置说明')


class PluginConfigUpdateModel(BaseModel):
    """
    插件配置更新模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    values: dict[str, PluginConfigValue] = Field(default_factory=dict, description='待更新的插件配置键值')


class PluginConfigImportModel(BaseModel):
    """
    插件配置导入模型。

    模型字段说明通过 Field 的 description 声明。
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    values: dict[str, PluginConfigValue] = Field(default_factory=dict, description='待导入的插件配置键值')
