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

    def __init__(self, backend_dir: Path) -> None:
        """
        初始化测试用运行时环境服务。

        :param backend_dir: 后端项目根目录
        """
        self.backend_dir = backend_dir
        self.frontend_mode = 'dev'
        self.backend_runtime_mode = 'dev'

    def get_backend_dir(self) -> str:
        """
        获取后端项目根目录。

        :return: 后端项目根目录
        """
        return str(self.backend_dir)

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
    install_enabled_menu_called = False
    install_plugin_menu_called_with: tuple[str, bool] | None = None
    install_config_called = False
    mark_installed_called = False
    mark_uninstalled_called_with: str | None = None
    purge_called = False
    update_enabled_called_with: tuple[str, bool] | None = None
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
        checksum = cls.migration_checksums.get((plugin_id, migration_path))
        if not checksum:
            return None

        return SimpleNamespace(migration_checksum=checksum)

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
            payload = {
                'key': item.key,
                'value': value,
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
    ) -> SimpleNamespace:
        """
        记录插件启停调用。

        :param query_db: orm对象
        :param plugin_id: 插件ID
        :param enabled: 是否启用
        :return: 操作响应
        """
        cls.update_enabled_called_with = (plugin_id, enabled)
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

    @staticmethod
    def build_migration_record(
        plugin_id: str,
        migration_path: str,
        checksum: str,
        version: str,
        statement_count: int,
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


def build_runtime(backend_root: Path) -> PluginRuntimeService:
    """
    构建测试用插件运行时服务。

    :param backend_root: 后端项目根目录
    :return: 插件运行时服务
    """
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
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
) -> PluginRuntimeService:
    """
    构建带测试运行时适配器的插件运行时服务。

    :param backend_root: 后端项目根目录
    :param gateway: 测试运行时适配器
    :return: 插件运行时服务
    """
    return PluginRuntimeService(
        runtime_environment=FakeRuntimeEnvironment(backend_root),
        dependency_checker=PluginDependencyChecker(
            python_inspector=PythonDependencyInspector(installed_packages={'openai': '2.17.0'}),
            npm_inspector=NpmDependencyInspector(installed_packages={'vue': '3.5.26'}),
        ),
        state_gateway=gateway,
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


def create_frontend_view(backend_root: Path, plugin_id: str, view_path: str = 'index.vue') -> None:
    """
    创建测试插件前端视图文件。

    :param backend_root: 后端项目根目录
    :param plugin_id: 插件ID
    :param view_path: 视图文件相对 views 目录路径
    :return: None
    """
    frontend_api = backend_root.parent / 'ruoyi-fastapi-frontend' / 'plugins' / plugin_id / 'api'
    frontend_api.mkdir(parents=True, exist_ok=True)
    frontend_view = backend_root.parent / 'ruoyi-fastapi-frontend' / 'plugins' / plugin_id / 'views' / view_path
    frontend_view.parent.mkdir(parents=True, exist_ok=True)
    frontend_view.write_text('<template />\n', encoding='utf-8')
