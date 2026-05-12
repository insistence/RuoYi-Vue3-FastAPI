from cli.core import (
    DEFAULT_CORE_SERVICES,
    CliContextFactory,
    CliExecutionService,
)
from cli.runtime.crypto import CRYPTO_RUNTIME, CryptoRuntimeService

from .presenter import CryptoCommandPresenter


class CryptoCommandController:
    """
    传输加密命令控制器。

    该控制器负责组织 `crypto` 命令组的上下文准备、runtime 调用、
    payload 注入，以及基于输出格式选择 presenter 或直接返回 JSON。

    :param context_factory: CLI 上下文工厂
    :param execution_service: CLI 执行服务
    :param presenter: 传输加密命令文本渲染器
    """

    def __init__(
        self,
        *,
        context_factory: CliContextFactory | None = None,
        execution_service: CliExecutionService | None = None,
        presenter: CryptoCommandPresenter | None = None,
        runtime_service: CryptoRuntimeService | None = None,
    ) -> None:
        """
        初始化传输加密命令控制器。

        :param context_factory: CLI 上下文工厂
        :param execution_service: CLI 执行服务
        :param presenter: 传输加密命令文本渲染器
        :param runtime_service: 传输加密运行时服务
        :return: None
        """
        self.context_factory = context_factory or DEFAULT_CORE_SERVICES.context_factory
        self.execution_service = execution_service or DEFAULT_CORE_SERVICES.execution_service
        self.presenter = presenter or CryptoCommandPresenter()
        self.runtime_service = runtime_service or CRYPTO_RUNTIME

    def validate(self, env: str, output: str) -> None:
        """
        校验传输加密配置。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        self.execution_service.complete_payload(ctx, self.runtime_service.validate_crypto_config())

    def keygen(self, env: str, output: str, *, kid: str, key_size: int) -> None:
        """
        生成新的传输加密密钥对。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param kid: 生成的密钥版本标识
        :param key_size: RSA 密钥长度
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.generate_crypto_key_pair(kid, key_size)
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_crypto_keygen_text,
            text_condition=lambda data: data.get('ok', False),
        )

    def rotate(
        self,
        env: str,
        output: str,
        allow_prod: bool,
        yes: bool,
        dry_run: bool,
        *,
        next_kid: str,
        key_size: int,
    ) -> None:
        """
        生成传输加密密钥轮换辅助结果。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否演练执行
        :param next_kid: 轮换后的新密钥版本标识
        :param key_size: 新密钥的 RSA 长度
        :return: None
        """
        ctx = self.context_factory.build_dangerous(
            env,
            output,
            allow_prod,
            yes,
            dry_run,
            command_name='crypto rotate',
        )
        self.execution_service.complete_payload(ctx, self.runtime_service.build_rotation_payload(next_kid, key_size))

    def export_public(self, env: str, output: str) -> None:
        """
        导出当前运行环境的公钥信息。

        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        ctx = self.context_factory.build_readonly(env, output)
        payload = self.runtime_service.export_public_key()
        payload['env'] = ctx.env
        self.execution_service.complete_payload_with_text(
            ctx,
            payload,
            text_builder=self.presenter.build_export_public_text,
            text_condition=lambda data: data.get('ok', False),
        )
