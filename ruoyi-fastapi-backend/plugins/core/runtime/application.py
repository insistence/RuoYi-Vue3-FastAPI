import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from functools import cache

from fastapi import FastAPI

from common.constant import LockConstant
from plugins.core.runtime.startup import PluginRuntimeStartupManager
from plugins.core.runtime.startup_coordination import PluginStartupGenerationResolver
from utils.log_util import logger

from .service.lifecycle_lock import NoopPluginLifecycleLock, PluginLifecycleLock


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
        failed_expire_seconds: int = LockConstant.PLUGIN_STARTUP_FAILED_EXPIRE_SECONDS,
        ready_wait_timeout_seconds: int = LockConstant.PLUGIN_STARTUP_READY_WAIT_TIMEOUT_SECONDS,
        ready_wait_interval_seconds: int = LockConstant.PLUGIN_STARTUP_READY_WAIT_INTERVAL_SECONDS,
        lifecycle_lock: PluginLifecycleLock | None = None,
        startup_generation: str | None = None,
    ) -> None:
        """
        初始化插件应用运行时适配器。

        :param startup_manager: 插件启动协调器
        :param ready_key: 插件启动 ready 标记 key
        :param ready_expire_seconds: ready 标记过期时间
        :param failed_expire_seconds: 失败标记过期时间
        :param ready_wait_timeout_seconds: 等待 ready 超时时间
        :param ready_wait_interval_seconds: 等待 ready 轮询间隔
        :param lifecycle_lock: 插件生命周期全局锁
        :param startup_generation: 测试或部署显式注入的启动代际
        :return: None
        """
        self.startup_manager = startup_manager or PluginRuntimeStartupManager()
        self.ready_key = ready_key
        self.ready_expire_seconds = ready_expire_seconds
        self.failed_expire_seconds = failed_expire_seconds
        self.ready_wait_timeout_seconds = ready_wait_timeout_seconds
        self.ready_wait_interval_seconds = ready_wait_interval_seconds
        self.lifecycle_lock = lifecycle_lock or NoopPluginLifecycleLock()
        self.startup_generation = startup_generation

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
        create_tables: Callable[[], Awaitable[None]],
    ) -> None:
        """
        启动插件运行时。

        同一发布代际只有一个 worker 能在全局生命周期锁内执行写入；其他 worker 等待
        当前代际 ready 后仅执行进程本地激活。插件启动不再依赖长期持有的调度器主节点锁。

        :param app: FastAPI对象
        :param create_tables: 数据库建表回调
        :return: None
        """
        self._ensure_bound(app)
        generation = self.resolve_startup_generation()
        app.state.plugin_startup_generation = generation
        app.state.plugin_startup_write_enabled = False

        ready_state = await self.get_startup_state(app, generation)
        logger.bind(
            startup_generation=generation,
            plugin_startup_role='reader',
            ready_status=ready_state.get('status', 'missing'),
        ).debug('🔎 开始检查插件启动代际 ready 状态')
        activated, stale_ready_reported = await self._process_startup_state(
            app,
            generation,
            ready_state,
            stale_ready_reported=False,
            ready_message='复用当前代际插件 ready，开始本地激活',
            failed_message='检测到当前代际插件启动 failed marker',
        )
        if activated:
            return

        deadline = time.monotonic() + self.ready_wait_timeout_seconds
        wait_reported = False
        while time.monotonic() < deadline:
            async with self.lifecycle_lock.lock('__runtime__', f'startup:{generation}') as lock_result:
                if lock_result.acquired:
                    ready_state = await self.get_startup_state(app, generation)
                    activated, stale_ready_reported = await self._process_startup_state(
                        app,
                        generation,
                        ready_state,
                        stale_ready_reported=stale_ready_reported,
                        ready_message='锁内复用当前代际插件 ready，开始本地激活',
                        failed_message='锁内检测到当前代际插件启动 failed marker',
                    )
                    if activated:
                        return
                    logger.bind(
                        startup_generation=generation,
                        plugin_startup_role='writer',
                        ready_status=ready_state.get('status', 'missing'),
                    ).info('🎯 当前 worker 成为插件启动 writer')
                    await self._run_startup_writer(app, generation, create_tables)
                    return

            ready_state = await self.get_startup_state(app, generation)
            activated, stale_ready_reported = await self._process_startup_state(
                app,
                generation,
                ready_state,
                stale_ready_reported=stale_ready_reported,
                ready_message='等待结束，复用当前代际插件 ready',
                failed_message='等待期间检测到当前代际插件启动 failed marker',
            )
            if activated:
                return
            if not wait_reported:
                logger.bind(
                    startup_generation=generation,
                    plugin_startup_role='reader',
                    ready_status=ready_state.get('status', 'missing'),
                ).debug('⏳ 等待插件启动 writer 发布当前代际 ready')
                wait_reported = True
            await asyncio.sleep(self.ready_wait_interval_seconds)

        logger.bind(
            startup_generation=generation,
            plugin_startup_role='reader',
            ready_status=ready_state.get('status', 'missing'),
        ).error('❌ 等待插件启动 ready 超时')
        raise TimeoutError(f'等待插件启动代际 {generation} ready 超时')

    async def _process_startup_state(
        self,
        app: FastAPI,
        generation: str,
        ready_state: Mapping[str, str],
        *,
        stale_ready_reported: bool,
        ready_message: str,
        failed_message: str,
    ) -> tuple[bool, bool]:
        """
        处理一次插件启动状态读取结果。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :param ready_state: 当前ready状态
        :param stale_ready_reported: 是否已记录过期ready告警
        :param ready_message: 复用ready时的日志
        :param failed_message: 发现failed marker时的日志
        :return: 是否已完成reader激活、是否已记录过期ready告警
        """
        ready_status = ready_state.get('status', 'missing')
        reader_logger = logger.bind(
            startup_generation=generation,
            plugin_startup_role='reader',
            ready_status=ready_status,
        )
        if ready_status == 'success':
            if await self.requires_startup_write():
                if not stale_ready_reported:
                    logger.bind(
                        startup_generation=generation,
                        plugin_startup_role='reader',
                        ready_status=ready_status,
                        stale_ready_ignored=True,
                        startup_write_required=True,
                        startup_write_reason='missing_default_plugin_state',
                    ).warning('⚠️ 数据库默认插件状态缺失，忽略当前代际旧 ready 标记')
                return False, True
            logger.bind(
                startup_generation=generation,
                plugin_startup_role='reader',
                ready_status=ready_status,
                plugin_install_lifecycle='skipped',
                plugin_resource_sync='skipped',
                plugin_entity_table_sync='skipped',
            ).info(
                '⏭️ 复用插件 ready 状态，跳过启动期全局写入：'
                'plugin_install_lifecycle=skipped，'
                'plugin_resource_sync=skipped，'
                'plugin_entity_table_sync=skipped'
            )
            reader_logger.debug(f'🔄 {ready_message}')
            await self._activate_startup_reader(app, generation)
            return True, stale_ready_reported
        if ready_status == 'failed':
            reader_logger.error(f'❌ {failed_message}')
            raise RuntimeError(self._build_startup_failure_message(ready_state))
        return False, stale_ready_reported

    async def requires_startup_write(self) -> bool:
        """
        校验 ready 标记对应的数据库状态是否仍然完整。

        测试替身或旧适配器未实现该能力时保持原有行为；生产启动管理器会检查
        默认启用插件是否仍具备安装状态。

        :return: 是否必须重新执行启动期写入
        """
        checker = getattr(type(self.startup_manager), 'requires_startup_write', None)
        if checker is None:
            return False
        return bool(await self.startup_manager.requires_startup_write())

    async def _run_startup_writer(
        self,
        app: FastAPI,
        generation: str,
        create_tables: Callable[[], Awaitable[None]],
    ) -> None:
        """
        执行当前代际唯一的插件启动写入。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :param create_tables: 数据库建表回调
        :return: None
        """
        app.state.plugin_startup_write_enabled = True
        writer_logger = logger.bind(
            startup_generation=generation,
            plugin_startup_role='writer',
            ready_status='initializing',
        )
        writer_logger.info('🔄 开始同步插件全局启动资源')
        await self.clear_startup_ready(app, generation)
        try:
            await self.startup_manager.prepare_enabled_plugins(app, startup_write_enabled=True)
            await create_tables()
            await self.startup_manager.activate_enabled_plugins(app, startup_write_enabled=True)
        except Exception as exc:
            await self.mark_startup_failed(app, generation, exc)
            logger.bind(
                startup_generation=generation,
                plugin_startup_role='writer',
                ready_status='failed',
            ).exception('❌ 插件全局启动资源同步失败，已写入 failed marker')
            raise
        await self.mark_startup_ready(app, generation)
        logger.bind(
            startup_generation=generation,
            plugin_startup_role='writer',
            ready_status='success',
        ).info('✅ 插件全局启动资源同步完成')
        self._log_startup_completed(app, generation, role='writer')

    async def _activate_startup_reader(self, app: FastAPI, generation: str) -> None:
        """
        在当前 worker 执行无全局写入的本地插件激活。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :return: None
        """
        reader_logger = logger.bind(
            startup_generation=generation,
            plugin_startup_role='reader',
            ready_status='success',
        )
        reader_logger.debug('🔄 开始执行插件本地实体、Hook和路由激活')
        await self.startup_manager.prepare_enabled_plugins(app, startup_write_enabled=False)
        await self.startup_manager.activate_enabled_plugins(app, startup_write_enabled=False)
        reader_logger.debug('✅ 插件本地实体、Hook和路由激活完成')
        self._log_startup_completed(app, generation, role='reader')

    @staticmethod
    def _log_startup_completed(app: FastAPI, generation: str, *, role: str) -> None:
        """
        为每个成功启动的worker输出一条稳定可见的插件运行时摘要。

        writer和reader内部过程仍按原有级别记录；该INFO摘要用于避免命中ready后
        只有DEBUG日志而表现为插件日志随机缺失。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :param role: 当前worker的插件启动角色
        :return: None
        """
        plugin_registry = getattr(app.state, 'plugin_registry', None)
        enabled_plugin_ids = (
            sorted(str(plugin.plugin_id) for plugin in plugin_registry.list_enabled_plugins())
            if plugin_registry is not None
            else []
        )
        enabled_plugins = ','.join(enabled_plugin_ids) or 'none'
        logger.bind(
            startup_generation=generation,
            plugin_startup_role=role,
            ready_status='success',
            enabled_plugin_ids=enabled_plugin_ids,
            enabled_plugin_count=len(enabled_plugin_ids),
        ).info(f'✅ 插件运行时启动完成：role={role}，generation={generation[:8]}，enabled={enabled_plugins}')

    async def shutdown(self, app: FastAPI) -> None:
        """
        关闭插件运行时。

        :param app: FastAPI对象
        :return: None
        """
        self._ensure_bound(app)
        startup_write_enabled = bool(getattr(app.state, 'plugin_startup_write_enabled', False))
        await self.startup_manager.shutdown(app, startup_write_enabled=startup_write_enabled)

    async def clear_startup_ready(self, app: FastAPI, generation: str | None = None) -> None:
        """
        清除指定代际的插件启动 ready 标记。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :return: None
        """
        resolved_generation = generation or self.resolve_startup_generation()
        await app.state.redis.delete(self.build_ready_key(resolved_generation))

    async def mark_startup_ready(self, app: FastAPI, generation: str | None = None) -> None:
        """
        标记指定代际已完成插件启动写入。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :return: None
        """
        resolved_generation = generation or self.resolve_startup_generation()
        await app.state.redis.set(
            self.build_ready_key(resolved_generation),
            json.dumps({'generation': resolved_generation, 'status': 'success'}, ensure_ascii=False),
            ex=self.ready_expire_seconds,
        )
        writer_logger = logger.bind(
            startup_generation=resolved_generation,
            plugin_startup_role='writer',
            ready_status='success',
        )
        failed_plugin_ids = getattr(app.state, 'plugin_dependency_failed_plugin_ids', set())
        if failed_plugin_ids:
            writer_logger.warning(
                f'⚠️ 插件启动协调已完成，依赖检查失败插件已隔离：{"、".join(sorted(failed_plugin_ids))}'
            )
            return
        writer_logger.info('✅ 插件启动资源已就绪')

    async def mark_startup_failed(self, app: FastAPI, generation: str, error: Exception) -> None:
        """
        标记指定插件启动代际初始化失败。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :param error: 启动异常
        :return: None
        """
        await app.state.redis.set(
            self.build_ready_key(generation),
            json.dumps(
                {
                    'generation': generation,
                    'status': 'failed',
                    'error': str(error)[:1000],
                },
                ensure_ascii=False,
            ),
            ex=self.failed_expire_seconds,
        )

    async def get_startup_state(self, app: FastAPI, generation: str) -> dict[str, str]:
        """
        读取指定代际的插件启动状态。

        :param app: FastAPI对象
        :param generation: 插件启动代际
        :return: 启动状态
        """
        raw_state = await app.state.redis.get(self.build_ready_key(generation))
        if not raw_state:
            return {}
        try:
            state = json.loads(raw_state)
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(state, dict) or state.get('generation') != generation:
            return {}
        return {str(key): str(value) for key, value in state.items()}

    def resolve_startup_generation(self) -> str:
        """
        解析当前插件启动代际。

        :return: 插件启动代际
        """
        if self.startup_generation:
            return self.startup_generation
        generation_resolver = PluginStartupGenerationResolver(self.startup_manager.builder.backend_root)
        self.startup_generation = generation_resolver.resolve()
        return self.startup_generation

    def build_ready_key(self, generation: str) -> str:
        """
        构建代际隔离的 ready key。

        :param generation: 插件启动代际
        :return: Redis key
        """
        return f'{self.ready_key}:{generation}'

    @staticmethod
    def _build_startup_failure_message(state: Mapping[str, str]) -> str:
        """
        构建启动失败错误消息。

        :param state: 启动状态
        :return: 错误消息
        """
        error_message = state.get('error') or '未知错误'
        return f'插件启动代际 {state.get("generation", "")} 初始化失败：{error_message}'

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
    from plugins.core.runtime.service.lifecycle_lock import RedisPluginLifecycleLock  # noqa: PLC0415

    startup_manager = PluginRuntimeStartupManager(
        management_gateway=PluginManagementStartupGateway(),
        route_state_gateway=PluginManagementRouteStateGateway(),
    )
    return PluginApplicationRuntime(
        startup_manager=startup_manager,
        lifecycle_lock=RedisPluginLifecycleLock(),
    )
