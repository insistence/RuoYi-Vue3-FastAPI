from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Optional, List


class CpuInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    cpu_num: Optional[int] = None
    used: Optional[float] = None
    sys: Optional[float] = None
    free: Optional[float] = None


class MemoryInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    total: Optional[str] = None
    used: Optional[str] = None
    free: Optional[str] = None
    usage: Optional[float] = None


class SysInfo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    computer_ip: Optional[str] = None
    computer_name: Optional[str] = None
    os_arch: Optional[str] = None
    os_name: Optional[str] = None
    user_dir: Optional[str] = None


class PyInfo(MemoryInfo):
    model_config = ConfigDict(alias_generator=to_camel)

    name: Optional[str] = None
    version: Optional[str] = None
    start_time: Optional[str] = None
    run_time: Optional[str] = None
    home: Optional[str] = None


class SysFiles(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    dir_name: Optional[str] = None
    sys_type_name: Optional[str] = None
    type_name: Optional[str] = None
    total: Optional[str] = None
    used: Optional[str] = None
    free: Optional[str] = None
    usage: Optional[str] = None


class ServerMonitorModel(BaseModel):
    """
    服务监控对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel)

    cpu: Optional[CpuInfo]
    py: Optional[PyInfo]
    mem: Optional[MemoryInfo]
    sys: Optional[SysInfo]
    sys_files: Optional[List[SysFiles]]
