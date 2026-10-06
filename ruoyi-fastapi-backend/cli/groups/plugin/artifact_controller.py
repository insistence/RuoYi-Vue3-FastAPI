import importlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.context import CliContext
from cli.core import DEFAULT_CORE_SERVICES, CliContextFactory, CliExecutionService
from cli.runtime.base import RUNTIME_OPERATOR

MAX_SIGNING_KEY_BYTES = 64 * 1024


class PluginArtifactCommandController:
    """
    制品发布命令控制器。

    普通插件命令及帮助查询不加载制品部署依赖。
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        config_factory: Callable[[], Any] | None = None,
        catalog_factory: Callable[[Any], Any] | None = None,
        service_factory: Callable[[Any], Any] | None = None,
        enablement_factory: Callable[[Any], Any] | None = None,
        maintenance_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        """
        初始化制品命令控制器，并保留部署依赖的延迟加载。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param config_factory: 制品部署配置工厂
        :param catalog_factory: 制品目录服务工厂
        :param service_factory: 维护发布服务工厂
        :param enablement_factory: 制品启停服务工厂
        :param maintenance_factory: 制品清理与签名轮换服务工厂
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.config_factory = config_factory or self._default_config
        self.catalog_factory = catalog_factory or self._default_catalog
        self.service_factory = service_factory or self._default_service
        self.enablement_factory = enablement_factory or self._default_enablement
        self.maintenance_factory = maintenance_factory or self._default_maintenance

    @staticmethod
    def _default_maintenance(config: Any) -> Any:
        """
        延迟创建制品维护服务，帮助查询不加载数据库。

        :param config: 制品发布配置
        :return: 制品维护服务
        """
        return importlib.import_module('plugins.core.deployment.maintenance').PluginArtifactMaintenanceService(config)

    def maintain_artifacts(
        self,
        operation: str,
        env: str,
        output: str,
        *,
        options: dict[str, Any],
        allow_prod: bool = False,
        yes: bool = False,
        dry_run: bool = False,
    ) -> None:
        """
        执行白名单中的维护操作，并复用 CLI 生产环境保护。

        :param operation: inspect、prune、rotate-signature 或 reconcile
        :param env: 当前命令环境
        :param output: 输出格式
        :param options: 当前命令显式支持的维护参数
        :param allow_prod: 是否允许生产环境变更
        :param yes: 是否跳过交互确认
        :param dry_run: 是否只生成清理计划
        :return: None
        """
        methods = {
            'inspect': 'inspect',
            'prune': 'prune',
            'rotate-signature': 'rotate_signature',
            'reconcile': 'reconcile',
        }
        if operation not in methods:
            raise ValueError('未知制品维护命令')
        ctx = self._context(
            env,
            output,
            command_name=None if operation == 'inspect' else f'plugin artifact {operation}',
            allow_prod=allow_prod,
            yes=yes,
            dry_run=dry_run,
        )
        arguments = dict(options)
        if operation != 'inspect':
            arguments['actor'] = ctx.operator
        if operation == 'prune':
            arguments['dry_run'] = dry_run
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                getattr(self.maintenance_factory(self.config_factory()), methods[operation])(**arguments)
            ),
        )

    @staticmethod
    def _default_config() -> Any:
        """
        延迟读取当前环境的制品部署配置。

        :return: 制品部署配置
        """
        module = importlib.import_module('plugins.core.deployment.config')
        return module.PluginDeploymentConfig.from_settings(Path(__file__).resolve().parents[3])

    @staticmethod
    def _default_catalog(config: Any) -> Any:
        """
        延迟创建制品目录服务。

        :param config: 制品部署配置
        :return: 制品目录服务
        """
        return importlib.import_module('plugins.core.deployment.catalog').PluginArtifactCatalog(config)

    @staticmethod
    def _default_service(config: Any) -> Any:
        """
        延迟创建维护发布服务。

        :param config: 制品部署配置
        :return: 维护发布服务
        """
        return importlib.import_module('plugins.core.deployment.service').PluginDeploymentService(config)

    @staticmethod
    def _default_enablement(config: Any) -> Any:
        """
        延迟创建维护启停服务。

        :param config: 制品部署配置
        :return: 维护启停服务
        """
        return importlib.import_module('plugins.core.deployment.enablement').PluginArtifactEnablementService(config)

    def _context(
        self,
        env: str,
        output: str,
        *,
        command_name: str | None = None,
        allow_prod: bool = False,
        yes: bool = False,
        dry_run: bool = False,
    ) -> CliContext:
        # config.env 可能在应用日志策略时首次导入，因此必须先设置命令选择的环境。
        """
        先设置命令环境，再应用危险操作保护并解析操作者。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param command_name: 用于匹配危险操作规则的命令名称
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演而不写入发布状态
        :return: 完成环境与操作者设置的 CLI 上下文
        """
        os.environ['APP_ENV'] = env
        if command_name and not dry_run:
            ctx = self.context_factory.build_dangerous(env, output, allow_prod, yes, dry_run, command_name=command_name)
        else:
            ctx = self.context_factory.build_regular(env, output, allow_prod, yes, dry_run)
        ctx.operator = RUNTIME_OPERATOR.resolve_operator()
        return ctx

    def _execute(self, ctx: CliContext, action: Callable[[], dict[str, Any]]) -> None:
        """
        执行命令操作并统一输出成功结果或异常信息。

        :param ctx: CLI 上下文
        :param action: 当前命令需要执行的操作
        :return: None
        """
        try:
            payload = action()
        except Exception as exc:
            payload = {'ok': False, 'message': str(exc), 'errorType': type(exc).__name__}
        self.execution_service.complete_payload(ctx, {**payload, 'env': ctx.env})

    @staticmethod
    def _identity(artifact: Any) -> dict[str, Any]:
        """
        提取制品身份和文件数量，供命令结果复用。

        :param artifact: 已构建或验证的制品
        :return: 制品身份字段
        """
        return {
            'pluginId': artifact.plugin_id,
            'version': artifact.version,
            'digest': artifact.digest,
            'keyId': artifact.key_id,
            'fileCount': len(artifact.files),
        }

    @staticmethod
    def _signing_key(source: Path, key_file: Path, password_env: str | None) -> Any:
        """
        读取位于插件目录之外的签名私钥，密码仅从指定环境变量读取。

        :param source: 已构建插件目录
        :param key_file: 插件目录之外的 Ed25519 PKCS8 私钥文件
        :param password_env: 保存加密私钥密码的环境变量名称
        :return: Ed25519 签名私钥
        """
        if key_file.resolve().is_relative_to(source.resolve()):
            raise ValueError('签名私钥必须放在插件源码/预构建目录之外，防止被打入制品')
        if not key_file.is_file() or key_file.stat().st_size > MAX_SIGNING_KEY_BYTES:
            raise ValueError('签名私钥文件不存在或过大')
        password = None
        if password_env is not None:
            value = os.environ.get(password_env)
            if not value:
                raise ValueError(f'私钥密码环境变量未设置：{password_env}')
            password = value.encode('utf-8')
        data = key_file.read_bytes()
        if not data.startswith((b'-----BEGIN PRIVATE KEY-----', b'-----BEGIN ENCRYPTED PRIVATE KEY-----')):
            raise ValueError('签名私钥必须是PKCS8 PEM格式')
        serialization = importlib.import_module('cryptography.hazmat.primitives.serialization')
        ed25519 = importlib.import_module('cryptography.hazmat.primitives.asymmetric.ed25519')
        try:
            key = serialization.load_pem_private_key(data, password=password)
        except (TypeError, ValueError):
            raise ValueError('无法读取PKCS8私钥，请检查密钥格式和密码环境变量') from None
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise ValueError('制品签名私钥必须为Ed25519')
        return key

    def build_artifact(
        self,
        source: Path,
        destination: Path,
        env: str,
        output: str,
        *,
        key_file: Path,
        key_id: str,
        password_env: str | None = None,
    ) -> None:
        """
        离线签名打包预构建目录，不加载部署配置或插件代码。

        :param source: 已构建插件目录
        :param destination: 签名制品输出文件
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param key_file: 插件目录之外的 Ed25519 PKCS8 私钥文件
        :param key_id: 发布者公钥标识
        :param password_env: 保存加密私钥密码的环境变量名称
        :return: None
        """
        ctx = self._context(env, output)

        def build() -> dict[str, Any]:
            """
            读取签名私钥并返回离线构建结果。

            :return: 制品路径和身份信息
            """
            key = self._signing_key(source, key_file, password_env)
            artifact = importlib.import_module('plugins.core.artifacts').build_artifact(
                source, destination, key, key_id
            )
            return {'ok': True, 'path': str(artifact.artifact_path), **self._identity(artifact)}

        self._execute(ctx, build)

    def verify_artifact(self, path: Path, env: str, output: str) -> None:
        """
        校验制品签名、完整摘要与发布者授权范围。

        :param path: 待处理的签名制品文件
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self._context(env, output)

        def verify() -> dict[str, Any]:
            """
            按当前宿主信任配置验证制品及发布者范围。

            :return: 制品验证结果
            """
            config = self.config_factory()
            verified = importlib.import_module('plugins.core.artifacts').verify_artifact(path, config.trusted_keys())
            config.authorize_publisher(verified.key_id, verified.plugin_id)
            return {'ok': True, 'message': '签名、完整摘要和发布者授权检查通过', **self._identity(verified)}

        self._execute(ctx, verify)

    def import_artifact(self, path: Path, env: str, output: str, *, allow_prod: bool, yes: bool, dry_run: bool) -> None:
        """
        导入已验证制品及其索引，预演时只执行检查。

        :param path: 待处理的签名制品文件
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演而不写入发布状态
        :return: None
        """
        ctx = self._context(
            env, output, command_name='plugin artifact import', allow_prod=allow_prod, yes=yes, dry_run=dry_run
        )
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.catalog_factory(self.config_factory()).import_artifact(path, actor=ctx.operator, dry_run=dry_run)
            ),
        )

    def list_artifacts(self, env: str, output: str, *, plugin_id: str | None = None) -> None:
        """
        查询已导入制品，可按插件 ID 筛选。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param plugin_id: 插件 ID
        :return: None
        """
        ctx = self._context(env, output)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.catalog_factory(self.config_factory()).list_artifacts(plugin_id)
            ),
        )

    def plan_release(self, plugin_id: str, digest: str, env: str, output: str) -> None:
        """
        静态检查目标制品并输出维护计划。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self._context(env, output)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.service_factory(self.config_factory()).plan(plugin_id, digest)
            ),
        )

    def prepare_release(
        self,
        plugin_id: str,
        digest: str,
        env: str,
        output: str,
        *,
        maintenance: bool,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """
        在维护窗口执行安装或升级，并记录制品准备结果。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演而不写入发布状态
        :return: None
        """
        ctx = self._context(
            env, output, command_name='plugin release prepare', allow_prod=allow_prod, yes=yes, dry_run=dry_run
        )
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.service_factory(self.config_factory()).prepare(
                    plugin_id, digest, maintenance=maintenance, actor=ctx.operator, dry_run=dry_run
                )
            ),
        )

    def select_release(
        self,
        plugin_id: str,
        digest: str,
        env: str,
        output: str,
        *,
        expected_generation: str,
        expected_workers: int,
        maintenance: bool,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        按预期发布代际选择目标制品，供重启后的 worker 加载。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param expected_workers: 发布完成时预期就绪的宿主 worker 数量
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self._context(env, output, command_name='plugin release select', allow_prod=allow_prod, yes=yes)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.service_factory(self.config_factory()).select(
                    plugin_id,
                    digest,
                    expected_generation=expected_generation,
                    expected_workers=expected_workers,
                    maintenance=maintenance,
                    actor=ctx.operator,
                )
            ),
        )

    def release_status(self, env: str, output: str, *, plugin_id: str | None = None) -> None:
        """
        查询目标制品、数据准备状态和 worker 加载结果。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param plugin_id: 插件 ID
        :return: None
        """
        ctx = self._context(env, output)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(self.service_factory(self.config_factory()).status(plugin_id)),
        )

    def rollback_release(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        expected_generation: str,
        schema_compatible: bool,
        maintenance: bool,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        确认数据兼容后选择上一代码制品，不回滚数据库迁移。

        :param plugin_id: 插件 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param schema_compatible: 是否确认旧代码兼容当前数据结构
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        ctx = self._context(env, output, command_name='plugin release rollback', allow_prod=allow_prod, yes=yes)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.service_factory(self.config_factory()).rollback(
                    plugin_id,
                    expected_generation=expected_generation,
                    schema_compatible=schema_compatible,
                    maintenance=maintenance,
                    actor=ctx.operator,
                )
            ),
        )

    def set_release_enabled(
        self,
        plugin_id: str,
        env: str,
        output: str,
        *,
        enabled: bool,
        expected_generation: str,
        maintenance: bool,
        allow_prod: bool,
        yes: bool,
    ) -> None:
        """
        在维护窗口更新目标制品的启停状态与发布代际。

        :param plugin_id: 插件 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param enabled: 是否启用目标制品
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        operation = 'enable' if enabled else 'disable'
        ctx = self._context(env, output, command_name=f'plugin release {operation}', allow_prod=allow_prod, yes=yes)
        self._execute(
            ctx,
            lambda: self.execution_service.run_async(
                self.enablement_factory(self.config_factory()).set_enabled(
                    plugin_id,
                    enabled=enabled,
                    expected_generation=expected_generation,
                    maintenance=maintenance,
                    actor=ctx.operator,
                )
            ),
        )
