# ruff: noqa: F401

import asyncio
import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from plugins.core.environment import PluginRuntimeEnvironmentService  # noqa: E402
from plugins.core.lifecycle.migration import PluginMigrationRunner  # noqa: E402
from plugins.core.lifecycle.purge import PluginPurgePlan, PluginPurgePlanItem, PluginPurgePlanner  # noqa: E402
from plugins.core.runtime.result import PluginOperationResult  # noqa: E402
from plugins.core.runtime.service import PluginRuntimeService  # noqa: E402
from plugins.core.runtime.service.dependency_container import PluginRuntimeGatewayOverrides  # noqa: E402
from plugins.core.runtime.service.migration_store import PluginDatabaseMigrationHistoryStore  # noqa: E402
from plugins.core.runtime.support import (  # noqa: E402
    PluginAuditPayloadBuilder,
    PluginBatchItemReport,
    PluginBatchReportBuilder,
    PluginConfigPayloadBuilder,
    PluginDependencyInstallPayloadBuilder,
    PluginDocumentationBuilder,
    PluginEnablePayloadBuilder,
    PluginLifecyclePayloadBuilder,
    PluginNpmPackageJsonSynchronizer,
    PluginPayloadBuilder,
    PluginPrecheckContext,
    PluginPurgePayloadBuilder,
    PluginRuntimePayloadBuilder,
)
from plugins.core.validation.dependencies import (  # noqa: E402
    DependencyCheckItem,
    DependencyCheckResult,
    DependencyInstallPlanItem,
    NpmDependencyInspector,
    PluginDependencyChecker,
    PythonDependencyInspector,
)
from plugins.core.validation.plugin_deps import (  # noqa: E402
    PluginDependencyCheckItem,
    PluginDependencyCheckResult,
    PluginDependencyPlan,
    PluginDependencyPlanBlocker,
    PluginDependencyPlanItem,
)

EXPECTED_DEPENDENCY_COUNT = 2
EXPECTED_PURGE_DESTRUCTIVE_COUNT = 5
EXPECTED_BATCH_SUCCEEDED_COUNT = 2
EXPECTED_CONFIG_ORDER = 10
EXPECTED_CONFIG_TOTAL = 3
EXPECTED_REQUIRED_CONFIG_COUNT = 2
EXPECTED_FRONTEND_BUILD_TIMEOUT = 300
MIN_NPM_INSTALL_COMMAND_LENGTH = 3


class FakeRuntimeEnvironment:
    """
    测试用运行时环境服务。
    """

    def __init__(self, backend_dir: Path, frontend_dir: Path | None = None) -> None:
        """
        初始化测试用运行时环境服务。

        :param backend_dir: 后端项目根目录
        :param frontend_dir: 前端项目根目录
        """
        self.backend_dir = backend_dir
        self.frontend_dir = frontend_dir or Path(
            PluginRuntimeEnvironmentService(backend_root=backend_dir).get_frontend_dir()
        )
        self.frontend_mode = 'dev'
        self.backend_runtime_mode = 'dev'

    def get_backend_dir(self) -> str:
        """
        获取后端项目根目录。

        :return: 后端项目根目录
        """
        return str(self.backend_dir)

    def get_backend_plugins_dir(self) -> str:
        """
        获取后端插件根目录。

        :return: 后端插件根目录
        """
        return str(self.backend_dir / 'plugins')

    def get_frontend_dir(self) -> str:
        """
        获取前端项目根目录。

        :return: 前端项目根目录
        """
        return str(self.frontend_dir)

    def get_frontend_plugins_dir(self) -> str:
        """
        获取前端插件根目录。

        :return: 前端插件根目录
        """
        return str(self.frontend_dir / 'plugins')

    @staticmethod
    def get_python_executable() -> str:
        """
        获取测试用 Python 解释器。

        :return: Python 解释器路径
        """
        return sys.executable

    def get_frontend_mode(self) -> str:
        """
        获取测试用前端模式。

        :return: 前端模式
        """
        return self.frontend_mode

    def get_backend_runtime_mode(self) -> str:
        """
        获取测试用后端运行模式。

        :return: 后端运行模式
        """
        return self.backend_runtime_mode


