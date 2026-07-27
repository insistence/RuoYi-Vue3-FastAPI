import base64
import hashlib
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml
from packaging.requirements import InvalidRequirement
from pydantic import ValidationError

from plugins.core.validation.dependencies import (
    DependencyInstallPlan,
    DependencyInstallPlanItem,
    DependencyKind,
    DependencyRequirementParser,
)
from plugins.core.validation.python_requirements import PythonRequirementParser
from plugins.core.validation.versioning import PluginVersionComparator, PluginVersionConstraintMatcher

DependencyInstallPolicyMode = Literal['disabled', 'plan_only', 'explicit', 'locked', 'offline']

PYTHON_PACKAGE_SEPARATOR_PATTERN = re.compile(r'[-_.]+')
DEPENDENCY_OPERATOR_PATTERN = re.compile(r'==|!=|>=|<=|=|>|<|\^|~')
VERSION_CONSTRAINT_PATTERN = re.compile(r'^(==|!=|>=|<=|=|>|<|\^|~)?\s*([A-Za-z0-9_.+\-!*]+)$')
SUPPORTED_NPM_INTEGRITY_ALGORITHMS = {'sha256', 'sha384', 'sha512'}


@dataclass(frozen=True)
class DependencyInstallPolicyConfig:
    """
    插件依赖安装策略配置。
    """

    mode: DependencyInstallPolicyMode | None = None
    env: str = 'dev'
    allow_prod: bool = False
    allow_prod_install: bool = False
    require_yes: bool = True
    require_lockfile: bool | None = None
    require_allowlist: bool | None = None
    allow_unlisted: bool = False
    lockfile_path: Path | str | None = None
    offline_dir: Path | str | None = None
    allowlist_path: Path | str | None = None
    pip_index_url: str | None = None
    npm_registry: str | None = None
    install_timeout_seconds: int = 600

    def __post_init__(self) -> None:
        """
        归一化路径和默认模式。

        :return: None
        """
        object.__setattr__(self, 'env', (self.env or 'dev').strip() or 'dev')
        object.__setattr__(self, 'mode', self.mode or self._default_mode(self.env))
        if self.lockfile_path is not None:
            object.__setattr__(self, 'lockfile_path', Path(self.lockfile_path))
        if self.offline_dir is not None:
            object.__setattr__(self, 'offline_dir', Path(self.offline_dir))
        if self.allowlist_path is not None:
            object.__setattr__(self, 'allowlist_path', Path(self.allowlist_path))

    @classmethod
    def from_environment(
        cls,
        *,
        env: str | None = None,
        mode: DependencyInstallPolicyMode | None = None,
        allow_prod: bool = False,
        allow_unlisted: bool = False,
        lockfile_path: Path | str | None = None,
        offline_dir: Path | str | None = None,
        require_lockfile: bool | None = None,
    ) -> 'DependencyInstallPolicyConfig':
        """
        从环境变量和 CLI 覆盖参数构建策略配置。

        :param env: 当前运行环境
        :param mode: 策略模式覆盖
        :param allow_prod: 是否允许生产环境危险安装
        :param allow_unlisted: 是否允许 dev 环境未命中 allowlist 的依赖仅告警
        :param lockfile_path: 锁文件路径
        :param offline_dir: 离线制品目录
        :param require_lockfile: 是否要求锁文件
        :return: 策略配置
        """
        settings = cls._load_environment_settings()
        resolved_env = env or os.getenv('APP_ENV', 'dev')
        return cls(
            mode=mode or cls._read_policy_mode(resolved_env, settings=settings),
            env=resolved_env,
            allow_prod=allow_prod,
            allow_prod_install=cls._read_bool(
                'PLUGIN_DEPENDENCY_ALLOW_PROD_INSTALL',
                attr='plugin_dependency_allow_prod_install',
                settings=settings,
                default=False,
            ),
            require_yes=cls._read_bool(
                'PLUGIN_DEPENDENCY_REQUIRE_YES',
                attr='plugin_dependency_require_yes',
                settings=settings,
                default=True,
            ),
            require_lockfile=(
                require_lockfile
                if require_lockfile is not None
                else cls._read_optional_bool(
                    'PLUGIN_DEPENDENCY_REQUIRE_LOCKFILE',
                    attr='plugin_dependency_require_lockfile',
                    settings=settings,
                )
            ),
            require_allowlist=cls._read_optional_bool(
                'PLUGIN_DEPENDENCY_REQUIRE_ALLOWLIST',
                attr='plugin_dependency_require_allowlist',
                settings=settings,
            ),
            allow_unlisted=allow_unlisted,
            lockfile_path=lockfile_path
            or cls._read_value(settings, 'plugin_dependency_lockfile', 'PLUGIN_DEPENDENCY_LOCKFILE')
            or None,
            offline_dir=offline_dir
            or cls._read_value(settings, 'plugin_dependency_offline_dir', 'PLUGIN_DEPENDENCY_OFFLINE_DIR')
            or None,
            allowlist_path=cls._read_value(settings, 'plugin_dependency_allowlist', 'PLUGIN_DEPENDENCY_ALLOWLIST')
            or None,
            pip_index_url=cls._read_value(
                settings, 'plugin_dependency_pip_index_url', 'PLUGIN_DEPENDENCY_PIP_INDEX_URL'
            )
            or None,
            npm_registry=cls._read_value(settings, 'plugin_dependency_npm_registry', 'PLUGIN_DEPENDENCY_NPM_REGISTRY')
            or None,
            install_timeout_seconds=cls._read_int(
                'PLUGIN_DEPENDENCY_INSTALL_TIMEOUT',
                attr='plugin_dependency_install_timeout',
                settings=settings,
                default=600,
            ),
        )

    @staticmethod
    def _default_mode(env: str) -> DependencyInstallPolicyMode:
        """
        获取环境默认策略模式。

        :param env: 当前运行环境
        :return: 默认策略模式
        """
        env_mode_map: dict[str, DependencyInstallPolicyMode] = {
            'dev': 'explicit',
            'test': 'plan_only',
            'stage': 'locked',
            'prod': 'plan_only',
        }
        return env_mode_map.get(env, 'plan_only')

    @classmethod
    def _load_environment_settings(cls) -> Any | None:
        """
        延迟加载统一配置入口中的插件依赖策略配置。

        :return: 插件依赖策略配置对象，缺失时返回 None
        """
        try:
            from config.env import get_config  # noqa: PLC0415
        except ImportError:
            return None
        getter = getattr(get_config, 'get_plugin_dependency_policy_config', None)
        if getter is None:
            return None
        try:
            return getter()
        except ValidationError as exc:
            raise ValueError(f'非法插件依赖策略布尔配置：{exc}') from exc

    @staticmethod
    def _read_value(settings: Any | None, attr: str, env_name: str, default: Any = None) -> Any:
        """
        从统一配置入口读取配置值，缺失时回退到环境变量。

        :param settings: 统一配置对象
        :param attr: 配置对象属性名
        :param env_name: 环境变量名称
        :param default: 默认值
        :return: 配置值
        """
        if settings is not None and hasattr(settings, attr):
            value = getattr(settings, attr)
            if value is not None:
                return value
        return os.getenv(env_name, default)

    @classmethod
    def _read_policy_mode(cls, env: str, *, settings: Any | None = None) -> DependencyInstallPolicyMode:
        """
        读取策略模式环境变量。

        :param env: 当前运行环境
        :param settings: 统一配置对象
        :return: 策略模式
        """
        value = str(
            cls._read_value(settings, 'plugin_dependency_policy_mode', 'PLUGIN_DEPENDENCY_POLICY_MODE', '')
        ).strip()
        if not value:
            return cls._default_mode(env)
        if '=' not in value:
            return cls._normalize_mode(value, cls._default_mode(env))
        entries = dict(
            part.split('=', maxsplit=1)
            for part in value.split(',')
            if '=' in part and part.split('=', maxsplit=1)[0].strip()
        )
        if env not in entries:
            return cls._default_mode(env)
        return cls._normalize_mode(entries[env], cls._default_mode(env))

    @staticmethod
    def _normalize_mode(value: str, default: DependencyInstallPolicyMode) -> DependencyInstallPolicyMode:
        """
        归一化策略模式。

        :param value: 原始模式
        :param default: 默认模式
        :return: 策略模式
        """
        normalized_value = value.strip()
        if normalized_value in {'disabled', 'plan_only', 'explicit', 'locked', 'offline'}:
            return normalized_value  # type: ignore[return-value]
        if not normalized_value:
            return default
        raise ValueError(f'非法插件依赖安装策略模式：{value}')

    @staticmethod
    def _parse_bool(value: object, *, name: str) -> bool:
        """
        解析布尔配置，拒绝未知字符串。

        :param value: 原始配置值
        :param name: 配置名称
        :return: 布尔值
        """
        if isinstance(value, bool):
            return value
        normalized_value = str(value).strip().lower()
        if normalized_value in {'1', 'true', 'yes', 'on'}:
            return True
        if normalized_value in {'0', 'false', 'no', 'off'}:
            return False
        raise ValueError(f'非法插件依赖策略布尔配置：{name}={value}')

    @classmethod
    def _read_bool(cls, name: str, *, default: bool, attr: str, settings: Any | None = None) -> bool:
        """
        读取布尔环境变量。

        :param name: 环境变量名称
        :param attr: 配置对象属性名
        :param settings: 统一配置对象
        :param default: 默认值
        :return: 布尔值
        """
        value = cls._read_value(settings, attr, name)
        if value is None or value == '':
            return default
        return cls._parse_bool(value, name=name)

    @classmethod
    def _read_optional_bool(cls, name: str, *, attr: str, settings: Any | None = None) -> bool | None:
        """
        读取可空布尔环境变量。

        :param name: 环境变量名称
        :param attr: 配置对象属性名
        :param settings: 统一配置对象
        :return: 布尔值或 None
        """
        value = cls._read_value(settings, attr, name)
        if value is None or value == '':
            return None
        return cls._parse_bool(value, name=name)

    @classmethod
    def _read_int(cls, name: str, *, attr: str, settings: Any | None, default: int) -> int:
        """
        读取整数配置。

        :param name: 环境变量名称
        :param attr: 配置对象属性名
        :param settings: 统一配置对象
        :param default: 默认值
        :return: 整数值
        """
        value = cls._read_value(settings, attr, name, default)
        if value is None or value == '':
            return default
        return int(value)

    @property
    def resolved_require_lockfile(self) -> bool:
        """
        判断当前策略是否要求锁文件。

        :return: 是否要求锁文件
        """
        if self.require_lockfile is not None:
            return self.require_lockfile
        return self.mode in {'locked', 'offline'} or self.env in {'stage', 'prod'}

    @property
    def resolved_require_allowlist(self) -> bool:
        """
        判断当前策略是否要求允许列表。

        :return: 是否要求允许列表
        """
        if self.require_allowlist is not None:
            return self.require_allowlist
        return self.env in {'stage', 'prod'}


