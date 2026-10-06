from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from cli.context import AllowProdOption, DryRunOption, EnvOption, OutputOption, YesOption
from cli.groups.plugin.commands.artifact_maintenance import register_artifact_maintenance_commands

MaintenanceOption = Annotated[
    bool, typer.Option('--maintenance', help='确认已停止全部宿主worker，并在独立维护进程执行')
]
ExpectedGenerationOption = Annotated[
    str, typer.Option('--expected-generation', help='最近一次plan/status返回的发布代际，防止并发覆盖')
]


def register_artifact_commands(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册制品与维护发布命令，帮助和补全阶段不加载配置或数据库。

    :param app: Typer 命令组
    :param get_controller: 制品命令控制器工厂
    :return: None
    """
    artifact_app = typer.Typer(help='构建、验证和导入签名插件制品', no_args_is_help=True)
    release_app = typer.Typer(help='维护准备、目标选择和worker实际加载状态', no_args_is_help=True)
    app.add_typer(artifact_app, name='artifact')
    app.add_typer(release_app, name='release')
    register_artifact_maintenance_commands(artifact_app, get_controller)
    _register_release_enablement(release_app, get_controller)

    @artifact_app.command('build', help='离线签名打包预构建插件目录，不覆盖已有输出')
    def artifact_build(
        source: Annotated[Path, typer.Argument(help='已构建插件目录，目录名必须与插件ID一致')],
        destination: Annotated[Path, typer.Argument(help='输出.rpk文件')],
        key_file: Annotated[Path, typer.Option('--key-file', help='插件目录之外的Ed25519 PKCS8 PEM签名私钥')],
        key_id: Annotated[str, typer.Option('--key-id', help='发布者公钥标识')],
        password_env: Annotated[str | None, typer.Option('--password-env', help='读取加密私钥密码的环境变量名')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        离线签名打包预构建插件目录。

        :param source: 已构建插件目录
        :param destination: 签名制品输出文件
        :param key_file: 插件目录之外的 Ed25519 PKCS8 私钥文件
        :param key_id: 发布者公钥标识
        :param password_env: 保存加密私钥密码的环境变量名称
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().build_artifact(
            source, destination, env, output, key_file=key_file, key_id=key_id, password_env=password_env
        )

    @artifact_app.command('verify', help='使用宿主信任公钥和发布者范围验证制品，不加载插件')
    def artifact_verify(
        path: Annotated[Path, typer.Argument(help='待验证.rpk文件')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        使用宿主信任配置验证制品。

        :param path: 待处理的签名制品文件
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().verify_artifact(path, env, output)

    @artifact_app.command('import', help='验证并导入不可变存储和制品索引，不安装或激活')
    def artifact_import(
        path: Annotated[Path, typer.Argument(help='待导入.rpk文件')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
        dry_run: DryRunOption = False,
    ) -> None:
        """
        导入不可变制品及索引，暂不激活插件。

        :param path: 待处理的签名制品文件
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演而不写入发布状态
        :return: None
        """
        get_controller().import_artifact(path, env, output, allow_prod=allow_prod, yes=yes, dry_run=dry_run)

    @artifact_app.command('list', help='查询已导入制品')
    def artifact_list(
        plugin_id: Annotated[str | None, typer.Option('--plugin-id', help='仅列出指定插件')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查询已导入的制品列表。

        :param plugin_id: 插件 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().list_artifacts(env, output, plugin_id=plugin_id)

    @release_app.command('plan', help='静态预检制品维护计划，不执行迁移或Hook')
    def release_plan(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        digest: Annotated[str, typer.Argument(help='已导入制品的SHA256')],
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查询目标制品的静态维护计划。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().plan_release(plugin_id, digest, env, output)

    @release_app.command('prepare', help='停机维护执行安装或升级，成功后记录精确制品准备证据')
    def release_prepare(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        digest: Annotated[str, typer.Argument(help='已导入制品的SHA256')],
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
        dry_run: DryRunOption = False,
    ) -> None:
        """
        在维护窗口准备指定制品的数据库与管理资源。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :param dry_run: 是否仅预演而不写入发布状态
        :return: None
        """
        get_controller().prepare_release(
            plugin_id, digest, env, output, maintenance=maintenance, allow_prod=allow_prod, yes=yes, dry_run=dry_run
        )

    @release_app.command('select', help='CAS选择已准备制品为目标，重启后由worker报告生效状态')
    def release_select(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        digest: Annotated[str, typer.Argument(help='已准备制品的SHA256')],
        expected_generation: ExpectedGenerationOption,
        expected_workers: Annotated[int, typer.Option('--expected-workers', min=1, help='预期宿主worker数量')] = 1,
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        按预期发布代际选择已准备的目标制品。

        :param plugin_id: 插件 ID
        :param digest: 已导入制品的 SHA256 摘要
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param expected_workers: 发布完成时预期就绪的宿主 worker 数量
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().select_release(
            plugin_id,
            digest,
            env,
            output,
            expected_generation=expected_generation,
            expected_workers=expected_workers,
            maintenance=maintenance,
            allow_prod=allow_prod,
            yes=yes,
        )

    @release_app.command('status', help='查询目标、数据库准备版本及各worker实际加载结果')
    def release_status(
        plugin_id: Annotated[str | None, typer.Option('--plugin-id', help='仅查询指定插件')] = None,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
    ) -> None:
        """
        查询制品发布状态及 worker 实际加载结果。

        :param plugin_id: 插件 ID
        :param env: 当前命令运行环境
        :param output: 输出格式
        :return: None
        """
        get_controller().release_status(env, output, plugin_id=plugin_id)

    @release_app.command('rollback', help='选择上一个代码制品，保留当前数据库安装版本')
    def release_rollback(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        expected_generation: ExpectedGenerationOption,
        schema_compatible: Annotated[
            bool, typer.Option('--schema-compatible', help='确认旧代码兼容当前数据结构，不执行数据库回滚')
        ] = False,
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        确认数据兼容后选择上一代码制品。

        :param plugin_id: 插件 ID
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param schema_compatible: 是否确认旧代码兼容当前数据结构
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().rollback_release(
            plugin_id,
            env,
            output,
            expected_generation=expected_generation,
            schema_compatible=schema_compatible,
            maintenance=maintenance,
            allow_prod=allow_prod,
            yes=yes,
        )


def _register_release_enablement(app: typer.Typer, get_controller: Callable[[], Any]) -> None:
    """
    注册维护窗口内使用的制品启停命令。

    :param app: Typer 命令组
    :param get_controller: 制品命令控制器工厂
    :return: None
    """

    @app.command('enable', help='维护启用目标制品并更新代际，重启后生效')
    def release_enable(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        expected_generation: ExpectedGenerationOption,
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        在维护窗口启用目标制品，重启后生效。

        :param plugin_id: 插件 ID
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().set_release_enabled(
            plugin_id,
            env,
            output,
            enabled=True,
            expected_generation=expected_generation,
            maintenance=maintenance,
            allow_prod=allow_prod,
            yes=yes,
        )

    @app.command('disable', help='维护停用目标制品并更新代际，重启后生效')
    def release_disable(
        plugin_id: Annotated[str, typer.Argument(help='插件ID')],
        expected_generation: ExpectedGenerationOption,
        maintenance: MaintenanceOption = False,
        env: EnvOption = 'dev',
        output: OutputOption = 'text',
        allow_prod: AllowProdOption = False,
        yes: YesOption = False,
    ) -> None:
        """
        在维护窗口停用目标制品，重启后生效。

        :param plugin_id: 插件 ID
        :param expected_generation: 最近一次查询得到的发布代际，用于防止并发覆盖
        :param maintenance: 是否确认已停止全部宿主 worker 并进入维护窗口
        :param env: 当前命令运行环境
        :param output: 输出格式
        :param allow_prod: 是否允许生产环境危险命令
        :param yes: 是否跳过确认
        :return: None
        """
        get_controller().set_release_enabled(
            plugin_id,
            env,
            output,
            enabled=False,
            expected_generation=expected_generation,
            maintenance=maintenance,
            allow_prod=allow_prod,
            yes=yes,
        )
