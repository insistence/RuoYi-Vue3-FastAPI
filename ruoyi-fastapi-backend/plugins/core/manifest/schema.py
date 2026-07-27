import re
from collections import Counter
from typing import Any, Literal

from packaging.requirements import InvalidRequirement
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from plugins.core.manifest.menu_tree import PluginMenuTree
from plugins.core.types import PluginConfigValue
from plugins.core.utils import PLUGIN_ID_PATTERN_TEXT, validate_plugin_id_value
from plugins.core.validation.python_requirements import PythonRequirementParser

RESERVED_PLUGIN_IDS = {'admin', 'system', 'monitor', 'tool'}
PERMISSION_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*(?::[a-z][a-z0-9_-]*)+$')
HOOK_PATTERN = re.compile(r'^[A-Za-z_][\w.]*:[A-Za-z_]\w*$')
CONFIG_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_.-]{0,127}$')
JOB_ID_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
JOB_CALLABLE_PATTERN = re.compile(r'^[A-Za-z_][\w.]*\.[A-Za-z_]\w*$')
PLUGIN_DEPENDENCY_PATTERN = re.compile(
    rf'^\s*({PLUGIN_ID_PATTERN_TEXT})\s*([<>=!~^]{{1,2}})?\s*([A-Za-z0-9_.+\-!*]+)?\s*$'
)
VERSION_CONSTRAINT_PATTERN = re.compile(r'^([<>=!~^]{1,2})?[A-Za-z0-9_.+\-!*]+$')
ROUTE_PATH_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$')
EXTERNAL_URL_PATTERN = re.compile(r'^https?://\S+$')
FRONTEND_RELATIVE_PATH_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$')
PLUGIN_COMPONENT_SEGMENT_PATTERN = re.compile(r'^[a-z][a-z0-9_-]*$')
RESOURCE_RELATIVE_PATH_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)*$')
CORE_FRONTEND_COMPONENTS = {'Layout', 'ParentView', 'InnerLink'}
MIN_PLUGIN_COMPONENT_PARTS = 3
SUPPORTED_MANIFEST_VERSION = 1


class PluginManifestError(ValueError):
    """
    插件清单校验异常。
    """


class RouterManifest(BaseModel):
    """
    插件路由声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    auto_scan: bool = Field(default=True, alias='autoScan', description='是否自动扫描插件控制器')


class HealthManifest(BaseModel):
    """
    插件健康检查声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    checker: str | None = Field(default=None, description='插件健康检查 callable，格式为 <module_path>:<callable_name>')

    @field_validator('checker')
    @classmethod
    def validate_checker(cls, value: str | None) -> str | None:
        """
        校验健康检查 callable 声明。

        :param value: 健康检查 callable 声明
        :return: 校验后的健康检查 callable 声明
        """
        if value is None or HOOK_PATTERN.match(value):
            return value
        raise ValueError('健康检查 checker 必须使用 <module_path>:<callable_name> 格式')