@dataclass(frozen=True)
class DependencyInstallPolicyItemDecision:
    """
    单条依赖安装计划的策略判定。
    """

    kind: DependencyKind
    name: str
    requirement: str
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    locked_version: str | None = None
    artifact_path: str | None = None
    artifact_verified: bool | None = None

    def to_payload(self) -> dict[str, object]:
        """
        转换为响应 payload。

        :return: 策略判定 payload
        """
        payload: dict[str, object] = {
            'kind': self.kind,
            'name': self.name,
            'requirement': self.requirement,
            'allowed': self.allowed,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'requirements': self.requirements,
        }
        if self.locked_version:
            payload['lockedVersion'] = self.locked_version
        if self.artifact_path:
            payload['artifactPath'] = self.artifact_path
        if self.artifact_verified is not None:
            payload['artifactVerified'] = self.artifact_verified
        return payload


@dataclass(frozen=True)
class DependencyInstallPolicyDecision:
    """
    依赖安装策略判定结果。
    """

    allowed: bool
    mode: DependencyInstallPolicyMode
    reasons: list[str]
    warnings: list[str]
    requirements: list[str]
    items: list[DependencyInstallPolicyItemDecision]
    install_plan_items: list[DependencyInstallPlanItem]

    def to_payload(self) -> dict[str, object]:
        """
        转换为响应 payload。

        :return: 策略判定 payload
        """
        return {
            'allowed': self.allowed,
            'mode': self.mode,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'requirements': self.requirements,
            'items': [item.to_payload() for item in self.items],
        }


