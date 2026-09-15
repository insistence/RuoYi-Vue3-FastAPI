from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from common.mixin import DateRangeQueryMixin
from common.types import ApiUtcDateTime
from config.env import AppConfig
from utils.cron_util import MyCronTrigger
from utils.time_util import TimezoneUtil


class JobModel(BaseModel):
    """
    定时任务调度表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_id: int | None = Field(default=None, gt=0, description='任务ID')
    job_name: str | None = Field(default=None, max_length=64, description='任务名称（同一业务分组内唯一）')
    job_group: str = Field(default='default', min_length=1, max_length=64, description='业务分组')
    job_store: Literal['default', 'sqlalchemy', 'redis'] = Field(default='default', description='调度存储')
    job_executor: Literal['default', 'processpool'] = Field(default='default', description='任务执行器')
    invoke_target: str | None = Field(default=None, description='调用目标字符串')
    job_args: list[JsonValue] = Field(default_factory=list, description='位置参数（JSON数组）')
    job_kwargs: dict[str, JsonValue] = Field(default_factory=dict, description='关键字参数（JSON对象）')
    cron_expression: str | None = Field(default=None, description='cron执行表达式')
    time_zone: str = Field(default_factory=lambda: AppConfig.app_timezone, description='cron时区（IANA）')
    misfire_grace_time: int | None = Field(
        default=1, ge=1, le=2147483647, strict=True, description='允许延迟秒数，null表示不限'
    )
    coalesce: bool = Field(default=False, strict=True, description='积压时是否只执行最近一次')
    max_instances: int = Field(default=1, ge=1, le=2147483647, strict=True, description='任务最大并发数')
    status: Literal['0', '1'] = Field(default='1', description='状态（0正常 1暂停），新增默认暂停')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: ApiUtcDateTime | None = Field(default=None, description='更新时间')
    remark: str | None = Field(default=None, description='备注信息')
    cron_next_time: ApiUtcDateTime | None = Field(
        default=None, description='Cron理论预览时刻（UTC）', json_schema_extra={'readOnly': True}
    )
    next_run_time: ApiUtcDateTime | None = Field(
        default=None, description='最近观测的实际下次调度时刻（UTC）', json_schema_extra={'readOnly': True}
    )
    schedule_observed_time: ApiUtcDateTime | None = Field(
        default=None, description='调度观测时刻（UTC）', json_schema_extra={'readOnly': True}
    )
    config_version: int | None = Field(default=None, description='最新配置版本', json_schema_extra={'readOnly': True})
    applied_version: int | None = Field(
        default=None, description='已应用配置版本', json_schema_extra={'readOnly': True}
    )
    sync_status: Literal['pending', 'applied', 'failed'] | None = Field(
        default=None,
        description='调度同步状态',
        json_schema_extra={'readOnly': True},
    )
    sync_error: str | None = Field(default=None, description='最近同步错误', json_schema_extra={'readOnly': True})
    applied_time: ApiUtcDateTime | None = Field(
        default=None,
        description='最近应用时刻',
        json_schema_extra={'readOnly': True},
    )

    @model_validator(mode='before')
    @classmethod
    def reject_legacy_policy(cls, value: Any) -> Any:
        """
        拒绝已替换的策略字段，避免旧调用方的配置被静默忽略

        :param value: 接口传入的任务数据
        :return: 使用当前字段的任务数据
        """
        if isinstance(value, dict) and {'misfirePolicy', 'misfire_policy', 'concurrent'} & value.keys():
            raise ValueError('请使用 misfireGraceTime、coalesce 和 maxInstances 配置执行策略')
        return value

    @field_validator('time_zone')
    @classmethod
    def validate_time_zone(cls, value: str) -> str:
        """
        校验任务IANA时区名称

        :param value: 任务时区名称
        :return: 去除首尾空白后的有效时区名称
        """
        return TimezoneUtil.validate_timezone_name(value)

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression(cls, value: str | None) -> str | None:
        """
        校验Quartz表达式语法

        :param value: 待校验的Cron表达式
        :return: 去除首尾空白后的表达式，未填写时保留None
        """
        if value is not None:
            MyCronTrigger.from_crontab(value, 'UTC')
            return value.strip()
        return value

    @NotBlank(field_name='invoke_target', message='调用目标字符串不能为空')
    @Size(field_name='invoke_target', min_length=0, max_length=500, message='调用目标字符串长度不能超过500个字符')
    def get_invoke_target(self) -> str | None:
        return self.invoke_target

    @NotBlank(field_name='cron_expression', message='Cron执行表达式不能为空')
    @Size(field_name='cron_expression', min_length=0, max_length=255, message='Cron执行表达式不能超过255个字符')
    def get_cron_expression(self) -> str | None:
        return self.cron_expression

    @Size(field_name='remark', min_length=0, max_length=500, message='备注长度不能超过500个字符')
    def get_remark(self) -> str | None:
        return self.remark

    def validate_fields(self) -> None:
        self.get_invoke_target()
        self.get_cron_expression()
        self.get_remark()


class JobPreviewRequest(BaseModel):
    """
    Cron执行时刻预览请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    cron_expression: str = Field(min_length=1, max_length=255, description='Cron 表达式')
    time_zone: str = Field(default_factory=lambda: AppConfig.app_timezone, description='任务 IANA 时区')
    start_time: ApiUtcDateTime | None = Field(default=None, description='起算时刻，省略时使用服务端当前时刻')
    count: int = Field(default=5, ge=1, le=20, description='返回的执行时刻数量')

    @field_validator('time_zone')
    @classmethod
    def validate_time_zone(cls, value: str) -> str:
        """
        校验任务IANA时区名称

        :param value: 任务时区名称
        :return: 去除首尾空白后的有效时区名称
        """
        return TimezoneUtil.validate_timezone_name(value)

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression(cls, value: str) -> str:
        """
        校验Quartz表达式语法

        :param value: 待校验的Cron表达式
        :return: 去除首尾空白后的表达式
        """
        MyCronTrigger.from_crontab(value, 'UTC')
        return value.strip()


