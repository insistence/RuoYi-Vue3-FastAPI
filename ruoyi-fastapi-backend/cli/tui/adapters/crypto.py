from dataclasses import dataclass
from typing import Any

from cli.tui.adapters.base import BaseDetailAdapter
from cli.tui.adapters.models import (
    TUI_ADAPTER_MODEL_RENDERER,
    DetailPageSnapshot,
    DetailSectionSnapshot,
)
from cli.tui.copy import TUI_COPY
from cli.tui.diagnostics import TUI_DIAGNOSTIC_SERVICE
from cli.utils import NESTED_CLI_SUPPORT, SHELL_TEXT_FORMATTER


@dataclass(frozen=True)
class CryptoDetailSourcePayloads:
    """
    传输加密详情页原始数据源快照。

    :param validate_payload: `crypto validate` 结果
    :param public_payload: `crypto export-public` 结果
    """

    validate_payload: dict[str, Any] | None
    public_payload: dict[str, Any] | None


class CryptoDetailSnapshotCollector:
    """
    传输加密详情页数据采集器。

    该对象负责拉取传输加密详情页所需的 CLI 原始结果，
    让 `CryptoDetailAdapter` 保持详情页编排职责。
    """

    def collect(self, env: str) -> CryptoDetailSourcePayloads:
        """
        采集传输加密详情页所需原始结果。

        :param env: 当前运行环境
        :return: 传输加密详情页原始数据源快照
        """
        return CryptoDetailSourcePayloads(
            validate_payload=NESTED_CLI_SUPPORT.run(
                'crypto',
                'validate',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
            public_payload=NESTED_CLI_SUPPORT.run(
                'crypto',
                'export-public',
                f'--env={env}',
                '--output=json',
                parse_json=True,
            ).payload,
        )


class CryptoSectionBuilder:
    """
    传输加密详情分区构建器。

    该构建器负责将传输加密相关 CLI 结果负载转换为 TUI 详情页分区，
    使详情页适配器本体只保留采集与编排职责。
    """

    @staticmethod
    def build_validate_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建传输加密运行校验分区。

        :param payload: `crypto validate` JSON 负载
        :return: 分区快照
        """
        if not isinstance(payload, dict):
            return DetailSectionSnapshot(
                title='运行校验',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='运行校验', empty_value='不可用'
                ),
            )
        lines = [
            '## 校验结果',
            f'状态: {"通过" if payload.get("ok", False) else "失败"}',
            f'说明: {SHELL_TEXT_FORMATTER.truncate_text(TUI_ADAPTER_MODEL_RENDERER.extract_payload_message(payload), 72)}',
        ]
        if payload.get('error'):
            lines.append(f'错误: {SHELL_TEXT_FORMATTER.truncate_text(payload.get("error", "-"), 72)}')
        return DetailSectionSnapshot(
            title='运行校验',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=lines,
        )

    @staticmethod
    def build_public_identity_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建公钥身份分区。

        :param payload: `crypto export-public` JSON 负载
        :return: 分区快照
        """
        public_key_payload = payload.get('publicKey') if isinstance(payload, dict) else None
        if not isinstance(public_key_payload, dict):
            return DetailSectionSnapshot(
                title='公钥身份',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(payload, empty_label='公钥', empty_value='不可用'),
            )
        return DetailSectionSnapshot(
            title='公钥身份',
            status='ok' if payload.get('ok', False) else 'fail',
            lines=[
                '## 当前版本',
                f'KID: {public_key_payload.get("kid", "-")}',
                f'算法: {public_key_payload.get("alg", "-")}',
                f'信封版本: {public_key_payload.get("envelopeVersion", "-")}',
                f'过期时间: {public_key_payload.get("expireAt", "-")}',
            ],
        )

    @staticmethod
    def build_supported_kids_section(payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建兼容版本分区。

        :param payload: `crypto export-public` JSON 负载
        :return: 分区快照
        """
        public_key_payload = payload.get('publicKey') if isinstance(payload, dict) else None
        if not isinstance(public_key_payload, dict):
            return DetailSectionSnapshot(
                title='兼容版本',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='兼容版本', empty_value='不可用'
                ),
            )
        supported_kids = public_key_payload.get('supportedKids')
        lines = TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
            empty_label='兼容版本',
            empty_value='0 个',
            detail='当前公钥未声明兼容版本 KID',
            suggestion='如需兼容旧版本客户端，可检查 supportedKids 配置',
        )
        if isinstance(supported_kids, list) and supported_kids:
            lines = ['## 兼容 KID', *[f'支持版本: {kid}' for kid in supported_kids[:10]]]
        return DetailSectionSnapshot(
            title='兼容版本',
            status='ok',
            lines=lines,
        )

    def build_public_preview_section(self, payload: dict[str, Any] | None) -> DetailSectionSnapshot:
        """
        构建公钥预览分区。

        :param payload: `crypto export-public` JSON 负载
        :return: 分区快照
        """
        public_key_payload = payload.get('publicKey') if isinstance(payload, dict) else None
        if not isinstance(public_key_payload, dict):
            return DetailSectionSnapshot(
                title='公钥预览',
                status='fail',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_failure_lines(
                    payload, empty_label='公钥预览', empty_value='不可用'
                ),
            )
        public_key = str(public_key_payload.get('publicKey', '') or '').splitlines()
        if not public_key:
            return DetailSectionSnapshot(
                title='公钥预览',
                status='info',
                lines=TUI_ADAPTER_MODEL_RENDERER.build_empty_lines(
                    empty_label='公钥预览',
                    empty_value='无内容',
                    detail='当前公钥内容为空，无法生成预览',
                    suggestion='可检查公钥导出结果，或重新生成公钥后再刷新',
                ),
            )
        return DetailSectionSnapshot(
            title='公钥预览',
            status='info',
            lines=['## 预览内容', *[SHELL_TEXT_FORMATTER.truncate_text(line, 88) for line in public_key[:6]]],
        )

    @staticmethod
    def build_overview_section(
        validate_payload: dict[str, Any] | None,
        public_payload: dict[str, Any] | None,
    ) -> DetailSectionSnapshot:
        """
        构建加密页总览判断分区。

        :param validate_payload: `crypto validate` JSON 负载
        :param public_payload: `crypto export-public` JSON 负载
        :return: 分区快照
        """
        validate_ok = bool(isinstance(validate_payload, dict) and validate_payload.get('ok', False))
        public_ok = bool(isinstance(public_payload, dict) and public_payload.get('ok', False))
        public_key_payload = public_payload.get('publicKey') if isinstance(public_payload, dict) else None
        supported_kids = public_key_payload.get('supportedKids') if isinstance(public_key_payload, dict) else None
        supported_count = len(supported_kids) if isinstance(supported_kids, list) else 0

        status = 'ok'
        conclusion = '传输加密基线正常，可继续查看公钥身份、兼容版本与预演入口'
        if not validate_ok:
            status = 'fail'
            conclusion = '运行校验失败，优先确认传输加密配置与环境变量'
        elif not public_ok or not isinstance(public_key_payload, dict):
            status = 'warn'
            conclusion = '公钥导出结果异常，建议先确认当前 KID 与公钥内容是否可用'

        return DetailSectionSnapshot(
            title='总览判断',
            status=status,
            lines=[
                '## 当前结论',
                conclusion,
                '',
                '## 核心指标',
                f'运行校验: {"通过" if validate_ok else "失败"}',
                f'当前 KID: {public_key_payload.get("kid", "-") if isinstance(public_key_payload, dict) else "-"}',
                f'算法: {public_key_payload.get("alg", "-") if isinstance(public_key_payload, dict) else "-"}',
                f'兼容版本数: {supported_count}',
                '',
                '## 建议入口',
                '优先关注：运行校验 / 公钥身份 / 兼容版本 / 轮换预演入口',
            ],
        )

    @staticmethod
    def build_rotation_entry_section(env: str) -> DetailSectionSnapshot:
        """
        构建加密密钥轮换预演入口分区。

        :param env: 当前运行环境
        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='轮换预演入口',
            status='warn',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备轮换传输加密密钥时，应先做 dry-run，确认新 KID、密钥长度和 guard 提示后再执行正式轮换。',
                command=TUI_COPY.build_cli_command_hint(
                    'crypto',
                    'rotate',
                    f'--env={env}',
                    '--dry-run',
                    '--output=json',
                ),
                guide='当前页面先提供预演入口；正式轮换仍应遵循危险命令确认流程，避免直接在未知环境落地变更。',
            ),
        )

    @staticmethod
    def build_keygen_entry_section(env: str) -> DetailSectionSnapshot:
        """
        构建加密密钥生成入口分区。

        :param env: 当前运行环境
        :return: 分区快照
        """
        return DetailSectionSnapshot(
            title='密钥生成入口',
            status='warn',
            lines=TUI_COPY.build_command_hint_lines(
                scenario='准备生成新的传输加密密钥对时，应在当前终端直接查看生成结果，并立即核对 KID、密钥长度和环境变量补丁。',
                command=TUI_COPY.build_cli_command_hint(
                    'crypto',
                    'keygen',
                    f'--env={env}',
                    '--output=text',
                ),
                guide='当前入口会在终端中直接输出新公钥、私钥和 env patch keys，后续再决定是否进入轮换流程。',
            ),
        )

    def build_sections(
        self,
        *,
        validate_payload: dict[str, Any] | None,
        public_payload: dict[str, Any] | None,
        env: str,
    ) -> list[DetailSectionSnapshot]:
        """
        构建传输加密页全部详情分区。

        :param validate_payload: `crypto validate` 结果负载
        :param public_payload: `crypto export-public` 结果负载
        :param env: 当前运行环境
        :return: 详情分区列表
        """
        return [
            self.build_overview_section(validate_payload, public_payload),
            self.build_validate_section(validate_payload),
            self.build_public_identity_section(public_payload),
            self.build_supported_kids_section(public_payload),
            self.build_public_preview_section(public_payload),
            self.build_keygen_entry_section(env),
            self.build_rotation_entry_section(env),
        ]


