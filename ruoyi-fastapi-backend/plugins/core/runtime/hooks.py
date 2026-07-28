import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from common.constant import PluginRuntimeConstant
from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.callable import LoadedPluginCallable, PluginCallableLoader
from utils.log_util import logger


@dataclass(frozen=True)
class PluginHookContext:
    """
    插件生命周期钩子上下文。

    :param plugin_id: 插件 ID
    :param hook_name: 钩子名称
    :param discovered_plugin: 已发现插件对象
    :param app: FastAPI 应用对象
    :param query_db: orm对象
    :param startup_write_enabled: 当前 worker 是否允许执行启动期全局写入
    :param startup_generation: 插件启动代际
    :param plugin_startup_role_at_creation: Hook 创建时的插件启动角色
    """

    plugin_id: str
    hook_name: str
    discovered_plugin: DiscoveredPlugin
    app: Any | None = None
    query_db: Any | None = None
    startup_write_enabled: bool = True
    startup_generation: str | None = None
    plugin_startup_role_at_creation: str = 'writer'


@dataclass(frozen=True)
class PluginHookResult:
    """
    插件生命周期钩子执行结果。

    :param hook_name: 钩子名称
    :param hook_path: 钩子声明路径
    :param module_name: 钩子模块名
    """

    hook_name: str
    hook_path: str
    module_name: str


class PluginHookRunner:
    """
    插件生命周期钩子运行器。

    使用 Command Runner 模式解析并执行 `plugin.yaml` 中声明的生命周期钩子。
    钩子必须使用 async def 声明，签名支持 `hook()` 或 `hook(context)`。

    同步函数在线程池超时后无法被 Python 安全终止，可能在生命周期事务已经回滚后
    继续产生副作用，因此平台拒绝执行同步生命周期钩子。
    """

    def __init__(
        self,
        discovered_plugin: DiscoveredPlugin,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        """
        初始化插件生命周期钩子运行器。

        :param discovered_plugin: 已发现插件对象
        :param timeout_seconds: 钩子执行超时时间
        """
        self.discovered_plugin = discovered_plugin
        self.timeout_seconds = timeout_seconds or PluginRuntimeConstant.PLUGIN_HOOK_TIMEOUT_SECONDS

    async def run(
        self,
        hook_name: str,
        *,
        app: Any | None = None,
        query_db: Any | None = None,
        startup_write_enabled: bool = True,
    ) -> PluginHookResult | None:
        """
        执行指定生命周期钩子。

        :param hook_name: 钩子名称，例如 `on_install`
        :param app: FastAPI 应用对象
        :param query_db: orm对象
        :param startup_write_enabled: 当前 worker 是否允许执行启动期全局写入
        :return: 钩子执行结果，未声明时返回 None
        """
        hook_path = getattr(self.discovered_plugin.manifest.backend.hooks, hook_name, None)
        if not hook_path:
            return None

        hook_callable = self._load_hook_callable(hook_path)
        startup_generation = None
        if app is not None and getattr(app, 'state', None) is not None:
            startup_generation = getattr(app.state, 'plugin_startup_generation', None)
        plugin_startup_role = 'writer' if startup_write_enabled else 'reader'
        context = PluginHookContext(
            plugin_id=self.discovered_plugin.manifest.id,
            hook_name=hook_name,
            discovered_plugin=self.discovered_plugin,
            app=app,
            query_db=query_db,
            startup_write_enabled=startup_write_enabled,
            startup_generation=startup_generation,
            plugin_startup_role_at_creation=plugin_startup_role,
        )
        with logger.contextualize(
            plugin_id=context.plugin_id,
            plugin_hook=hook_name,
            startup_generation=startup_generation,
            plugin_startup_role_at_creation=plugin_startup_role,
            startup_write_enabled=startup_write_enabled,
            origin_hook=hook_name,
            created_during_startup=hook_name == 'on_startup',
        ):
            logger.debug('🔄 开始执行插件生命周期钩子')
            try:
                await self._invoke_hook_with_timeout(hook_callable, context)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f'生命周期钩子执行超时：{hook_name}，超过 {self.timeout_seconds} 秒') from exc
            logger.debug('✅ 插件生命周期钩子执行完成')

        return PluginHookResult(hook_name=hook_name, hook_path=hook_path, module_name=hook_callable.module_name)

    def _load_hook_callable(self, hook_path: str) -> LoadedPluginCallable:
        """
        加载生命周期钩子函数。

        :param hook_path: 钩子声明路径
        :return: 已加载的生命周期钩子函数
        """
        return PluginCallableLoader(self.discovered_plugin, label='生命周期钩子').load(hook_path)

    async def _invoke_hook_with_timeout(
        self,
        hook_callable: LoadedPluginCallable,
        context: PluginHookContext,
    ) -> None:
        """
        在超时约束内执行生命周期钩子。

        :param hook_callable: 已加载的钩子函数
        :param context: 钩子上下文
        :return: None
        """
        callable_object = hook_callable.callable_object
        if not inspect.iscoroutinefunction(callable_object):
            raise TypeError('生命周期钩子必须使用 async def 声明，平台不会在线程中执行不可终止的同步钩子')
        result = self._invoke_hook(hook_callable, context)
        if inspect.isawaitable(result):
            await asyncio.wait_for(result, timeout=self.timeout_seconds)

    @staticmethod
    def _invoke_hook(hook_callable: LoadedPluginCallable, context: PluginHookContext) -> object:
        """
        调用生命周期钩子函数。

        :param hook_callable: 已加载的钩子函数
        :param context: 钩子上下文
        :return: 钩子函数返回值
        """
        callable_object = hook_callable.callable_object
        signature = inspect.signature(callable_object)
        if not signature.parameters:
            return callable_object()

        return callable_object(context)
