import argparse
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _resource_roots(source: Path, manifest: Any, output: Path) -> list[Path]:
    """
    检查清单声明的资源根路径及前端入口，在构建前拒绝缺失产物。

    :param source: 原生插件源码根目录
    :param manifest: 已解析的插件清单
    :param output: 待创建的构建输出目录
    :return: 通过路径检查的部署资源根路径
    """
    from plugins.core.artifacts.package import is_link_or_reparse  # noqa: PLC0415
    from plugins.core.artifacts.schema import safe_artifact_path  # noqa: PLC0415

    resources = {str(item) for item in manifest.backend.migrations}
    resources.update(str(item) for item in manifest.backend.seeds)
    if (source / 'plugin.lock.yaml').exists():
        resources.add('plugin.lock.yaml')
    if manifest.frontend.delivery.type == 'bundle':
        bundle = manifest.frontend.bundle
        resources.add(bundle.directory)
        if not (source / bundle.directory / bundle.entry).is_file():
            raise ValueError('缺少 bundle HTML 入口，请先独立构建前端后再组装制品')

    roots = []
    for relative in sorted(resources):
        safe_artifact_path(relative)
        resource = source / relative
        # 逐级检查，不能先 resolve 后丢失中间目录的链接信息。
        current = source
        for component in Path(relative).parts:
            current /= component
            if is_link_or_reparse(current.lstat()):
                raise ValueError(f'交付资源不能包含链接或重解析点：{relative}')
        if resource.is_dir() and output.is_relative_to(resource.resolve()):
            raise ValueError('输出目录不能位于待交付资源目录内')
        roots.append(resource)
    return roots


def collect_deployment_resources(source: Path, manifest: Any, output: Path) -> dict[str, Path]:
    """
    收集清单资源和已构建 bundle，拒绝开发工程、敏感文件及链接。

    :param source: 原生插件源码根目录
    :param manifest: 已解析的插件清单
    :param output: 待创建的构建输出目录
    :return: 插件内相对路径与对应源码文件的映射
    """
    from plugins.core.artifacts.package import (  # noqa: PLC0415
        CACHE_DIRECTORIES,
        FORBIDDEN_DIRECTORIES,
        FORBIDDEN_FILES,
        FORBIDDEN_SUFFIXES,
        is_link_or_reparse,
    )
    from plugins.core.artifacts.schema import (  # noqa: PLC0415
        DEFAULT_LIMITS,
        safe_artifact_path,
        validate_path_inventory,
    )

    files: dict[str, Path] = {}
    total_bytes = 0
    native_root = Path(manifest.backend.native.module_root)
    for resource in _resource_roots(source, manifest, output):
        pending = [resource]
        while pending:
            item = pending.pop()
            name = item.relative_to(source).as_posix()
            path = safe_artifact_path(name)
            if any(part.casefold() in CACHE_DIRECTORIES for part in path.parts):
                continue
            if (
                any(part.casefold() in FORBIDDEN_DIRECTORIES for part in path.parts)
                or path.name.casefold() in FORBIDDEN_FILES
                or path.suffix.casefold() in FORBIDDEN_SUFFIXES
                or any(part.casefold() == '.env' or part.casefold().startswith('.env.') for part in path.parts)
            ):
                raise ValueError(f'交付资源包含开发工程或敏感配置：{name}')
            info = item.lstat()
            if is_link_or_reparse(info) or not item.resolve().is_relative_to(source):
                raise ValueError(f'交付资源不能包含链接或越界路径：{name}')
            if stat.S_ISDIR(info.st_mode):
                pending.extend(item.iterdir())
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError(f'交付资源不能包含硬链接或特殊文件：{name}')
            if name.casefold() == 'plugin.yaml' or Path(name).is_relative_to(native_root):
                raise ValueError(f'交付资源不能覆盖清单或原生发行包：{name}')
            if name in files:
                continue
            files[name] = item
            total_bytes += info.st_size
            if (
                len(files) > DEFAULT_LIMITS.max_files
                or info.st_size > DEFAULT_LIMITS.max_file_bytes
                or total_bytes > DEFAULT_LIMITS.max_total_bytes
            ):
                raise ValueError('交付资源超过制品文件数量或大小限制')
    validate_path_inventory(tuple(files))
    return files