@dataclass(frozen=True)
class DependencyLockEntry:
    """
    锁文件中的单条依赖。
    """

    kind: DependencyKind
    name: str
    requirement: str
    resolved_version: str | None
    hashes: list[str] = field(default_factory=list)
    integrity: str | None = None


@dataclass(frozen=True)
class DependencyLockfile:
    """
    插件依赖锁文件。
    """

    path: Path
    entries: dict[tuple[DependencyKind, str], DependencyLockEntry]

    @classmethod
    def load(cls, path: Path | str | None) -> 'DependencyLockfile | None':
        """
        加载锁文件。

        :param path: 锁文件路径
        :return: 锁文件对象，缺失时返回 None
        """
        if path is None:
            return None
        lockfile_path = Path(path)
        if not lockfile_path.is_file():
            return None
        data = yaml.safe_load(lockfile_path.read_text(encoding='utf-8')) or {}
        entries: dict[tuple[DependencyKind, str], DependencyLockEntry] = {}
        for kind in ('python', 'npm', 'npmDev'):
            for raw_entry in data.get(kind, []) or []:
                if not isinstance(raw_entry, dict):
                    continue
                name = str(raw_entry.get('name', '')).strip()
                if not name:
                    continue
                entry = DependencyLockEntry(
                    kind=kind,
                    name=name,
                    requirement=str(raw_entry.get('requirement', '') or '').strip(),
                    resolved_version=str(raw_entry.get('resolvedVersion', '') or '').strip() or None,
                    hashes=[str(item) for item in raw_entry.get('hashes', []) or []],
                    integrity=str(raw_entry.get('integrity', '') or '').strip() or None,
                )
                entries[(kind, normalize_dependency_name(kind, name))] = entry

        return cls(path=lockfile_path, entries=entries)

    def get_entry(self, item: DependencyInstallPlanItem) -> DependencyLockEntry | None:
        """
        获取安装计划项对应的锁定依赖。

        :param item: 安装计划项
        :return: 锁文件项
        """
        return self.entries.get((item.kind, normalize_dependency_name(item.kind, item.name)))


@dataclass(frozen=True)
class DependencyVersionBound:
    """
    依赖版本范围边界。
    """

    version: str
    inclusive: bool


@dataclass(frozen=True)
class DependencyVersionRange:
    """
    可保守比较的依赖版本范围。
    """

    lower: DependencyVersionBound | None = None
    upper: DependencyVersionBound | None = None
    exact: str | None = None


