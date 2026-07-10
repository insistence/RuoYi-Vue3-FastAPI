import asyncio
import time
from collections.abc import Awaitable, Callable
from functools import cache

from fastapi import FastAPI

from common.constant import LockConstant
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from utils.log_util import logger


class PluginApplicationRuntime:
    """
    应用入口侧插件运行时适配器。

    server.py 只依赖该适配器提供的高层扩展点，插件实体导入、二次建表、启动资源安装、
    多 worker ready barrier 和生命周期钩子等细节留在插件运行时内部。
    """

    def __init__(
        self,
        startup_manager: PluginRuntimeStartupManager | None = None,
        *,
        ready_key: str = LockConstant.PLUGIN_STARTUP_READY_KEY,
        ready_expire_seconds: int = LockConstant.PLUGIN_STARTUP_READY_EXPIRE_SECONDS,
        ready_wait_timeout_seconds: int = LockConstant.PLUGIN_STARTUP_READY_WAIT_TIMEOUT_SECONDS,
        ready_wait_interval_seconds: int = LockConstant.PLUGIN_STARTUP_READY_WAIT_INTERVAL_SECONDS,
    ) -> None:
        """
        初始化插件应用运行时适配器。

        :param startup_manager: 插件启动协调器
        :param ready_key: 插件启动 ready 标记 key
        :param ready_expire_seconds: ready 标记过期时间
        :param ready_wait_timeout_seconds: 等待 ready 超时时间
        :param ready_wait_interval_seconds: 等待 ready 轮询间隔
        :return: None
        """
        self.startup_manager = startup_manager or PluginRuntimeStartupManager()
        self.ready_key = ready_key
        self.ready_expire_seconds = ready_expire_seconds
        self.ready_wait_timeout_seconds = ready_wait_timeout_seconds
        self.ready_wait_interval_seconds = ready_wait_interval_seconds

    def bind_app(self, app: FastAPI) -> None:
        """
        绑定插件运行时到 FastAPI app。

        :param app: FastAPI对象
        :return: None
        """
        app.state.plugin_application_runtime = self
        self.startup_manager.bind_app(app)

    def prepare_metadata(self, app: FastAPI) -> None:
        """
        准备插件平台自身元数据。

        :param app: FastAPI对象
        :return: None
        """
        self._ensure_bound(app)
        self.startup_manager.import_builtin_entities()

    async def startup(
        self,
        app: FastAPI,
        *,
        startup_write_enabled: bool,
        create_tables: Callable[[], Awaitable[None]],
    ) -> None:
        """
        启动插件运行时。

        :param app: FastAPI对象
        :param startup_write_enabled: 当前 worker 是否允许执行启动期写库操作
        :param create_tables: 数据库建表回调
        :return: None
        """
        self._ensure_bound(app)
        if startup_write_enabled:
            await self.clear_startup_ready(app)
            await self.startup_manager.prepare_enabled_plugins(app, startup_write_enabled=True)
            await create_tables()
            await self.startup_manager.activate_enabled_plugins(app, startup_write_enabled=True)
            await self.mark_startup_ready(app)
            return

        await self.wait_startup_ready(app)
        await self.startup_manager.prepare_enabled_plugins(app, startup_write_enabled=False)
        await self.startup_manager.activate_enabled_plugins(app, startup_write_enabled=False)

    async def shutdown(self, app: FastAPI, *, startup_write_enabled: bool) -> None:
        """
        关闭插件运行时。

        :param app: FastAPI对象
        :param startup_write_enabled: 当前 worker 是否允许执行启动期写库操作
        :return: None
        """
        self._ensure_bound(app)
        await self.startup_manager.shutdown(app, startup_write_enabled=startup_write_enabled)

    async def clear_startup_ready(self, app: FastAPI) -> None:
        """
        清除上一轮插件启动 ready 标记。

        :param app: FastAPI对象
        :return: None
        """
        await app.state.redis.delete(self.ready_key)

    async def mark_startup_ready(self, app: FastAPI) -> None:
        """
        标记当前启动锁持有者已完成插件启动写入。

        :param app: FastAPI对象
        :return: None
        """
        startup_owner = await self._get_startup_owner(app)
        if not startup_owner:
            raise RuntimeError('插件启动 ready 标记失败：应用启动锁不存在')
        await app.state.redis.set(self.ready_key, startup_owner, ex=self.ready_expire_seconds)
        logger.info('插件启动资源已就绪')

    async def wait_startup_ready(self, app: FastAPI) -> None:
        """
        等待启动写入 worker 完成插件初始化。

        :param app: FastAPI对象
        :return: None
        """
        startup_owner = await self._get_startup_owner(app)
        if not startup_owner:
            raise RuntimeError('插件启动 ready 等待失败：应用启动锁不存在')

        deadline = time.monotonic() + self.ready_wait_timeout_seconds
        while time.monotonic() < deadline:
            ready_owner = await app.state.redis.get(self.ready_key)
            if ready_owner == startup_owner:
                return
            await asyncio.sleep(self.ready_wait_interval_seconds)

        raise TimeoutError('等待插件启动 ready 超时')

    async def _get_startup_owner(self, app: FastAPI) -> str | None:
        """
        获取当前应用启动锁持有者。

        :param app: FastAPI对象
        :return: 启动锁持有者
        """
        return await app.state.redis.get(LockConstant.APP_STARTUP_LOCK_KEY)

    def _ensure_bound(self, app: FastAPI) -> None:
        """
        确保插件运行时已绑定到 app。

        :param app: FastAPI对象
        :return: None
        """
        if getattr(app.state, 'plugin_application_runtime', None) is not self:
            self.bind_app(app)


@cache
def get_plugin_application_runtime() -> PluginApplicationRuntime:
    """
    获取应用插件运行时适配器。

    :return: 应用插件运行时适配器
    """
    from plugins.core.management.service.startup_gateway import (  # noqa: PLC0415
        PluginManagementRouteStateGateway,
        PluginManagementStartupGateway,
    )

    startup_manager = PluginRuntimeStartupManager(
        management_gateway=PluginManagementStartupGateway(),
        route_state_gateway=PluginManagementRouteStateGateway(),
    )
    return PluginApplicationRuntime(startup_manager=startup_manager)
