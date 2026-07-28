import base64
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from cli.exit_codes import RUNTIME_ERROR, SUCCESS
from plugins.core.utils import validate_plugin_id_value

DEPENDENCY_OPERATOR_PATTERN = re.compile(r'==|!=|>=|<=|=|>|<|\^|~')
PYTHON_PACKAGE_SEPARATOR_PATTERN = re.compile(r'[-_.]+')
NPM_LOCKFILE_INTEGRITY_ALGORITHM = 'sha512'
PLUGIN_DEPENDENCY_ALLOWLIST_EXAMPLE_YAML = """# 插件外部依赖允许列表示例。
#
# 使用方式：
# 1. 将本文件保存为 plugin_dependency_allowlist.yaml。
# 2. 按团队实际批准的 Python/npm 包和版本范围调整。
# 3. 在 .env.* 中配置 PLUGIN_DEPENDENCY_ALLOWLIST 指向该文件。
#
# 版本范围应尽量写成可证明的连续闭合范围，例如 ">=2.0.0,<3.0.0"。
# 未声明上界、通配版本、!=、^、~ 等无法证明完全包含的约束会被策略保守阻断。

python:
  openai:
    versions:
      - ">=2.0.0,<3.0.0"
    source: internal-pypi
    reason: 示例：仅允许 OpenAI SDK 2.x
  requests:
    versions:
      - ">=2.32.0,<3.0.0"
    source: internal-pypi
    reason: 示例：允许 requests 2.x 安全维护版本
npm:
  dayjs:
    versions:
      - ">=1.11.0,<2.0.0"
    source: internal-npm
    reason: 示例：允许 dayjs 1.x
npmDev:
  vitest:
    versions:
      - ">=3.0.0,<4.0.0"
    source: internal-npm
    reason: 示例：仅允许开发依赖测试工具
"""


@dataclass(frozen=True)
class PluginTestTarget:
    """
    插件测试目标。

    :param kind: 测试目标类型
    :param target_path: 测试目标路径
    :param command: 测试执行命令
    :param workdir: 命令工作目录
    :param timeout: 命令超时时间
    """

    kind: str
    target_path: Path
    command: list[str]
    workdir: Path
    timeout: int


@dataclass(frozen=True)
class PluginTestCommandResultPayload:
    """
    插件测试命令执行结果负载。
    """

    completed: Any

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件测试命令执行结果负载
        """
        return {
            'returnCode': self.completed.returncode,
            'stdout': self.completed.stdout[-4000:] if self.completed.stdout else '',
            'stderr': self.completed.stderr[-4000:] if self.completed.stderr else '',
        }


@dataclass(frozen=True)
class PluginTestResultItemPayload:
    """
    插件测试单目标执行结果负载。
    """

    target: PluginTestTarget
    completed: Any

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件测试单目标执行结果负载
        """
        return {
            'kind': self.target.kind,
            'target': str(self.target.target_path),
            'command': self.target.command,
            'workdir': str(self.target.workdir),
            'test': PluginTestCommandResultPayload(self.completed).to_payload(),
        }


@dataclass(frozen=True)
class PluginTestMissingPayload:
    """
    插件测试目标缺失负载。
    """

    plugin_id: str
    expected_paths: list[Path]

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件测试目标缺失负载
        """
        return {
            'ok': False,
            'message': '插件测试目录不存在',
            'pluginId': self.plugin_id,
            'targets': [str(path) for path in self.expected_paths],
        }


@dataclass(frozen=True)
class PluginTestExecutionPayload:
    """
    插件测试执行结果负载。
    """

    plugin_id: str
    keyword: str
    maxfail: int
    quiet: bool
    frontend_build: bool
    results: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 插件测试执行结果负载
        """
        ok = all(item['test']['returnCode'] == 0 for item in self.results)

        return {
            'ok': ok,
            'message': '插件测试执行完成' if ok else '插件测试执行失败',
            'pluginId': self.plugin_id,
            'targets': [item['target'] for item in self.results],
            'keyword': self.keyword,
            'maxfail': self.maxfail,
            'quiet': self.quiet,
            'frontendBuild': self.frontend_build,
            'results': self.results,
            'test': self.results[0]['test'] if len(self.results) == 1 else None,
            'command': self.results[0]['command'] if len(self.results) == 1 else None,
        }


