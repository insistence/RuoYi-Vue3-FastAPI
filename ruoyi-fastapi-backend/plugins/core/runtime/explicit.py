import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from starlette.requests import Request
from starlette.routing import Mount
from starlette.types import Scope

from config.database import Base, DataSourceRegistry
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from plugins.core.discovery.registry import PluginRegistry, RegisteredPlugin
from plugins.core.discovery.scanner import is_artifact_plugin
from plugins.core.runtime.asgi import PluginGatewayASGI, PluginLifespanManager
from plugins.core.runtime.browser_session import authenticate_browser_session
from plugins.core.runtime.bundle import PluginBundleASGI
from plugins.core.runtime.configuration import PluginConfigObservation, PluginConfigReader, config_revision
from plugins.core.runtime.connections import AUTH_RECHECK_KEY
from plugins.core.runtime.entrypoint import PluginEntrypointLoader
from plugins.core.runtime.health import PluginHealthChecker
from plugins.core.runtime.host_services import build_host_services
from plugins.core.runtime.job_dispatcher import PluginJobBinding, bind_plugin_jobs, unbind_plugin_jobs
from plugins.core.runtime.metrics import PluginObservedASGI, PluginRuntimeMetrics
from plugins.core.runtime.metrics_store import PluginMetricsReporter
from plugins.core.runtime.route_guard import PluginEnabledDependency, PluginRouteStateGateway
from plugins.core.sdk import PluginDefinition, PluginHostContext, PluginRequestContext
from plugins.core.sdk.request import current_plugin_request_id
from plugins.core.validation.manifest import PluginManifestChecker
from plugins.core.validation.structure import PluginStructureChecker
from utils.log_util import logger


@dataclass
class LoadedExplicitPlugin:
    """
    一个 worker 的已加载定义及可选 lifespan。

    :param plugin: 注册表中的插件记录
    :param host: 当前插件的宿主能力上下文
    :param definition: 入口返回的插件能力定义
    :param lifespan: ASGI 子应用生命周期管理器
    :param active: 插件是否已完成激活
    :param jobs: 当前 worker 中的插件任务绑定
    :param gateway: 当前 worker 的 ASGI 长连接管理入口
    """

    plugin: RegisteredPlugin
    host: PluginHostContext
    definition: PluginDefinition
    lifespan: PluginLifespanManager | None = None
    active: bool = False
    jobs: PluginJobBinding | None = None
    gateway: PluginGatewayASGI | None = None


