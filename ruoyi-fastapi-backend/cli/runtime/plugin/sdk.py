import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from plugins.core.frontend import (
    PluginFrontendFrameworkResolver,
    resolve_frontend_framework_request,
    select_frontend_root,
    validate_frontend_framework,
)

SDK_FILES = ('pluginBridge.js', 'pluginBridge.d.ts')
SDK_METADATA = 'pluginBridge.sdk.json'
VENDOR_FILES = (*SDK_FILES, SDK_METADATA)
HASH_ALGORITHM = 'sha256-utf8-lf'
SDK_PROJECT = 'RuoYi-FastAPI'
SDK_SOURCE = {'project': SDK_PROJECT, 'directory': 'ruoyi-fastapi-frontend/vue3/web/src/utils'}
METADATA_FIELDS = {'schemaVersion', 'sdkVersion', 'bridgeVersion', 'capabilities'}
SCHEMA_VERSION = 1
MANIFEST_VERSION = 2


class PluginBridgeSdk:
    """离线检查和更新独立 bundle 工程中的桥接 SDK 副本。"""

    def __init__(self, frontend_root: Path, frontend_framework: str = 'auto') -> None:
        """
        保存用于读取当前宿主 SDK 的前端目录，不初始化宿主运行环境。

        :param frontend_root: 宿主前端工程根目录或包含框架分类的聚合目录
        :param frontend_framework: SDK 来源宿主的框架标识，auto 表示自动识别
        :return: None
        """
        self.frontend_root = select_frontend_root(frontend_root, frontend_framework)
        self.frontend_framework = resolve_frontend_framework_request(self.frontend_root, frontend_framework)

    def build_vendor_files(self) -> dict[str, str]:
        """
        校验宿主 SDK 并生成使用 UTF-8、LF 和内容摘要的三个副本文件。

        :return: 按固定文件名索引的文本，不包含时间戳或本机路径
        """
        directory = self._safe_path(self.frontend_root / 'src' / 'utils')
        contents: dict[str, str] = {}
        for name in VENDOR_FILES:
            path = self._safe_path(directory / name)
            if not path.is_file():
                raise ValueError(f'缺少宿主桥接 SDK：{path}；请配置正确的前端工程目录')
            contents[name] = self._text(path.read_bytes())
        metadata = self._metadata(contents[SDK_METADATA], vendor=False)
        self._validate_exports(contents, metadata)
        self._safe_path(self.frontend_root / 'package.json')
        frontend_framework = PluginFrontendFrameworkResolver.resolve(self.frontend_root, self.frontend_framework)
        metadata.update(
            hashAlgorithm=HASH_ALGORITHM,
            source={
                'project': SDK_PROJECT,
                'directory': f'ruoyi-fastapi-frontend/{frontend_framework}/web/src/utils',
            },
            files={name: self._hash(contents[name]) for name in SDK_FILES},
        )
        contents[SDK_METADATA] = json.dumps(metadata, ensure_ascii=False, indent=2) + '\n'
        return contents

    def check(self, project: Path) -> dict[str, Any]:
        """
        静态检查 v2 bundle 工程副本，仅与当前宿主完全一致时通过检查。

        :param project: 含 plugin.yaml 的独立插件工程目录
        :return: 副本状态、版本、协议兼容性与三个文件的摘要信息
        """
        try:
            current = self.build_vendor_files()
            _, vendor = self._project_paths(project)
            report, _ = self._inspect(vendor, current)
            return report
        except (OSError, ValueError, yaml.YAMLError) as exc:
            return self._report('invalid', f'SDK 检查失败：{exc}')

    def update(self, project: Path, *, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
        """
        备份并更新三个 SDK 文件，先写代码和类型、最后写来源记录。

        :param project: 含 plugin.yaml 的独立插件工程目录
        :param dry_run: 仅预演，不创建锁、目录、备份或文件
        :param force: 允许备份后覆盖改动副本或纳管缺失、损坏的来源记录
        :return: 更新结果、原状态、备份位置及更新后的检查信息
        """
        backup: Path | None = None
        previous: dict[str, Any] = self._report('invalid', 'SDK 更新尚未执行')
        try:
            current = self.build_vendor_files()
            root, vendor = self._project_paths(project)
            previous, _ = self._inspect(vendor, current)
            refusal = self._refusal(previous, force=force)
            if refusal:
                return {**previous, 'ok': False, 'message': refusal, 'dryRun': dry_run, 'updated': False}
            backup_root = self._safe_path(root / '.plugin-sdk-backups')
            if backup_root.exists() and not backup_root.is_dir():
                raise ValueError('SDK 备份路径必须是目录')
            if dry_run or previous['status'] == 'current':
                return {
                    **previous,
                    'ok': True,
                    'dryRun': dry_run,
                    'updated': False,
                    'backupDir': None,
                    'previousStatus': previous['status'],
                    'message': 'SDK 已与当前宿主一致' if previous['status'] == 'current' else '可备份并更新 SDK 副本',
                }
            with self._lock(root):
                # 取得锁后重新读取，不能覆盖另一次更新之后的新状态。
                root, vendor = self._project_paths(root)
                previous, original = self._inspect(vendor, current)
                refusal = self._refusal(previous, force=force)
                if refusal:
                    return {**previous, 'ok': False, 'message': refusal, 'dryRun': False, 'updated': False}
                if previous['status'] == 'current':
                    return {**previous, 'dryRun': False, 'updated': False, 'backupDir': None}
                backup = self._backup(root, original)
                vendor.mkdir(parents=True, exist_ok=True)
                result = self._apply(vendor, current, original, backup)
            return {
                **result,
                'dryRun': False,
                'updated': True,
                'backupDir': str(backup),
                'previousStatus': previous['status'],
                'message': 'SDK 副本已更新，原文件已备份；请重新构建并验证插件',
            }
        except (OSError, ValueError, yaml.YAMLError) as exc:
            return {
                **self._report('invalid', f'SDK 更新失败：{exc}'),
                'dryRun': dry_run,
                'updated': False,
                'backupDir': str(backup) if backup is not None else None,
                'previousStatus': previous['status'],
            }

    @staticmethod
    def _text(content: bytes) -> str:
        """
        解码 UTF-8 并统一换行，忽略编辑器添加的 UTF-8 BOM。

        :param content: 文件原始字节
        :return: 不含 BOM 且只使用 LF 的文本
        """
        return content.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')

    @staticmethod
    def _hash(content: str) -> str:
        """
        计算归一文本的内容摘要，该摘要不是发布者签名。

        :param content: 已归一为 LF 的文本
        :return: UTF-8 字节的 SHA256 十六进制摘要
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    @staticmethod
    def _safe_path(path: Path) -> Path:
        """
        逐级拒绝符号链接和 Windows 重解析点，避免操作越过实际工程路径。

        :param path: 待使用的文件或目录路径
        :return: 已检查现存路径组件的绝对路径
        """
        absolute = Path(os.path.abspath(path))
        for component in reversed((absolute, *absolute.parents)):
            try:
                info = component.lstat()
            except FileNotFoundError:
                continue
            reparse = getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
            if stat.S_ISLNK(info.st_mode) or reparse:
                raise ValueError(f'SDK 路径不能包含符号链接或重解析点：{component}')
        return absolute

    @classmethod
    def _project_paths(cls, project: Path) -> tuple[Path, Path]:
        """
        只读取 YAML 判定工程类型，固定副本位置而不导入插件入口。

        :param project: 用户指定的插件工程根目录
        :return: 工程根目录及固定的 web/vendor 目录
        """
        root = cls._safe_path(project)
        if not root.is_dir():
            raise ValueError('插件工程目录不存在')
        manifest_path = cls._safe_path(root / 'plugin.yaml')
        manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, dict) or type(manifest.get('manifestVersion')) is not int:
            raise ValueError('SDK 命令只支持 manifestVersion: 2 的 bundle 工程')
        frontend = manifest.get('frontend')
        delivery = frontend.get('delivery') if isinstance(frontend, dict) else None
        if (
            manifest['manifestVersion'] != MANIFEST_VERSION
            or not isinstance(delivery, dict)
            or delivery.get('type') != 'bundle'
        ):
            raise ValueError('SDK 命令只支持 manifestVersion: 2 的 bundle 工程')
        vendor = cls._safe_path(root / 'web' / 'vendor')
        if vendor.exists() and not vendor.is_dir():
            raise ValueError('web/vendor 必须是目录')
        for name in VENDOR_FILES:
            path = cls._safe_path(vendor / name)
            if path.exists() and not path.is_file():
                raise ValueError(f'SDK 目标必须是普通文件：{name}')
        return root, vendor

    @staticmethod
    def _metadata(content: str, *, vendor: bool) -> dict[str, Any]:
        """
        校验版本与来源记录结构，不把自报摘要当作来源真实性证明。

        :param content: 元数据 JSON 文本
        :param vendor: 是否要求副本的摘要与来源字段
        :return: 通过字段及类型检查的元数据
        """
        metadata = json.loads(content)
        fields = METADATA_FIELDS | ({'hashAlgorithm', 'source', 'files'} if vendor else set())
        if not isinstance(metadata, dict) or set(metadata) != fields:
            raise ValueError('桥接 SDK 元数据字段无效')
        if type(metadata['schemaVersion']) is not int or metadata['schemaVersion'] != SCHEMA_VERSION:
            raise ValueError('桥接 SDK 元数据 schemaVersion 无效')
        version = metadata['sdkVersion']
        if not isinstance(version, str) or not re.fullmatch(
            r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)'
            r'(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?',
            version,
        ):
            raise ValueError('桥接 SDK 的 sdkVersion 无效')
        if type(metadata['bridgeVersion']) is not int or metadata['bridgeVersion'] <= 0:
            raise ValueError('桥接 SDK 的 bridgeVersion 无效')
        capabilities = metadata['capabilities']
        if not isinstance(capabilities, dict) or any(
            not isinstance(name, str) or not name or type(value) is not int or value <= 0
            for name, value in capabilities.items()
        ):
            raise ValueError('桥接 SDK 的 capabilities 无效')
        if vendor:
            hashes = metadata['files']
            if metadata['hashAlgorithm'] != HASH_ALGORITHM:
                raise ValueError('桥接 SDK 的摘要算法无效')
            PluginBridgeSdk._validate_source(metadata['source'])
            if (
                not isinstance(hashes, dict)
                or set(hashes) != set(SDK_FILES)
                or any(
                    not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes.values()
                )
            ):
                raise ValueError('桥接 SDK 文件摘要记录无效')
        return metadata

    @staticmethod
    def _validate_source(source: Any) -> None:
        """
        校验来源记录使用当前项目名和规范的框架工程路径。

        :param source: SDK 副本中的来源记录
        :return: None
        """
        if not isinstance(source, dict) or set(source) != {'project', 'directory'} or source['project'] != SDK_PROJECT:
            raise ValueError('桥接 SDK 的来源记录无效')
        directory = source['directory']
        match = (
            re.fullmatch(r'ruoyi-fastapi-frontend/([^/]+)/web/src/utils', directory)
            if isinstance(directory, str)
            else None
        )
        if match is None:
            raise ValueError('桥接 SDK 的来源目录无效')
        validate_frontend_framework(match.group(1))

    @staticmethod
    def _wire_versions(content: str) -> list[str]:
        """
        只识别固定格式的协议版本导出，不执行或推断任意 JavaScript 表达式。

        :param content: JS 或类型声明内容
        :return: 所有可明确识别的协议版本字面量
        """
        return re.findall(
            r'^\s*export\s+(?:declare\s+)?const\s+PLUGIN_BRIDGE_VERSION\s*[:=]\s*(\d+)\s*;?\s*$',
            content,
            re.MULTILINE,
        )

    @classmethod
    def _validate_exports(cls, contents: dict[str, str], metadata: dict[str, Any]) -> None:
        """
        静态核对 JS 与类型声明导出的 SDK 版本及通信协议版本。

        :param contents: SDK 的 JS 和类型声明文本
        :param metadata: 对应的元数据
        :return: None
        """
        for name in SDK_FILES:
            sdk_versions = re.findall(
                r'^\s*export\s+(?:declare\s+)?const\s+PLUGIN_BRIDGE_SDK_VERSION\s*[:=]\s*[\'"]([^\'"]+)[\'"]\s*;?\s*$',
                contents[name],
                re.MULTILINE,
            )
            bridge_versions = cls._wire_versions(contents[name])
            if sdk_versions != [metadata['sdkVersion']] or bridge_versions != [str(metadata['bridgeVersion'])]:
                raise ValueError(f'桥接 SDK 版本声明与元数据不一致：{name}')

    @classmethod
    def _protocol_compatible(
        cls, contents: dict[str, str], current_wire: int, saved: dict[str, Any] | None
    ) -> bool | None:
        """
        结合实际导出和来源记录判断协议，无法识别实际导出时保留未知。

        :param contents: 可成功解码的本地副本内容
        :param current_wire: 当前宿主的协议版本
        :param saved: 有效的本地来源记录，缺失或损坏时为 None
        :return: True 表示协议一致，False 表示明确不兼容，None 表示无法确认
        """
        versions = [cls._wire_versions(contents.get(name, '')) for name in SDK_FILES]
        if (saved is not None and saved['bridgeVersion'] != current_wire) or any(
            value != str(current_wire) for values in versions for value in values
        ):
            return False
        return True if all(len(values) == 1 for values in versions) else None

    @staticmethod
    def _report(status: str, message: str) -> dict[str, Any]:
        """
        创建稳定的检查结果字段，未知协议不伪报兼容。

        :param status: current、outdated、modified、untracked、invalid 或 incompatible
        :param message: 可读的检查说明
        :return: 初始检查结果
        """
        return {
            'ok': status == 'current',
            'status': status,
            'sdkVersion': None,
            'currentSdkVersion': None,
            'protocolCompatible': None,
            'updateAvailable': False,
            'files': {},
            'message': message,
            'forceRequired': False,
        }

    @classmethod
    def _snapshot(
        cls, vendor: Path, latest: dict[str, Any]
    ) -> tuple[dict[str, bytes | None], dict[str, str], dict[str, dict[str, Any]]]:
        """
        读取固定的三个文件，并保留不可解码文件的原始字节供备份。

        :param vendor: 已完成路径检查的副本目录
        :param latest: 当前宿主的来源记录
        :return: 原始字节、可解码文本及文件摘要信息
        """
        originals = {name: (vendor / name).read_bytes() if (vendor / name).exists() else None for name in VENDOR_FILES}
        contents: dict[str, str] = {}
        rows: dict[str, dict[str, Any]] = {}
        for name, raw in originals.items():
            row: dict[str, Any] = {'exists': raw is not None}
            rows[name] = row
            if name in SDK_FILES:
                row.update(sha256=None, recordedSha256=None, currentSha256=latest['files'][name])
            if raw is not None:
                try:
                    contents[name] = cls._text(raw)
                    row['sha256'] = cls._hash(contents[name])
                except UnicodeError:
                    row['error'] = '文件不是有效 UTF-8'
        return originals, contents, rows

    @classmethod
    def _inspect(cls, vendor: Path, current: dict[str, str]) -> tuple[dict[str, Any], dict[str, bytes | None]]:
        """
        将现存副本与记录摘要及当前宿主比较，保留原始字节供备份和回滚。

        :param vendor: 已完成路径检查的 SDK 副本目录
        :param current: 当前宿主规范化后的三个 SDK 文件
        :return: 检查结果及原始文件快照
        """
        latest = cls._metadata(current[SDK_METADATA], vendor=True)
        originals, contents, rows = cls._snapshot(vendor, latest)
        report = cls._report('untracked', 'SDK 副本缺少来源记录，需显式强制纳管')
        report.update(currentSdkVersion=latest['sdkVersion'], updateAvailable=True, forceRequired=True, files=rows)
        saved = None
        if originals[SDK_METADATA] is not None:
            try:
                saved = cls._metadata(contents.get(SDK_METADATA, ''), vendor=True)
                report['sdkVersion'] = saved['sdkVersion']
            except ValueError as exc:
                report.update(status='invalid', message=str(exc))
        report['protocolCompatible'] = cls._protocol_compatible(contents, latest['bridgeVersion'], saved)
        if report['protocolCompatible'] is False:
            report.update(
                status='incompatible',
                message='SDK 通信协议版本不同，需要人工迁移',
                updateAvailable=False,
                forceRequired=False,
            )
            return report, originals
        if saved is None:
            return report, originals
        for name in SDK_FILES:
            report['files'][name]['recordedSha256'] = saved['files'][name]
        if any(report['files'][name]['sha256'] != saved['files'][name] for name in SDK_FILES):
            report.update(status='modified', message='SDK 文件缺失或已修改，默认不覆盖本地改动')
            return report, originals
        try:
            cls._validate_exports(contents, saved)
        except ValueError as exc:
            report.update(status='invalid', message=str(exc))
            return report, originals
        report['forceRequired'] = False
        if saved == latest:
            report.update(status='current', ok=True, message='SDK 副本与当前宿主一致', updateAvailable=False)
        else:
            report.update(status='outdated', message='SDK 副本完整，但与当前宿主不同，可显式更新')
        return report, originals

    @staticmethod
    def _refusal(report: dict[str, Any], *, force: bool) -> str | None:
        """
        判定更新是否允许，强制模式不能绕过明确的通信协议不兼容。

        :param report: 最新副本检查结果
        :param force: 是否明确允许覆盖本地副本
        :return: 拒绝说明；可更新时为 None
        """
        if report['protocolCompatible'] is False:
            return 'SDK 通信协议不兼容，不能通过强制更新绕过，请先人工迁移'
        if report['forceRequired'] and not force:
            return 'SDK 副本存在改动或缺少有效来源记录；请检查后使用 --force 备份并更新'
        return None

    @classmethod
    @contextmanager
    def _lock(cls, root: Path) -> Iterator[None]:
        """
        用工程局部独占文件串行更新，不自动抢占可能仍被使用的旧锁。

        :param root: 已验证的工程根目录
        :return: 持有更新锁的上下文
        """
        path = cls._safe_path(root / '.plugin-sdk.lock')
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError('SDK 更新锁已存在，请确认没有并发更新后再处理锁文件') from exc
        try:
            os.close(descriptor)
            yield
        finally:
            cls._safe_path(path).unlink()

    @classmethod
    def _backup(cls, root: Path, originals: dict[str, bytes | None]) -> Path:
        """
        在唯一目录保留原文件字节，不覆盖已有备份。

        :param root: 已验证的工程根目录
        :param originals: SDK 原始文件内容，None 表示原来不存在
        :return: 本次更新的备份目录
        """
        parent = cls._safe_path(root / '.plugin-sdk-backups')
        parent.mkdir(exist_ok=True)
        backup = parent / uuid4().hex
        backup.mkdir()
        for name, content in originals.items():
            if content is not None:
                (backup / name).write_bytes(content)
        return backup

    @classmethod
    def _write(cls, path: Path, content: bytes) -> None:
        """
        在同目录排他创建临时文件，再原子替换固定的 SDK 目标。

        :param path: 待替换的 SDK 文件路径
        :param content: 要保存的原始字节
        :return: None
        """
        cls._safe_path(path)
        temporary = path.with_name(f'.{path.name}.{uuid4().hex}.tmp')
        try:
            with temporary.open('xb') as output:
                output.write(content)
            cls._safe_path(path)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _apply(
        cls, vendor: Path, current: dict[str, str], originals: dict[str, bytes | None], backup: Path
    ) -> dict[str, Any]:
        """
        按元数据最后的顺序写入；失败时恢复全部原文件并保留备份。

        :param vendor: 固定 SDK 副本目录
        :param current: 当前宿主 SDK 文本
        :param originals: 更新前的原始字节快照
        :param backup: 可供人工恢复的原文件备份目录
        :return: 更新后已核实为 current 的检查结果
        """
        try:
            for name in VENDOR_FILES:
                cls._write(vendor / name, current[name].encode('utf-8'))
            result, _ = cls._inspect(vendor, current)
            if not result['ok']:
                raise ValueError('SDK 更新后的内容校验失败')
            return result
        except BaseException as exc:
            failures = []
            for name in VENDOR_FILES:
                try:
                    path = cls._safe_path(vendor / name)
                    if originals[name] is None:
                        path.unlink(missing_ok=True)
                    else:
                        cls._write(path, originals[name])
                except (OSError, ValueError) as rollback_error:  # noqa: PERF203 - 单个恢复失败不能跳过其他原文件。
                    failures.append(f'{name}: {rollback_error}')
            if failures:
                raise ValueError(f'SDK 更新失败且回滚未完成，请从 {backup} 恢复：{"；".join(failures)}') from exc
            raise