class HookManifest(BaseModel):
    """
    插件生命周期钩子声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    on_install: str | None = Field(default=None, alias='onInstall', description='插件安装钩子')
    on_upgrade: str | None = Field(default=None, alias='onUpgrade', description='插件升级钩子')
    on_startup: str | None = Field(default=None, alias='onStartup', description='插件启动钩子')
    on_shutdown: str | None = Field(default=None, alias='onShutdown', description='插件关闭钩子')
    on_purge: str | None = Field(default=None, alias='onPurge', description='插件物理清理钩子')

    @field_validator('on_install', 'on_upgrade', 'on_startup', 'on_shutdown', 'on_purge')
    @classmethod
    def validate_hook(cls, value: str | None) -> str | None:
        """
        校验生命周期钩子声明。

        :param value: 钩子声明字符串
        :return: 校验后的钩子声明字符串
        """
        if value is None or HOOK_PATTERN.match(value):
            return value
        raise ValueError('生命周期钩子必须使用 <module_path>:<callable_name> 格式')


class PluginJobManifest(BaseModel):
    """
    插件定时任务声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    id: str = Field(description='插件内定时任务唯一标识')
    name: str | None = Field(default=None, description='定时任务展示名称')
    callable: str = Field(description='定时任务调用目标，格式为 Python 模块路径加函数名')
    trigger: Literal['cron'] = Field(default='cron', description='定时任务触发器类型')
    cron_expression: str = Field(alias='cronExpression', description='cron 执行表达式')
    args: list[str] = Field(default_factory=list, description='位置参数列表')
    kwargs: dict[str, Any] = Field(default_factory=dict, description='关键字参数字典')
    enabled: bool = Field(default=True, description='是否默认启用任务')
    description: str = Field(default='', description='任务说明')
    misfire_policy: Literal['1', '2', '3'] = Field(
        default='3',
        alias='misfirePolicy',
        description='计划执行错误策略（1立即执行 2执行一次 3放弃执行）',
    )
    concurrent: Literal['0', '1'] = Field(default='1', description='是否并发执行（0允许 1禁止）')
    executor: Literal['default', 'processpool'] = Field(default='default', description='任务执行器')

    @field_validator('id')
    @classmethod
    def validate_job_id(cls, value: str) -> str:
        """
        校验插件任务 ID。

        :param value: 插件任务 ID
        :return: 校验后的插件任务 ID
        """
        if not JOB_ID_PATTERN.match(value):
            raise ValueError('插件任务 id 只能包含小写字母、数字、下划线和中划线，并且必须以小写字母开头')
        return value

    @field_validator('callable')
    @classmethod
    def validate_callable(cls, value: str) -> str:
        """
        校验插件任务调用目标格式。

        :param value: 任务调用目标
        :return: 校验后的任务调用目标
        """
        if not JOB_CALLABLE_PATTERN.match(value):
            raise ValueError('插件任务 callable 必须使用 <module_path>.<callable_name> 格式')
        return value

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """
        校验插件任务展示名称。

        :param value: 任务展示名称
        :return: 校验后的任务展示名称
        """
        if value is not None and not value.strip():
            raise ValueError('插件任务 name 不能为空白字符串')
        return value

    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression_text(cls, value: str) -> str:
        """
        校验插件任务 cron 表达式文本。

        :param value: cron 表达式
        :return: 校验后的 cron 表达式
        """
        if not value.strip():
            raise ValueError('插件任务 cronExpression 不能为空')
        return value

    @model_validator(mode='after')
    def fill_name(self) -> 'PluginJobManifest':
        """
        填充任务展示名称默认值。

        :return: 填充后的任务声明
        """
        if self.name is None:
            self.name = self.id
        return self


class BackendManifest(BaseModel):
    """
    插件后端声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    module: str = Field(description='插件后端 Python 模块路径')
    routers: RouterManifest = Field(default_factory=RouterManifest, description='插件路由声明')
    health: HealthManifest = Field(default_factory=HealthManifest, description='插件健康检查声明')
    migrations: list[str] = Field(default_factory=list, description='数据库迁移脚本列表')
    seeds: list[str] = Field(default_factory=list, description='初始化数据脚本列表')
    hooks: HookManifest = Field(default_factory=HookManifest, description='生命周期钩子声明')
    jobs: list[PluginJobManifest] = Field(default_factory=list, description='插件定时任务声明列表')

    @field_validator('module')
    @classmethod
    def validate_module(cls, value: str) -> str:
        """
        校验插件后端模块路径。

        :param value: 后端模块路径
        :return: 校验后的后端模块路径
        """
        if not value.strip():
            raise ValueError('backend.module 不能为空')
        return value

    @model_validator(mode='after')
    def validate_unique_jobs(self) -> 'BackendManifest':
        """
        校验插件定时任务 ID 唯一性。

        :return: 校验后的后端声明
        """
        job_id_counts = Counter(job.id for job in self.jobs)
        duplicated_job_ids = {job_id for job_id, count in job_id_counts.items() if count > 1}
        if duplicated_job_ids:
            raise ValueError(f'插件任务 id 不能重复：{"、".join(sorted(duplicated_job_ids))}')
        return self


class PluginDependencyManifest(BaseModel):
    """
    插件间依赖声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    id: str = Field(description='依赖插件ID')
    version: str | None = Field(default=None, description='依赖插件版本约束，例如 >=1.0.0')
    description: str = Field(default='', description='依赖说明')

    @model_validator(mode='before')
    @classmethod
    def normalize_dependency(cls, value: Any) -> dict[str, Any]:
        """
        兼容字符串和对象两种插件依赖声明。

        :param value: 原始插件依赖声明
        :return: 规范化后的插件依赖声明
        """
        if isinstance(value, str):
            matched_dependency = PLUGIN_DEPENDENCY_PATTERN.match(value)
            if not matched_dependency:
                raise ValueError('插件依赖字符串必须使用 <plugin_id><version_constraint> 格式')
            plugin_id, operator, version = matched_dependency.groups()
            return {'id': plugin_id, 'version': f'{operator}{version}' if operator and version else None}
        if isinstance(value, dict):
            return value
        raise ValueError('插件依赖必须是字符串或对象')

    @field_validator('id')
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        """
        校验依赖插件 ID。

        :param value: 依赖插件 ID
        :return: 校验后的依赖插件 ID
        """
        return validate_plugin_id_value(value, field_name='依赖插件 id')

    @field_validator('version')
    @classmethod
    def validate_version_constraint(cls, value: str | None) -> str | None:
        """
        校验插件版本约束。

        :param value: 版本约束
        :return: 校验后的版本约束
        """
        if value is None:
            return value
        if not VERSION_CONSTRAINT_PATTERN.match(value):
            raise ValueError('依赖插件 version 必须是版本号或带操作符的版本约束')
        return value