@dataclass(frozen=True)
class DependencyAllowlist:
    """
    插件依赖允许列表。
    """

    entries: dict[DependencyKind, dict[str, dict[str, Any]]]

    @classmethod
    def load(cls, path: Path | str | None) -> 'DependencyAllowlist':
        """
        加载允许列表。

        :param path: 允许列表路径
        :return: 允许列表
        """
        if path is None or not Path(path).is_file():
            return cls(entries={'python': {}, 'npm': {}, 'npmDev': {}})
        data = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
        entries: dict[DependencyKind, dict[str, dict[str, Any]]] = {'python': {}, 'npm': {}, 'npmDev': {}}
        for kind in entries:
            kind_entries = data.get(kind, {}) or {}
            if not isinstance(kind_entries, dict):
                continue
            entries[kind] = {
                normalize_dependency_name(kind, str(name)): entry if isinstance(entry, dict) else {}
                for name, entry in kind_entries.items()
            }
        return cls(entries=entries)

    def is_allowed(self, item: DependencyInstallPlanItem) -> bool:
        """
        判断依赖是否命中允许列表。

        :param item: 安装计划项
        :return: 是否允许
        """
        entry = self.entries.get(item.kind, {}).get(normalize_dependency_name(item.kind, item.name))
        if entry is None:
            return False
        versions = [str(version) for version in entry.get('versions', []) or []]
        if not versions:
            return True
        if item.kind == 'python':
            try:
                requested_version_text = PythonRequirementParser.parse(item.requirement).required_version
            except InvalidRequirement:
                return False
            if not requested_version_text:
                return False
            requested_range = parse_version_range(requested_version_text)
        else:
            requested_version_text = extract_dependency_required_version(item.requirement)
            requested_range = parse_dependency_requirement_range(item.requirement)
        if requested_range is None:
            return requested_version_text in versions
        if requested_version_text in versions:
            return True
        for version_range in versions:
            allowed_range = parse_version_range(version_range)
            if allowed_range is not None and version_range_contains(allowed_range, requested_range):
                return True
        return False


class DependencyArtifactStore:
    """
    离线依赖制品仓库。
    """

    def __init__(self, offline_dir: Path | str | None) -> None:
        """
        初始化离线制品仓库。

        :param offline_dir: 离线制品根目录
        :return: None
        """
        self.offline_dir = Path(offline_dir) if offline_dir is not None else None

    def find_artifact(self, entry: DependencyLockEntry) -> Path | None:
        """
        查找锁定依赖对应的离线制品。

        :param entry: 锁文件项
        :return: 制品路径
        """
        if self.offline_dir is None or not entry.resolved_version:
            return None
        if entry.kind == 'python':
            return self._find_python_artifact(entry)
        return self._find_npm_artifact(entry)

    def verify_artifact(self, entry: DependencyLockEntry, artifact_path: Path) -> str | None:
        """
        校验离线制品内容完整性。

        :param entry: 锁文件项
        :param artifact_path: 制品路径
        :return: 不匹配原因，匹配时返回 None
        """
        if entry.kind == 'python':
            return self._verify_python_artifact(entry, artifact_path)
        return self._verify_npm_artifact(entry, artifact_path)

    def _find_python_artifact(self, entry: DependencyLockEntry) -> Path | None:
        """
        查找 Python 离线制品。

        :param entry: 锁文件项
        :return: 制品路径
        """
        artifact_dir = self.offline_dir / 'python' if self.offline_dir else None
        if artifact_dir is None or not artifact_dir.is_dir() or not entry.resolved_version:
            return None
        normalized_name = normalize_dependency_name('python', entry.name).replace('-', '[-_]')
        patterns = [
            f'{normalized_name}-{entry.resolved_version}*.whl',
            f'{normalized_name}-{entry.resolved_version}*.tar.gz',
        ]
        for artifact_path in artifact_dir.iterdir():
            if any(re.fullmatch(pattern.replace('*', '.*'), artifact_path.name) for pattern in patterns):
                return artifact_path
        return None

    def _find_npm_artifact(self, entry: DependencyLockEntry) -> Path | None:
        """
        查找 npm 离线制品。

        :param entry: 锁文件项
        :return: 制品路径
        """
        artifact_dir = self.offline_dir / 'npm' if self.offline_dir else None
        if artifact_dir is None or not artifact_dir.is_dir() or not entry.resolved_version:
            return None
        normalized_name = normalize_dependency_name(entry.kind, entry.name).replace('/', '-').lstrip('@')
        candidates = sorted(artifact_dir.glob(f'{normalized_name}-{entry.resolved_version}.tgz'))
        return candidates[0] if candidates else None

    @staticmethod
    def _verify_python_artifact(entry: DependencyLockEntry, artifact_path: Path) -> str | None:
        """
        校验 Python 离线制品 sha256。

        :param entry: 锁文件项
        :param artifact_path: 制品路径
        :return: 不匹配原因，匹配时返回 None
        """
        expected_hashes = [
            hash_value.split(':', maxsplit=1)[1].strip().lower()
            for hash_value in entry.hashes
            if hash_value.lower().startswith('sha256:')
        ]
        if not expected_hashes:
            return f'锁文件缺少可校验 Python sha256：{entry.kind} {entry.name}'
        actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest().lower()
        if actual_hash not in expected_hashes:
            return f'离线制品哈希不匹配：{entry.kind} {entry.name} {entry.resolved_version}'
        return None

    @staticmethod
    def _verify_npm_artifact(entry: DependencyLockEntry, artifact_path: Path) -> str | None:
        """
        校验 npm 离线制品 integrity。

        :param entry: 锁文件项
        :param artifact_path: 制品路径
        :return: 不匹配原因，匹配时返回 None
        """
        if not entry.integrity:
            return f'锁文件缺少可校验 npm integrity：{entry.kind} {entry.name}'
        artifact_bytes = artifact_path.read_bytes()
        found_supported_integrity = False
        for token in entry.integrity.split():
            if '-' not in token:
                continue
            algorithm, expected_digest = token.split('-', maxsplit=1)
            algorithm = algorithm.lower()
            if algorithm not in SUPPORTED_NPM_INTEGRITY_ALGORITHMS:
                continue
            found_supported_integrity = True
            actual_digest = base64.b64encode(hashlib.new(algorithm, artifact_bytes).digest()).decode('ascii')
            if normalize_sri_digest(actual_digest) == normalize_sri_digest(expected_digest):
                return None
        if not found_supported_integrity:
            return f'锁文件缺少可校验 npm integrity：{entry.kind} {entry.name}'
        return f'离线制品 integrity 不匹配：{entry.kind} {entry.name} {entry.resolved_version}'


