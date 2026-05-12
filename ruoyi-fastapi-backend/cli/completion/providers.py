import asyncio
import os
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

import click

from cli.metadata import (
    COMPLETION_SHELL_SPEC_REGISTRY,
    ENVIRONMENT_OPTION_SERVICE,
    CompletionShellSpecRegistry,
    EnvironmentOptionService,
)

DEFAULT_ALEMBIC_REVISION_CHOICES = ('head', 'base', 'current', '-1')
DYNAMIC_COMPLETION_TIMEOUT_SECONDS = 0.8


@dataclass(frozen=True)
class CompletionContextResolver:
    """
    shell completion 上下文解析器。

    该对象负责解析当前补全场景下的环境、缓存名称和项目目录，
    将原本散落的参数与环境变量解析逻辑收口到单一职责对象中。
    """

    def resolve_completion_env(self, ctx: click.Context | None) -> str:
        """
        解析当前 completion 场景使用的环境名称。

        :param ctx: Click 上下文
        :return: 环境名称，默认返回 `dev`
        """
        if ctx is not None:
            env_value = getattr(ctx, 'params', {}).get('env')
            if isinstance(env_value, str) and env_value.strip():
                return env_value.strip()

        comp_words = os.environ.get('COMP_WORDS', '').strip()
        if comp_words:
            tokens = comp_words.split()
            for index, token in enumerate(tokens):
                if token.startswith('--env='):
                    env_value = token.split('=', 1)[1].strip()
                    if env_value:
                        return env_value
                if token == '--env' and index + 1 < len(tokens):
                    env_value = tokens[index + 1].strip()
                    if env_value:
                        return env_value

        return 'dev'

    def resolve_cache_name_for_completion(self, ctx: click.Context | None) -> str:
        """
        解析当前 cache key 补全场景使用的缓存名称。

        :param ctx: Click 上下文
        :return: 缓存名称，缺失时返回空字符串
        """
        if ctx is not None:
            cache_name = getattr(ctx, 'params', {}).get('cache_name')
            if isinstance(cache_name, str) and cache_name.strip():
                return cache_name.strip()

        comp_words = os.environ.get('COMP_WORDS', '').strip()
        if not comp_words:
            return ''

        tokens = comp_words.split()
        try:
            cache_index = tokens.index('cache')
        except ValueError:
            return ''

        if cache_index + 2 >= len(tokens):
            return ''

        subcommand = tokens[cache_index + 1]
        if subcommand not in {'get', 'ttl'}:
            return ''

        cache_name = tokens[cache_index + 2].strip()
        if cache_name.startswith('-'):
            return ''
        return cache_name

    @staticmethod
    def resolve_project_dir() -> Path:
        """
        获取当前 CLI 工作目录对应的项目根目录。

        :return: 当前项目根目录
        """
        return Path.cwd().resolve()

    @staticmethod
    def normalize_completion_prefix(incomplete: str) -> str:
        """
        规范化补全输入前缀。

        :param incomplete: 原始未完成输入
        :return: 规范化后的前缀文本
        """
        return incomplete.strip()

    @staticmethod
    def to_display_path(path: Path, *, project_dir: Path) -> str:
        """
        将绝对路径转换为适合补全显示的路径文本。

        :param path: 原始路径
        :param project_dir: 项目根目录
        :return: 用于 shell completion 的显示路径
        """
        try:
            relative_path = path.relative_to(project_dir)
            return str(relative_path) or '.'
        except ValueError:
            return str(path)