class DependencyManifest(BaseModel):
    """
    插件依赖声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    python: list[str] = Field(default_factory=list, description='Python 依赖声明')
    npm: list[str] = Field(default_factory=list, description='前端 npm 依赖声明')
    npm_dev: list[str] = Field(default_factory=list, alias='npmDev', description='前端 npm 开发依赖声明')
    plugins: list[PluginDependencyManifest] = Field(default_factory=list, description='插件间依赖声明')

    @field_validator('python')
    @classmethod
    def validate_python_requirements(cls, value: list[str]) -> list[str]:
        """
        校验 Python 依赖符合 PEP 508。

        :param value: Python 依赖声明列表
        :return: 校验后的 Python 依赖声明列表
        """
        for requirement in value:
            cls._validate_python_requirement(requirement)
        return value

    @staticmethod
    def _validate_python_requirement(requirement: str) -> None:
        """
        校验单条 Python 依赖声明。

        :param requirement: Python 依赖声明
        :return: None
        """
        try:
            PythonRequirementParser.parse(requirement)
        except InvalidRequirement as exc:
            raise ValueError(f'Python 依赖声明无效：{requirement}') from exc

    @model_validator(mode='after')
    def validate_unique_plugins(self) -> 'DependencyManifest':
        """
        校验依赖插件 ID 唯一性。

        :return: 校验后的依赖声明
        """
        plugin_id_counts = Counter(plugin.id for plugin in self.plugins)
        duplicated_plugin_ids = {plugin_id for plugin_id, count in plugin_id_counts.items() if count > 1}
        if duplicated_plugin_ids:
            raise ValueError(f'依赖插件 id 不能重复：{"、".join(sorted(duplicated_plugin_ids))}')
        return self


class PluginMetadataManifest(BaseModel):
    """
    插件展示元数据声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    category: str = Field(default='', description='插件分类')
    tags: list[str] = Field(default_factory=list, description='插件标签')
    author: str = Field(default='', description='插件作者')
    license: str = Field(default='', description='插件许可证')
    homepage: str = Field(default='', description='插件主页')
    repository: str = Field(default='', description='插件代码仓库')
    documentation: str = Field(default='', description='插件文档地址')

    @field_validator('category', 'author', 'license')
    @classmethod
    def strip_text(cls, value: str) -> str:
        """
        清理展示元数据文本。

        :param value: 原始文本
        :return: 清理后的文本
        """
        return value.strip()

    @field_validator('homepage', 'repository', 'documentation')
    @classmethod
    def validate_url(cls, value: str, info: ValidationInfo) -> str:
        """
        校验展示元数据地址。

        :param value: 原始地址
        :param info: 字段信息
        :return: 校验后的地址
        """
        value = value.strip()
        if value and not EXTERNAL_URL_PATTERN.match(value):
            raise ValueError(f'metadata.{info.field_name} 必须是 http/https 地址')
        return value

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        """
        清理并校验插件标签。

        :param value: 原始标签列表
        :return: 清理后的标签列表
        """
        tags = [tag.strip() for tag in value if tag.strip()]
        tag_counts = Counter(tags)
        duplicated_tags = {tag for tag, count in tag_counts.items() if count > 1}
        if duplicated_tags:
            raise ValueError(f'插件 metadata.tags 不能重复：{"、".join(sorted(duplicated_tags))}')
        return tags