class FakeSession:
    """
    测试用异步数据库会话。
    """

    def __init__(self) -> None:
        """
        初始化测试用异步数据库会话。
        """
        self.committed = False
        self.rolled_back = False
        self.executed_statements = []

    async def __aenter__(self) -> 'FakeSession':
        """
        进入异步上下文。

        :return: 测试会话
        """
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """
        退出异步上下文。

        :param exc_type: 异常类型
        :param exc: 异常对象
        :param traceback: 异常堆栈
        :return: None
        """

    async def commit(self) -> None:
        """
        记录提交动作。

        :return: None
        """
        self.committed = True

    async def rollback(self) -> None:
        """
        记录回滚动作。

        :return: None
        """
        self.rolled_back = True

    async def execute(self, statement: object) -> None:
        """
        记录 SQL 执行动作。

        :param statement: SQL 语句
        :return: None
        """
        self.executed_statements.append(str(statement))


class FakeSessionLocal:
    """
    测试用异步数据库会话工厂。
    """

    def __init__(self) -> None:
        """
        初始化测试用异步数据库会话工厂。

        :return: None
        """
        self.last_session: FakeSession | None = None
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        """
        创建测试会话。

        :return: 测试会话
        """
        self.last_session = FakeSession()
        self.sessions.append(self.last_session)
        return self.last_session

    @property
    def audit_session(self) -> FakeSession | None:
        """
        获取最后一个审计会话。

        :return: 审计会话
        """
        return self.sessions[-1] if self.sessions else None

    @property
    def committed_session(self) -> FakeSession | None:
        """
        获取最后一个已提交会话。

        :return: 已提交会话
        """
        committed_sessions = [session for session in self.sessions if session.committed]
        return committed_sessions[-1] if committed_sessions else None

    @property
    def executed_session(self) -> FakeSession | None:
        """
        获取最后一个执行过 SQL 的会话。

        :return: 执行过 SQL 的会话
        """
        executed_sessions = [session for session in self.sessions if session.executed_statements]
        return executed_sessions[-1] if executed_sessions else None