@dataclass
class DynamicCompletionService:
    """
    动态补全执行服务。

    该服务负责 runtime 模块导入、只读协程执行、标准 payload 提取与
    候选过滤，从而避免各补全函数继续复制相同的模板。

    :param context_resolver: completion 上下文解析器
    :param timeout_seconds: 动态补全超时时间
    """

    context_resolver: CompletionContextResolver = field(default_factory=CompletionContextResolver)
    timeout_seconds: float = DYNAMIC_COMPLETION_TIMEOUT_SECONDS

    @staticmethod
    def _scoped_app_env(env: str) -> Any:
        """
        为动态补全临时注入 `APP_ENV` 环境变量。

        `config.env` 在导入阶段会优先读取 `APP_ENV`，因此补全场景下
        直接切换进程环境变量比改写 `sys.argv` 更稳定，也更符合当前
        后端配置模块的解析约束。

        :param env: 当前补全环境名称
        :return: 环境变量恢复上下文
        """

        class _CompletionEnvScope:
            def __enter__(self) -> None:
                self._original_app_env = os.environ.get('APP_ENV')
                os.environ['APP_ENV'] = env

            def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
                if self._original_app_env is None:
                    os.environ.pop('APP_ENV', None)
                else:
                    os.environ['APP_ENV'] = self._original_app_env

        return _CompletionEnvScope()

    def load_runtime_module(self, module_name: str) -> Any:
        """
        加载动态补全依赖的 runtime 模块。

        :param module_name: runtime 模块名
        :return: 已导入模块
        """
        return import_module(module_name)

    def run_completion_coroutine(self, coroutine: Any, *, env: str) -> Any:
        """
        在补全场景下执行异步只读查询，并临时注入 `APP_ENV`。

        :param coroutine: 待执行协程
        :param env: 当前补全环境名称
        :return: 协程执行结果
        """
        try:
            with self._scoped_app_env(env):
                return asyncio.run(asyncio.wait_for(coroutine, timeout=self.timeout_seconds))
        finally:
            if asyncio.iscoroutine(coroutine):
                coroutine.close()

    @staticmethod
    def extract_completion_items(payload: dict[str, Any], field_name: str) -> list[str]:
        """
        从 CLI 标准结果中提取补全候选字段列表。

        :param payload: CLI 标准结果字典
        :param field_name: 需要提取的字段名
        :return: 去重后的字符串列表
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return []

        items = payload.get('items')
        if not isinstance(items, list):
            page_payload = payload.get('page')
            if isinstance(page_payload, dict):
                items = page_payload.get('rows')
        if not isinstance(items, list):
            return []

        candidates = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        return sorted(set(candidates))

    @staticmethod
    def extract_completion_values(payload: dict[str, Any], field_name: str) -> list[str]:
        """
        从 CLI 标准结果中提取字符串或整数类型的补全候选值。

        :param payload: CLI 标准结果字典
        :param field_name: 需要提取的字段名
        :return: 去重后的字符串列表
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return []

        items = payload.get('items')
        if not isinstance(items, list):
            page_payload = payload.get('page')
            if isinstance(page_payload, dict):
                items = page_payload.get('rows')
        if not isinstance(items, list):
            return []

        candidates = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get(field_name)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
            elif isinstance(value, int):
                candidates.append(str(value))
        return sorted(set(candidates))

    @staticmethod
    def extract_completion_list(payload: dict[str, Any], field_name: str) -> list[str]:
        """
        从 CLI 标准结果中提取直接位于顶层字段的字符串列表。

        该方法用于缓存键名等不走 `items/page.rows` 结构的场景，
        使这类动态补全也能统一复用 runtime 对象加载与协程执行逻辑。

        :param payload: CLI 标准结果字典
        :param field_name: 需要提取的顶层字段名
        :return: 去重后的字符串列表
        """
        if not isinstance(payload, dict) or not payload.get('ok', False):
            return []

        items = payload.get(field_name)
        if not isinstance(items, list):
            return []

        candidates = [item.strip() for item in items if isinstance(item, str) and item.strip()]
        return sorted(set(candidates))

    @staticmethod
    def filter_candidates(candidates: list[str], incomplete: str) -> list[str]:
        """
        按未完成输入前缀过滤候选值。

        :param candidates: 原始候选列表
        :param incomplete: 当前未完成输入
        :return: 过滤后的候选列表
        """
        normalized_incomplete = incomplete.strip().lower()
        return [candidate for candidate in candidates if candidate.lower().startswith(normalized_incomplete)]

    def complete_dynamic_items(
        self,
        ctx: click.Context | None,
        incomplete: str,
        *,
        runtime_module_name: str,
        runtime_object_name: str | None = None,
        runtime_method_name: str,
        runtime_kwargs: dict[str, Any],
        field_name: str,
        allow_int_values: bool = False,
    ) -> list[str]:
        """
        执行通用的动态只读补全查询。

        :param ctx: Click 上下文
        :param incomplete: 当前未完成输入
        :param runtime_module_name: runtime 模块名
        :param runtime_object_name: runtime 对象名，为空时直接使用模块
        :param runtime_method_name: runtime 方法名
        :param runtime_kwargs: runtime 调用参数
        :param field_name: 待提取字段名
        :param allow_int_values: 是否允许整数候选
        :return: 过滤后的候选列表
        """
        env = self.context_resolver.resolve_completion_env(ctx)
        try:
            runtime_module = self.load_runtime_module(runtime_module_name)
            runtime_target = getattr(runtime_module, runtime_object_name) if runtime_object_name else runtime_module
            runtime_method = getattr(runtime_target, runtime_method_name)
            payload = self.run_completion_coroutine(runtime_method(**runtime_kwargs), env=env)
        except Exception:
            return []

        if allow_int_values:
            candidates = self.extract_completion_values(payload, field_name)
        else:
            candidates = self.extract_completion_items(payload, field_name)
        return self.filter_candidates(candidates, incomplete)

    def complete_dynamic_list(
        self,
        ctx: click.Context | None,
        incomplete: str,
        *,
        runtime_module_name: str,
        runtime_object_name: str | None = None,
        runtime_method_name: str,
        runtime_args: tuple[Any, ...] = (),
        runtime_kwargs: dict[str, Any] | None = None,
        field_name: str,
    ) -> list[str]:
        """
        执行返回顶层字符串列表字段的动态只读补全查询。

        :param ctx: Click 上下文
        :param incomplete: 当前未完成输入
        :param runtime_module_name: runtime 模块名
        :param runtime_object_name: runtime 对象名，为空时直接使用模块
        :param runtime_method_name: runtime 方法名
        :param runtime_args: runtime 位置参数
        :param runtime_kwargs: runtime 关键字参数
        :param field_name: 顶层列表字段名
        :return: 过滤后的候选列表
        """
        env = self.context_resolver.resolve_completion_env(ctx)
        try:
            runtime_module = self.load_runtime_module(runtime_module_name)
            runtime_target = getattr(runtime_module, runtime_object_name) if runtime_object_name else runtime_module
            runtime_method = getattr(runtime_target, runtime_method_name)
            payload = self.run_completion_coroutine(
                runtime_method(*runtime_args, **(runtime_kwargs or {})),
                env=env,
            )
        except Exception:
            return []

        candidates = self.extract_completion_list(payload, field_name)
        return self.filter_candidates(candidates, incomplete)