class DependencyInstallPolicyEvaluator:
    """
    插件依赖安装策略判定器。
    """

    def __init__(self, config: DependencyInstallPolicyConfig | None = None) -> None:
        """
        初始化策略判定器。

        :param config: 策略配置
        :return: None
        """
        self.config = config or DependencyInstallPolicyConfig.from_environment()

    def evaluate(
        self, install_plan: DependencyInstallPlan, *, confirmed: bool = False
    ) -> DependencyInstallPolicyDecision:
        """
        判定依赖安装计划是否允许真实执行。

        :param install_plan: 依赖安装计划
        :param confirmed: 是否已显式确认
        :return: 策略判定结果
        """
        if not install_plan.has_actions:
            return DependencyInstallPolicyDecision(
                allowed=True,
                mode=self.config.mode or 'plan_only',
                reasons=[],
                warnings=[],
                requirements=[],
                items=[],
                install_plan_items=[],
            )

        global_reasons, global_requirements = self._build_global_blockers(confirmed)
        allowlist = DependencyAllowlist.load(self.config.allowlist_path)
        lockfile = DependencyLockfile.load(self.config.lockfile_path)
        artifact_store = DependencyArtifactStore(self.config.offline_dir)
        rewritten_items: list[DependencyInstallPlanItem] = []
        item_decisions: list[DependencyInstallPolicyItemDecision] = []

        if self.config.resolved_require_lockfile and lockfile is None:
            append_unique(global_requirements, '需要 plugin.lock.yaml')
        if self.config.mode == 'offline' and self.config.offline_dir is None:
            append_unique(global_requirements, '需要离线制品目录')

        for item in install_plan.items:
            item_decision, rewritten_item = self._evaluate_item(
                item,
                allowlist=allowlist,
                lockfile=lockfile,
                artifact_store=artifact_store,
                global_blocked=bool(global_reasons or global_requirements),
            )
            rewritten_items.append(rewritten_item)
            item_decisions.append(item_decision)

        lockfile_reasons = self._build_lockfile_extra_reasons(lockfile, install_plan)
        global_reasons.extend(reason for reason in lockfile_reasons if reason not in global_reasons)

        reasons = list_unique([*global_reasons, *(reason for item in item_decisions for reason in item.reasons)])
        requirements = list_unique(
            [*global_requirements, *(requirement for item in item_decisions for requirement in item.requirements)]
        )
        warnings = list_unique([warning for item in item_decisions for warning in item.warnings])
        allowed = not reasons and not requirements and all(item.allowed for item in item_decisions)

        return DependencyInstallPolicyDecision(
            allowed=allowed,
            mode=self.config.mode or 'plan_only',
            reasons=reasons,
            warnings=warnings,
            requirements=requirements,
            items=item_decisions,
            install_plan_items=rewritten_items,
        )

    def _build_global_blockers(self, confirmed: bool) -> tuple[list[str], list[str]]:
        """
        构建全局阻断原因和前置要求。

        :param confirmed: 是否已显式确认
        :return: 阻断原因和前置要求
        """
        reasons: list[str] = []
        requirements: list[str] = []
        if self.config.mode == 'disabled':
            reasons.append('插件依赖真实安装已禁用')
        if self.config.mode == 'plan_only':
            reasons.append('当前策略仅允许生成依赖安装计划')
        if self.config.env == 'prod' and self.config.mode != 'plan_only':
            if not self.config.allow_prod_install:
                reasons.append('生产环境禁止真实依赖安装')
            if not self.config.allow_prod:
                requirements.append('需要 --allow-prod 确认生产环境安装')
        if self.config.require_yes and not confirmed and self.config.mode not in {'disabled', 'plan_only'}:
            requirements.append('需要显式确认 --yes')
        return reasons, requirements

    def _evaluate_item(
        self,
        item: DependencyInstallPlanItem,
        *,
        allowlist: DependencyAllowlist,
        lockfile: DependencyLockfile | None,
        artifact_store: DependencyArtifactStore,
        global_blocked: bool,
    ) -> tuple[DependencyInstallPolicyItemDecision, DependencyInstallPlanItem]:
        """
        判定单条安装计划并生成可能改写后的计划项。

        :param item: 安装计划项
        :param allowlist: 允许列表
        :param lockfile: 锁文件
        :param artifact_store: 离线制品仓库
        :param global_blocked: 是否存在全局阻断
        :return: 单项判定和安装计划项
        """
        reasons: list[str] = []
        warnings: list[str] = []
        requirements: list[str] = []
        rewritten_item = item
        locked_version: str | None = None
        artifact_path: str | None = None
        artifact_verified: bool | None = None

        if self.config.mode in {'disabled', 'plan_only'}:
            reasons.append('当前策略不允许执行真实安装')

        self._evaluate_allowlist(item, allowlist, reasons, warnings)
        lock_entry = self._evaluate_lockfile(item, lockfile, reasons)
        if lock_entry and lock_entry.resolved_version:
            locked_version = lock_entry.resolved_version
            rewritten_item = self._build_locked_plan_item(item, lock_entry)

        if self.config.mode == 'offline' and lock_entry and lock_entry.resolved_version:
            artifact = artifact_store.find_artifact(lock_entry)
            if artifact is None:
                reasons.append(f'缺少离线制品：{item.kind} {item.name} {lock_entry.resolved_version}')
            else:
                artifact_path = str(artifact)
                integrity_reason = artifact_store.verify_artifact(lock_entry, artifact)
                if integrity_reason:
                    reasons.append(integrity_reason)
                    artifact_verified = False
                else:
                    artifact_verified = True
                rewritten_item = self._build_offline_plan_item(item, lock_entry, artifact)

        allowed = not global_blocked and not reasons and not requirements
        return (
            DependencyInstallPolicyItemDecision(
                kind=item.kind,
                name=item.name,
                requirement=item.requirement,
                allowed=allowed,
                reasons=reasons,
                warnings=warnings,
                requirements=requirements,
                locked_version=locked_version,
                artifact_path=artifact_path,
                artifact_verified=artifact_verified,
            ),
            rewritten_item,
        )

    def _evaluate_allowlist(
        self,
        item: DependencyInstallPlanItem,
        allowlist: DependencyAllowlist,
        reasons: list[str],
        warnings: list[str],
    ) -> None:
        """
        评估允许列表。

        :param item: 安装计划项
        :param allowlist: 允许列表
        :param reasons: 阻断原因
        :param warnings: 告警列表
        :return: None
        """
        if allowlist.is_allowed(item):
            return
        message = f'依赖未命中允许列表：{item.kind} {item.name}'
        if self.config.resolved_require_allowlist:
            reasons.append(message)
            return
        if self.config.allowlist_path or self.config.allow_unlisted:
            warnings.append(message)

    def _evaluate_lockfile(
        self,
        item: DependencyInstallPlanItem,
        lockfile: DependencyLockfile | None,
        reasons: list[str],
    ) -> DependencyLockEntry | None:
        """
        评估锁文件。

        :param item: 安装计划项
        :param lockfile: 锁文件
        :param reasons: 阻断原因
        :return: 锁文件项
        """
        if not self.config.resolved_require_lockfile:
            return None
        if lockfile is None:
            return None
        lock_entry = lockfile.get_entry(item)
        if lock_entry is None or lock_entry.requirement != item.requirement:
            reasons.append(f'锁文件缺少匹配依赖：{item.kind} {item.name} {item.requirement}')
            return None
        if not lock_entry.resolved_version:
            reasons.append(f'锁文件缺少 resolvedVersion：{item.kind} {item.name}')
            return None
        if not self._lockfile_version_satisfies_requirement(item, lock_entry):
            reasons.append(
                f'锁文件 resolvedVersion 不满足依赖声明：{item.kind} {item.name} '
                f'{lock_entry.resolved_version} not in {item.requirement}'
            )
            return None
        if item.kind == 'python' and not lock_entry.hashes:
            reasons.append(f'锁文件缺少 Python 哈希：{item.kind} {item.name}')
        if item.kind in {'npm', 'npmDev'} and not lock_entry.integrity:
            reasons.append(f'锁文件缺少 npm integrity：{item.kind} {item.name}')
        return lock_entry

    @staticmethod
    def _lockfile_version_satisfies_requirement(
        item: DependencyInstallPlanItem,
        lock_entry: DependencyLockEntry,
    ) -> bool:
        """
        判断锁文件 resolvedVersion 是否满足插件依赖声明。

        :param item: 安装计划项
        :param lock_entry: 锁文件项
        :return: 是否满足
        """
        if not lock_entry.resolved_version:
            return False
        if item.kind == 'python':
            try:
                parsed_requirement = PythonRequirementParser.parse(item.requirement)
            except InvalidRequirement:
                return False
            return parsed_requirement.is_version_satisfied(lock_entry.resolved_version)
        required_version = extract_dependency_required_version(item.requirement)
        if not required_version:
            return True
        return version_satisfies_range(lock_entry.resolved_version, required_version)

    @staticmethod
    def _build_lockfile_extra_reasons(
        lockfile: DependencyLockfile | None,
        install_plan: DependencyInstallPlan,
    ) -> list[str]:
        """
        构建锁文件额外安装项阻断原因。

        :param lockfile: 锁文件
        :param install_plan: 安装计划
        :return: 阻断原因
        """
        if lockfile is None:
            return []
        plan_keys = {
            (item.kind, normalize_dependency_name(item.kind, item.name), item.requirement)
            for item in install_plan.items
        }
        reasons = []
        for entry in lockfile.entries.values():
            key = (entry.kind, normalize_dependency_name(entry.kind, entry.name), entry.requirement)
            if key not in plan_keys:
                reasons.append(f'锁文件包含未声明依赖：{entry.kind} {entry.name} {entry.requirement}')
        return reasons

    def _build_locked_plan_item(
        self,
        item: DependencyInstallPlanItem,
        lock_entry: DependencyLockEntry,
    ) -> DependencyInstallPlanItem:
        """
        构建锁定版本安装计划项。

        :param item: 原始安装计划项
        :param lock_entry: 锁文件项
        :return: 改写后的安装计划项
        """
        if item.kind == 'python':
            command = [item.command[0], '-m', 'pip', 'install']
            if self.config.pip_index_url:
                command.extend(['--index-url', self.config.pip_index_url])
            command.append(f'{lock_entry.name}=={lock_entry.resolved_version}')
            return replace(item, command=command, requirement=f'{lock_entry.name}=={lock_entry.resolved_version}')

        command = ['npm', 'install']
        if item.kind == 'npmDev':
            command.append('--save-dev')
        if self.config.npm_registry:
            command.extend(['--registry', self.config.npm_registry])
        command.append(f'{lock_entry.name}@{lock_entry.resolved_version}')
        return replace(item, command=command, requirement=f'{lock_entry.name}@{lock_entry.resolved_version}')

    @staticmethod
    def _build_offline_plan_item(
        item: DependencyInstallPlanItem,
        lock_entry: DependencyLockEntry,
        artifact_path: Path,
    ) -> DependencyInstallPlanItem:
        """
        构建离线安装计划项。

        :param item: 原始安装计划项
        :param lock_entry: 锁文件项
        :param artifact_path: 本地制品路径
        :return: 改写后的安装计划项
        """
        if item.kind == 'python':
            command = [
                item.command[0],
                '-m',
                'pip',
                'install',
                '--no-index',
                '--find-links',
                str(artifact_path.parent),
                f'{lock_entry.name}=={lock_entry.resolved_version}',
            ]
            return replace(item, command=command, requirement=f'{lock_entry.name}=={lock_entry.resolved_version}')

        command = ['npm', 'install']
        if item.kind == 'npmDev':
            command.append('--save-dev')
        command.extend([str(artifact_path), '--offline'])
        return replace(item, command=command, requirement=str(artifact_path))