class FakePluginService:
    """
    测试用插件服务。
    """

    upsert_called = False
    upsert_backend_root: Path | None = None
    upsert_frontend_root: Path | None = None
    install_enabled_menu_called = False
    install_plugin_menu_called_with: tuple[str, bool] | None = None
    install_config_called = False
    mark_installed_called = False
    mark_uninstalled_called_with: str | None = None
    purge_called = False
    update_enabled_called_with: tuple[str, bool, object | None] | None = None
    detail_plugin: SimpleNamespace | None = None
    upsert_plugin: SimpleNamespace | None = None
    installed_menu_conflicts: list[SimpleNamespace] = []
    migration_checksums: dict[tuple[str, str], str] = {}
    migration_records: list[object] = []
    operation_logs: list[object] = []
    plugin_list: list[SimpleNamespace] = []
    marked_errors: list[tuple[str, str]] = []

    @classmethod
    def reset(cls) -> None:
        """
        重置调用记录。

        :return: None
        """
        cls.upsert_called = False
        cls.upsert_backend_root = None
        cls.upsert_frontend_root = None
        cls.install_enabled_menu_called = False
        cls.install_plugin_menu_called_with = None
        cls.install_config_called = False
        cls.mark_installed_called = False
        cls.mark_uninstalled_called_with = None
        cls.purge_called = False
        cls.update_enabled_called_with = None
        cls.detail_plugin = None
        cls.upsert_plugin = None
        cls.installed_menu_conflicts = []
        cls.migration_checksums = {}
        cls.migration_records = []
        cls.operation_logs = []
        cls.plugin_list = []
        cls.marked_errors = []

    @classmethod
    async def get_plugin_list_services(cls, query_db: object) -> list[SimpleNamespace]:
        """
        读取测试用插件列表。

        :param query_db: orm对象
        :return: 插件列表
        """
        return cls.plugin_list

    @classmethod
    async def plugin_detail_services(cls, query_db: object, plugin_id: str) -> SimpleNamespace | None:
        """
        读取测试插件详情。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 插件模型
        """
        return cls.detail_plugin

    @classmethod
    async def upsert_discovered_plugin_services(
        cls,
        query_db: object,
        discovered_plugin: object,
        backend_root: Path,
        frontend_root: Path,
    ) -> SimpleNamespace:
        """
        记录插件写入调用。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件模型
        """
        cls.upsert_called = True
        cls.upsert_backend_root = backend_root
        cls.upsert_frontend_root = frontend_root
        if cls.upsert_plugin:
            return cls.upsert_plugin
        return SimpleNamespace(
            plugin_id=discovered_plugin.manifest.id,
            installed_version=discovered_plugin.manifest.version,
            enabled='0',
            status='installed',
            model_dump=lambda by_alias=True: {'pluginId': discovered_plugin.manifest.id},
        )

    @classmethod
    async def check_installed_menu_conflict_services(
        cls,
        query_db: object,
        discovered_plugin: object,
    ) -> list[SimpleNamespace]:
        """
        读取测试用已安装菜单冲突。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :return: 菜单冲突列表
        """
        return cls.installed_menu_conflicts

    @classmethod
    async def get_plugin_migration_services(
        cls,
        query_db: object,
        plugin_id: str,
        migration_path: str,
    ) -> SimpleNamespace | None:
        """
        读取测试用插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: migration 执行历史
        """
        for migration in reversed(cls.migration_records):
            if (
                getattr(migration, 'plugin_id', None) == plugin_id
                and getattr(migration, 'migration_path', None) == migration_path
            ):
                return migration

        checksum = cls.migration_checksums.get((plugin_id, migration_path))
        if not checksum:
            return None

        return SimpleNamespace(migration_checksum=checksum)

    @classmethod
    async def get_plugin_migration_list_services(
        cls,
        query_db: object,
        plugin_id: str,
        status: str | None = None,
    ) -> list[SimpleNamespace]:
        """
        读取测试用插件 migration 执行历史列表。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: migration 执行历史列表
        """
        return [
            migration
            for migration in cls.migration_records
            if getattr(migration, 'plugin_id', None) == plugin_id
            and (not status or getattr(migration, 'status', None) == status)
        ]

    @classmethod
    async def add_plugin_migration_services(
        cls,
        query_db: object,
        plugin_migration: object,
    ) -> object:
        """
        记录插件 migration 执行历史。

        :param query_db: orm对象
        :param plugin_migration: migration 执行历史对象
        :return: migration 执行历史对象
        """
        cls.migration_records.append(plugin_migration)
        return plugin_migration

    @classmethod
    async def mark_plugin_migration_status_services(
        cls,
        query_db: object,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> object | None:
        """
        人工标记测试用插件 migration 执行历史状态。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 更新后的 migration 执行历史
        """
        for migration in reversed(cls.migration_records):
            if (
                getattr(migration, 'plugin_id', None) == plugin_id
                and getattr(migration, 'migration_path', None) == migration_path
            ):
                migration.status = status
                migration.error_message = error_message
                return migration

        return None

    @classmethod
    async def add_plugin_operation_log_services(
        cls,
        query_db: object,
        payload: dict[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> SimpleNamespace:
        """
        记录测试用插件批量操作审计日志。

        :param query_db: orm对象
        :param payload: 插件批量执行负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: 操作日志对象
        """
        operation_log = SimpleNamespace(
            payload=payload,
            dry_run=dry_run,
            continue_on_error=continue_on_error,
        )
        cls.operation_logs.append(operation_log)

        return operation_log

    @classmethod
    async def get_plugin_operation_log_export_list_services(
        cls,
        query_db: object,
        query_object: object,
    ) -> list[SimpleNamespace]:
        """
        读取测试用插件操作审计导出列表。

        :param query_db: orm对象
        :param query_object: 审计查询对象
        :return: 插件操作审计列表
        """
        return [
            SimpleNamespace(
                operation_id=index + 1,
                operation=getattr(operation_log, 'payload', {}).get('operation', 'unknown'),
                plugin_ids=[getattr(operation_log, 'payload', {}).get('pluginId', '-')],
                dry_run=getattr(operation_log, 'dry_run', False),
                continue_on_error=getattr(operation_log, 'continue_on_error', False),
                status='success' if getattr(operation_log, 'payload', {}).get('ok', False) else 'failed',
                summary=getattr(operation_log, 'payload', {}).get('summary', {}),
                create_time=None,
                remark=getattr(operation_log, 'payload', {}).get('message'),
            )
            for index, operation_log in enumerate(cls.operation_logs)
        ]

    @classmethod
    async def install_enabled_plugin_menu_services(cls, query_db: object, plugin_registry: object) -> None:
        """
        记录插件菜单安装调用。

        :param query_db: orm对象
        :param plugin_registry: 插件注册表
        :return: None
        """
        cls.install_enabled_menu_called = True

    @classmethod
    async def install_plugin_menu_services(
        cls,
        query_db: object,
        discovered_plugin: object,
        *,
        enabled: bool,
    ) -> None:
        """
        记录指定插件菜单安装调用。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :param enabled: 插件菜单是否启用
        :return: None
        """
        cls.install_plugin_menu_called_with = (discovered_plugin.manifest.id, enabled)

    @classmethod
    async def install_plugin_default_config_services(
        cls,
        query_db: object,
        discovered_plugin: object,
    ) -> list[SimpleNamespace]:
        """
        记录插件默认配置安装调用。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :return: 插件配置列表
        """
        cls.install_config_called = True
        configs = []
        for item in discovered_plugin.manifest.config.items:
            payload = {
                'pluginId': discovered_plugin.manifest.id,
                'configKey': item.key,
            }
            configs.append(SimpleNamespace(model_dump=lambda by_alias=True, payload=payload: payload))

        return configs

    @classmethod
    async def get_plugin_config_services(
        cls,
        query_db: object,
        discovered_plugin: object,
        *,
        reveal_secret: bool = False,
    ) -> list[SimpleNamespace]:
        """
        读取测试用插件配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :param reveal_secret: 是否展示敏感配置原值
        :return: 插件配置列表
        """
        configs = []
        for item in discovered_plugin.manifest.config.items:
            value = '******' if item.secret and not reveal_secret else item.default
            default = '******' if item.secret and not reveal_secret else item.default
            payload = {
                'key': item.key,
                'value': value,
                'default': default,
                'secret': item.secret,
                'group': item.group,
                'order': item.order,
                'placeholder': item.placeholder,
                'min': item.min_value,
                'max': item.max_value,
                'pattern': item.pattern,
            }
            configs.append(SimpleNamespace(model_dump=lambda by_alias=True, payload=payload: payload))

        return configs

    @classmethod
    async def update_plugin_config_services(
        cls,
        query_db: object,
        discovered_plugin: object,
        update_model: object,
    ) -> list[SimpleNamespace]:
        """
        更新测试用插件配置。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :param update_model: 配置更新模型
        :return: 插件配置列表
        """
        configs = []
        for key, value in update_model.values.items():
            payload = {
                'key': key,
                'value': value,
                'secret': False,
            }
            configs.append(SimpleNamespace(model_dump=lambda by_alias=True, payload=payload: payload))

        return configs

    @classmethod
    async def mark_plugin_installed_services(
        cls,
        query_db: object,
        discovered_plugin: object,
    ) -> SimpleNamespace:
        """
        记录插件安装完成标记调用。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :return: 插件模型
        """
        cls.mark_installed_called = True
        cls.plugin_list = [
            plugin for plugin in cls.plugin_list if getattr(plugin, 'plugin_id', None) != discovered_plugin.manifest.id
        ]
        cls.plugin_list.append(
            SimpleNamespace(
                plugin_id=discovered_plugin.manifest.id,
                installed_version=discovered_plugin.manifest.version,
                enabled='0',
                status='installed',
            )
        )
        return SimpleNamespace(
            model_dump=lambda by_alias=True: {
                'pluginId': discovered_plugin.manifest.id,
                'installedVersion': discovered_plugin.manifest.version,
                'status': 'installed',
            }
        )

    @classmethod
    async def update_plugin_enabled_services(
        cls,
        query_db: object,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> SimpleNamespace:
        """
        记录插件启停调用。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件
        :return: 操作响应
        """
        cls.update_enabled_called_with = (plugin_id, enabled, discovered_plugin)
        return SimpleNamespace(is_success=True, message='启用成功' if enabled else '停用成功')

    @classmethod
    async def mark_plugin_uninstalled_services(cls, query_db: object, plugin_id: str) -> SimpleNamespace:
        """
        记录插件卸载标记调用。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :return: 操作响应
        """
        cls.mark_uninstalled_called_with = plugin_id
        return SimpleNamespace(is_success=True, message='卸载成功')

    @classmethod
    async def mark_plugin_error_services(
        cls,
        query_db: object,
        plugin_id: str,
        error_message: str,
    ) -> SimpleNamespace:
        """
        记录插件错误状态标记调用。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 操作响应
        """
        cls.marked_errors.append((plugin_id, error_message))

        return SimpleNamespace(is_success=True, message='插件状态已标记为异常')

    @classmethod
    async def build_plugin_purge_plan_services(cls, query_db: object, discovered_plugin: object) -> object:
        """
        构建测试用插件物理清理计划。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        return PluginPurgePlanner.build_plan(
            discovered_plugin,
            menu_count=1,
            config_count=2,
            migration_count=3,
            job_count=4,
        )

    @classmethod
    async def purge_plugin_services(cls, query_db: object, discovered_plugin: object) -> object:
        """
        记录插件物理清理调用。

        :param query_db: orm对象
        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        cls.purge_called = True
        return await cls.build_plugin_purge_plan_services(query_db, discovered_plugin)


class FakePluginLifecycleUnitOfWork:
    """
    测试用插件生命周期主事务工作单元。
    """

    def __init__(self, gateway: 'FakePluginRuntimeGateway') -> None:
        """
        初始化测试生命周期 UoW。

        :param gateway: 测试运行时适配器
        :return: None
        """
        self.gateway = gateway
        self.session_context: FakeSession | None = None
        self.session: FakeSession | None = None

    async def __aenter__(self) -> 'FakePluginLifecycleUnitOfWork':
        """
        打开测试生命周期主事务会话。

        :return: 测试生命周期 UoW
        """
        self.session_context = self.gateway.session_local()
        self.session = await self.session_context.__aenter__()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """
        关闭测试生命周期主事务会话。

        :param exc_type: 异常类型
        :param exc: 异常对象
        :param traceback: 异常堆栈
        :return: None
        """
        if self.session_context is None:
            return
        await self.session_context.__aexit__(exc_type, exc, traceback)
        self.session_context = None
        self.session = None

    async def check_installed_menu_conflicts(self, discovered_plugin: object) -> list[SimpleNamespace]:
        """
        检查已安装菜单冲突。

        :param discovered_plugin: 已发现插件
        :return: 菜单冲突列表
        """
        return await FakePluginService.check_installed_menu_conflict_services(self.session, discovered_plugin)

    async def upsert_discovered_plugin(
        self,
        discovered_plugin: object,
        backend_root: Path,
        frontend_root: Path | None = None,
    ) -> SimpleNamespace:
        """
        写入或更新已发现插件。

        :param discovered_plugin: 已发现插件
        :param backend_root: 后端插件根目录
        :param frontend_root: 前端插件根目录
        :return: 插件模型
        """
        return await FakePluginService.upsert_discovered_plugin_services(
            self.session,
            discovered_plugin,
            backend_root,
            frontend_root,
        )

    async def install_plugin_menu(self, discovered_plugin: object, *, enabled: bool) -> None:
        """
        安装插件菜单。

        :param discovered_plugin: 已发现插件
        :param enabled: 是否启用菜单
        :return: None
        """
        await FakePluginService.install_plugin_menu_services(self.session, discovered_plugin, enabled=enabled)

    async def install_enabled_plugin_menus(self, plugin_registry: object) -> None:
        """
        安装启用插件菜单。

        :param plugin_registry: 插件注册表
        :return: None
        """
        await FakePluginService.install_enabled_plugin_menu_services(self.session, plugin_registry)

    async def install_plugin_default_config(self, discovered_plugin: object) -> list[SimpleNamespace]:
        """
        安装插件默认配置。

        :param discovered_plugin: 已发现插件
        :return: 插件配置列表
        """
        return await FakePluginService.install_plugin_default_config_services(self.session, discovered_plugin)

    async def mark_plugin_installed(self, discovered_plugin: object) -> SimpleNamespace:
        """
        标记插件已安装。

        :param discovered_plugin: 已发现插件
        :return: 插件模型
        """
        return await FakePluginService.mark_plugin_installed_services(self.session, discovered_plugin)

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """
        构建插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        return await FakePluginService.build_plugin_purge_plan_services(self.session, discovered_plugin)

    async def purge_plugin_metadata(self, discovered_plugin: object) -> object:
        """
        清理插件平台元数据。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        return await FakePluginService.purge_plugin_services(self.session, discovered_plugin)

    async def commit(self) -> None:
        """
        提交测试生命周期主事务。

        :return: None
        """
        await self.session.commit()


class FakePluginRuntimeGateway:
    """
    测试用插件运行时适配器。
    """

    def __init__(self) -> None:
        """
        初始化测试用插件运行时适配器。
        """
        self.session_local = FakeSessionLocal()
        self.completed_process = CompletedProcess(args=[], returncode=0, stdout='1 passed\n', stderr='')
        self.commands: list[tuple[list[str], str, int | None]] = []

    def open_lifecycle_unit_of_work(self) -> FakePluginLifecycleUnitOfWork:
        """
        打开测试生命周期主事务工作单元。

        :return: 测试生命周期主事务工作单元
        """
        return FakePluginLifecycleUnitOfWork(self)

    def get_async_session_local(self) -> FakeSessionLocal:
        """
        获取测试会话工厂。

        :return: 测试会话工厂
        """
        return self.session_local

    def get_plugin_service(self) -> type[FakePluginService]:
        """
        获取测试插件服务。

        :return: 测试插件服务
        """
        return FakePluginService

    async def list_plugin_states(self) -> list[SimpleNamespace]:
        """
        获取测试插件状态列表。

        :return: 测试插件状态列表
        """
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_list_services(session)

    async def get_plugin_state(self, plugin_id: str) -> SimpleNamespace | None:
        """
        获取测试插件状态。

        :param plugin_id: 插件ID
        :return: 测试插件状态
        """
        async with self.session_local() as session:
            return await FakePluginService.plugin_detail_services(session, plugin_id)

    @staticmethod
    def build_operation_log_export_query(export_limit: int) -> SimpleNamespace:
        """
        构建测试用插件操作日志导出查询对象。

        :param export_limit: 导出数量上限
        :return: 测试用插件操作日志导出查询对象
        """
        return SimpleNamespace(export_limit=export_limit, exportLimit=export_limit)

    @staticmethod
    def build_config_update(values: dict[str, object]) -> SimpleNamespace:
        """
        构建测试用插件配置更新对象。

        :param values: 配置键值
        :return: 测试用插件配置更新对象
        """
        return SimpleNamespace(values=values)

    async def get_plugin_config(
        self,
        discovered_plugin: object,
        *,
        reveal_secret: bool = False,
    ) -> list[SimpleNamespace]:
        """
        获取测试插件配置。

        :param discovered_plugin: 已发现插件
        :param reveal_secret: 是否展示敏感配置原值
        :return: 测试插件配置列表
        """
        async with self.session_local() as session:
            configs = await FakePluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=reveal_secret,
            )
            await session.commit()
            return configs

    async def update_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, object],
    ) -> list[SimpleNamespace]:
        """
        更新测试插件配置。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :return: 测试插件配置列表
        """
        async with self.session_local() as session:
            configs = await FakePluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                self.build_config_update(values),
            )
            await session.commit()
            return configs

    async def set_plugin_config(
        self,
        discovered_plugin: object,
        values: dict[str, object],
        *,
        audit_operation: str,
        success_message: str,
    ) -> list[SimpleNamespace]:
        """
        在同一事务中更新测试插件配置并记录审计日志。

        :param discovered_plugin: 已发现插件
        :param values: 配置键值
        :param audit_operation: 审计操作类型
        :param success_message: 操作成功提示
        :return: 测试插件配置列表
        """
        async with self.session_local() as session:
            before_configs = await FakePluginService.get_plugin_config_services(
                session,
                discovered_plugin,
                reveal_secret=True,
            )
            configs = await FakePluginService.update_plugin_config_services(
                session,
                discovered_plugin,
                self.build_config_update(values),
            )
            audit_payload = PluginConfigPayloadBuilder.build_audit_payload(
                discovered_plugin.manifest.id,
                operation=audit_operation,
                values=values,
                before_configs=before_configs,
                after_configs=configs,
                message=success_message,
            )
            await FakePluginService.add_plugin_operation_log_services(
                session,
                audit_payload,
                dry_run=False,
                continue_on_error=False,
            )
            await session.commit()
            return configs

    async def add_plugin_operation_log(
        self,
        payload: dict[str, object],
        *,
        dry_run: bool,
        continue_on_error: bool,
    ) -> None:
        """
        记录测试插件操作日志。

        :param payload: 操作日志负载
        :param dry_run: 是否预演
        :param continue_on_error: 失败后是否继续
        :return: None
        """
        async with self.session_local() as session:
            await FakePluginService.add_plugin_operation_log_services(
                session,
                payload,
                dry_run=dry_run,
                continue_on_error=continue_on_error,
            )
            await session.commit()

    async def list_plugin_operation_logs(self, *, export_limit: int) -> list[SimpleNamespace]:
        """
        获取测试插件操作审计日志列表。

        :param export_limit: 导出数量上限
        :return: 测试插件操作审计列表
        """
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_operation_log_export_list_services(
                session,
                self.build_operation_log_export_query(export_limit),
            )

    async def mark_plugin_error(self, plugin_id: str, error_message: str) -> bool:
        """
        标记测试插件错误状态。

        :param plugin_id: 插件ID
        :param error_message: 错误信息
        :return: 是否标记成功
        """
        async with self.session_local() as session:
            result = await FakePluginService.mark_plugin_error_services(session, plugin_id, error_message)
            if getattr(result, 'is_success', False):
                await session.commit()
                return True
            return False

    async def list_plugin_migrations(
        self,
        plugin_id: str,
        status: str | None = None,
    ) -> list[SimpleNamespace]:
        """
        查询测试插件 migration 历史。

        :param plugin_id: 插件ID
        :param status: 执行状态
        :return: 测试插件 migration 历史列表
        """
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_migration_list_services(session, plugin_id, status)

    async def get_plugin_migration(self, plugin_id: str, migration_path: str) -> SimpleNamespace | None:
        """
        获取测试插件 migration 历史。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :return: 测试插件 migration 历史
        """
        async with self.session_local() as session:
            return await FakePluginService.get_plugin_migration_services(session, plugin_id, migration_path)

    async def mark_plugin_migration_status(
        self,
        plugin_id: str,
        migration_path: str,
        status: str,
        error_message: str | None = None,
    ) -> SimpleNamespace | None:
        """
        人工标记测试插件 migration 历史状态。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param status: 执行状态
        :param error_message: 失败错误信息
        :return: 测试插件 migration 历史
        """
        async with self.session_local() as session:
            migration = await FakePluginService.mark_plugin_migration_status_services(
                session,
                plugin_id,
                migration_path,
                status,
                error_message,
            )
            if migration:
                await session.commit()
            return migration

    async def build_plugin_purge_plan(self, discovered_plugin: object) -> object:
        """
        构建测试插件物理清理计划。

        :param discovered_plugin: 已发现插件
        :return: 插件物理清理计划
        """
        async with self.session_local() as session:
            return await FakePluginService.build_plugin_purge_plan_services(session, discovered_plugin)

    async def run_plugin_migrations(self, discovered_plugin: object) -> list[object]:
        """
        使用独立测试 session 执行插件 migration。

        :param discovered_plugin: 已发现插件
        :return: migration 执行结果列表
        """
        async with self.session_local() as migration_session:
            return await PluginMigrationRunner(
                discovered_plugin,
                PluginDatabaseMigrationHistoryStore.with_model_gateway(
                    FakePluginService,
                    self,
                    self.session_local,
                ),
                manage_execution_transaction=True,
            ).run(migration_session)

    async def set_plugin_enabled_state(
        self,
        plugin_id: str,
        enabled: bool,
        discovered_plugin: object | None = None,
    ) -> SimpleNamespace:
        """
        更新测试插件启停状态，并在启用时同步菜单。

        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :param discovered_plugin: 已发现插件
        :return: 操作响应
        """
        async with self.session_local() as session:
            response = await FakePluginService.update_plugin_enabled_services(
                session,
                plugin_id,
                enabled,
                discovered_plugin,
            )
            if getattr(response, 'is_success', False):
                if enabled and discovered_plugin is not None:
                    await FakePluginService.install_plugin_menu_services(session, discovered_plugin, enabled=True)
                await session.commit()
            return response

    async def mark_plugin_uninstalled_state(self, plugin_id: str) -> SimpleNamespace:
        """
        标记测试插件安全卸载。

        :param plugin_id: 插件ID
        :return: 操作响应
        """
        async with self.session_local() as session:
            response = await FakePluginService.mark_plugin_uninstalled_services(session, plugin_id)
            if getattr(response, 'is_success', False):
                await session.commit()
            return response

    @staticmethod
    def build_migration_record(
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
        status: str = 'success',
        error_message: str | None = None,
    ) -> SimpleNamespace:
        """
        构建测试用插件 migration 执行历史对象。

        :param plugin_id: 插件ID
        :param migration_path: migration 相对路径
        :param checksum: 内容校验值
        :param version: 执行时插件版本
        :param statement_count: SQL 语句数量
        :return: 测试用插件 migration 执行历史对象
        """
        return SimpleNamespace(
            plugin_id=plugin_id,
            migration_path=migration_path,
            migration_checksum=checksum,
            version=version,
            statement_count=statement_count,
            status=status,
            error_message=error_message,
            attempt_count=0,
            started_time=None,
            finished_time=None,
            create_time=None,
            update_time=None,
        )

    def run_command(
        self,
        command: list[str],
        workdir: str,
        *,
        timeout: int | None = None,
    ) -> CompletedProcess[str]:
        """
        记录测试用系统命令。

        :param command: 命令参数列表
        :param workdir: 命令工作目录
        :param timeout: 命令超时时间
        :return: 命令执行结果
        """
        self.commands.append((command, workdir, timeout))
        self._simulate_npm_package_json_update(command, workdir)
        return self.completed_process

    def _simulate_npm_package_json_update(self, command: list[str], workdir: str) -> None:
        """
        模拟 npm install 对 package.json 根依赖声明的改写。

        :param command: 命令参数列表
        :param workdir: 命令工作目录
        :return: None
        """
        if (
            self.completed_process.returncode != 0
            or len(command) < MIN_NPM_INSTALL_COMMAND_LENGTH
            or command[:2] != ['npm', 'install']
        ):
            return
        target = command[-1]
        package_json_path = Path(workdir) / 'package.json'
        if not package_json_path.is_file():
            return
        package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
        dependency_field = 'devDependencies' if '--save-dev' in command else 'dependencies'
        dependency_name = target.rsplit('@', maxsplit=1)[0] if '@' in target.lstrip('@') else target
        package_json.setdefault(dependency_field, {})[dependency_name] = '^npm-written'
        package_json_path.write_text(json.dumps(package_json, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_manifest(plugin_dir: Path, content: str) -> None:
    """
    写入测试插件清单。

    :param plugin_dir: 插件目录
    :param content: 清单内容
    :return: None
    """
    plugin_dir.mkdir(parents=True)
    (plugin_dir / 'plugin.yaml').write_text(content, encoding='utf-8')


def build_runtime(backend_root: Path, frontend_root: Path | None = None) -> PluginRuntimeService:
    """
    构建测试用插件运行时服务。

    :param backend_root: 后端项目根目录
    :param frontend_root: 前端项目根目录
    :return: 插件运行时服务
    """
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
    )


def build_gateway_overrides(gateway: object) -> PluginRuntimeGatewayOverrides:
    """
    构建测试用插件运行时窄端口覆盖项。

    :param gateway: 测试运行时适配器
    :return: 插件运行时窄端口覆盖项
    """
    return PluginRuntimeGatewayOverrides(
        config_gateway=gateway,
        audit_gateway=gateway,
        state_query_gateway=gateway,
        migration_history_gateway=gateway,
        purge_plan_gateway=gateway,
        lifecycle_state_gateway=gateway,
        lifecycle_uow_gateway=gateway,
        migration_execution_gateway=gateway,
    )


def build_fake_lifecycle_precheck(ok: bool = True) -> SimpleNamespace:
    """
    构建测试用插件生命周期预检上下文。

    :param ok: 预检是否通过
    :return: 测试用预检上下文
    """
    return SimpleNamespace(
        ok=ok,
        manifest_result=SimpleNamespace(ok=ok),
        plugin_dependency_result=SimpleNamespace(ok=ok),
        structure_result=SimpleNamespace(ok=ok),
        menu_conflict_result=SimpleNamespace(ok=ok),
        operation_payload={'manifestOk': ok, 'dependencyOk': ok},
        check_payload={'manifestOk': ok, 'dependencyOk': ok},
        menu_conflicts=[],
    )


def build_runtime_with_gateway(
    backend_root: Path,
    gateway: FakePluginRuntimeGateway,
    frontend_root: Path | None = None,
) -> PluginRuntimeService:
    """
    构建带测试运行时适配器的插件运行时服务。

    :param backend_root: 后端项目根目录
    :param gateway: 测试运行时适配器
    :param frontend_root: 前端项目根目录
    :return: 插件运行时服务
    """
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root, frontend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
        gateways=build_gateway_overrides(gateway),
        model_gateway=gateway,
        command_gateway=gateway,
    )


def create_controller_dir(plugin_root: Path) -> None:
    """
    创建测试插件 controller 目录。

    :param plugin_root: 插件根目录
    :return: None
    """
    (plugin_root / 'controller').mkdir(parents=True)


def create_frontend_view(
    backend_root: Path,
    plugin_id: str,
    view_path: str = 'index.vue',
    frontend_root: Path | None = None,
) -> None:
    """
    创建测试插件前端视图文件。

    :param backend_root: 后端项目根目录
    :param plugin_id: 插件ID
    :param view_path: 视图文件相对 views 目录路径
    :param frontend_root: 前端项目根目录
    :return: None
    """
    resolved_frontend_root = frontend_root or Path(
        PluginRuntimeEnvironmentService(backend_root=backend_root).get_frontend_dir()
    )
    frontend_api = resolved_frontend_root / 'plugins' / plugin_id / 'api'
    frontend_api.mkdir(parents=True, exist_ok=True)
    frontend_view = resolved_frontend_root / 'plugins' / plugin_id / 'views' / view_path
    frontend_view.parent.mkdir(parents=True, exist_ok=True)
    frontend_view.write_text('<template />\n', encoding='utf-8')
