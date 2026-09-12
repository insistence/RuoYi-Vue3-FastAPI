from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from common.types import ApiUtcDateTime


class JobExecutionModel(BaseModel):
    """
    可供管理界面查询的执行状态，不包含执行占用凭据
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    execution_id: str = Field(description='执行ID')
    job_id: int = Field(description='任务ID')
    job_name: str | None = Field(default=None, description='任务名称')
    source: Literal['manual', 'cron'] = Field(description='执行来源（manual手动 cron定时）')
    status: Literal[
        'pending', 'submitted', 'running', 'success', 'failed', 'rejected', 'missed', 'cancelled', 'unknown'
    ] = Field(description='执行状态')
    message: str | None = Field(default=None, description='执行结果或未执行原因')
    requested_by: str | None = Field(default=None, description='手动执行提交者')
    create_time: ApiUtcDateTime | None = Field(default=None, description='创建时间')
    scheduled_time: ApiUtcDateTime | None = Field(default=None, description='计划执行时刻')
    start_time: ApiUtcDateTime | None = Field(default=None, description='实际执行开始时刻')
    end_time: ApiUtcDateTime | None = Field(default=None, description='实际执行结束时刻')
    run_duration_ms: int | None = Field(default=None, description='实际执行耗时（毫秒）')


class JobExecutionQueryModel(BaseModel):
    """
    执行记录分页查询条件
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_id: int | None = Field(default=None, gt=0, description='任务ID')
    execution_id: str | None = Field(
        default=None, min_length=32, max_length=32, pattern='^[0-9a-f]{32}$', description='执行ID'
    )
    status: str | None = Field(default=None, description='执行状态')
    source: Literal['manual', 'cron'] | None = Field(default=None, description='执行来源（manual手动 cron定时）')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=100, description='每页记录数')


class JobSyncModel(BaseModel):
    """
    单任务配置版本和实际应用状态
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_id: int = Field(description='任务ID')
    config_version: int = Field(description='最新配置版本')
    applied_version: int = Field(description='已应用配置版本')
    sync_status: Literal['pending', 'applied', 'failed'] = Field(
        description='调度同步状态（pending待同步 applied已生效 failed同步失败）'
    )
    sync_error: str | None = Field(default=None, description='最近同步错误')
    deleted: bool = Field(description='任务是否已删除')
    applied_time: ApiUtcDateTime | None = Field(default=None, description='最近应用时刻')
    next_run_time: ApiUtcDateTime | None = Field(default=None, description='最近观测的实际下次调度时刻')
    schedule_observed_time: ApiUtcDateTime | None = Field(default=None, description='Leader调度观测时刻')
    update_time: ApiUtcDateTime | None = Field(default=None, description='更新时间')


class JobSyncQueryModel(BaseModel):
    """
    包含删除记录的同步状态分页查询条件
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_id: int | None = Field(default=None, gt=0, description='任务ID')
    sync_status: Literal['pending', 'applied', 'failed'] | None = Field(
        default=None, description='调度同步状态（pending待同步 applied已生效 failed同步失败）'
    )
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=100, description='每页记录数')


class JobMutationResult(BaseModel):
    """
    业务修改已保存与调度配置已生效分开表达的响应数据
    """

    model_config = ConfigDict(alias_generator=to_camel)

    saved: bool = Field(description='业务修改是否已提交')
    sync_status: Literal['pending', 'applied', 'failed'] = Field(
        description='调度同步状态（pending待同步 applied已生效 failed同步失败）'
    )
    sync_error: str | None = Field(default=None, description='最近同步错误')
    jobs: list[JobSyncModel] = Field(description='各任务的调度同步结果')
