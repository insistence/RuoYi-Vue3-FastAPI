from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from cli.utils import SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class DiagnosticPagePolicy:
    """
    TUI 页面诊断策略定义。

    :param focus_terms: 页面聚焦词
    :param subtitle_builder: 页面摘要构建函数
    """

    focus_terms: tuple[str, ...]
    subtitle_builder: Callable[..., str]


@dataclass(frozen=True)
class DiagnosticPagePolicyRegistry:
    """
    TUI 页面诊断策略注册表。

    :param policies: 页面诊断策略映射
    """

    policies: dict[str, DiagnosticPagePolicy]

    def get(self, page_key: str) -> DiagnosticPagePolicy:
        """
        读取指定页面诊断策略。

        :param page_key: 页面标识
        :return: 页面诊断策略
        :raises KeyError: 页面未注册时抛出异常
        """
        return self.policies[page_key]


class TuiDiagnosticService:
    """
    统一封装 TUI 页面诊断提示与摘要拼装逻辑。

    该服务通过页面级诊断策略注册表管理各页面的聚焦词和 subtitle 规则，
    供 adapter、dashboard 等对象复用。

    :param page_policy_registry: 页面诊断策略注册表
    """

    def __init__(self, page_policy_registry: DiagnosticPagePolicyRegistry) -> None:
        """
        初始化诊断服务。

        :param page_policy_registry: 页面诊断策略注册表
        :return: None
        """
        self.page_policy_registry = page_policy_registry

    @staticmethod
    def build_focus_hint(terms: tuple[str, ...]) -> str:
        """
        将诊断聚焦词渲染为统一提示文本。

        :param terms: 聚焦词元组
        :return: 提示文本
        """
        return f'聚焦：{" / ".join(terms)}'

    def build_page_focus_hint(self, page_key: str) -> str:
        """
        构建指定页面统一聚焦词。

        :param page_key: 页面标识
        :return: 聚焦提示
        """
        return self.build_focus_hint(self.page_policy_registry.get(page_key).focus_terms)

    def build_database_focus_hint(self) -> str:
        """
        构建数据库页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('database')

    def build_ops_focus_hint(self) -> str:
        """
        构建运维页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('ops')

    def build_cache_focus_hint(self) -> str:
        """
        构建缓存页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('cache')

    def build_app_focus_hint(self) -> str:
        """
        构建应用页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('app')

    def build_jobs_focus_hint(self) -> str:
        """
        构建任务页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('jobs')

    def build_configs_focus_hint(self) -> str:
        """
        构建参数配置页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('configs')

    def build_gen_focus_hint(self) -> str:
        """
        构建代码生成页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('gen')

    def build_crypto_focus_hint(self) -> str:
        """
        构建加密页统一聚焦词。

        :return: 聚焦提示
        """
        return self.build_page_focus_hint('crypto')

    @staticmethod
    def _build_app_subtitle(
        env_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        routes_payload: dict[str, Any] | None,
        completion_payload: dict[str, Any] | None,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建应用页诊断摘要。

        :param env_payload: `app env` 结果
        :param config_payload: `app config` 结果
        :param doctor_payload: `app doctor` 结果
        :param routes_payload: `app routes` 结果
        :param completion_payload: `completion doctor` 结果
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        env_ok = bool(isinstance(env_payload, dict) and env_payload.get('ok', False))
        config_ok = bool(isinstance(config_payload, dict) and config_payload.get('ok', False))
        doctor_ok = bool(isinstance(doctor_payload, dict) and doctor_payload.get('ok', False))
        routes_ok = bool(isinstance(routes_payload, dict) and routes_payload.get('ok', False))
        completion_ok = bool(isinstance(completion_payload, dict) and completion_payload.get('ok', False))
        route_count = routes_payload.get('count', 0) if isinstance(routes_payload, dict) else 0

        if not env_ok or not config_ok:
            return f'{focus_hint} | 应用基础信息读取异常，优先确认环境映射与配置摘要'
        if not doctor_ok:
            return f'{focus_hint} | 启动前检查异常，优先确认数据库、Redis 与加密组件状态'
        if not completion_ok:
            return f'{focus_hint} | 补全诊断读取异常，优先确认项目目录与 shell 补全配置'
        if not routes_ok:
            return f'{focus_hint} | 路由摘要读取异常，优先确认应用初始化与路由注册状态'
        return (
            f'{focus_hint} | 当前已加载 {route_count} 条注册路由，'
            '可继续查看环境映射、配置摘要、启动前检查、补全诊断与路由状态'
        )

    @staticmethod
    def _build_database_subtitle(
        revision_payload: dict[str, Any] | None,
        check_payload: dict[str, Any] | None,
        heads_payload: dict[str, Any] | None,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建数据库页诊断摘要。

        :param revision_payload: `db current` 结果
        :param check_payload: `db check` 结果
        :param heads_payload: `db heads` 结果
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        revision = revision_payload.get('currentRevision', '-') if isinstance(revision_payload, dict) else '-'
        revision_text = SHELL_TEXT_FORMATTER.truncate_text(str(revision or '-'), 48)
        revision_ok = bool(isinstance(revision_payload, dict) and revision_payload.get('ok', False))
        check_ok = bool(isinstance(check_payload, dict) and check_payload.get('ok', False))
        heads_ok = bool(isinstance(heads_payload, dict) and heads_payload.get('ok', False))
        heads_items = heads_payload.get('items') if isinstance(heads_payload, dict) else None
        heads_count = len(heads_items) if isinstance(heads_items, list) else 0

        if not revision_ok or not check_ok:
            return f'{focus_hint} | 数据库异常，优先确认迁移版本、连接状态与 heads 信息'
        if not heads_ok or heads_count != 1:
            return f'{focus_hint} | 数据库存在迁移分叉风险，优先确认 heads 和历史版本'
        return f'{focus_hint} | 数据库基线正常，当前 revision {revision_text}，可继续查看连接、heads 和历史版本'

    @staticmethod
    def _build_ops_subtitle(
        health_payload: dict[str, Any] | None,
        deps_payload: dict[str, Any] | None,
        server_payload: dict[str, Any] | None,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建运维页诊断摘要。

        :param health_payload: `ops health` 结果
        :param deps_payload: `ops deps` 结果
        :param server_payload: `ops server-info` 结果
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        health_ok = bool(isinstance(health_payload, dict) and health_payload.get('ok', False))
        deps_ok = bool(isinstance(deps_payload, dict) and deps_payload.get('ok', False))
        server_ok = bool(isinstance(server_payload, dict) and server_payload.get('ok', False))

        if not health_ok:
            return f'{focus_hint} | 运维探活存在异常，优先核对数据库/Redis 连通性与依赖版本'
        if not deps_ok:
            return f'{focus_hint} | 运维依赖存在异常，优先核对缺失依赖与版本兼容性'
        if not server_ok:
            return f'{focus_hint} | 服务器信息采集异常，优先重新检查主机资源与运行环境'
        return f'{focus_hint} | 基础探活和依赖状态正常，可继续查看服务器资源与磁盘样本'

    @staticmethod
    def _build_cache_subtitle(
        stats_payload: dict[str, Any] | None,
        matched_count: int,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建缓存页诊断摘要。

        :param stats_payload: `cache stats` 结果
        :param matched_count: 当前筛选后缓存名数量
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        db_size = stats_payload.get('dbSize', '-') if isinstance(stats_payload, dict) else '-'
        client_count = '-'
        if isinstance(stats_payload, dict) and isinstance(stats_payload.get('info'), dict):
            client_count = stats_payload['info'].get('connected_clients', '-')  # type: ignore[index]
        return (
            f'{focus_hint} | 缓存基线正常，当前已加载 {matched_count} 个缓存名，'
            f'Redis 键数 {db_size}，连接数 {client_count}，可继续查看键列表、键值样本和 TTL'
        )

    @staticmethod
    def _build_jobs_subtitle(
        filter_label: str,
        matched_count: int,
        failed_job_names: set[str],
        paused_count: int,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建任务页诊断摘要。

        :param filter_label: 当前筛选标签
        :param matched_count: 当前匹配任务数
        :param failed_job_names: 最近失败任务集合
        :param paused_count: 暂停任务数量
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        if failed_job_names:
            return (
                f'{focus_hint} | 当前筛选：{filter_label}，已匹配 {matched_count} 条任务，'
                f'失败任务 {len(failed_job_names)} 个，暂停任务 {paused_count} 个'
            )
        return (
            f'{focus_hint} | 当前筛选：{filter_label}，已匹配 {matched_count} 条任务，'
            f'当前没有失败任务，暂停任务 {paused_count} 个'
        )

    @staticmethod
    def _build_configs_subtitle(
        filter_label: str,
        matched_count: int,
        mismatch_count: int,
        drift_count: int,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建参数配置页诊断摘要。

        :param filter_label: 当前筛选标签
        :param matched_count: 当前匹配配置数
        :param mismatch_count: 值不一致数量
        :param drift_count: 缓存漂移数量
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        return (
            f'{focus_hint} | 当前筛选：{filter_label}，已匹配 {matched_count} 项配置，'
            f'值不一致 {mismatch_count} 项，缓存漂移 {drift_count} 项'
        )

    @staticmethod
    def _build_gen_subtitle(
        matched_count: int,
        importable_count: int,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建代码生成页诊断摘要。

        :param matched_count: 当前匹配业务表数
        :param importable_count: 可导入物理表数
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        return (
            f'{focus_hint} | 当前已匹配 {matched_count} 张业务表，'
            f'可导入物理表 {importable_count} 张，可继续查看表定义、预检查和代码预览'
        )

    @staticmethod
    def _build_crypto_subtitle(
        validate_payload: dict[str, Any] | None,
        public_payload: dict[str, Any] | None,
        *,
        focus_hint: str,
    ) -> str:
        """
        构建加密页诊断摘要。

        :param validate_payload: `crypto validate` 结果
        :param public_payload: `crypto export-public` 结果
        :param focus_hint: 聚焦提示
        :return: 页面摘要
        """
        validate_ok = bool(isinstance(validate_payload, dict) and validate_payload.get('ok', False))
        public_ok = bool(isinstance(public_payload, dict) and public_payload.get('ok', False))
        public_key_payload = public_payload.get('publicKey') if isinstance(public_payload, dict) else None
        current_kid = public_key_payload.get('kid', '-') if isinstance(public_key_payload, dict) else '-'
        supported_kids = public_key_payload.get('supportedKids') if isinstance(public_key_payload, dict) else None
        supported_count = len(supported_kids) if isinstance(supported_kids, list) else 0

        if not validate_ok:
            return f'{focus_hint} | 运行校验失败，优先确认传输加密配置与环境变量'
        if not public_ok or not isinstance(public_key_payload, dict):
            return f'{focus_hint} | 公钥导出结果异常，优先确认当前 KID 与公钥内容'
        return (
            f'{focus_hint} | 当前 KID {current_kid}，兼容版本 {supported_count} 个，'
            '可继续查看公钥身份、兼容版本与轮换预演入口'
        )

    def build_app_diagnostic_subtitle(
        self,
        env_payload: dict[str, Any] | None,
        config_payload: dict[str, Any] | None,
        doctor_payload: dict[str, Any] | None,
        routes_payload: dict[str, Any] | None,
        completion_payload: dict[str, Any] | None,
    ) -> str:
        """
        构建应用页统一诊断摘要。

        :param env_payload: `app env` 结果
        :param config_payload: `app config` 结果
        :param doctor_payload: `app doctor` 结果
        :param routes_payload: `app routes` 结果
        :param completion_payload: `completion doctor` 结果
        :return: 页面摘要
        """
        return self.page_policy_registry.get('app').subtitle_builder(
            env_payload,
            config_payload,
            doctor_payload,
            routes_payload,
            completion_payload,
            focus_hint=self.build_app_focus_hint(),
        )

    def build_database_diagnostic_subtitle(
        self,
        revision_payload: dict[str, Any] | None,
        check_payload: dict[str, Any] | None,
        heads_payload: dict[str, Any] | None,
    ) -> str:
        """
        构建数据库页统一诊断摘要。

        :param revision_payload: `db current` 结果
        :param check_payload: `db check` 结果
        :param heads_payload: `db heads` 结果
        :return: 页面摘要
        """
        return self.page_policy_registry.get('database').subtitle_builder(
            revision_payload,
            check_payload,
            heads_payload,
            focus_hint=self.build_database_focus_hint(),
        )

    def build_ops_diagnostic_subtitle(
        self,
        health_payload: dict[str, Any] | None,
        deps_payload: dict[str, Any] | None,
        server_payload: dict[str, Any] | None,
    ) -> str:
        """
        构建运维页统一诊断摘要。

        :param health_payload: `ops health` 结果
        :param deps_payload: `ops deps` 结果
        :param server_payload: `ops server-info` 结果
        :return: 页面摘要
        """
        return self.page_policy_registry.get('ops').subtitle_builder(
            health_payload,
            deps_payload,
            server_payload,
            focus_hint=self.build_ops_focus_hint(),
        )

    def build_cache_diagnostic_subtitle(
        self,
        stats_payload: dict[str, Any] | None,
        matched_count: int,
    ) -> str:
        """
        构建缓存页统一诊断摘要。

        :param stats_payload: `cache stats` 结果
        :param matched_count: 当前筛选后缓存名数量
        :return: 页面摘要
        """
        return self.page_policy_registry.get('cache').subtitle_builder(
            stats_payload,
            matched_count,
            focus_hint=self.build_cache_focus_hint(),
        )

    def build_jobs_diagnostic_subtitle(
        self,
        filter_label: str,
        matched_count: int,
        failed_job_names: set[str],
        paused_count: int,
    ) -> str:
        """
        构建任务页统一诊断摘要。

        :param filter_label: 当前筛选标签
        :param matched_count: 当前匹配任务数
        :param failed_job_names: 最近失败任务集合
        :param paused_count: 暂停任务数量
        :return: 页面摘要
        """
        return self.page_policy_registry.get('jobs').subtitle_builder(
            filter_label,
            matched_count,
            failed_job_names,
            paused_count,
            focus_hint=self.build_jobs_focus_hint(),
        )

    def build_configs_diagnostic_subtitle(
        self,
        filter_label: str,
        matched_count: int,
        mismatch_count: int,
        drift_count: int,
    ) -> str:
        """
        构建参数配置页统一诊断摘要。

        :param filter_label: 当前筛选标签
        :param matched_count: 当前匹配配置数
        :param mismatch_count: 值不一致数量
        :param drift_count: 缓存漂移数量
        :return: 页面摘要
        """
        return self.page_policy_registry.get('configs').subtitle_builder(
            filter_label,
            matched_count,
            mismatch_count,
            drift_count,
            focus_hint=self.build_configs_focus_hint(),
        )

    def build_gen_diagnostic_subtitle(
        self,
        matched_count: int,
        importable_count: int,
    ) -> str:
        """
        构建代码生成页统一诊断摘要。

        :param matched_count: 当前匹配业务表数
        :param importable_count: 可导入物理表数
        :return: 页面摘要
        """
        return self.page_policy_registry.get('gen').subtitle_builder(
            matched_count,
            importable_count,
            focus_hint=self.build_gen_focus_hint(),
        )

    def build_crypto_diagnostic_subtitle(
        self,
        validate_payload: dict[str, Any] | None,
        public_payload: dict[str, Any] | None,
    ) -> str:
        """
        构建加密页统一诊断摘要。

        :param validate_payload: `crypto validate` 结果
        :param public_payload: `crypto export-public` 结果
        :return: 页面摘要
        """
        return self.page_policy_registry.get('crypto').subtitle_builder(
            validate_payload,
            public_payload,
            focus_hint=self.build_crypto_focus_hint(),
        )


TUI_DIAGNOSTIC_PAGE_POLICY_REGISTRY = DiagnosticPagePolicyRegistry(
    policies={
        'database': DiagnosticPagePolicy(
            focus_terms=('迁移版本', '连接状态', 'Heads'),
            subtitle_builder=TuiDiagnosticService._build_database_subtitle,
        ),
        'ops': DiagnosticPagePolicy(
            focus_terms=('数据库连通性', 'Redis 连通性', '依赖版本'),
            subtitle_builder=TuiDiagnosticService._build_ops_subtitle,
        ),
        'cache': DiagnosticPagePolicy(
            focus_terms=('Redis 键数', '连接数', '缓存名前缀'),
            subtitle_builder=TuiDiagnosticService._build_cache_subtitle,
        ),
        'app': DiagnosticPagePolicy(
            focus_terms=('环境映射', '配置摘要', '启动前检查'),
            subtitle_builder=TuiDiagnosticService._build_app_subtitle,
        ),
        'jobs': DiagnosticPagePolicy(
            focus_terms=('失败聚合', '暂停任务', '执行轨迹'),
            subtitle_builder=TuiDiagnosticService._build_jobs_subtitle,
        ),
        'configs': DiagnosticPagePolicy(
            focus_terms=('高风险配置', '值不一致', '缓存漂移'),
            subtitle_builder=TuiDiagnosticService._build_configs_subtitle,
        ),
        'gen': DiagnosticPagePolicy(
            focus_terms=('生成前校验', '同步预检查', '代码预览'),
            subtitle_builder=TuiDiagnosticService._build_gen_subtitle,
        ),
        'crypto': DiagnosticPagePolicy(
            focus_terms=('运行校验', '公钥身份', '兼容版本'),
            subtitle_builder=TuiDiagnosticService._build_crypto_subtitle,
        ),
    }
)
TUI_DIAGNOSTIC_SERVICE = TuiDiagnosticService(TUI_DIAGNOSTIC_PAGE_POLICY_REGISTRY)
