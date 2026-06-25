import inspect
from dataclasses import dataclass
from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.callable import LoadedPluginCallable, PluginCallableLoader


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
    """

    plugin_id: str
    hook_name: str
    discovered_plugin: DiscoveredPlugin
    app: Any | None = None
    query_db: Any | None = None
    startup_write_enabled: bool = True


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
    钩子函数可以是同步或异步函数，签名支持 `hook()` 或 `hook(context)`。
    """

    def __init__(self, discovered_plugin: DiscoveredPlugin) -> None:
        """
        初始化插件生命周期钩子运行器。

        :param discovered_plugin: 已发现插件对象
        """
        self.discovered_plugin = discovered_plugin

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
        context = PluginHookContext(
            plugin_id=self.discovered_plugin.manifest.id,
            hook_name=hook_name,
            discovered_plugin=self.discovered_plugin,
            app=app,
            query_db=query_db,
            startup_write_enabled=startup_write_enabled,
        )
        result = self._invoke_hook(hook_callable, context)
        if inspect.isawaitable(result):
            await result

        return PluginHookResult(hook_name=hook_name, hook_path=hook_path, module_name=hook_callable.module_name)

    def _load_hook_callable(self, hook_path: str) -> LoadedPluginCallable:
        """
        加载生命周期钩子函数。

        :param hook_path: 钩子声明路径
        :return: 已加载的生命周期钩子函数
        """
        return PluginCallableLoader(self.discovered_plugin, label='生命周期钩子').load(hook_path)

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