class CompatibilityManifest(BaseModel):
    """
    插件平台兼容性声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    backend_version: str | None = Field(default=None, alias='backendVersion', description='后端版本约束')
    frontend_version: str | None = Field(default=None, alias='frontendVersion', description='前端版本约束')
    python_version: str | None = Field(default=None, alias='pythonVersion', description='Python 版本约束')
    node_version: str | None = Field(default=None, alias='nodeVersion', description='Node.js 版本约束')
    databases: list[Literal['mysql', 'postgresql']] = Field(default_factory=list, description='支持的数据库类型')

    @field_validator('backend_version', 'frontend_version', 'python_version', 'node_version')
    @classmethod
    def validate_version_constraint(cls, value: str | None) -> str | None:
        """
        校验平台兼容性版本约束。

        :param value: 版本约束
        :return: 校验后的版本约束
        """
        if value is None:
            return value
        if not VERSION_CONSTRAINT_PATTERN.match(value):
            raise ValueError('compatibility 版本约束必须是版本号或带操作符的版本约束')
        return value

    @field_validator('databases')
    @classmethod
    def validate_unique_databases(
        cls, value: list[Literal['mysql', 'postgresql']]
    ) -> list[Literal['mysql', 'postgresql']]:
        """
        校验数据库类型声明不重复。

        :param value: 数据库类型列表
        :return: 校验后的数据库类型列表
        """
        database_counts = Counter(value)
        duplicated_databases = {database for database, count in database_counts.items() if count > 1}
        if duplicated_databases:
            raise ValueError(f'compatibility.databases 不能重复：{"、".join(sorted(duplicated_databases))}')
        return value


class PluginResourceManifest(BaseModel):
    """
    插件资源声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    static: list[str] = Field(default_factory=list, description='插件静态资源相对路径列表')
    uploads: list[str] = Field(default_factory=list, description='插件上传资源相对路径列表')
    temp: list[str] = Field(default_factory=list, description='插件临时资源相对路径列表')

    @field_validator('static', 'uploads', 'temp')
    @classmethod
    def validate_resource_paths(cls, value: list[str]) -> list[str]:
        """
        校验资源相对路径列表。

        :param value: 资源相对路径列表
        :return: 校验后的资源相对路径列表
        """
        path_counts = Counter(value)
        duplicated_paths = {path for path, count in path_counts.items() if count > 1}
        if duplicated_paths:
            raise ValueError(f'插件资源路径不能重复：{"、".join(sorted(duplicated_paths))}')
        invalid_paths = [path for path in value if not RESOURCE_RELATIVE_PATH_PATTERN.match(path)]
        if invalid_paths:
            raise ValueError(f'插件资源路径必须是安全相对路径：{"、".join(sorted(invalid_paths))}')
        return value


class PluginPermissionManifest(BaseModel):
    """
    插件权限声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    code: str = Field(validation_alias=AliasChoices('code', 'perms', 'permission'), description='权限标识')
    name: str | None = Field(default=None, description='权限展示名称')
    description: str = Field(default='', description='权限说明')

    @model_validator(mode='before')
    @classmethod
    def normalize_string_permission(cls, value: Any) -> Any:
        """
        兼容 permissions 字符串简写。

        :param value: 原始权限声明
        :return: 权限对象声明
        """
        if isinstance(value, str):
            return {'code': value}
        return value

    @field_validator('code')
    @classmethod
    def validate_code(cls, value: str) -> str:
        """
        校验权限标识。

        :param value: 权限标识
        :return: 校验后的权限标识
        """
        if not PERMISSION_PATTERN.match(value):
            raise ValueError(f'插件权限格式无效：{value}')
        return value

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """
        校验权限展示名称。

        :param value: 权限展示名称
        :return: 校验后的权限展示名称
        """
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError('插件权限 name 不能为空白字符串')
        return value

    @field_validator('description')
    @classmethod
    def validate_description(cls, value: str) -> str:
        """
        清理权限说明。

        :param value: 权限说明
        :return: 清理后的权限说明
        """
        return value.strip()


class PluginConfigOptionManifest(BaseModel):
    """
    插件配置选项声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    label: str = Field(description='配置选项展示名称')
    value: PluginConfigValue = Field(description='配置选项值')