def normalize_dependency_name(kind: DependencyKind, name: str) -> str:
    """
    归一化依赖名称。

    :param kind: 依赖类型
    :param name: 依赖名称
    :return: 归一化名称
    """
    normalized_name = name.strip()
    if kind == 'python':
        return PYTHON_PACKAGE_SEPARATOR_PATTERN.sub('-', normalized_name).lower()
    return normalized_name.lower()


def extract_dependency_constraints(requirement: str) -> list[str]:
    """
    从依赖声明中提取版本约束列表。

    :param requirement: 依赖声明或版本范围
    :return: 版本约束列表
    """
    normalized_requirement = requirement.strip()
    if not normalized_requirement:
        return []
    operator_match = DEPENDENCY_OPERATOR_PATTERN.search(normalized_requirement)
    constraint_text = normalized_requirement[operator_match.start() :] if operator_match else normalized_requirement
    return [constraint.strip() for constraint in constraint_text.split(',') if constraint.strip()]


def extract_dependency_required_version(requirement: str) -> str | None:
    """
    提取依赖声明中的原始版本约束文本。

    :param requirement: 依赖声明
    :return: 原始版本约束文本
    """
    constraints = extract_dependency_constraints(requirement)
    return ','.join(constraints) if constraints else None


def parse_dependency_requirement_range(requirement: str) -> DependencyVersionRange | None:
    """
    解析依赖声明中的版本范围。

    :param requirement: 依赖声明
    :return: 可比较的版本范围
    """
    constraints = extract_dependency_constraints(requirement)
    return parse_constraints_as_range(constraints)


