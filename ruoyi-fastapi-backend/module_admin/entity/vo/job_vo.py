from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Union, Optional, List
from datetime import datetime
from module_admin.annotation.pydantic_annotation import as_query, as_form


class JobModel(BaseModel):
    """
    定时任务调度表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_id: Optional[int] = None
    job_name: Optional[str] = None
    job_group: Optional[str] = None
    job_executor: Optional[str] = None
    invoke_target: Optional[str] = None
    job_args: Optional[str] = None
    job_kwargs: Optional[str] = None
    cron_expression: Optional[str] = None
    misfire_policy: Optional[str] = None
    concurrent: Optional[str] = None
    status: Optional[str] = None
    create_by: Optional[str] = None
    create_time: Optional[datetime] = None
    update_by: Optional[str] = None
    update_time: Optional[datetime] = None
    remark: Optional[str] = None


class JobLogModel(BaseModel):
    """
    定时任务调度日志表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    job_log_id: Optional[int] = None
    job_name: Optional[str] = None
    job_group: Optional[str] = None
    job_executor: Optional[str] = None
    invoke_target: Optional[str] = None
    job_args: Optional[str] = None
    job_kwargs: Optional[str] = None
    job_trigger: Optional[str] = None
    job_message: Optional[str] = None
    status: Optional[str] = None
    exception_info: Optional[str] = None
    create_time: Optional[datetime] = None


class JobQueryModel(JobModel):
    """
    定时任务管理不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class JobPageQueryModel(JobQueryModel):
    """
    定时任务管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class EditJobModel(JobModel):
    """
    编辑定时任务模型
    """
    type: Optional[str] = None


class DeleteJobModel(BaseModel):
    """
    删除定时任务模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    job_ids: str


class JobLogQueryModel(JobLogModel):
    """
    定时任务日志不分页查询模型
    """
    begin_time: Optional[str] = None
    end_time: Optional[str] = None


@as_query
@as_form
class JobLogPageQueryModel(JobLogQueryModel):
    """
    定时任务日志管理分页查询模型
    """
    page_num: int = 1
    page_size: int = 10


class DeleteJobLogModel(BaseModel):
    """
    删除定时任务日志模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    job_log_ids: str
