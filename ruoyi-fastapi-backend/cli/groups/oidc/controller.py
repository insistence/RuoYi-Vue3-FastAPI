from cli.core import DEFAULT_CORE_SERVICES, CliContextFactory, CliExecutionService
from cli.runtime.oidc import OIDC_RUNTIME, OidcRuntimeCliService


class OidcCommandController:
    """
    OIDC 命令控制器

    该控制器负责组织 OIDC 命令组的上下文准备、危险操作保护、
    runtime 调用和结果输出。
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        runtime_service: OidcRuntimeCliService | None = None,
    ) -> None:
        """
        初始化 OIDC 命令控制器

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param runtime_service: OIDC CLI 运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.runtime_service = runtime_service or OIDC_RUNTIME

    def bootstrap_key(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        kid: str,
        actor: str,
    ) -> None:
        """
        执行幂等首把 OIDC 签名密钥初始化

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否只执行预演
        :param kid: 首把签名密钥标识
        :param actor: 部署操作人标识
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='oidc key bootstrap',
        )
        payload = self.execution_service.run_async(
            self.runtime_service.bootstrap_signing_key(kid, actor=actor, dry_run=dry_run)
        )
        payload['env'] = ctx.env
        self.execution_service.complete_payload(ctx, payload)
