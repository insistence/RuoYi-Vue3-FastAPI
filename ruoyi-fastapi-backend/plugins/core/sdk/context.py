import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from plugins.core.sdk.request import PluginHttpRequest
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
    :param query_db: 显式事务块内有效的数据库会话，不得跨任务共享
    :param request: SDK 接口适配器提供的 HTTP 请求数据快照
    :param _transaction: 宿主内部的会话所有权记录，业务代码不应自行构造
    """

    host: PluginHostContext
    user: Any
    permissions: frozenset[str] = frozenset()
    request_id: str | None = None
    query_db: Any = None
    request: PluginHttpRequest | None = None
    _transaction: '_PluginTransactionState | None' = field(default=None, repr=False, compare=False)

    def require_permission(self, permission: str) -> None:
        """
        执行接口权限检查；数据权限由具体服务按当前用户处理。

        :param permission: 当前操作要求的接口权限标识
        :return: None
        """
        if permission not in self.permissions and '*:*:*' not in self.permissions:
            raise PermissionError(f'缺少权限：{permission}')

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator['PluginRequestContext']:
        """
        为当前任务创建显式事务，成功提交、异常或取消回滚，并关闭独占会话。

        :return: 仅在当前事务块和当前 asyncio 任务内有效的请求上下文
        :raises RuntimeError: 嵌套事务、缺少会话工厂或在失效上下文上重新开启事务
        """
        if self.query_db is not None or self._transaction is not None:
            raise RuntimeError('插件请求事务不能嵌套或复用，请使用原始请求上下文')
        if self.host.session_factory is None:
            raise RuntimeError('宿主未提供数据库会话工厂')
        async with self.host.session_factory() as db:
            state = _PluginTransactionState(db, asyncio.current_task())
            try:
                async with db.begin():
                    yield replace(self, query_db=db, _transaction=state)
            finally:
                state.active = False

    def transaction_session(self) -> Any:
        """
        为宿主服务取得当前任务拥有的事务会话，拒绝过期、伪造或跨任务复用。

        :return: 当前有效事务的会话；未开启事务时为 None
        :raises RuntimeError: 事务所有权或有效期不符合要求
        """
        state = self._transaction
        if state is None and self.query_db is None:
            return None
        if state is None or not state.active or state.session is not self.query_db:
            raise RuntimeError('插件请求事务上下文已失效或不是由宿主创建')
        if state.owner is not asyncio.current_task():
            raise RuntimeError('插件请求事务会话不能跨 asyncio 任务共享')
        return state.session


@dataclass
class _PluginTransactionState:
    """
    记录显式事务的会话、所属任务和有效期。

    :param session: 当前事务独占的数据库会话
    :param owner: 开启事务的 asyncio 任务
    :param active: 事务块是否仍有效
    """

    session: Any
    owner: asyncio.Task[Any] | None
    active: bool = True


@dataclass(frozen=True)
class PluginTaskContext:
    """
    后台任务身份；不隐式授予请求用户或管理员权限。

    :param host: 当前插件的宿主能力上下文
    :param job_id: 插件清单声明的任务 ID
    :param request_id: 本次任务执行的独立追踪标识
    """

    host: PluginHostContext
    job_id: str
    request_id: str | None = None