class CryptoDetailAdapter(BaseDetailAdapter):
    """
    传输加密详情页适配器。

    该适配器负责采集传输加密相关 CLI 结果，并组装为 TUI 详情页快照。
    页面私有的解析逻辑、分区构建逻辑和快照采集流程统一收口在该类中。

    :param section_builder: 传输加密详情分区构建器
    """

    def __init__(
        self,
        section_builder: CryptoSectionBuilder | None = None,
        snapshot_collector: CryptoDetailSnapshotCollector | None = None,
    ) -> None:
        """
        初始化传输加密详情页适配器。

        :param section_builder: 传输加密详情分区构建器
        :param snapshot_collector: 传输加密详情页数据采集器
        :return: None
        """
        super().__init__(
            page_title='传输加密',
            search_view_key='crypto',
            default_suggestions=[
                '总览判断',
                '运行校验',
                '公钥身份',
                '兼容版本',
                '公钥预览',
                '密钥生成入口',
                '轮换预演入口',
            ],
        )
        self.section_builder = section_builder or CryptoSectionBuilder()
        self.snapshot_collector = snapshot_collector or CryptoDetailSnapshotCollector()

    def collect_snapshot(self, env: str, query: str = '') -> DetailPageSnapshot:
        """
        采集传输加密状态页只读快照。

        :param env: 当前运行环境
        :param query: 当前搜索词
        :return: 页面快照
        """
        source_payloads = self.snapshot_collector.collect(env)
        sections = self.section_builder.build_sections(
            validate_payload=source_payloads.validate_payload,
            public_payload=source_payloads.public_payload,
            env=env,
        )
        return DetailPageSnapshot(
            title='传输加密',
            subtitle=TUI_DIAGNOSTIC_SERVICE.build_crypto_diagnostic_subtitle(
                source_payloads.validate_payload,
                source_payloads.public_payload,
            ),
            sections=self.filter_sections(sections, query),
            search=self.resolve_search_context(query),
        )


CRYPTO_DETAIL_ADAPTER = CryptoDetailAdapter()
