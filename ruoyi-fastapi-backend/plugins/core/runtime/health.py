import inspect
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from plugins.core.discovery.scanner import DiscoveredPlugin
from plugins.core.runtime.callable import LoadedPluginCallable, PluginCallableLoader


@dataclass(frozen=True)
class PluginHealthContext:
    """
    插件健康检查上下文。

    :param plugin_id: 插件 ID
    :param discovered_plugin: 已发现插件对象
    :param app: FastAPI 应用对象
    :param query_db: orm对象
    """

    plugin_id: str
    discovered_plugin: DiscoveredPlugin
    app: Any | None = None
    query_db: Any | None = None


@dataclass(frozen=True)
class PluginHealthResult:
    """
    插件健康检查结果。

    :param plugin_id: 插件 ID
    :param ok: 健康检查是否通过
    :param status: 健康状态
    :param message: 健康检查说明
    :param checker: 健康检查声明路径
    :param duration_ms: 检查耗时毫秒
    :param details: 健康检查扩展详情
    :param error: 健康检查异常信息
    """

    plugin_id: str
    ok: bool
    status: str
    message: str
    checker: str | None
    duration_ms: float
    details: dict[str, Any]
    error: str | None = None


class PluginHealthChecker:
    """
    插件健康检查器。

    使用 Strategy + Command Runner 思路执行插件 manifest 中声明的只读健康检查 callable。
    """

    def __init__(self, discovered_plugin: DiscoveredPlugin) -> None:
        """
        初始化插件健康检查器。

        :param discovered_plugin: 已发现插件对象
        :return: None
        """
        self.discovered_plugin = discovered_plugin

    async def check(self, *, app: Any | None = None, query_db: Any | None = None) -> PluginHealthResult:
        """
        执行插件健康检查。

        :param app: FastAPI 应用对象
        :param query_db: orm对象
        :return: 插件健康检查结果
        """
        checker_path = self.discovered_plugin.manifest.backend.health.checker
        started_at = perf_counter()
        if not checker_path:
            return self._build_result(
                ok=True,
                status='unknown',
                message='插件未声明健康检查',
                checker=None,
                started_at=started_at,
            )

        try:
            checker_callable = self._load_checker_callable(checker_path)
            context = PluginHealthContext(
                plugin_id=self.discovered_plugin.manifest.id,
                discovered_plugin=self.discovered_plugin,
                app=app,
                query_db=query_db,
            )
            raw_result = self._invoke_checker(checker_callable, context)
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
            return self._normalize_result(raw_result, checker_path, started_at)
        except Exception as exc:
            return self._build_result(
                ok=False,
                status='error',
                message='插件健康检查执行失败',
                checker=checker_path,
                started_at=started_at,
                error=str(exc),
            )

    def _load_checker_callable(self, checker_path: str) -> LoadedPluginCallable:
        """
        加载健康检查 callable。

        :param checker_path: 健康检查声明路径
        :return: 健康检查 callable
        """
        return PluginCallableLoader(self.discovered_plugin, label='健康检查').load(checker_path)

    @staticmethod
    def _invoke_checker(checker_callable: LoadedPluginCallable, context: PluginHealthContext) -> Any:
        """
        调用健康检查 callable。

        :param checker_callable: 已加载的健康检查 callable
        :param context: 健康检查上下文
        :return: 健康检查原始返回值
        """
        callable_object = checker_callable.callable_object
        signature = inspect.signature(callable_object)
        if not signature.parameters:
            return callable_object()

        return callable_object(context)

    def _normalize_result(self, raw_result: Any, checker_path: str, started_at: float) -> PluginHealthResult:
        """
        规范化健康检查返回值。

        :param raw_result: 健康检查原始返回值
        :param checker_path: 健康检查声明路径
        :param started_at: 检查开始时间
        :return: 插件健康检查结果
        """
        if isinstance(raw_result, dict):
            ok = bool(raw_result.get('ok', raw_result.get('healthy', True)))
            return self._build_result(
                ok=ok,
                status=str(raw_result.get('status') or ('healthy' if ok else 'unhealthy')),
                message=str(raw_result.get('message') or ('插件健康检查通过' if ok else '插件健康检查未通过')),
                checker=checker_path,
                started_at=started_at,
                details=raw_result.get('details') if isinstance(raw_result.get('details'), dict) else {},
            )
        if isinstance(raw_result, bool):
            return self._build_result(
                ok=raw_result,
                status='healthy' if raw_result else 'unhealthy',
                message='插件健康检查通过' if raw_result else '插件健康检查未通过',
                checker=checker_path,
                started_at=started_at,
            )

        return self._build_result(
            ok=True,
            status='healthy',
            message='插件健康检查通过',
            checker=checker_path,
            started_at=started_at,
        )

    def _build_result(
        self,
        *,
        ok: bool,
        status: str,
        message: str,
        checker: str | None,
        started_at: float,
        details: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> PluginHealthResult:
        """
        构建健康检查结果。

        :param ok: 健康检查是否通过
        :param status: 健康状态
        :param message: 健康检查说明
        :param checker: 健康检查声明路径
        :param started_at: 检查开始时间
        :param details: 健康检查扩展详情
        :param error: 健康检查异常信息
        :return: 插件健康检查结果
        """
        return PluginHealthResult(
            plugin_id=self.discovered_plugin.manifest.id,
            ok=ok,
            status=status,
            message=message,
            checker=checker,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
            details=details or {},
            error=error,
        )
