import importlib
import json
import os
from pathlib import Path
from typing import Annotated, Any

import typer

from cli.context import CliContext, DryRunOption, OutputOption
from cli.core import DEFAULT_CORE_SERVICES
from cli.exit_codes import ARGUMENT_ERROR, DEPENDENCY_ERROR, RUNTIME_ERROR, SUCCESS

FrontendRootOption = Annotated[
    Path | None,
    typer.Option('--frontend-root', help='作为 SDK 来源的宿主前端目录，默认相邻前端或 RUOYI_PLUGIN_FRONTEND_ROOT'),
]


def _format_sdk_result(payload: dict[str, Any]) -> str:
    """
    展示来源版本、检查状态和备份位置，方便人工核对更新结果。

    :param payload: SDK 操作结果
    :return: 文本输出
    """
    lines = [f'ok: {str(payload.get("ok", False)).lower()}']
    lines.extend(
        f'{key}: {payload[key]}'
        for key in (
            'status',
            'message',
            'sdkVersion',
            'currentSdkVersion',
            'protocolCompatible',
            'updateAvailable',
            'backupDir',
        )
        if key in payload
    )
    if payload.get('files'):
        lines.append('files: ' + json.dumps(payload['files'], ensure_ascii=False))
    return '\n'.join(lines)


def _execute_sdk(
    operation: str,
    project: Path,
    frontend_root: Path | None,
    output: str,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """
    仅加载离线 SDK 文件服务，使用统一 CLI 输出和非零失败退出码。

    :param operation: check 或 update
    :param project: 独立 bundle 源码工程目录
    :param frontend_root: 可选宿主前端源码目录
    :param output: text 或 json
    :param dry_run: 是否只预演更新
    :param force: 是否备份后替换改动过或未跟踪的 SDK
    :return: None
    """
    try:
        root = frontend_root or Path(
            os.environ.get('RUOYI_PLUGIN_FRONTEND_ROOT')
            or Path(__file__).resolve().parents[5] / 'ruoyi-fastapi-frontend'
        )
        service = importlib.import_module('cli.runtime.plugin.sdk').PluginBridgeSdk(root)
        payload = (
            service.check(project) if operation == 'check' else service.update(project, dry_run=dry_run, force=force)
        )
        code = SUCCESS if payload['ok'] else DEPENDENCY_ERROR
    except ValueError as exc:
        payload = {'ok': False, 'status': 'invalid', 'message': str(exc), 'error': str(exc)}
        code = ARGUMENT_ERROR
    except OSError as exc:
        payload = {'ok': False, 'status': 'error', 'message': str(exc), 'error': str(exc)}
        code = RUNTIME_ERROR
    DEFAULT_CORE_SERVICES.execution_service.complete_payload_with_text(
        CliContext(output=output, dry_run=dry_run),
        payload,
        text_builder=_format_sdk_result,
        default_exit_code=code,
    )


def register_sdk_commands(app: typer.Typer) -> None:
    """
    注册纯离线 SDK 子命令，帮助查询不加载工程或宿主配置。

    :param app: 插件命令组
    :return: None
    """
    sdk_app = typer.Typer(help='检查和显式更新独立 bundle 工程中的桥接 SDK', no_args_is_help=True)
    app.add_typer(sdk_app, name='sdk')

    @sdk_app.command('check', help='比较 SDK 版本、摘要和当前宿主副本，非 current 状态返回非零退出码')
    def check_sdk(
        project: Annotated[Path, typer.Argument(help='含 plugin.yaml 的独立 bundle 源码工程目录')],
        frontend_root: FrontendRootOption = None,
        output: OutputOption = 'text',
    ) -> None:
        """
        检查源码工程的 SDK 来源与本地修改，不写文件或连接外部服务。

        :param project: 独立 bundle 源码工程目录
        :param frontend_root: 可选宿主前端源码目录
        :param output: 输出格式
        :return: None
        """
        _execute_sdk('check', project, frontend_root, output)

    @sdk_app.command('update', help='备份后更新 SDK 的三个文件；不会构建、安装或重启插件')
    def update_sdk(
        project: Annotated[Path, typer.Argument(help='含 plugin.yaml 的独立 bundle 源码工程目录')],
        frontend_root: FrontendRootOption = None,
        output: OutputOption = 'text',
        dry_run: DryRunOption = False,
        force: Annotated[bool, typer.Option('--force', help='备份后纳管旧副本或替换本地 SDK 修改')] = False,
    ) -> None:
        """
        显式更新源码工程的 SDK；默认拒绝覆盖用户改动或来源不明的副本。

        :param project: 独立 bundle 源码工程目录
        :param frontend_root: 可选宿主前端源码目录
        :param output: 输出格式
        :param dry_run: 是否仅预演而不写入文件
        :param force: 是否备份后替换改动或未跟踪副本
        :return: None
        """
        _execute_sdk('update', project, frontend_root, output, dry_run=dry_run, force=force)