class JobPreviewResult(BaseModel):
    """
    Cron执行时刻预览结果模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    time_zone: str = Field(description='任务IANA时区名称')
    start_time: ApiUtcDateTime = Field(description='本次预览的UTC起算时刻')
    next_run_times: list[ApiUtcDateTime] = Field(description='未来UTC执行时刻列表')


class JobLogModel(BaseModel):
    """
    定时任务调度日志表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_log_id: int | None = Field(default=None, description='任务日志ID')
    job_id: int | None = Field(default=None, description='逻辑任务ID')
    execution_id: str | None = Field(default=None, description='执行ID')
    job_name: str | None = Field(default=None, description='任务名称')
    job_group: str | None = Field(default=None, description='任务组名')
    job_store: str | None = Field(default=None, description='调度存储快照')
    job_executor: str | None = Field(default=None, description='任务执行器')
    invoke_target: str | None = Field(default=None, description='调用目标字符串')
    job_args: list[JsonValue] | None = Field(default=None, description='位置参数快照（JSON数组）')
    job_kwargs: dict[str, JsonValue] | None = Field(default=None, description='关键字参数快照（JSON对象）')
    job_trigger: str | None = Field(default=None, description='任务触发器')
    time_zone: str | None = Field(default=None, description='任务时区快照（IANA）')
    job_message: str | None = Field(default=None, description='日志信息')
    status: Literal['0', '1'] | None = Field(default=None, description='执行状态（0正常 1失败）')
    exception_info: str | None = Field(default=None, description='异常信息')
    scheduled_time: ApiUtcDateTime | None = Field(default=None, description='计划执行时刻')
    start_time: ApiUtcDateTime | None = Field(default=None, description='执行开始时间')
    end_time: ApiUtcDateTime | None = Field(default=None, description='执行结束时间')
    run_duration_ms: int | None = Field(default=None, ge=0, description='实际执行耗时（毫秒）')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')


class JobQueryModel(DateRangeQueryMixin, BaseModel):
    """
    定时任务管理不分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_name: str | None = Field(default=None, description='任务名称')
    job_group: str | None = Field(default=None, description='业务分组')
    status: Literal['0', '1'] | None = Field(default=None, description='任务状态')
    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class JobPageQueryModel(JobQueryModel):
    """
    定时任务管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class EditJobModel(JobModel):
    """
    编辑定时任务模型
    """

    job_id: int = Field(gt=0, description='任务ID')
    type: str | None = Field(default=None, description='操作类型')


class JobRunModel(BaseModel):
    """
    手动执行请求，仅按稳定任务ID读取已保存配置
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_id: int = Field(gt=0, description='任务ID')


class ChangeJobStatusModel(JobRunModel):
    """
    修改任务状态请求
    """

    status: Literal['0', '1'] = Field(description='状态（0正常 1暂停）')


class DeleteJobModel(BaseModel):
    """
    删除定时任务模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_ids: str = Field(description='需要删除的定时任务ID')


class JobLogQueryModel(DateRangeQueryMixin, BaseModel):
    """
    定时任务日志不分页查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_id: int | None = Field(default=None, gt=0, description='逻辑任务ID')
    execution_id: str | None = Field(default=None, pattern='^[0-9a-f]{32}$', description='执行ID')
    job_name: str | None = Field(default=None, description='任务名称快照')
    job_group: str | None = Field(default=None, description='业务分组快照')
    status: Literal['0', '1'] | None = Field(default=None, description='执行状态')
    begin_time: str | None = Field(default=None, description='开始时间')
    end_time: str | None = Field(default=None, description='结束时间')


class JobLogPageQueryModel(JobLogQueryModel):
    """
    定时任务日志管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteJobLogModel(BaseModel):
    """
    删除定时任务日志模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_log_ids: str = Field(description='需要删除的定时任务日志ID')
