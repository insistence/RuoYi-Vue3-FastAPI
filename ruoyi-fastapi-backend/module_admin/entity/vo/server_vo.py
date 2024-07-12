from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import List, Optional


class CpuInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    cpu_num: Optional[int] = Field(default=None, description='核心数')
    used: Optional[float] = Field(default=None, description='CPU用户使用率')
    sys: Optional[float] = Field(default=None, description='CPU系统使用率')
    free: Optional[float] = Field(default=None, description='CPU当前空闲率')


class MemoryInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    total: Optional[str] = Field(default=None, description='内存总量')
    used: Optional[str] = Field(default=None, description='已用内存')
    free: Optional[str] = Field(default=None, description='剩余内存')
    usage: Optional[float] = Field(default=None, description='使用率')


class SysInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    computer_ip: Optional[str] = Field(default=None, description='服务器IP')
    computer_name: Optional[str] = Field(default=None, description='服务器名称')
    os_arch: Optional[str] = Field(default=None, description='系统架构')
    os_name: Optional[str] = Field(default=None, description='操作系统')
    user_dir: Optional[str] = Field(default=None, description='项目路径')


class PyInfo(MemoryInfo):
    model_config = ConfigDict(alias_generator=to_camel)

    name: Optional[str] = Field(default=None, description='Python名称')
    version: Optional[str] = Field(default=None, description='Python版本')
    start_time: Optional[str] = Field(default=None, description='启动时间')
    run_time: Optional[str] = Field(default=None, description='运行时长')
    home: Optional[str] = Field(default=None, description='安装路径')


class SysFiles(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    dir_name: Optional[str] = Field(default=None, description='盘符路径')
    sys_type_name: Optional[str] = Field(default=None, description='盘符类型')
    type_name: Optional[str] = Field(default=None, description='文件类型')
    total: Optional[str] = Field(default=None, description='总大小')
    used: Optional[str] = Field(default=None, description='已经使用量')
    free: Optional[str] = Field(default=None, description='剩余大小')
    usage: Optional[str] = Field(default=None, description='资源的使用率')


class ServerMonitorModel(BaseModel):
    """
    服务监控对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    cpu: Optional[CpuInfo] = Field(description='CPU相关信息')
    py: Optional[PyInfo] = Field(description='Python相关信息')
    mem: Optional[MemoryInfo] = Field(description='內存相关信息')
    sys: Optional[SysInfo] = Field(description='服务器相关信息')
    sys_files: Optional[List[SysFiles]] = Field(description='磁盘相关信息')