class PluginConfigItemManifest(BaseModel):
    """
    插件配置项声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    key: str = Field(description='配置键名')
    label: str | None = Field(default=None, description='配置展示名称')
    type: Literal['string', 'number', 'boolean', 'select', 'textarea', 'password', 'json'] = Field(
        default='string',
        description='配置值类型',
    )
    default: PluginConfigValue = Field(default=None, description='默认配置值')
    required: bool = Field(default=False, description='是否必填')
    group: str = Field(default='default', description='配置分组')
    order: int = Field(default=0, description='配置排序值')
    placeholder: str = Field(default='', description='配置输入占位提示')
    min_value: float | None = Field(default=None, alias='min', description='数字配置最小值')
    max_value: float | None = Field(default=None, alias='max', description='数字配置最大值')
    pattern: str | None = Field(default=None, description='字符串配置正则表达式')
    description: str = Field(default='', description='配置说明')
    options: list[PluginConfigOptionManifest] = Field(default_factory=list, description='配置选项列表')
    secret: bool = Field(default=False, description='是否敏感配置')

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, value: str | None) -> str:
        """
        规范化配置项类型。

        :param value: 原始配置项类型
        :return: 规范化后的配置项类型
        """
        if value is None:
            return 'string'
        type_aliases = {
            'text': 'string',
            'switch': 'boolean',
        }

        return type_aliases.get(str(value), str(value))

    @field_validator('key')
    @classmethod
    def validate_key(cls, value: str) -> str:
        """
        校验配置键名。

        :param value: 配置键名
        :return: 校验后的配置键名
        """
        if not CONFIG_KEY_PATTERN.match(value):
            raise ValueError('配置 key 只能包含小写字母、数字、下划线、中划线和点号，并且必须以小写字母开头')
        return value

    @model_validator(mode='after')
    def fill_label(self) -> 'PluginConfigItemManifest':
        """
        填充配置展示名称默认值。

        :return: 填充后的配置项声明
        """
        if self.label is None:
            self.label = self.key
        return self

    @model_validator(mode='after')
    def validate_options_and_default(self) -> 'PluginConfigItemManifest':
        """
        校验配置选项、默认值和增强约束。

        :return: 校验后的配置项声明
        """
        self._validate_select_options()
        self._validate_default_value()
        self._validate_number_range()
        self._validate_pattern()
        return self

    @field_validator('group', 'placeholder')
    @classmethod
    def validate_optional_text(cls, value: str) -> str:
        """
        校验配置增强文本字段。

        :param value: 配置增强文本字段
        :return: 校验后的配置增强文本字段
        """
        return value.strip()

    def _validate_select_options(self) -> None:
        """
        校验 select 配置选项。

        :return: None
        """
        if self.type != 'select':
            return
        if not self.options:
            raise ValueError(f'配置 {self.key} 类型为 select 时必须声明 options')
        option_values = [option.value for option in self.options]
        option_value_counts = Counter(option_values)
        duplicated_values = {value for value, count in option_value_counts.items() if count > 1}
        if duplicated_values:
            raise ValueError(f'配置 {self.key} 的 options.value 不能重复')
        if self.default is not None and self.default not in option_values:
            raise ValueError(f'配置 {self.key} 的 default 必须位于 options.value 中')

    def _validate_default_value(self) -> None:
        """
        校验配置默认值类型。

        :return: None
        """
        if self.default is None:
            return
        if self.type == 'boolean' and not isinstance(self.default, bool):
            raise ValueError(f'配置 {self.key} 的 default 必须是布尔值')
        if self.type == 'number' and (not isinstance(self.default, int | float) or isinstance(self.default, bool)):
            raise ValueError(f'配置 {self.key} 的 default 必须是数字')
        if self.type == 'json' and not isinstance(self.default, dict | list):
            raise ValueError(f'配置 {self.key} 的 default 必须是对象或数组')

    def _validate_number_range(self) -> None:
        """
        校验数字配置范围。

        :return: None
        """
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f'配置 {self.key} 的 min 不能大于 max')
        if self.default is None or self.type != 'number':
            return
        if self.min_value is not None and self.default < self.min_value:
            raise ValueError(f'配置 {self.key} 的 default 不能小于 min')
        if self.max_value is not None and self.default > self.max_value:
            raise ValueError(f'配置 {self.key} 的 default 不能大于 max')

    def _validate_pattern(self) -> None:
        """
        校验字符串配置正则表达式。

        :return: None
        """
        if not self.pattern:
            return
        try:
            pattern = re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f'配置 {self.key} 的 pattern 不是合法正则表达式：{exc}') from exc
        if (
            self.default is not None
            and self.type in {'string', 'textarea', 'password'}
            and not pattern.fullmatch(str(self.default))
        ):
            raise ValueError(f'配置 {self.key} 的 default 不匹配 pattern')


class PluginConfigManifest(BaseModel):
    """
    插件配置声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    items: list[PluginConfigItemManifest] = Field(default_factory=list, description='插件配置项列表')

    @model_validator(mode='before')
    @classmethod
    def normalize_config(cls, value: Any) -> dict[str, Any]:
        """
        兼容多种插件配置声明写法。

        :param value: 原始配置声明
        :return: 规范化后的配置声明
        """
        if value is None:
            return {'items': []}
        if isinstance(value, list):
            return {'items': value}
        if isinstance(value, dict) and 'items' in value:
            return value
        if isinstance(value, dict):
            items = []
            for key, item in value.items():
                if isinstance(item, dict):
                    items.append({'key': key, **item})
                else:
                    items.append({'key': key, 'default': item})
            return {'items': items}
        raise ValueError('插件 config 必须是对象或配置项列表')

    @model_validator(mode='after')
    def validate_unique_keys(self) -> 'PluginConfigManifest':
        """
        校验配置键名唯一性。

        :return: 校验后的配置声明
        """
        key_counts = Counter(item.key for item in self.items)
        duplicated_keys = {key for key, count in key_counts.items() if count > 1}
        if duplicated_keys:
            raise ValueError(f'插件配置 key 不能重复：{"、".join(sorted(duplicated_keys))}')
        return self


