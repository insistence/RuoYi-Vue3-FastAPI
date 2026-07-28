from pathlib import Path

from pydantic import BaseModel, Field

from plugins.core.discovery.registry import PluginRegistry
from plugins.core.discovery.scanner import (
    DiscoveredPlugin,
    PluginDiscoveryError,
    PluginScanner,
)
from plugins.core.environment import PluginRuntimeEnvironmentService
from plugins.core.runtime.entities import EntityModuleImporter
from plugins.core.types import PluginStateRecord
from utils.log_util import logger


class PluginEntityImportFailure(BaseModel):
    """
    插件实体导入失败结果。
    """

    plugin_id: str = Field(description='插件ID')
    error_message: str = Field(description='错误信息')


class PluginEntityImportResult(BaseModel):
    """
    插件实体导入结果。
    """

    imported_count: int = Field(default=0, description='成功导入实体模块数量')
    failures: list[PluginEntityImportFailure] = Field(default_factory=list, description='实体导入失败结果列表')


class PluginRuntimeBuilder:
    """
    插件运行时构建器。

    使用 Builder 模式封装插件发现和运行时注册表构建过程，便于后续逐步加入数据库状态、
    依赖检查和生命周期处理。
    """

    def __init__(self, backend_root: Path | str | None = None) -> None:
        """
        初始化插件运行时构建器。

        :param backend_root: 后端项目根目录
        """
        self.backend_root = Path(backend_root) if backend_root else Path(__file__).resolve().parents[3]
        self.plugins_root = self.backend_root / 'plugins'
        self.frontend_plugins_root = Path(
            PluginRuntimeEnvironmentService(backend_root=self.backend_root).get_frontend_plugins_dir()
        )
        self.entity_importer = EntityModuleImporter(self.backend_root)
        self._discovered_plugins: list[DiscoveredPlugin] | None = None
        self._discovery_errors: list[PluginDiscoveryError] | None = None

    def discover_plugins(self) -> list[DiscoveredPlugin]:
        """
        发现后端插件。

        单个损坏插件不会影响其他正常插件，失败明细记录在 :attr:`discovery_errors` 中，
        便于上层日志和监控。根目录配置类错误（目录不存在、文件名非法等）仍以异常形式抛出。

        :return: 已发现插件列表
        """
        if self._discovered_plugins is not None:
            return self._discovered_plugins
        discovery_result = PluginScanner(self.plugins_root).discover_with_errors()
        self._discovered_plugins = discovery_result.plugins
        self._discovery_errors = discovery_result.errors
        for error in discovery_result.errors:
            logger.error(f'❌ 插件扫描失败，已隔离损坏插件：目录={error.plugin_dir}，错误：{error.error_message}')

        return self._discovered_plugins

    @property
    def discovery_errors(self) -> list[PluginDiscoveryError]:
        """
        获取插件扫描错误明细。

        :return: 插件扫描错误明细列表
        """
        if self._discovery_errors is None:
            self.discover_plugins()
        return self._discovery_errors or []

    def build_registry(self, database_plugins: list[PluginStateRecord] | None = None) -> PluginRegistry:
        """
        构建插件运行时注册表。

        :param database_plugins: 数据库插件状态列表
        :return: 插件运行时注册表
        """
        return PluginRegistry.build(self.discover_plugins(), database_plugins)

    def import_builtin_entities(self) -> None:
        """
        导入内置业务模块实体。

        :return: None
        """
        self.entity_importer.import_builtin_entities()

    def import_plugin_entities(self, plugin_registry: PluginRegistry) -> PluginEntityImportResult:
        """
        导入启用插件实体。

        :param plugin_registry: 插件运行时注册表
        :return: 插件实体导入结果
        """
        import_result = PluginEntityImportResult()
        for plugin in plugin_registry.list_enabled_plugins():
            entity_do_dir = plugin.backend_path / 'entity' / 'do'
            if not entity_do_dir.is_dir():
                continue
            try:
                imported_modules = self.entity_importer.import_entity_dirs([entity_do_dir], strict=True)
                import_result.imported_count += len(imported_modules)
            except Exception as exc:
                logger.exception(f'❌ 插件实体导入失败：{plugin.plugin_id}，错误：{exc}')
                import_result.failures.append(
                    PluginEntityImportFailure(plugin_id=plugin.plugin_id, error_message=str(exc))
                )

        return import_result