class ExplicitPluginRuntime:
    """
    仅负责当前 worker 的代码和资源，全局迁移仍由原有 writer 处理。
    """

    def __init__(self, route_state_gateway: PluginRouteStateGateway) -> None:
        """
        初始化当前 worker 的显式插件运行时。

        :param route_state_gateway: 插件启用状态查询网关
        :return: None
        """
        self.route_state_gateway = route_state_gateway
        self.loaded: dict[str, LoadedExplicitPlugin] = {}
        self.metrics = PluginRuntimeMetrics()
        self.metrics_reporter = PluginMetricsReporter(self.metrics)
        self._closing = False

    @staticmethod
    def ordered_plugins(registry: PluginRegistry) -> list[RegisteredPlugin]:
        """
        稳定的依赖拓扑排序，拒绝缺失依赖及循环。

        :param registry: 包含待排序插件的注册表
        :return: 按依赖优先顺序排列的已启用插件
        """
        plugins = {item.plugin_id: item for item in registry.list_enabled_plugins()}
        visiting: set[str] = set()
        visited: set[str] = set()
        result = []

        def visit(plugin_id: str) -> None:
            """
            递归访问插件依赖并记录拓扑顺序。

            :param plugin_id: 当前访问的插件 ID
            :return: None
            """
            if plugin_id in visited:
                return
            if plugin_id in visiting:
                raise ValueError(f'插件存在循环依赖：{plugin_id}')
            if plugin_id not in plugins:
                raise ValueError(f'插件依赖未启用：{plugin_id}')
            visiting.add(plugin_id)
            plugin = plugins[plugin_id]
            for dependency in plugin.discovered_plugin.manifest.dependencies.plugins:
                visit(dependency.id)
            visiting.remove(plugin_id)
            visited.add(plugin_id)
            result.append(plugin)

        for plugin_id in plugins:
            visit(plugin_id)
        return result

    @classmethod
    def dependency_order(cls, registry: PluginRegistry) -> tuple[list[RegisteredPlugin], dict[str, str]]:
        """
        按依赖闭包分别排序，损坏分支不阻断独立插件。

        :param registry: 包含全部已发现插件的注册表
        :return: 可加载的插件依赖顺序及各失败入口的错误信息
        """
        plugins = {item.plugin_id: item for item in registry.list_enabled_plugins()}
        ordered: dict[str, RegisteredPlugin] = {}
        errors: dict[str, str] = {}
        for plugin_id, plugin in plugins.items():
            if not plugin.discovered_plugin.manifest.uses_entrypoint:
                continue
            closure: dict[str, RegisteredPlugin] = {}

            def collect(current: str, closure: dict[str, RegisteredPlugin] = closure) -> None:
                """
                收集当前入口依赖的插件闭包。

                :param current: 当前访问的插件 ID
                :param closure: 当前入口已收集的依赖插件映射
                :return: None
                """
                if current in closure:
                    return
                if current not in plugins:
                    raise ValueError(f'插件依赖未启用：{current}')
                closure[current] = plugins[current]
                for dependency in plugins[current].discovered_plugin.manifest.dependencies.plugins:
                    collect(dependency.id, closure)

            try:
                collect(plugin_id)
                for dependency in cls.ordered_plugins(PluginRegistry(list(closure.values()))):
                    ordered[dependency.plugin_id] = dependency
            except ValueError as exc:
                errors[plugin_id] = str(exc)
        return list(ordered.values()), errors

    def prepare(
        self,
        plugin: RegisteredPlugin,
        app: FastAPI,
        *,
        startup_write_enabled: bool,
        config_values: Mapping[str, Any] | None = None,
    ) -> None:
        """
        导入显式模型定义，在原有建表步骤之前完成。

        :param plugin: 注册表中的待准备插件
        :param app: 宿主 FastAPI 应用
        :param startup_write_enabled: 当前 worker 是否允许执行启动期全局写入
        :param config_values: 插件专属配置快照，未提供时使用清单默认值
        :return: None
        """
        if plugin.plugin_id in self.loaded:
            return
        discovered = plugin.discovered_plugin
        manifest = discovered.manifest
        builder = getattr(app.state, 'plugin_runtime_builder', None)
        backend_root = getattr(builder, 'backend_root', discovered.backend_path.parents[1])
        structure = PluginStructureChecker(backend_root).check(discovered, include_frontend=False)
        if not structure.ok:
            raise ValueError('；'.join(item.message for item in structure.failed_items))
        compatibility = PluginManifestChecker(backend_root=backend_root).check(manifest)
        if not compatibility.ok:
            raise ValueError('；'.join(item.message for item in compatibility.error_issues))
        values = (
            dict(config_values)
            if config_values is not None
            else {item.key: item.default for item in manifest.config.items}
        )
        observation = PluginConfigObservation(
            plugin_id=plugin.plugin_id,
            version=manifest.version,
            digest=discovered.artifact_digest,
            generation=discovered.artifact_generation,
            startup_revision=config_revision(plugin.plugin_id, values),
        )
        host = PluginHostContext(
            plugin_id=plugin.plugin_id,
            resource_root=discovered.backend_path,
            config=values,
            config_revision=observation.startup_revision,
            config_reader=PluginConfigReader(discovered, DataSourceRegistry.session, observation).read,
            session_factory=DataSourceRegistry.session,
            services=build_host_services(
                plugin.plugin_id, DataSourceRegistry.session, getattr(app.state, 'redis', None)
            ),
            redis=getattr(app.state, 'redis', None),
            logger=logger.bind(plugin_id=plugin.plugin_id),
            startup_write_enabled=startup_write_enabled and not is_artifact_plugin(discovered),
        )
        existing_tables = set(Base.metadata.tables)
        try:
            definition = PluginEntrypointLoader(discovered).load(host)
            if definition.register_models:
                result = definition.register_models(host)
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise TypeError('register_models 必须同步注册元数据，不能执行异步数据库操作')
        finally:
            if is_artifact_plugin(discovered):
                for key in set(Base.metadata.tables) - existing_tables:
                    Base.metadata.tables[key].info['plugin_artifact'] = plugin.plugin_id
        self.loaded[plugin.plugin_id] = LoadedExplicitPlugin(plugin, host, definition)
        worker = getattr(app.state, 'plugin_release_worker', None)
        if worker is not None:
            self.metrics.worker_id = worker.worker_id
        self.metrics.register(
            plugin.plugin_id, manifest.version, discovered.artifact_digest, discovered.artifact_generation
        )
        if plugin.plugin_id in self.metrics.identities:
            self.metrics.configurations[plugin.plugin_id] = observation
        app.state.plugin_metrics_reporter = self.metrics_reporter

    async def activate(self, plugin_id: str, app: FastAPI) -> None:
        """
        全部校验和初始化成功后才向应用注册路由或挂载子应用。

        :param plugin_id: 已完成准备的插件 ID
        :param app: 宿主 FastAPI 应用
        :return: None
        """
        if self._closing:
            raise RuntimeError('插件运行时已进入关闭阶段，不能激活插件')
        loaded = self.loaded[plugin_id]
        if loaded.active:
            return
        if loaded.lifespan is not None and loaded.lifespan.has_pending_task:
            raise RuntimeError(f'插件上一次生命周期尚未退出：{plugin_id}')
        if loaded.plugin.discovered_plugin.manifest.backend.jobs:
            loaded.jobs = bind_plugin_jobs(
                loaded.plugin.discovered_plugin,
                loaded.host,
                self.route_state_gateway,
                lambda: loaded.active and (loaded.lifespan is None or loaded.lifespan.ready),
                metrics=self.metrics,
            )
        try:
            await self._activate_web(loaded, app)
        except BaseException:
            if loaded.jobs is not None:
                try:
                    await unbind_plugin_jobs(loaded.jobs)
                    loaded.jobs = None
                except Exception:
                    logger.exception(f'插件激活失败后的任务回收失败：{plugin_id}')
            raise
        loaded.active = True
        if plugin_id in self.metrics.configurations:
            self.metrics.configurations[plugin_id].active = True
        app.openapi_schema = None

    async def _activate_web(self, loaded: LoadedExplicitPlugin, app: FastAPI) -> None:
        """
        任务绑定成功后再注册 Web 能力，避免重复 worker 实例留下半注册路由。

        :param loaded: 当前 worker 已准备的插件实例
        :param app: 宿主 FastAPI 应用
        :return: None
        """
        plugin_id = loaded.plugin.plugin_id
        manifest = loaded.plugin.discovered_plugin.manifest
        if manifest.integration_kind == 'router':
            await self._check_health(loaded, app)
            if self._closing:
                raise RuntimeError('插件运行时已进入关闭阶段，不能注册路由')
            self._register_routers(loaded, app)
        else:
            child = loaded.definition.app_factory(loaded.host)
            if inspect.isawaitable(child):
                if inspect.iscoroutine(child):
                    child.close()
                raise TypeError('app_factory 必须同步返回 ASGI 应用')
            if not callable(child):
                raise TypeError('app_factory 必须返回 ASGI callable')
            if isinstance(child, FastAPI):
                child.state.plugin_host = loaded.host
                child.state.redis = loaded.host.redis
            mount_path = manifest.backend.asgi.mount_path
            if any(getattr(route, 'path', None) == mount_path for route in app.routes):
                raise ValueError(f'插件挂载路径冲突：{mount_path}')
            manager = PluginLifespanManager(child, managed=manifest.backend.asgi.lifespan == 'managed')
            loaded.lifespan = manager
            try:
                await manager.startup()
                await self._check_health(loaded, app)
                if self._closing:
                    raise RuntimeError('插件运行时已进入关闭阶段，不能挂载子应用')
                web_app = child
                if manifest.frontend.delivery.type == 'bundle':
                    web_app = PluginBundleASGI(child, plugin_id, loaded.plugin.backend_path, manifest.frontend.bundle)
                gateway = PluginGatewayASGI(web_app, manager, self._authorizer(loaded, app))
                observed = PluginObservedASGI(gateway, self.metrics, plugin_id)
                app.router.routes.append(Mount(mount_path, app=observed, name=f'plugin:{plugin_id}'))
                loaded.gateway = gateway
            except BaseException:
                try:
                    await manager.shutdown()
                except Exception:
                    logger.exception(f'插件激活失败后的 ASGI 回收失败：{plugin_id}')
                raise

    @staticmethod
    async def _check_health(loaded: LoadedExplicitPlugin, app: FastAPI) -> None:
        """
        执行清单声明的健康检查并阻止不健康插件激活。

        :param loaded: 当前 worker 已准备的插件实例
        :param app: 宿主 FastAPI 应用
        :return: None
        """
        if loaded.plugin.discovered_plugin.manifest.backend.health.checker:
            result = await PluginHealthChecker(loaded.plugin.discovered_plugin).check(app=app)
            if not result.ok:
                raise RuntimeError(f'插件激活健康检查失败：{result.message}')

    def _register_routers(self, loaded: LoadedExplicitPlugin, app: FastAPI) -> None:
        """
        校验插件路由命名空间并注册带宿主权限依赖的路由。

        :param loaded: 当前 worker 已准备的插件实例
        :param app: 宿主 FastAPI 应用
        :return: None
        """
        plugin_id = loaded.plugin.plugin_id

        async def set_context(request: Request, user: Any = Depends(LoginService.get_current_user)) -> None:
            """
            检查插件状态并向请求写入宿主身份上下文。

            :param request: 插件接口请求
            :param user: 宿主登录依赖返回的当前用户
            :return: None
            """
            if not loaded.active:
                raise HTTPException(status_code=503, detail='插件未就绪')
            try:
                request.state.plugin_context = self._request_context(loaded, user)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

        for router in loaded.definition.routers:
            for route in router.routes:
                if not PluginStructureChecker._is_plugin_route_prefix(plugin_id, getattr(route, 'path', '')):
                    raise ValueError(f'插件路由越过命名空间：{getattr(route, "path", "")}')
                if not hasattr(route, 'methods'):
                    raise ValueError('v2 Router 的 WebSocket 或嵌套 Mount 请使用 ASGI 接入')
        for router in loaded.definition.routers:
            previous_routes = len(app.router.routes)
            app.include_router(
                router,
                dependencies=[
                    PluginEnabledDependency(plugin_id, self.route_state_gateway),
                    Depends(set_context),
                ],
            )
            for route in app.router.routes[previous_routes:]:
                route.handle = PluginObservedASGI(route.handle, self.metrics, plugin_id)

    def _authorizer(self, loaded: LoadedExplicitPlugin, app: FastAPI) -> Any:
        """
        创建复用宿主登录及插件会话校验的 ASGI 授权器。

        :param loaded: 当前 worker 已准备的插件实例
        :param app: 宿主 FastAPI 应用
        :return: 根据请求作用域构建插件身份上下文的异步函数
        """

        async def authorize(scope: Scope) -> PluginRequestContext:
            # LoginService 使用宿主 request.app.state，而子应用会替换 scope['app']。
            """
            校验插件启用状态和登录凭证，并构建插件请求身份。

            :param scope: HTTP 或 WebSocket 的 ASGI 请求作用域
            :return: 已通过宿主身份及插件访问权限校验的请求上下文
            """
            auth_scope = dict(scope, type='http', app=app)
            request = Request(auth_scope)
            if not loaded.active:
                raise PermissionError('插件未激活或正在关闭')
            authorization = request.headers.get('authorization', '')
            scheme, _, token = authorization.partition(' ')
            async with DataSourceRegistry.session() as db:
                if not await self.route_state_gateway.is_plugin_enabled(db, loaded.plugin.plugin_id):
                    raise PermissionError('插件未启用')
                if authorization:
                    if scheme.lower() != 'bearer' or not token.strip():
                        raise LookupError('Bearer 凭证无效')
                    try:
                        resolve_user = (
                            LoginService.get_current_user_for_plugin_session
                            if scope.get(AUTH_RECHECK_KEY)
                            else LoginService.get_current_user
                        )
                        user = await resolve_user(request=request, token=token.strip(), query_db=db)
                    except AuthException as exc:
                        raise LookupError('登录已失效') from exc
                elif loaded.plugin.discovered_plugin.manifest.frontend.delivery.type == 'bundle':
                    user = await authenticate_browser_session(
                        request,
                        plugin_id=loaded.plugin.plugin_id,
                        version=loaded.plugin.discovered_plugin.manifest.version,
                        query_db=db,
                        websocket=scope['type'] == 'websocket',
                    )
                else:
                    raise LookupError('缺少 Bearer 凭证')
            return self._request_context(loaded, user)

        return authorize

    @staticmethod
    def _request_context(loaded: LoadedExplicitPlugin, user: Any) -> PluginRequestContext:
        """
        检查插件访问权限并构建宿主签发的请求上下文。

        :param loaded: 当前 worker 已准备的插件实例
        :param user: 宿主登录服务返回的当前用户
        :return: 绑定插件能力与当前用户身份的请求上下文
        """
        permissions = frozenset(user.permissions)
        declared = set(loaded.plugin.discovered_plugin.manifest.permission_codes)
        if declared and '*:*:*' not in permissions and not declared.intersection(permissions):
            raise PermissionError('缺少插件访问权限')
        return PluginRequestContext(loaded.host, user, permissions, request_id=current_plugin_request_id())

    async def shutdown(self) -> None:
        """
        逆序关闭，每个实例的失败不阻止其他实例释放资源。

        :return: None
        """
        self._closing = True
        instances = list(reversed(self.loaded.values()))
        for loaded in instances:
            loaded.active = False
            if loaded.plugin.plugin_id in self.metrics.configurations:
                self.metrics.configurations[loaded.plugin.plugin_id].active = False
        for loaded in instances:
            if loaded.gateway is not None:
                try:
                    await loaded.gateway.drain()
                except Exception:
                    logger.exception(f'插件长连接关闭失败：{loaded.plugin.plugin_id}')
            if loaded.jobs is not None:
                try:
                    await unbind_plugin_jobs(loaded.jobs)
                    loaded.jobs = None
                except Exception:
                    logger.exception(f'插件任务关闭失败：{loaded.plugin.plugin_id}')
            if loaded.lifespan is not None:
                try:
                    await loaded.lifespan.shutdown()
                except Exception:
                    logger.exception(f'插件 ASGI 关闭失败：{loaded.plugin.plugin_id}')
        try:
            await self.metrics_reporter.stop()
        except Exception:
            logger.exception('插件指标上报关闭失败')
