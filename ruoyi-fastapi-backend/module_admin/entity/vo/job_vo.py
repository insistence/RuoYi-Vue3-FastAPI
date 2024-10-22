from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class JobModel(BaseModel):
    """
    定时任务调度表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_id: Optional[int] = Field(default=None, description='任务ID')
    job_name: Optional[str] = Field(default=None, description='任务名称')
    job_group: Optional[str] = Field(default=None, description='任务组名')
    job_executor: Optional[str] = Field(default=None, description='任务执行器')
    invoke_target: Optional[str] = Field(default=None, description='调用目标字符串')
    job_args: Optional[str] = Field(default=None, description='位置参数')
    job_kwargs: Optional[str] = Field(default=None, description='关键字参数')
    cron_expression: Optional[str] = Field(default=None, description='cron执行表达式')
    misfire_policy: Optional[Literal['1', '2', '3']] = Field(
        default=None, description='计划执行错误策略（1立即执行 2执行一次 3放弃执行）'
    )
    concurrent: Optional[Literal['0', '1']] = Field(default=None, description='是否并发执行（0允许 1禁止）')
    status: Optional[Literal['0', '1']] = Field(default=None, description='状态（0正常 1暂停）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注信息')

    @NotBlank(field_name='invoke_target', message='调用目标字符串不能为空')
    @Size(field_name='invoke_target', min_length=0, max_length=500, message='调用目标字符串长度不能超过500个字符')
    def get_invoke_target(self):
        return self.invoke_target

    @NotBlank(field_name='cron_expression', message='Cron执行表达式不能为空')
    @Size(field_name='cron_expression', min_length=0, max_length=255, message='Cron执行表达式不能超过255个字符')
    def get_cron_expression(self):
        return self.cron_expression

    def validate_fields(self):
        self.get_invoke_target()
        self.get_cron_expression()


class JobLogModel(BaseModel):
    """
    定时任务调度日志表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_log_id: Optional[int] = Field(default=None, description='任务日志ID')
    job_name: Optional[str] = Field(default=None, description='任务名称')
    job_group: Optional[str] = Field(default=None, description='任务组名')
    job_executor: Optional[str] = Field(default=None, description='任务执行器')
    invoke_target: Optional[str] = Field(default=None, description='调用目标字符串')
    job_args: Optional[str] = Field(default=None, description='位置参数')
    job_kwargs: Optional[str] = Field(default=None, description='关键字参数')
    job_trigger: Optional[str] = Field(default=None, description='任务触发器')
    job_message: Optional[str] = Field(default=None, description='日志信息')
    status: Optional[Literal['0', '1']] = Field(default=None, description='执行状态（0正常 1失败）')
    exception_info: Optional[str] = Field(default=None, description='异常信息')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')


class JobQueryModel(JobModel):
    """
    定时任务管理不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
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

    type: Optional[str] = Field(default=None, description='操作类型')


class DeleteJobModel(BaseModel):
    """
    删除定时任务模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    job_ids: str = Field(description='需要删除的定时任务ID')


class JobLogQueryModel(JobLogModel):
    """
    定时任务日志不分页查询模型
    """

    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
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