def parse_version_range(version_range: str) -> DependencyVersionRange | None:
    """
    解析允许列表版本范围。

    :param version_range: 版本范围
    :return: 可比较的版本范围
    """
    return parse_constraints_as_range(extract_dependency_constraints(version_range))


def parse_constraints_as_range(constraints: list[str]) -> DependencyVersionRange | None:
    """
    将约束列表解析为单一连续范围。

    :param constraints: 版本约束列表
    :return: 可比较的版本范围
    """
    if not constraints:
        return None
    lower: DependencyVersionBound | None = None
    upper: DependencyVersionBound | None = None
    exact: str | None = None
    for constraint in constraints:
        matched_constraint = VERSION_CONSTRAINT_PATTERN.match(constraint)
        if not matched_constraint:
            return None
        operator, version = matched_constraint.groups()
        operator = operator or '=='
        if operator in {'^', '~', '!='}:
            return None
        if operator in {'==', '='}:
            exact = version
            lower = DependencyVersionBound(version=version, inclusive=True)
            upper = DependencyVersionBound(version=version, inclusive=True)
            continue
        if operator in {'>=', '>'}:
            lower = select_tighter_lower_bound(
                lower,
                DependencyVersionBound(version=version, inclusive=operator == '>='),
            )
            if lower is None:
                return None
            continue
        if operator in {'<=', '<'}:
            upper = select_tighter_upper_bound(
                upper,
                DependencyVersionBound(version=version, inclusive=operator == '<='),
            )
            if upper is None:
                return None
            continue
        return None
    return DependencyVersionRange(lower=lower, upper=upper, exact=exact)


def select_tighter_lower_bound(
    current: DependencyVersionBound | None,
    candidate: DependencyVersionBound,
) -> DependencyVersionBound | None:
    """
    选择更严格的下界。

    :param current: 当前下界
    :param candidate: 候选下界
    :return: 更严格下界
    """
    if current is None:
        return candidate
    comparison = compare_dependency_versions(candidate.version, current.version)
    if comparison is None:
        return None
    if comparison > 0:
        return candidate
    if comparison < 0:
        return current
    return candidate if current.inclusive and not candidate.inclusive else current


