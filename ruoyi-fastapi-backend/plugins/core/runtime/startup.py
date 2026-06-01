from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI

from common.router import auto_register_plugin_routers
from config.get_db import get_db
from plugins.core.discovery.registry import RegisteredPlugin
from plugins.core.management.service.service import PluginService
from plugins.core.runtime.bootstrap import PluginRuntimeBuilder
from plugins.core.runtime.hooks import PluginHookRunner
from utils.log_util import logger


class PluginRuntimeStartupManager:
    """
    插件运行时启动协调器。

    将插件发现、实体导入、资源安装、路由注册和生命周期钩子从应用入口中隔离出来，
    让 server.py 只保留高层启动顺序。
    """

    def __init__(self, builder: PluginRuntimeBuilder | None = None) -> None:
        """
        初始化插件运行时启动协调器。

        :param builder: 插件运行时构建器
        :return: None
        """
        self.builder = builder or PluginRuntimeBuilder()

    def bind_app(self, app: FastAPI) -> None:
        """
        绑定插件运行时对象到 FastAPI state。

        :param app: FastAPI对象
        :return: None
        """
        app.state.plugin_runtime_startup = self
        app.state.plugin_runtime_builder = self.builder
        if not hasattr(app.state, 'plugin_registry'):
            app.state.plugin_registry = self.builder.build_registry()
        if not hasattr(app.state, 'plugin_routes_registered'):
            app.state.plugin_routes_registered = False

    def import_builtin_entities(self) -> None:
        """
        导入内置业务模块实体。

        :return: None
        """
        self.builder.import_builtin_entities()

    async def prepare_enabled_plugins(self, app: FastAPI) -> None:
        """
        准备启用插件运行时实体。

        :param app: FastAPI对象
        :return: None
        """
        await self.load_registry_from_database(app)
        await self.import_enabled_plugin_entities(app)

    async def activate_enabled_plugins(self, app: FastAPI) -> None:
        """
        激活启用插件运行时资源。

        :param app: FastAPI对象
        :return: None
        """
        await self.install_enabled_plugin_resources(app)
        self.register_enabled_plugin_routers(app)
        await self.run_enabled_plugin_hooks(app, 'on_startup')

    async def shutdown(self, app: FastAPI) -> None:
        """
        执行插件运行时关闭接入流程。

        :param app: FastAPI对象
        :return: None
        """
        await self.run_enabled_plugin_hooks(app, 'on_shutdown')

    async def load_registry_from_database(self, app: FastAPI) -> None:
        """
        从数据库插件状态构建运行时插件注册表。

        :param app: FastAPI对象
        :return: None
        """
        async for query_db in get_db():
            plugin_list = await PluginService.get_plugin_list_services(query_db)
            app.state.plugin_registry = self.builder.build_registry(plugin_list)

    async def import_enabled_plugin_entities(self, app: FastAPI) -> None:
        """
        导入启用插件实体并标记导入失败插件。

        :param app: FastAPI对象
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return

        import_result = self.builder.import_plugin_entities(plugin_registry)
        for failure in import_result.failures:
            await self.mark_plugin_runtime_error(app, failure.plugin_id, failure.error_message)

    async def install_enabled_plugin_resources(self, app: FastAPI) -> None:
        """
        安装启用插件启动期资源。

        :param app: FastAPI对象
        :return: None
        """
        await self.install_enabled_plugin_menus(app)
        await self.install_enabled_plugin_configs(app)
        await self.install_enabled_plugin_jobs(app)

    async def install_enabled_plugin_menus(self, app: FastAPI) -> None:
        """
        安装启用插件菜单。

        :param app: FastAPI对象
        :return: None
        """
        await self.install_enabled_plugin_resource(app, PluginService.install_enabled_plugin_menu_services)

    async def install_enabled_plugin_configs(self, app: FastAPI) -> None:
        """
        安装启用插件默认配置。

        :param app: FastAPI对象
        :return: None
        """
        await self.install_enabled_plugin_resource(app, PluginService.install_enabled_plugin_config_services)

    async def install_enabled_plugin_jobs(self, app: FastAPI) -> None:
        """
        安装启用插件声明的定时任务。

        :param app: FastAPI对象
        :return: None
        """
        await self.install_enabled_plugin_resource(app, PluginService.install_enabled_plugin_job_services)

    async def install_enabled_plugin_resource(
        self,
        app: FastAPI,
        installer: Callable[[Any, Any], Awaitable[Any]],
    ) -> None:
        """
        安装启用插件启动期资源。

        :param app: FastAPI对象
        :param installer: 资源安装服务方法
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return
        async for query_db in get_db():
            await installer(query_db, plugin_registry)
            await query_db.commit()

    def register_enabled_plugin_routers(self, app: FastAPI) -> None:
        """
        注册启用插件 controller 路由。

        :param app: FastAPI对象
        :return: None
        """
        if getattr(app.state, 'plugin_routes_registered', False):
            return
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        plugin_ids = []
        if plugin_registry:
            plugin_ids = [
                plugin.plugin_id
                for plugin in plugin_registry.list_enabled_plugins()
                if plugin.discovered_plugin.manifest.backend.routers.auto_scan
            ]
        auto_register_plugin_routers(app, plugin_ids)
        app.state.plugin_routes_registered = True

    async def run_enabled_plugin_hooks(self, app: FastAPI, hook_name: str) -> None:
        """
        执行启用插件生命周期钩子。

        :param app: FastAPI对象
        :param hook_name: 钩子名称
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return

        for plugin in plugin_registry.list_enabled_plugins():
            await self.run_single_plugin_hook(app, plugin, hook_name)

    async def run_single_plugin_hook(self, app: FastAPI, plugin: RegisteredPlugin, hook_name: str) -> None:
        """
        执行单个插件生命周期钩子并处理运行时异常。

        :param app: FastAPI对象
        :param plugin: 插件运行时快照
        :param hook_name: 钩子名称
        :return: None
        """
        try:
            await PluginHookRunner(plugin.discovered_plugin).run(hook_name, app=app)
        except Exception as exc:
            logger.exception(f'插件生命周期钩子执行失败：{plugin.plugin_id}.{hook_name}，错误：{exc}')
            await self.mark_plugin_runtime_error(app, plugin.plugin_id, str(exc))

    async def mark_plugin_runtime_error(self, app: FastAPI, plugin_id: str, error_message: str) -> None:
        """
        标记插件运行时异常并刷新运行时注册表。

        :param app: FastAPI对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: None
        """
        async for query_db in get_db():
            result = await PluginService.mark_plugin_error_services(query_db, plugin_id, error_message)
            if not result.is_success:
                await query_db.rollback()
                registered_plugin = self.get_registered_plugin(app, plugin_id)
                if registered_plugin:
                    await PluginService.upsert_discovered_plugin_services(
                        query_db,
                        registered_plugin.discovered_plugin,
                        self.builder.plugins_root,
                    )
                    result = await PluginService.mark_plugin_error_services(query_db, plugin_id, error_message)
            if result.is_success:
                await query_db.commit()
            else:
                await query_db.rollback()
                logger.warning(f'插件运行时异常状态写入失败：{plugin_id}，原因：{result.message}')
        await self.load_registry_from_database(app)

    @staticmethod
    def get_registered_plugin(app: FastAPI, plugin_id: str) -> RegisteredPlugin | None:
        """
        从应用运行时注册表获取插件快照。

        :param app: FastAPI对象
        :param plugin_id: 插件ID
        :return: 插件运行时快照
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        if plugin_registry is None:
            return None

        return plugin_registry.get_plugin(plugin_id)
