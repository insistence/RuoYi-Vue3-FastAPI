from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Literal, Optional
from module_admin.annotation.pydantic_annotation import as_query


class OperLogModel(BaseModel):
    """
    操作日志表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    oper_id: Optional[int] = Field(default=None, description='日志主键')
    title: Optional[str] = Field(default=None, description='模块标题')
    business_type: Optional[Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']] = (
        Field(
            default=None, description='业务类型（0其它 1新增 2修改 3删除 4授权 5导出 6导入 7强退 8生成代码 9清空数据）'
        )
    )
    method: Optional[str] = Field(default=None, description='方法名称')
    request_method: Optional[str] = Field(default=None, description='请求方式')
    operator_type: Optional[Literal[0, 1, 2]] = Field(
        default=None, description='操作类别（0其它 1后台用户 2手机端用户）'
    )
    oper_name: Optional[str] = Field(default=None, description='操作人员')
    dept_name: Optional[str] = Field(default=None, description='部门名称')
    oper_url: Optional[str] = Field(default=None, description='请求URL')
    oper_ip: Optional[str] = Field(default=None, description='主机地址')
    oper_location: Optional[str] = Field(default=None, description='操作地点')
    oper_param: Optional[str] = Field(default=None, description='请求参数')
    json_result: Optional[str] = Field(default=None, description='返回参数')
    status: Optional[Literal[0, 1, '0', '1']] = Field(default=None, description='操作状态（0正常 1异常）')
    error_msg: Optional[str] = Field(default=None, description='错误消息')
    oper_time: Optional[datetime] = Field(default=None, description='操作时间')
    cost_time: Optional[int] = Field(default=None, description='消耗时间')


class LogininforModel(BaseModel):
    """
    登录日志表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    info_id: Optional[int] = Field(default=None, description='访问ID')
    user_name: Optional[str] = Field(default=None, description='用户账号')
    ipaddr: Optional[str] = Field(default=None, description='登录IP地址')
    login_location: Optional[str] = Field(default=None, description='登录地点')
    browser: Optional[str] = Field(default=None, description='浏览器类型')
    os: Optional[str] = Field(default=None, description='操作系统')
    status: Optional[Literal['0', '1']] = Field(default=None, description='登录状态（0成功 1失败）')
    msg: Optional[str] = Field(default=None, description='提示消息')
    login_time: Optional[datetime] = Field(default=None, description='访问时间')


class OperLogQueryModel(OperLogModel):
    """
    操作日志管理不分页查询模型
    """

    order_by_column: Optional[str] = Field(default=None, description='排序的字段名称')
    is_asc: Optional[Literal['ascending', 'descending']] = Field(
        default=None, description='排序方式（ascending升序 descending降序）'
    )
    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class OperLogPageQueryModel(OperLogQueryModel):
    """
    操作日志管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteOperLogModel(BaseModel):
    """
    删除操作日志模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    oper_ids: str = Field(description='需要删除的日志主键')


class LoginLogQueryModel(LogininforModel):
    """
    登录日志管理不分页查询模型
    """

    order_by_column: Optional[str] = Field(default=None, description='排序的字段名称')
    is_asc: Optional[Literal['ascending', 'descending']] = Field(
        default=None, description='排序方式（ascending升序 descending降序）'
    )
    begin_time: Optional[str] = Field(default=None, description='开始时间')
    end_time: Optional[str] = Field(default=None, description='结束时间')


@as_query
class LoginLogPageQueryModel(LoginLogQueryModel):
    """
    登录日志管理分页查询模型
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class DeleteLoginLogModel(BaseModel):
    """
    删除登录日志模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    info_ids: str = Field(description='需要删除的访问ID')


class UnlockUser(BaseModel):
    """
    解锁用户模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    user_name: str = Field(description='用户名称')
