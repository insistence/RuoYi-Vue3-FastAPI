from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from plugins.core.sdk.version import HOST_API_VERSION


@dataclass(frozen=True)
class PluginHostContext:
    """
    宿主注入的能力集合；不保存当前用户或请求数据库会话。

    services 只包含宿主显式登记的接口，不提供通过字符串导入任意服务的执行器。
    具体服务仍负责权限和事务规则；该对象不是针对不可信代码的沙箱。

    :param plugin_id: 插件 ID
    :param resource_root: 插件资源根目录
    :param config: 当前插件的只读配置快照
    :param services: 宿主显式注册的只读服务映射
    :param session_factory: 由宿主提供的数据库会话工厂
    :param redis: 宿主共享的 Redis 客户端
    :param logger: 绑定插件标识的日志对象
    :param startup_write_enabled: 当前实例是否允许执行启动期全局写入
    :param api_version: 宿主插件 API 版本
    """

    plugin_id: str
    resource_root: Path
    config: Mapping[str, Any] = field(default_factory=dict, repr=False)
    services: Mapping[str, Any] = field(default_factory=dict)
    session_factory: Callable[..., Any] | None = None
    redis: Any = None
    logger: Any = None
    startup_write_enabled: bool = False
    api_version: str = HOST_API_VERSION

    def __post_init__(self) -> None:
        """
        规范化资源根目录，并将配置和服务映射转换为只读快照。

        :return: None
        """
        object.__setattr__(self, 'resource_root', self.resource_root.resolve())
        object.__setattr__(self, 'config', MappingProxyType(dict(self.config)))
        object.__setattr__(self, 'services', MappingProxyType(dict(self.services)))

    def resource(self, relative_path: str) -> Path:
        """
        解析自身资源；读取前再次检查真实路径以拒绝链接逃逸。

        :param relative_path: 相对于当前插件资源根目录的路径
        :return: 通过插件目录边界校验的资源绝对路径
        """
        path = (self.resource_root / relative_path).resolve()
        if not path.is_relative_to(self.resource_root):
            raise ValueError('插件资源路径不能越过插件根目录')
        return path

    def service(self, name: str) -> Any:
        """
        获取宿主显式注册的服务能力。

        :param name: 宿主注册的版本化服务名称
        :return: 对应的宿主服务能力对象
        """
        if name not in self.services:
            raise LookupError(f'宿主未提供插件服务：{name}')
        return self.services[name]


@dataclass(frozen=True)
class PluginRequestContext:
    """
    由宿主鉴权层建立的请求身份，不能由客户端字段直接构造。

    :param host: 当前插件的宿主能力上下文
    :param user: 宿主登录服务返回的当前用户
    :param permissions: 当前用户的接口权限集合
    :param request_id: 宿主提供的请求关联标识
    :param query_db: 由宿主按请求需要注入的数据库会话
    """

    host: PluginHostContext
    user: Any
    permissions: frozenset[str] = frozenset()
    request_id: str | None = None
    query_db: Any = None

    def require_permission(self, permission: str) -> None:
        """
        执行接口权限检查；数据权限由具体服务按当前用户处理。

        :param permission: 当前操作要求的接口权限标识
        :return: None
        """
        if permission not in self.permissions and '*:*:*' not in self.permissions:
            raise PermissionError(f'缺少权限：{permission}')


@dataclass(frozen=True)
class PluginTaskContext:
    """
    后台任务身份；不隐式授予请求用户或管理员权限。

    :param host: 当前插件的宿主能力上下文
    :param job_id: 插件清单声明的任务 ID
    """

    host: PluginHostContext
    job_id: str