@dataclass(frozen=True)
class CliPluginRuntimeExceptionPayload:
    """
    CLI 插件运行时异常负载。
    """

    exception_payload: dict[str, Any]
    failure_code: int = RUNTIME_ERROR

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: CLI 插件运行时异常负载
        """
        return {**self.exception_payload, 'exit_code': self.failure_code}


@dataclass(frozen=True)
class CliPluginRuntimeExitCodePayload:
    """
    CLI 插件运行时退出码负载。
    """

    payload: dict[str, Any]
    success_code: int = SUCCESS
    failure_code: int = RUNTIME_ERROR

    def to_payload(self) -> dict[str, Any]:
        """
        序列化为既有 CLI payload 契约。

        :return: 带退出码的 CLI 插件运行时负载
        """
        return {**self.payload, 'exit_code': self.success_code if self.payload.get('ok') else self.failure_code}


@dataclass(frozen=True)
class PluginDependencyLockfileTemplate:
    """
    插件依赖锁文件模板。

    :param plugin_id: 插件ID
    :param plugin_version: 插件版本
    :param generated_at: 生成时间
    :param python: Python 依赖锁定项
    :param npm: npm 依赖锁定项
    :param npm_dev: npmDev 依赖锁定项
    :param artifact_count: 已从离线制品反填的依赖项数量
    :param warnings: 生成过程告警
    """

    plugin_id: str
    plugin_version: str
    generated_at: str
    python: list[dict[str, object]]
    npm: list[dict[str, object]]
    npm_dev: list[dict[str, object]]
    artifact_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        """
        获取锁文件模板依赖项数量。

        :return: 依赖项数量
        """
        return len(self.python) + len(self.npm) + len(self.npm_dev)

    def to_dict(self) -> dict[str, object]:
        """
        序列化为锁文件 YAML 字典。

        :return: 锁文件字典
        """
        return {
            'plugin': self.plugin_id,
            'version': self.plugin_version,
            'generatedAt': self.generated_at,
            'python': self.python,
            'npm': self.npm,
            'npmDev': self.npm_dev,
        }

    def to_yaml(self) -> str:
        """
        序列化为锁文件 YAML 文本。

        :return: YAML 文本
        """
        return yaml.safe_dump(self.to_dict(), allow_unicode=True, sort_keys=False)


class PluginDependencyLockfileTemplateBuilder:
    """
    插件依赖锁文件模板构建器。

    该构建器只根据 manifest 声明生成待补全模板，不联网解析真实版本或哈希。
    """

    @classmethod
    def build(cls, manifest: Any, *, offline_dir: Path | str | None = None) -> PluginDependencyLockfileTemplate:
        """
        根据插件 manifest 构建锁文件模板。

        :param manifest: 插件 manifest
        :param offline_dir: 离线制品根目录
        :return: 锁文件模板
        """
        generated_at = datetime.now().astimezone().isoformat()
        dependencies = manifest.dependencies
        artifact_resolver = PluginDependencyOfflineArtifactResolver(offline_dir)
        warnings: list[str] = []
        artifact_count = 0
        python_entries = []
        npm_entries = []
        npm_dev_entries = []
        for requirement in dependencies.python:
            entry, artifact_warning = cls._build_python_entry(requirement, artifact_resolver=artifact_resolver)
            python_entries.append(entry)
            artifact_count += 1 if entry.get('resolvedVersion') else 0
            if artifact_warning:
                warnings.append(artifact_warning)
        for requirement in dependencies.npm:
            entry, artifact_warning = cls._build_npm_entry(
                requirement,
                kind='npm',
                artifact_resolver=artifact_resolver,
            )
            npm_entries.append(entry)
            artifact_count += 1 if entry.get('resolvedVersion') else 0
            if artifact_warning:
                warnings.append(artifact_warning)
        for requirement in dependencies.npm_dev:
            entry, artifact_warning = cls._build_npm_entry(
                requirement,
                kind='npmDev',
                artifact_resolver=artifact_resolver,
            )
            npm_dev_entries.append(entry)
            artifact_count += 1 if entry.get('resolvedVersion') else 0
            if artifact_warning:
                warnings.append(artifact_warning)
        return PluginDependencyLockfileTemplate(
            plugin_id=manifest.id,
            plugin_version=manifest.version,
            generated_at=generated_at,
            python=python_entries,
            npm=npm_entries,
            npm_dev=npm_dev_entries,
            artifact_count=artifact_count,
            warnings=warnings,
        )

    @staticmethod
    def _extract_dependency_name(requirement: str) -> str:
        """
        提取依赖包名。

        :param requirement: 依赖声明
        :return: 依赖包名
        """
        from plugins.core.validation.dependencies import DependencyRequirementParser  # noqa: PLC0415

        normalized_requirement = requirement.strip()
        operator_match = DEPENDENCY_OPERATOR_PATTERN.search(normalized_requirement)
        if operator_match:
            package_name = normalized_requirement[: operator_match.start()].strip()
            if package_name:
                return package_name
        return DependencyRequirementParser.parse(requirement).name

    @classmethod
    def _build_python_entry(
        cls,
        requirement: str,
        *,
        artifact_resolver: 'PluginDependencyOfflineArtifactResolver',
    ) -> tuple[dict[str, object], str | None]:
        """
        构建 Python 锁文件模板项。

        :param requirement: Python 依赖声明
        :param artifact_resolver: 离线制品解析器
        :return: 锁文件模板项和告警
        """
        name = cls._extract_dependency_name(requirement)
        artifact_match, artifact_warning = artifact_resolver.resolve_python(name, requirement)
        return {
            'name': name,
            'requirement': requirement,
            'resolvedVersion': artifact_match.version if artifact_match else '',
            'hashes': artifact_match.hashes if artifact_match else [],
        }, artifact_warning

    @classmethod
    def _build_npm_entry(
        cls,
        requirement: str,
        *,
        kind: str,
        artifact_resolver: 'PluginDependencyOfflineArtifactResolver',
    ) -> tuple[dict[str, object], str | None]:
        """
        构建 npm 锁文件模板项。

        :param requirement: npm 依赖声明
        :param kind: npm 依赖类型
        :param artifact_resolver: 离线制品解析器
        :return: 锁文件模板项和告警
        """
        name = cls._extract_dependency_name(requirement)
        artifact_match, artifact_warning = artifact_resolver.resolve_npm(kind, name, requirement)
        return {
            'name': name,
            'requirement': requirement,
            'resolvedVersion': artifact_match.version if artifact_match else '',
            'integrity': artifact_match.integrity if artifact_match else '',
        }, artifact_warning


@dataclass(frozen=True)
class PluginDependencyOfflineArtifactMatch:
    """
    离线制品匹配结果。

    :param path: 制品路径
    :param version: 制品版本
    :param hashes: Python 制品哈希
    :param integrity: npm 制品 SRI
    """

    path: Path
    version: str
    hashes: list[str] = field(default_factory=list)
    integrity: str = ''


class PluginDependencyOfflineArtifactResolver:
    """
    插件离线依赖制品解析器。
    """

    def __init__(self, offline_dir: Path | str | None = None) -> None:
        """
        初始化离线依赖制品解析器。

        :param offline_dir: 离线制品根目录
        :return: None
        """
        self.offline_dir = Path(offline_dir) if offline_dir else None

    def resolve_python(
        self,
        name: str,
        requirement: str,
    ) -> tuple[PluginDependencyOfflineArtifactMatch | None, str | None]:
        """
        匹配 Python 离线制品并生成哈希。

        :param name: 依赖包名
        :param requirement: 依赖声明
        :return: 制品匹配结果和告警
        """
        if self.offline_dir is None:
            return None, None
        artifact_dir = self._artifact_dir('python')
        candidates = (
            [
                (artifact_path, version)
                for artifact_path in sorted(artifact_dir.iterdir())
                if (version := self._extract_python_artifact_version(artifact_path, name))
            ]
            if artifact_dir is not None
            else []
        )
        return self._build_python_match('python', name, requirement, candidates)

    def resolve_npm(
        self,
        kind: str,
        name: str,
        requirement: str,
    ) -> tuple[PluginDependencyOfflineArtifactMatch | None, str | None]:
        """
        匹配 npm 离线制品并生成 SRI。

        :param kind: 依赖类型
        :param name: 依赖包名
        :param requirement: 依赖声明
        :return: 制品匹配结果和告警
        """
        if self.offline_dir is None:
            return None, None
        artifact_dir = self._artifact_dir('npm')
        normalized_name = self._normalize_npm_artifact_name(name)
        candidates = (
            [
                (artifact_path, version)
                for artifact_path in sorted(artifact_dir.glob(f'{normalized_name}-*.tgz'))
                if (version := self._extract_npm_artifact_version(artifact_path, normalized_name))
            ]
            if artifact_dir is not None
            else []
        )
        return self._build_npm_match(kind, name, requirement, candidates)

    def _artifact_dir(self, kind: str) -> Path | None:
        """
        获取离线制品分类目录。

        :param kind: 制品分类
        :return: 制品目录
        """
        if self.offline_dir is None:
            return None
        artifact_dir = self.offline_dir / kind
        return artifact_dir if artifact_dir.is_dir() else None

    def _build_python_match(
        self,
        kind: str,
        name: str,
        requirement: str,
        candidates: list[tuple[Path, str]],
    ) -> tuple[PluginDependencyOfflineArtifactMatch | None, str | None]:
        """
        构建 Python 制品匹配结果。

        :param kind: 依赖类型
        :param name: 依赖包名
        :param requirement: 依赖声明
        :param candidates: 候选制品
        :return: 制品匹配结果和告警
        """
        artifact_path, version, warning = self._select_artifact(kind, name, requirement, candidates)
        if artifact_path is None or version is None:
            return None, warning
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        return PluginDependencyOfflineArtifactMatch(
            path=artifact_path,
            version=version,
            hashes=[f'sha256:{artifact_hash}'],
        ), None

    def _build_npm_match(
        self,
        kind: str,
        name: str,
        requirement: str,
        candidates: list[tuple[Path, str]],
    ) -> tuple[PluginDependencyOfflineArtifactMatch | None, str | None]:
        """
        构建 npm 制品匹配结果。

        :param kind: 依赖类型
        :param name: 依赖包名
        :param requirement: 依赖声明
        :param candidates: 候选制品
        :return: 制品匹配结果和告警
        """
        artifact_path, version, warning = self._select_artifact(kind, name, requirement, candidates)
        if artifact_path is None or version is None:
            return None, warning
        integrity_digest = base64.b64encode(
            hashlib.new(NPM_LOCKFILE_INTEGRITY_ALGORITHM, artifact_path.read_bytes()).digest()
        ).decode('ascii')
        return PluginDependencyOfflineArtifactMatch(
            path=artifact_path,
            version=version,
            integrity=f'{NPM_LOCKFILE_INTEGRITY_ALGORITHM}-{integrity_digest}',
        ), None

    def _select_artifact(
        self,
        kind: str,
        name: str,
        requirement: str,
        candidates: list[tuple[Path, str]],
    ) -> tuple[Path | None, str | None, str | None]:
        """
        从候选制品中选择一个满足声明的制品。

        :param kind: 依赖类型
        :param name: 依赖包名
        :param requirement: 依赖声明
        :param candidates: 候选制品
        :return: 制品路径、版本和告警
        """
        if not candidates:
            return None, None, f'未找到离线制品：{kind} {name}'
        matching_candidates = [
            (artifact_path, version)
            for artifact_path, version in candidates
            if self._artifact_version_satisfies_requirement(version, requirement)
        ]
        if not matching_candidates:
            candidate_versions = ', '.join(version for _, version in candidates)
            return None, None, f'离线制品版本不满足声明：{kind} {name} {candidate_versions}'
        if len(matching_candidates) > 1:
            return None, None, f'离线制品不唯一：{kind} {name}'
        artifact_path, version = matching_candidates[0]
        return artifact_path, version, None

    @staticmethod
    def _artifact_version_satisfies_requirement(version: str, requirement: str) -> bool:
        """
        判断制品版本是否满足 manifest 声明。

        :param version: 制品版本
        :param requirement: 依赖声明
        :return: 是否满足声明
        """
        operator_match = DEPENDENCY_OPERATOR_PATTERN.search(requirement.strip())
        if operator_match is None:
            return True
        version_range = requirement[operator_match.start() :]
        from plugins.core.validation.dependency_policy import version_satisfies_range  # noqa: PLC0415

        return version_satisfies_range(version, version_range)

    @classmethod
    def _extract_python_artifact_version(cls, artifact_path: Path, name: str) -> str | None:
        """
        从 Python wheel/sdist 文件名中提取版本。

        :param artifact_path: 制品路径
        :param name: 依赖包名
        :return: 制品版本
        """
        if artifact_path.suffix == '.whl':
            return cls._extract_python_version_from_parts(artifact_path.stem.split('-'), name)
        if artifact_path.name.endswith('.tar.gz'):
            return cls._extract_python_version_from_parts(artifact_path.name.removesuffix('.tar.gz').split('-'), name)
        return None

    @classmethod
    def _extract_python_version_from_parts(cls, parts: list[str], name: str) -> str | None:
        """
        从 Python 制品文件名片段中提取版本。

        :param parts: 文件名按短横线分隔后的片段
        :param name: 依赖包名
        :return: 制品版本
        """
        normalized_name = cls._normalize_python_artifact_name(name)
        for index in range(1, len(parts)):
            candidate_name = '-'.join(parts[:index])
            if cls._normalize_python_artifact_name(candidate_name) == normalized_name:
                return parts[index] or None
        return None

    @staticmethod
    def _extract_npm_artifact_version(artifact_path: Path, normalized_name: str) -> str | None:
        """
        从 npm tgz 文件名中提取版本。

        :param artifact_path: 制品路径
        :param normalized_name: 归一化 npm 制品包名
        :return: 制品版本
        """
        stem = artifact_path.name.removesuffix('.tgz')
        expected_prefix = f'{normalized_name}-'
        if not stem.startswith(expected_prefix):
            return None
        return stem.removeprefix(expected_prefix) or None

    @staticmethod
    def _normalize_python_artifact_name(name: str) -> str:
        """
        归一化 Python 制品名。

        :param name: 包名或文件名片段
        :return: 归一化名称
        """
        return PYTHON_PACKAGE_SEPARATOR_PATTERN.sub('-', name.strip()).lower()

    @staticmethod
    def _normalize_npm_artifact_name(name: str) -> str:
        """
        归一化 npm 制品名。

        :param name: 包名
        :return: 归一化名称
        """
        return name.strip().lower().replace('/', '-').lstrip('@')


class PluginDependencyLockPayloadBuilder:
    """
    插件依赖锁文件模板 payload 构建器。
    """

    @staticmethod
    def build_success_payload(
        plugin_id: str,
        lockfile_template: PluginDependencyLockfileTemplate,
        output_path: Path,
        *,
        dry_run: bool,
        written: bool,
        overwritten: bool,
    ) -> dict[str, object]:
        """
        构建锁文件模板生成成功 payload。

        :param plugin_id: 插件ID
        :param lockfile_template: 锁文件模板
        :param output_path: 输出路径
        :param dry_run: 是否仅预演
        :param written: 是否已写入文件
        :param overwritten: 是否覆盖了已有文件
        :return: payload
        """
        return CliPluginRuntimeExitCodePayload(
            {
                'ok': True,
                'message': '插件依赖锁文件模板生成完成',
                'pluginId': plugin_id,
                'dryRun': dry_run,
                'outputFile': str(output_path),
                'written': written,
                'overwritten': overwritten,
                'entryCount': lockfile_template.entry_count,
                'artifactCount': lockfile_template.artifact_count,
                'lockfile': lockfile_template.to_yaml(),
                'warnings': lockfile_template.warnings
                or (
                    []
                    if lockfile_template.artifact_count == lockfile_template.entry_count
                    else [
                        '锁文件模板尚未包含 resolvedVersion、hashes 或 integrity，需人工或 CI 补全后才能用于 locked/offline 策略。'
                    ]
                ),
            },
            success_code=SUCCESS,
            failure_code=RUNTIME_ERROR,
        ).to_payload()

    @staticmethod
    def build_exists_payload(plugin_id: str, output_path: Path) -> dict[str, object]:
        """
        构建锁文件已存在 payload。

        :param plugin_id: 插件ID
        :param output_path: 输出路径
        :return: payload
        """
        return CliPluginRuntimeExitCodePayload(
            {
                'ok': False,
                'message': '插件依赖锁文件已存在，请传入 --overwrite 覆盖',
                'pluginId': plugin_id,
                'dryRun': False,
                'outputFile': str(output_path),
                'written': False,
            },
            success_code=SUCCESS,
            failure_code=RUNTIME_ERROR,
        ).to_payload()

    @staticmethod
    def build_not_found_payload(plugin_id: str) -> dict[str, object]:
        """
        构建插件不存在 payload。

        :param plugin_id: 插件ID
        :return: payload
        """
        return CliPluginRuntimeExitCodePayload(
            {
                'ok': False,
                'message': '插件不存在',
                'pluginId': plugin_id,
                'dryRun': False,
                'written': False,
            },
            success_code=SUCCESS,
            failure_code=RUNTIME_ERROR,
        ).to_payload()


class PluginDependencyAllowlistExamplePayloadBuilder:
    """
    插件依赖允许列表示例 payload 构建器。
    """

    @staticmethod
    def build_success_payload(
        output_path: Path,
        *,
        allowlist_text: str,
        dry_run: bool,
        written: bool,
        overwritten: bool,
    ) -> dict[str, object]:
        """
        构建允许列表示例生成成功 payload。

        :param output_path: 输出路径
        :param allowlist_text: 允许列表 YAML 文本
        :param dry_run: 是否仅预演
        :param written: 是否已写入文件
        :param overwritten: 是否覆盖了已有文件
        :return: payload
        """
        return CliPluginRuntimeExitCodePayload(
            {
                'ok': True,
                'message': '插件依赖允许列表示例生成完成',
                'dryRun': dry_run,
                'outputFile': str(output_path),
                'written': written,
                'overwritten': overwritten,
                'allowlist': allowlist_text,
            },
            success_code=SUCCESS,
            failure_code=RUNTIME_ERROR,
        ).to_payload()

    @staticmethod
    def build_exists_payload(output_path: Path) -> dict[str, object]:
        """
        构建允许列表示例文件已存在 payload。

        :param output_path: 输出路径
        :return: payload
        """
        return CliPluginRuntimeExitCodePayload(
            {
                'ok': False,
                'message': '插件依赖允许列表文件已存在，请传入 --overwrite 覆盖',
                'dryRun': False,
                'outputFile': str(output_path),
                'written': False,
            },
            success_code=SUCCESS,
            failure_code=RUNTIME_ERROR,
        ).to_payload()


class PluginTestPlanBuilder:
    """
    插件 CLI 测试计划构建器。

    使用 Builder 模式发现后端 pytest 与前端 node 测试目标，并生成可执行命令。
    """

    def __init__(
        self,
        *,
        backend_root: Path,
        frontend_root: Path,
        python_executable: str,
        node_executable: str = 'node',
        timeout: int = 120,
    ) -> None:
        """
        初始化插件 CLI 测试计划构建器。

        :param backend_root: 后端项目根目录
        :param frontend_root: 前端项目根目录
        :param python_executable: Python 解释器
        :param node_executable: Node.js 可执行命令
        :param timeout: 命令超时时间
        :return: None
        """
        self.backend_root = backend_root
        self.frontend_root = frontend_root
        self.python_executable = python_executable
        self.node_executable = node_executable
        self.timeout = timeout

    def build(
        self,
        plugin_id: str,
        *,
        keyword: str = '',
        maxfail: int = 0,
        quiet: bool = False,
        frontend_build: bool = False,
    ) -> list[PluginTestTarget]:
        """
        构建插件测试目标列表。

        :param plugin_id: 插件ID
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: pytest 最大失败数
        :param quiet: pytest 是否启用简洁输出
        :param frontend_build: 是否追加前端构建验收目标
        :return: 插件测试目标列表
        """
        validate_plugin_id_value(plugin_id)
        targets = []
        backend_target = self.backend_root / 'tests' / 'plugins' / plugin_id
        if backend_target.exists():
            targets.append(
                PluginTestTarget(
                    kind='backend',
                    target_path=backend_target,
                    command=self._build_backend_command(
                        backend_target,
                        keyword=keyword,
                        maxfail=maxfail,
                        quiet=quiet,
                    ),
                    workdir=self.backend_root,
                    timeout=self.timeout,
                )
            )

        frontend_target = self.frontend_root / 'tests' / 'plugins' / plugin_id
        if frontend_target.exists():
            targets.extend(
                [
                    PluginTestTarget(
                        kind='frontend',
                        target_path=test_file,
                        command=[self.node_executable, str(test_file)],
                        workdir=self.frontend_root,
                        timeout=self.timeout,
                    )
                    for test_file in sorted(frontend_target.glob('*.test.js'))
                ]
            )
        if frontend_build and self.frontend_root.exists():
            targets.append(
                PluginTestTarget(
                    kind='frontend-build',
                    target_path=self.frontend_root,
                    command=['npm', 'run', 'build:stage'],
                    workdir=self.frontend_root,
                    timeout=max(self.timeout, 300),
                )
            )

        return targets

    def expected_paths(self, plugin_id: str) -> list[Path]:
        """
        获取插件测试约定目录列表。

        :param plugin_id: 插件ID
        :return: 插件测试约定目录列表
        """
        return [
            self.backend_root / 'tests' / 'plugins' / plugin_id,
            self.frontend_root / 'tests' / 'plugins' / plugin_id,
        ]

    def _build_backend_command(
        self,
        target_path: Path,
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
    ) -> list[str]:
        """
        构建插件 pytest 命令。

        :param target_path: 测试目标路径
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :return: pytest 命令参数列表
        """
        command = [self.python_executable, '-m', 'pytest']
        if quiet:
            command.append('-q')
        if keyword:
            command.extend(['-k', keyword])
        if maxfail > 0:
            command.append(f'--maxfail={maxfail}')
        command.append(str(target_path))

        return command


class PluginTestPayloadBuilder:
    """
    插件 CLI 测试负载构建器。

    使用 Builder 模式将测试目标和命令结果转换为稳定命令负载。
    """

    @staticmethod
    def build_command_result(completed: Any) -> dict[str, Any]:
        """
        构建 CLI 系统命令执行结果负载。

        :param completed: 命令执行结果
        :return: 系统命令执行结果负载
        """
        return PluginTestCommandResultPayload(completed).to_payload()

    @staticmethod
    def build_result_item(target: PluginTestTarget, completed: Any) -> dict[str, Any]:
        """
        构建单个插件测试结果项。

        :param target: 插件测试目标
        :param completed: 命令执行结果
        :return: 插件测试结果项
        """
        return PluginTestResultItemPayload(target, completed).to_payload()

    @staticmethod
    def with_exit_code(
        payload: dict[str, Any],
        *,
        success_code: int = SUCCESS,
        failure_code: int = RUNTIME_ERROR,
    ) -> dict[str, Any]:
        """
        为插件测试负载补充退出码。

        :param payload: 插件测试负载
        :param success_code: 成功退出码
        :param failure_code: 失败退出码
        :return: 带退出码的插件测试负载
        """
        return CliPluginRuntimeExitCodePayload(
            payload,
            success_code=success_code,
            failure_code=failure_code,
        ).to_payload()

    @staticmethod
    def build_missing_payload(plugin_id: str, expected_paths: list[Path]) -> dict[str, Any]:
        """
        构建插件测试目标缺失负载。

        :param plugin_id: 插件ID
        :param expected_paths: 约定测试目录列表
        :return: 插件测试目标缺失负载
        """
        return PluginTestMissingPayload(plugin_id, expected_paths).to_payload()

    @staticmethod
    def build_execution_payload(
        plugin_id: str,
        *,
        keyword: str,
        maxfail: int,
        quiet: bool,
        frontend_build: bool,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        构建插件测试执行结果负载。

        :param plugin_id: 插件ID
        :param keyword: pytest `-k` 过滤表达式
        :param maxfail: 最大失败数
        :param quiet: 是否启用简洁输出
        :param frontend_build: 是否执行前端构建验收
        :param results: 测试结果项列表
        :return: 插件测试执行结果负载
        """
        return PluginTestExecutionPayload(
            plugin_id=plugin_id,
            keyword=keyword,
            maxfail=maxfail,
            quiet=quiet,
            frontend_build=frontend_build,
            results=results,
        ).to_payload()