def main() -> None:
    """
    构建原生 wheel 并组装可离线交付的插件目录与 ZIP。

    :return: None
    """
    parser = argparse.ArgumentParser(
        description='构建、静态验证并组装原生插件；使用当前 Python 环境，不写入运行中的 plugins。'
    )
    parser.add_argument('--source', type=Path, default=BACKEND_ROOT / 'plugins' / 'examples' / 'rust' / 'rust_demo')
    parser.add_argument('--output', type=Path, required=True, help='全新输出目录（其中创建 <plugin_id>/）')
    arguments = parser.parse_args()
    source = arguments.source.resolve()
    output = arguments.output.resolve()
    if output.exists():
        parser.error('输出目录已存在，请选择全新目录，避免覆盖正在使用的二进制')
    sys.path.insert(0, str(BACKEND_ROOT))
    from plugins.core.discovery.scanner import PluginScanner  # noqa: PLC0415
    from plugins.core.native.wheel import install_native_wheel, select_native_wheel  # noqa: PLC0415
    from plugins.core.validation.structure import PluginStructureChecker  # noqa: PLC0415

    manifest = PluginScanner(source.parent).load_manifest(source / 'plugin.yaml').manifest
    if manifest.runtime_kind != 'native':
        parser.error('清单必须声明 native 运行时')
    if manifest.frontend.delivery.type not in {'none', 'bundle'}:
        parser.error('原生交付只支持 none 或已独立构建的 bundle 前端')
    if not (source / 'Cargo.lock').is_file():
        parser.error('缺少 Cargo.lock，请先在源码目录执行 cargo generate-lockfile 并提交锁文件')
    collect_deployment_resources(source, manifest, output)
    output.mkdir(parents=True)
    wheels = output / 'wheels'
    subprocess.run(
        [
            sys.executable,
            '-m',
            'maturin',
            'build',
            '--release',
            '--locked',
            '--strip',
            '--interpreter',
            sys.executable,
            '--manifest-path',
            str(source / 'Cargo.toml'),
            '--out',
            str(wheels),
        ],
        cwd=source,
        check=True,
    )
    wheel = select_native_wheel(wheels, manifest)
    plugin = output / manifest.id
    install_native_wheel(wheel, plugin / manifest.backend.native.module_root, manifest)
    shutil.copyfile(source / 'plugin.yaml', plugin / 'plugin.yaml')
    # 复制预检过的部署文件；前端必须已构建，不隐式运行 npm。
    # Cargo 构建可能耗时较长，复制前再次检查资源路径。
    resources = collect_deployment_resources(source, manifest, output)
    for relative, resource in sorted(resources.items()):
        target = (plugin / relative).resolve()
        if not resource.is_relative_to(source) or not target.is_relative_to(plugin):
            raise ValueError('交付资源不能越过插件目录')
        if target.exists():
            raise ValueError(f'交付资源重复或覆盖原生目录：{relative}')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resource, target)
    discovered = PluginScanner(output).load_manifest(plugin / 'plugin.yaml')
    checked = PluginStructureChecker(BACKEND_ROOT).check(discovered)
    if not checked.ok:
        raise ValueError('；'.join(item.message for item in checked.failed_items))
    archive_path = output / f'{manifest.id}-{manifest.version}.zip'
    with ZipFile(archive_path, 'x', compression=ZIP_DEFLATED) as archive:
        for item in sorted(plugin.rglob('*')):
            if item.is_file():
                archive.write(item, item.relative_to(output).as_posix())
    print(json.dumps({'wheel': str(wheel), 'plugin': str(plugin), 'archive': str(archive_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