class PluginMenuManifest(BaseModel):
    """
    插件菜单声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    name: str = Field(description='菜单名称')
    path: str = Field(description='路由路径')
    component: str = Field(default='Layout', description='组件路径')
    perms: str = Field(default='', description='权限标识')
    icon: str = Field(default='#', description='菜单图标')
    type: Literal['M', 'C', 'F'] = Field(default='C', description='菜单类型')
    order_num: int = Field(default=0, alias='orderNum', description='显示顺序')
    query: str | None = Field(default=None, description='路由参数')
    route_name: str | None = Field(default=None, alias='routeName', description='路由名称')
    is_frame: Literal[0, 1] = Field(default=1, alias='isFrame', description='是否为外链（0是 1否）')
    is_cache: Literal[0, 1] = Field(default=0, alias='isCache', description='是否缓存（0缓存 1不缓存）')
    visible: Literal['0', '1'] = Field(default='0', description='是否显示')
    status: Literal['0', '1'] = Field(default='0', description='菜单状态')
    children: list['PluginMenuManifest'] = Field(default_factory=list, description='子菜单列表')

    @field_validator('name', 'path')
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """
        校验菜单必填文本。

        :param value: 菜单文本
        :return: 校验后的菜单文本
        """
        if not value.strip():
            raise ValueError('菜单 name 和 path 不能为空')
        return value

    @field_validator('query', 'route_name')
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        """
        校验菜单可选文本。

        :param value: 菜单可选文本
        :return: 校验后的菜单可选文本
        """
        if value is None:
            return value
        return value.strip()

    @field_validator('perms')
    @classmethod
    def validate_perms(cls, value: str) -> str:
        """
        校验菜单权限标识。

        :param value: 菜单权限标识
        :return: 校验后的菜单权限标识
        """
        if not value:
            return value
        if not PERMISSION_PATTERN.match(value):
            raise ValueError('菜单 perms 必须使用小写冒号分隔格式，例如 demo:list')
        return value

    @field_validator('path')
    @classmethod
    def validate_path(cls, value: str) -> str:
        """
        校验菜单路径格式。

        :param value: 菜单路径
        :return: 校验后的菜单路径
        """
        if not ROUTE_PATH_PATTERN.match(value) and not EXTERNAL_URL_PATTERN.match(value):
            raise ValueError('菜单 path 必须是插件路由路径或 http/https 外链地址')
        return value

    @model_validator(mode='after')
    def validate_component_for_menu_type(self) -> 'PluginMenuManifest':
        """
        校验菜单组件和菜单类型的基础关系。

        :return: 校验后的菜单声明
        """
        if self.type != 'F' and not self.component.strip():
            raise ValueError('非按钮菜单 component 不能为空')
        if self.is_frame == 0 and not EXTERNAL_URL_PATTERN.match(self.path):
            raise ValueError('外链菜单 path 必须是 http/https 地址')
        if self.is_frame == 1 and EXTERNAL_URL_PATTERN.match(self.path):
            raise ValueError('非外链菜单 path 不能是 http/https 地址')
        return self


class FrontendDeliveryManifest(BaseModel):
    """
    插件前端交付声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    type: Literal['none', 'source'] = Field(default='none', description='前端交付类型')
    build_required: bool = Field(default=False, alias='buildRequired', description='前端资源是否需要构建后生效')