def select_tighter_upper_bound(
    current: DependencyVersionBound | None,
    candidate: DependencyVersionBound,
) -> DependencyVersionBound | None:
    """
    选择更严格的上界。

    :param current: 当前上界
    :param candidate: 候选上界
    :return: 更严格上界
    """
    if current is None:
        return candidate
    comparison = compare_dependency_versions(candidate.version, current.version)
    if comparison is None:
        return None
    if comparison < 0:
        return candidate
    if comparison > 0:
        return current
    return candidate if current.inclusive and not candidate.inclusive else current


def version_range_contains(allowed_range: DependencyVersionRange, requested_range: DependencyVersionRange) -> bool:
    """
    判断允许范围是否完整包含请求范围。

    :param allowed_range: 允许列表范围
    :param requested_range: 依赖声明范围
    :return: 是否包含
    """
    if requested_range.exact:
        return version_range_contains_version(allowed_range, requested_range.exact)
    if allowed_range.exact:
        return False
    return lower_bound_contains(allowed_range.lower, requested_range.lower) and upper_bound_contains(
        allowed_range.upper,
        requested_range.upper,
    )


def version_range_contains_version(version_range: DependencyVersionRange, version: str) -> bool:
    """
    判断版本是否落入范围。

    :param version_range: 版本范围
    :param version: 版本
    :return: 是否落入范围
    """
    if version_range.exact:
        return PluginVersionComparator.equals(version, version_range.exact)
    if version_range.lower:
        lower_comparison = compare_dependency_versions(version, version_range.lower.version)
        if lower_comparison is None or lower_comparison < 0:
            return False
        if lower_comparison == 0 and not version_range.lower.inclusive:
            return False
    if version_range.upper:
        upper_comparison = compare_dependency_versions(version, version_range.upper.version)
        if upper_comparison is None or upper_comparison > 0:
            return False
        if upper_comparison == 0 and not version_range.upper.inclusive:
            return False
    return True


def lower_bound_contains(
    allowed_lower: DependencyVersionBound | None,
    requested_lower: DependencyVersionBound | None,
) -> bool:
    """
    判断请求下界是否被允许下界覆盖。

    :param allowed_lower: 允许范围下界
    :param requested_lower: 请求范围下界
    :return: 是否覆盖
    """
    if allowed_lower is None:
        return True
    if requested_lower is None:
        return False
    comparison = compare_dependency_versions(requested_lower.version, allowed_lower.version)
    if comparison is None:
        return False
    if comparison > 0:
        return True
    if comparison < 0:
        return False
    return allowed_lower.inclusive or not requested_lower.inclusive


def upper_bound_contains(
    allowed_upper: DependencyVersionBound | None,
    requested_upper: DependencyVersionBound | None,
) -> bool:
    """
    判断请求上界是否被允许上界覆盖。

    :param allowed_upper: 允许范围上界
    :param requested_upper: 请求范围上界
    :return: 是否覆盖
    """
    if allowed_upper is None:
        return True
    if requested_upper is None:
        return False
    comparison = compare_dependency_versions(requested_upper.version, allowed_upper.version)
    if comparison is None:
        return False
    if comparison < 0:
        return True
    if comparison > 0:
        return False
    return allowed_upper.inclusive or not requested_upper.inclusive


def compare_dependency_versions(left: str, right: str) -> int | None:
    """
    比较依赖版本。

    :param left: 左侧版本
    :param right: 右侧版本
    :return: 比较结果
    """
    return PluginVersionComparator.compare(left, right)


def version_satisfies_range(version: str, version_range: str) -> bool:
    """
    判断版本是否满足逗号分隔的版本范围。

    :param version: 版本
    :param version_range: 版本范围
    :return: 是否满足
    """
    constraints = [constraint.strip() for constraint in version_range.split(',') if constraint.strip()]
    if not constraints:
        return True
    for constraint in constraints:
        parsed_dependency = DependencyRequirementParser.parse(f'pkg{constraint}')
        if not PluginVersionConstraintMatcher.is_satisfied(
            version,
            parsed_dependency.operator,
            parsed_dependency.version,
        ):
            return False
    return True


def normalize_sri_digest(digest: str) -> str:
    """
    归一化 SRI base64 摘要。

    :param digest: 摘要
    :return: 去除填充后的摘要
    """
    return digest.strip().rstrip('=')


def append_unique(items: list[str], item: str) -> None:
    """
    追加唯一字符串。

    :param items: 字符串列表
    :param item: 待追加字符串
    :return: None
    """
    if item not in items:
        items.append(item)


def list_unique(items: list[str]) -> list[str]:
    """
    保持顺序去重。

    :param items: 字符串列表
    :return: 去重结果
    """
    result: list[str] = []
    for item in items:
        append_unique(result, item)
    return result


__all__ = [
    'DependencyAllowlist',
    'DependencyArtifactStore',
    'DependencyInstallPolicyConfig',
    'DependencyInstallPolicyDecision',
    'DependencyInstallPolicyEvaluator',
    'DependencyInstallPolicyItemDecision',
    'DependencyInstallPolicyMode',
    'DependencyLockEntry',
    'DependencyLockfile',
]
