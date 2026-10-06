import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter
from starlette.types import ASGIApp

from plugins.core.sdk.context import PluginHostContext


@dataclass(frozen=True)
class PluginDefinition:
    """
    入口返回值；构造时不打开连接、不执行迁移。

    原生扩展通过 PyO3 导入这个类并创建实例即可，无需继承 Python 基类。
    生命周期 Hook 继续在清单中声明，避免安装命令和请求 worker 得到不同的能力清单。

    :param api_version: 插件能力对象协议版本
    :param routers: Router 接入方式显式提供的路由集合
    :param app_factory: ASGI 接入方式创建子应用的同步工厂
    :param register_models: 同步注册 ORM 元数据的可选回调
    """

    api_version: int = 1
    routers: Sequence[APIRouter] = field(default_factory=tuple)
    app_factory: Callable[[PluginHostContext], ASGIApp] | None = None
    register_models: Callable[[PluginHostContext], None] | None = None

    def validate(self, integration: str) -> None:
        """
        导入后验证对象协议，不依赖 Rust 函数的反射签名。

        :param integration: 清单声明的 Web 接入方式
        :return: None
        """
        if type(self.api_version) is not int or self.api_version != 1:
            raise ValueError(f'不支持的 PluginDefinition API 版本：{self.api_version}')
        if any(not isinstance(router, APIRouter) for router in self.routers):
            raise TypeError('PluginDefinition.routers 必须包含 APIRouter 实例')
        if integration == 'asgi':
            if not callable(self.app_factory) or self.routers:
                raise ValueError('ASGI 插件必须提供 app_factory，且不能同时返回 routers')
        elif integration == 'router':
            if self.app_factory is not None:
                raise ValueError('Router 插件不能返回 app_factory')
        else:
            raise ValueError(f'不支持的插件接入方式：{integration}')
        if self.register_models is not None and not callable(self.register_models):
            raise TypeError('register_models 必须可调用')


async def await_plugin_callback(
    callback: Callable[..., Any],
    *args: Any,
    timeout: float = 30.0,
    kwargs: Mapping[str, Any] | None = None,
) -> Any:
    """
    等待 Python 或原生 awaitable；同步入口必须立即返回。

    超时只能取消异步等待，不能强制终止阻塞原生函数。平台不在线程池中执行
    生命周期写操作，也不将同步返回值视为成功，以免事务结束后继续产生副作用。

    :param callback: 必须立即返回可等待对象的插件回调
    :param args: 传给回调的位置参数
    :param timeout: 异步等待超时时间，单位为秒
    :param kwargs: 传给回调的关键字参数
    :return: 等待插件回调完成后的返回值
    """
    result = callback(*args, **(kwargs or {}))
    if not inspect.isawaitable(result):
        raise TypeError('v2 插件异步回调必须立即返回 awaitable')
    return await asyncio.wait_for(result, timeout=timeout)