class FrontendManifest(BaseModel):
    """
    插件前端声明。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    plugin_id: str | None = Field(default=None, alias='pluginId', description='前端插件目录名')
    base_path: str | None = Field(default=None, alias='basePath', description='前端基础路径')
    views_path: str = Field(default='views', alias='viewsPath', description='前端视图目录')
    api_path: str = Field(default='api', alias='apiPath', description='前端 API 目录')
    delivery: FrontendDeliveryManifest = Field(default_factory=FrontendDeliveryManifest, description='前端交付声明')
    menus: list[PluginMenuManifest] = Field(default_factory=list, description='菜单声明列表')

    @field_validator('plugin_id')
    @classmethod
    def validate_plugin_id(cls, value: str | None) -> str | None:
        """
        校验前端插件目录名格式。

        :param value: 前端插件目录名
        :return: 校验后的前端插件目录名
        """
        return validate_plugin_id_value(value, field_name='frontend.pluginId') if value is not None else value

    @field_validator('base_path')
    @classmethod
    def validate_base_path(cls, value: str | None) -> str | None:
        """
        校验前端基础路径格式。

        :param value: 前端基础路径
        :return: 校验后的前端基础路径
        """
        if value is not None and not FRONTEND_RELATIVE_PATH_PATTERN.match(value):
            raise ValueError('frontend.basePath 只能包含小写字母、数字、下划线、中划线和正斜杠')
        return value

    @field_validator('views_path', 'api_path')
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        """
        校验前端相对目录路径格式。

        :param value: 前端相对目录路径
        :return: 校验后的前端相对目录路径
        """
        if not FRONTEND_RELATIVE_PATH_PATTERN.match(value):
            raise ValueError('frontend viewsPath/apiPath 只能包含小写字母、数字、下划线、中划线和正斜杠')
        return value


class PluginManifest(BaseModel):
    """
    插件主清单。
    """

    model_config = ConfigDict(populate_by_name=True, extra='forbid')

    manifest_version: Literal[1] = Field(
        default=SUPPORTED_MANIFEST_VERSION,
        alias='manifestVersion',
        description='插件清单版本',
    )
    id: str = Field(description='插件唯一标识')
    name: str = Field(description='插件名称')
    version: str = Field(description='插件版本')
    description: str = Field(default='', description='插件说明')
    metadata: PluginMetadataManifest = Field(default_factory=PluginMetadataManifest, description='插件展示元数据')
    backend: BackendManifest = Field(description='后端声明')
    frontend: FrontendManifest = Field(default_factory=FrontendManifest, description='前端声明')
    permissions: list[PluginPermissionManifest] = Field(default_factory=list, description='权限声明列表')
    dependencies: DependencyManifest = Field(default_factory=DependencyManifest, description='依赖声明')
    compatibility: CompatibilityManifest = Field(default_factory=CompatibilityManifest, description='平台兼容性声明')
    resources: PluginResourceManifest = Field(default_factory=PluginResourceManifest, description='插件资源声明')
    config: PluginConfigManifest = Field(default_factory=PluginConfigManifest, description='插件配置声明')

    @field_validator('id')
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        """
        校验插件 ID。

        :param value: 插件 ID
        :return: 校验后的插件 ID
        """
        validate_plugin_id_value(value, field_name='插件 id')
        if value in RESERVED_PLUGIN_IDS:
            raise ValueError(f'插件 id 不能使用保留名称：{value}')
        return value

    @field_validator('name', 'version')
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """
        校验插件必填文本。

        :param value: 插件文本
        :return: 校验后的插件文本
        """
        if not value.strip():
            raise ValueError('插件 name 和 version 不能为空')
        return value

    @field_validator('permissions')
    @classmethod
    def validate_permissions(cls, value: list[PluginPermissionManifest]) -> list[PluginPermissionManifest]:
        """
        校验插件权限声明。

        :param value: 权限声明列表
        :return: 校验后的权限声明列表
        """
        permission_code_counts = Counter(permission.code for permission in value)
        duplicated_permissions = {permission for permission, count in permission_code_counts.items() if count > 1}
        if duplicated_permissions:
            raise ValueError(f'插件权限不能重复：{"、".join(sorted(duplicated_permissions))}')
        return value

    @property
    def permission_codes(self) -> list[str]:
        """
        获取权限标识列表。

        :return: 权限标识列表
        """
        return [permission.code for permission in self.permissions]

    @property
    def permission_name_map(self) -> dict[str, str]:
        """
        获取权限展示名称映射。

        :return: 权限标识到展示名称的映射
        """
        return {permission.code: permission.name for permission in self.permissions if permission.name}

    @model_validator(mode='after')
    def fill_frontend_defaults(self) -> 'PluginManifest':
        """
        填充前端声明默认值并执行跨字段校验。

        :return: 填充默认值并完成校验后的插件清单
        """
        if self.frontend.plugin_id is None:
            self.frontend.plugin_id = self.id
        if self.frontend.base_path is None:
            self.frontend.base_path = self.id
        self._fill_frontend_delivery_defaults()
        self._validate_backend_module()
        self._validate_frontend_plugin_id()
        self._validate_plugin_dependencies()
        self._validate_permission_prefixes()
        self._validate_menu_permissions_declared()
        self._validate_menu_components()
        self._validate_unique_menu_paths()
        self._validate_job_callable_prefixes()
        return self

    def _validate_backend_module(self) -> None:
        """
        校验后端模块路径与插件 ID 一致。

        :return: None
        """
        expected_module = f'plugins.{self.id}'
        if self.backend.module != expected_module:
            raise ValueError(f'backend.module 必须为 {expected_module}')

    def _validate_frontend_plugin_id(self) -> None:
        """
        校验前端插件目录名与插件 ID 一致。

        :return: None
        """
        if self.frontend.plugin_id != self.id:
            raise ValueError(f'frontend.pluginId 必须与插件 id 一致：{self.id}')

    def _validate_permission_prefixes(self) -> None:
        """
        校验插件权限标识必须使用插件 ID 前缀。

        :return: None
        """
        expected_prefix = f'{self.id}:'
        permission_set = set(self.permission_codes) | PluginMenuTree.collect_permissions(self.frontend.menus)
        invalid_permissions = sorted(
            permission for permission in permission_set if not permission.startswith(expected_prefix)
        )
        if invalid_permissions:
            raise ValueError(f'插件权限必须使用 {expected_prefix} 前缀：{"、".join(invalid_permissions)}')

    def _fill_frontend_delivery_defaults(self) -> None:
        """
        根据前端声明和 npm 依赖补全前端交付默认值。

        :return: None
        """
        has_frontend_resources = bool(self.frontend.menus or self.dependencies.npm or self.dependencies.npm_dev)
        if has_frontend_resources and self.frontend.delivery.type == 'none':
            self.frontend.delivery.type = 'source'
        if self.frontend.delivery.type == 'source':
            self.frontend.delivery.build_required = True

    def _validate_plugin_dependencies(self) -> None:
        """
        校验插件间依赖声明。

        :return: None
        """
        if any(plugin.id == self.id for plugin in self.dependencies.plugins):
            raise ValueError('插件不能依赖自身')

    def _validate_menu_permissions_declared(self) -> None:
        """
        校验菜单权限已在顶层 permissions 中声明。

        :return: None
        """
        menu_permissions = PluginMenuTree.collect_permissions(self.frontend.menus)
        undeclared_permissions = sorted(menu_permissions - set(self.permission_codes))
        if undeclared_permissions:
            raise ValueError(f'菜单权限必须在 permissions 中声明：{"、".join(undeclared_permissions)}')

    def _validate_menu_components(self) -> None:
        """
        校验菜单组件路径符合插件前端视图或核心布局组件约定。

        :return: None
        """
        for menu in PluginMenuTree.flatten(self.frontend.menus):
            if menu.type == 'F' and not menu.component:
                continue
            if menu.component in CORE_FRONTEND_COMPONENTS:
                continue
            if not menu.component.startswith('plugin/'):
                raise ValueError(f'菜单 component 只允许核心布局组件或插件视图路径：{menu.component}')
            self._validate_plugin_component(menu.component)

    def _validate_plugin_component(self, component: str) -> None:
        """
        校验插件视图组件路径。

        :param component: 菜单组件路径
        :return: None
        """
        parts = component.split('/')
        if len(parts) < MIN_PLUGIN_COMPONENT_PARTS or parts[0] != 'plugin':
            raise ValueError(f'插件组件路径必须使用 plugin/<plugin_id>/<view_path> 格式：{component}')
        if parts[1] != self.frontend.plugin_id:
            raise ValueError(f'插件组件路径必须引用当前插件目录：{component}')
        invalid_segments = [part for part in parts[2:] if not PLUGIN_COMPONENT_SEGMENT_PATTERN.match(part)]
        if invalid_segments:
            raise ValueError(f'插件组件路径包含非法片段：{component}')

    def _validate_unique_menu_paths(self) -> None:
        """
        校验菜单路由路径在当前插件内不重复。

        :return: None
        """
        route_paths = PluginMenuTree.collect_route_paths(self.frontend.menus)
        route_path_counts = Counter(route_paths)
        duplicated_paths = {route_path for route_path, count in route_path_counts.items() if count > 1}
        if duplicated_paths:
            raise ValueError(f'菜单 path 不能重复：{"、".join(sorted(duplicated_paths))}')

    def _validate_job_callable_prefixes(self) -> None:
        """
        校验插件定时任务 callable 必须归属当前插件模块。

        定时任务由系统调度器直接 importlib 导入执行，不经过 PluginCallableLoader 的模块归属
        校验，因此必须在清单校验阶段限制 callable 模块前缀，防止插件执行任意模块的函数。

        :return: None
        """
        expected_prefix = f'plugins.{self.id}.'
        invalid_callables = [job.callable for job in self.backend.jobs if not job.callable.startswith(expected_prefix)]
        if invalid_callables:
            raise ValueError(f'插件任务 callable 必须使用 {expected_prefix} 前缀：{"、".join(invalid_callables)}')


PluginMenuManifest.model_rebuild()


class PluginManifestFactory:
    """
    插件清单工厂。

    使用工厂模式集中处理从原始字典到 `PluginManifest` 的构造，避免发现器直接依赖
    Pydantic 的创建细节。
    """

    @classmethod
    def create(cls, raw_manifest: dict[str, Any]) -> PluginManifest:
        """
        从原始字典创建插件清单。

        :param raw_manifest: YAML 解析得到的原始清单字典
        :return: 插件清单模型
        """
        return PluginManifest.model_validate(raw_manifest)