@dataclass
class StaticCompletionProvider:
    """
    静态 completion 提供器。

    该对象负责 shell、环境、缓存名称以及 Alembic revision 等静态或
    本地推导型补全候选。

    :param context_resolver: completion 上下文解析器
    :param dynamic_service: 动态补全执行服务
    :param shell_spec_registry: shell 元数据注册表
    :param environment_option_service: 环境选项服务
    """

    context_resolver: CompletionContextResolver = field(default_factory=CompletionContextResolver)
    dynamic_service: DynamicCompletionService = field(
        default_factory=lambda: DynamicCompletionService(context_resolver=CompletionContextResolver())
    )
    shell_spec_registry: CompletionShellSpecRegistry = field(default_factory=lambda: COMPLETION_SHELL_SPEC_REGISTRY)
    environment_option_service: EnvironmentOptionService = field(default_factory=lambda: ENVIRONMENT_OPTION_SERVICE)

    def list_completion_shells(self) -> list[str]:
        """
        获取已声明的 completion shell 列表。

        :return: shell 名称列表
        """
        return self.shell_spec_registry.list_shell_names()

    def list_static_cache_names(self) -> list[str]:
        """
        读取系统内置缓存名称列表。

        :return: 缓存名称列表
        """
        try:
            redis_init_key_config = self.dynamic_service.load_runtime_module('common.enums').RedisInitKeyConfig
        except Exception:
            return []
        return [key_config.key for key_config in redis_init_key_config if getattr(key_config, 'key', '')]

    def complete_env_values(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 `--env` 选项提供可补全的环境名称。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 匹配的环境名称列表
        """
        del ctx, args
        normalized_incomplete = incomplete.strip().lower()
        return [
            env_name
            for env_name in self.environment_option_service.discover_env_names()
            if env_name.lower().startswith(normalized_incomplete)
        ]

    def complete_shell_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 shell 参数提供静态补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: shell 名称列表
        """
        del ctx, args
        normalized_incomplete = incomplete.strip().lower()
        return [
            shell_name for shell_name in self.list_completion_shells() if shell_name.startswith(normalized_incomplete)
        ]

    def complete_cache_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为缓存名称参数提供静态补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 缓存名称列表
        """
        del ctx, args
        normalized_incomplete = incomplete.strip().lower()
        return [
            cache_name
            for cache_name in sorted(self.list_static_cache_names())
            if cache_name.lower().startswith(normalized_incomplete)
        ]

    def complete_alembic_revisions(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为数据库迁移版本参数提供本地补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 迁移版本候选列表
        """
        del ctx, args
        normalized_incomplete = self.context_resolver.normalize_completion_prefix(incomplete).lower()
        revision_choices = set(DEFAULT_ALEMBIC_REVISION_CHOICES)
        versions_dir = self.context_resolver.resolve_project_dir() / 'alembic' / 'versions'
        if versions_dir.is_dir():
            for revision_file in versions_dir.glob('*.py'):
                revision_stem = revision_file.stem
                revision_id = revision_stem.split('-', 1)[-1].split('_', 1)[0].strip()
                if revision_id:
                    revision_choices.add(revision_id)
        return sorted(choice for choice in revision_choices if choice.lower().startswith(normalized_incomplete))


@dataclass
class PathCompletionProvider:
    """
    路径 completion 提供器。

    该对象负责项目相对 SQL 文件路径和输出路径补全。

    :param context_resolver: completion 上下文解析器
    """

    context_resolver: CompletionContextResolver = field(default_factory=CompletionContextResolver)

    def complete_sql_files(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 SQL 文件参数提供项目内 `.sql` 文件补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: SQL 文件路径列表
        """
        del ctx, args
        normalized_incomplete = self.context_resolver.normalize_completion_prefix(incomplete).lower()
        project_dir = self.context_resolver.resolve_project_dir()
        candidates = []
        for sql_file in project_dir.rglob('*.sql'):
            if '.git' in sql_file.parts or '__pycache__' in sql_file.parts:
                continue
            display_path = self.context_resolver.to_display_path(sql_file, project_dir=project_dir)
            if display_path.lower().startswith(normalized_incomplete):
                candidates.append(display_path)
        return sorted(candidates)

    def complete_output_paths(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为导出文件参数提供目录和 `.zip` 文件补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 目录或 zip 文件路径列表
        """
        del ctx, args
        raw_incomplete = self.context_resolver.normalize_completion_prefix(incomplete)
        project_dir = self.context_resolver.resolve_project_dir()

        expanded_input = Path(raw_incomplete).expanduser()
        input_is_absolute = expanded_input.is_absolute()
        if raw_incomplete.endswith(('/', os.sep)):
            search_dir = expanded_input if input_is_absolute else (project_dir / expanded_input).resolve()
            partial_name = ''
        else:
            search_dir = (
                expanded_input.parent
                if input_is_absolute
                else (
                    project_dir / expanded_input.parent if str(expanded_input.parent) != '.' else project_dir
                ).resolve()
            )
            partial_name = expanded_input.name

        if not search_dir.exists() or not search_dir.is_dir():
            return []

        candidates = []
        for child_path in sorted(search_dir.iterdir()):
            if not child_path.name.startswith(partial_name):
                continue
            if child_path.is_dir():
                display_path = self.context_resolver.to_display_path(child_path, project_dir=project_dir)
                candidates.append(f'{display_path}/')
                continue
            if child_path.suffix.lower() == '.zip':
                candidates.append(self.context_resolver.to_display_path(child_path, project_dir=project_dir))
        return candidates


@dataclass
class DomainDynamicCompletionProvider:
    """
    业务域动态 completion 提供器。

    该对象负责配置、代码生成、缓存、任务等运行时驱动的只读补全。

    :param context_resolver: completion 上下文解析器
    :param dynamic_service: 动态补全执行服务
    """

    context_resolver: CompletionContextResolver = field(default_factory=CompletionContextResolver)
    dynamic_service: DynamicCompletionService = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化动态补全执行服务。

        :return: None
        """
        self.dynamic_service = DynamicCompletionService(context_resolver=self.context_resolver)

    def complete_config_keys(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为参数键名提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 参数键名列表
        """
        del args
        return self.dynamic_service.complete_dynamic_items(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.config',
            runtime_object_name='CONFIG_RUNTIME',
            runtime_method_name='list_configs',
            runtime_kwargs={'config_key': incomplete, 'paged': True, 'page_num': 1, 'page_size': 20},
            field_name='configKey',
        )

    def complete_gen_table_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为代码生成业务表名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 业务表名称列表
        """
        del args
        return self.dynamic_service.complete_dynamic_items(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.gen',
            runtime_object_name='GEN_RUNTIME',
            runtime_method_name='list_gen_tables',
            runtime_kwargs={'table_name': incomplete, 'paged': True, 'page_num': 1, 'page_size': 20},
            field_name='tableName',
        )

    def complete_gen_db_table_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为数据库物理表名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 数据库物理表名称列表
        """
        del args
        return self.dynamic_service.complete_dynamic_items(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.gen',
            runtime_object_name='GEN_RUNTIME',
            runtime_method_name='list_gen_db_tables',
            runtime_kwargs={'table_name': incomplete, 'paged': True, 'page_num': 1, 'page_size': 20},
            field_name='tableName',
        )

    def complete_cache_keys(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为缓存键名提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 缓存键名列表
        """
        del args
        cache_name = self.context_resolver.resolve_cache_name_for_completion(ctx)
        if not cache_name:
            return []
        return self.dynamic_service.complete_dynamic_list(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.cache',
            runtime_object_name='CACHE_RUNTIME',
            runtime_method_name='list_cache_keys',
            runtime_args=(cache_name,),
            field_name='keys',
        )

    def complete_job_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为任务名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 任务名称列表
        """
        del args
        return self.dynamic_service.complete_dynamic_items(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.job',
            runtime_object_name='JOB_RUNTIME',
            runtime_method_name='list_jobs',
            runtime_kwargs={'job_name': incomplete, 'paged': True, 'page_num': 1, 'page_size': 20},
            field_name='jobName',
        )

    def complete_job_ids(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为任务 ID 提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 任务 ID 列表
        """
        del args
        return self.dynamic_service.complete_dynamic_items(
            ctx,
            incomplete,
            runtime_module_name='cli.runtime.job',
            runtime_object_name='JOB_RUNTIME',
            runtime_method_name='list_jobs',
            runtime_kwargs={'paged': True, 'page_num': 1, 'page_size': 20},
            field_name='jobId',
            allow_int_values=True,
        )


@dataclass
class CompletionProviderRegistry:
    """
    completion 提供器注册表。

    该注册表只负责持有静态补全、路径补全与动态只读补全 provider，
    供上层 gateway、安装器与其他协作者按职责选择使用。

    :param context_resolver: completion 上下文解析器
    :param dynamic_service: 动态补全执行服务
    :param static_provider: 静态 completion 提供器
    :param path_provider: 路径 completion 提供器
    :param domain_provider: 业务域动态 completion 提供器
    """

    context_resolver: CompletionContextResolver = field(default_factory=CompletionContextResolver)
    dynamic_service: DynamicCompletionService = field(init=False)
    static_provider: StaticCompletionProvider = field(init=False)
    path_provider: PathCompletionProvider = field(init=False)
    domain_provider: DomainDynamicCompletionProvider = field(init=False)

    def __post_init__(self) -> None:
        """
        初始化聚合 provider 依赖。

        :return: None
        """
        self.dynamic_service = DynamicCompletionService(context_resolver=self.context_resolver)
        self.static_provider = StaticCompletionProvider(
            context_resolver=self.context_resolver,
            dynamic_service=self.dynamic_service,
        )
        self.path_provider = PathCompletionProvider(context_resolver=self.context_resolver)
        self.domain_provider = DomainDynamicCompletionProvider(context_resolver=self.context_resolver)
        self.domain_provider.dynamic_service = self.dynamic_service


@dataclass
class CompletionProviderGateway:
    """
    completion 对外网关。

    该对象负责对命令声明层、上下文层和 TUI 层暴露统一的 completion 入口，
    避免 `CompletionProviderRegistry` 本体继续膨胀为大而全的委托门面。

    :param provider_registry: completion provider 注册表
    """

    provider_registry: CompletionProviderRegistry = field(default_factory=CompletionProviderRegistry)

    def list_completion_shells(self) -> list[str]:
        """
        获取已声明的 completion shell 列表。

        :return: shell 名称列表
        """
        return self.provider_registry.static_provider.list_completion_shells()

    def list_static_cache_names(self) -> list[str]:
        """
        读取系统内置缓存名称列表。

        :return: 缓存名称列表
        """
        return self.provider_registry.static_provider.list_static_cache_names()

    def complete_env_values(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 `--env` 选项提供可补全的环境名称。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 匹配的环境名称列表
        """
        return self.provider_registry.static_provider.complete_env_values(ctx, args, incomplete)

    def complete_shell_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 shell 参数提供静态补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: shell 名称列表
        """
        return self.provider_registry.static_provider.complete_shell_names(ctx, args, incomplete)

    def complete_cache_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为缓存名称参数提供静态补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 缓存名称列表
        """
        return self.provider_registry.static_provider.complete_cache_names(ctx, args, incomplete)

    def complete_alembic_revisions(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为数据库迁移版本参数提供本地补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 迁移版本候选列表
        """
        return self.provider_registry.static_provider.complete_alembic_revisions(ctx, args, incomplete)

    def complete_sql_files(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为 SQL 文件参数提供项目内 `.sql` 文件补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: SQL 文件路径列表
        """
        return self.provider_registry.path_provider.complete_sql_files(ctx, args, incomplete)

    def complete_output_paths(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为导出文件参数提供目录和 `.zip` 文件补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 目录或 zip 文件路径列表
        """
        return self.provider_registry.path_provider.complete_output_paths(ctx, args, incomplete)

    def complete_config_keys(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为参数键名提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 参数键名列表
        """
        return self.provider_registry.domain_provider.complete_config_keys(ctx, args, incomplete)

    def complete_gen_table_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为代码生成业务表名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 业务表名称列表
        """
        return self.provider_registry.domain_provider.complete_gen_table_names(ctx, args, incomplete)

    def complete_gen_db_table_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为数据库物理表名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 数据库物理表名称列表
        """
        return self.provider_registry.domain_provider.complete_gen_db_table_names(ctx, args, incomplete)

    def complete_cache_keys(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为缓存键名提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 缓存键名列表
        """
        return self.provider_registry.domain_provider.complete_cache_keys(ctx, args, incomplete)

    def complete_job_names(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为任务名称提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 任务名称列表
        """
        return self.provider_registry.domain_provider.complete_job_names(ctx, args, incomplete)

    def complete_job_ids(
        self,
        ctx: click.Context | None,
        args: list[str] | None,
        incomplete: str,
    ) -> list[str]:
        """
        为任务 ID 提供动态只读补全结果。

        :param ctx: Click 上下文
        :param args: 当前命令参数列表
        :param incomplete: 当前未完成输入片段
        :return: 任务 ID 列表
        """
        return self.provider_registry.domain_provider.complete_job_ids(ctx, args, incomplete)


COMPLETION_PROVIDER_REGISTRY = CompletionProviderRegistry()
COMPLETION_PROVIDER_GATEWAY = CompletionProviderGateway(provider_registry=COMPLETION_PROVIDER_REGISTRY)
