from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionTemplate, TuiActionTemplateSupport
from cli.tui.adapters.models import BrowserRecordSnapshot
from cli.tui.copy import TUI_COPY


@dataclass(frozen=True)
class StaticActionTemplateFactory:
    """
    静态页面动作模板工厂。

    该对象负责生成不依赖当前记录内容的页面动作模板，统一详情页和
    部分浏览页的固定动作定义。

    :param support: 动作模板共享构建支持
    """

    support: TuiActionTemplateSupport

    @staticmethod
    def build_job_sync_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建任务同步命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {}

    @staticmethod
    def build_config_sync_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建配置同步命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {}

    @staticmethod
    def build_cache_warmup_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建缓存预热命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {}

    @staticmethod
    def build_db_upgrade_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建数据库升级预演参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'revision': 'head', 'dry_run': True}

    @staticmethod
    def build_db_init_dry_run_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建数据库初始化预演命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'dry_run': True}

    @staticmethod
    def build_app_precheck_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建应用启动前检查参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'include_config': True}

    @staticmethod
    def build_completion_install_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建补全安装命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'activate': True}

    @staticmethod
    def build_prod_check_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建综合运行巡检参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'include_config': True}

    @staticmethod
    def build_crypto_rotate_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建加密轮换预演命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'key_size': 2048}

    @staticmethod
    def build_crypto_keygen_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建加密密钥生成命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {'key_size': 2048}

    @staticmethod
    def build_ops_ping_db_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建数据库探活命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {}

    @staticmethod
    def build_ops_ping_redis_parameters(record: BrowserRecordSnapshot | None, env: str) -> dict[str, object]:
        """
        构建 Redis 探活命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return {}

    def create_config_sync_template(self) -> TuiActionTemplate:
        """
        创建配置同步动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='config-sync-cache',
            label=TUI_COPY.build_action_label('config_sync'),
            parameter_builder=self.build_config_sync_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('config_sync'),
                TUI_COPY.build_action_purpose_label('config_sync'),
            ),
        )

    def create_db_upgrade_dry_run_template(self) -> TuiActionTemplate:
        """
        创建数据库升级预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='db-upgrade-dry-run',
            label='数据库升级预演',
            parameter_builder=self.build_db_upgrade_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境数据库升级范围',
                '生成目标 revision 为 head 的 dry-run SQL 预演',
            ),
            consequence_text='仅生成升级到 head 的 Alembic SQL 预演，不修改数据库。',
        )

    def create_db_init_dry_run_template(self) -> TuiActionTemplate:
        """
        创建数据库初始化预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='db-init-dry-run',
            label=TUI_COPY.build_action_label('db_init_dry_run'),
            parameter_builder=self.build_db_init_dry_run_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('db_init_dry_run'),
                TUI_COPY.build_action_purpose_label('db_init_dry_run'),
            ),
        )

    def create_app_precheck_template(self) -> TuiActionTemplate:
        """
        创建应用启动前检查动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='app-precheck',
            label='启动前检查',
            parameter_builder=self.build_app_precheck_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境应用依赖',
                '并发检查数据库、Redis、传输加密和运行配置',
            ),
            consequence_text='仅执行应用启动前检查，不启动服务器进程。',
        )

    def create_completion_install_template(self) -> TuiActionTemplate:
        """
        创建补全安装动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='completion-install',
            label=TUI_COPY.build_action_label('completion_install'),
            parameter_builder=self.build_completion_install_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('completion_install'),
                TUI_COPY.build_action_purpose_label('completion_install'),
            ),
            consequence_text='在当前进程内安装补全脚本，并按需更新当前 Shell 的 rc 文件。',
            refresh_view=False,
        )

    def create_prod_check_template(self) -> TuiActionTemplate:
        """
        创建综合运行巡检动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='prod-check',
            label='综合运行巡检',
            parameter_builder=self.build_prod_check_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境运行依赖',
                '统一检查数据库、Redis、传输加密和运行配置',
            ),
            consequence_text='在当前进程内并发检查数据库、Redis 和参数配置，不启动外部命令。',
        )

    def create_crypto_rotate_dry_run_template(self) -> TuiActionTemplate:
        """
        创建加密轮换预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='crypto-rotate-dry-run',
            label=TUI_COPY.build_action_label('crypto_rotate_dry_run'),
            parameter_builder=self.build_crypto_rotate_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境传输加密轮换预演',
                '仅生成轮换辅助结果，不直接写入新密钥配置',
            ),
        )

    def create_crypto_keygen_template(self) -> TuiActionTemplate:
        """
        创建密钥生成动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='crypto-keygen',
            label=TUI_COPY.build_action_label('crypto_keygen'),
            parameter_builder=self.build_crypto_keygen_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境新密钥生成流程',
                '在终端中直接输出新密钥材料和环境变量补丁建议',
            ),
            consequence_text='在内存中生成新密钥材料，不写入环境文件。',
            refresh_view=False,
        )

    def create_ops_ping_db_template(self) -> TuiActionTemplate:
        """
        创建数据库探活动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='ops-ping-db',
            label=TUI_COPY.build_action_label('ops_ping_db'),
            parameter_builder=self.build_ops_ping_db_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('ops_ping_db'),
                TUI_COPY.build_action_purpose_label('ops_ping_db'),
            ),
        )

    def create_ops_ping_redis_template(self) -> TuiActionTemplate:
        """
        创建 Redis 探活动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='ops-ping-redis',
            label=TUI_COPY.build_action_label('ops_ping_redis'),
            parameter_builder=self.build_ops_ping_redis_parameters,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('ops_ping_redis'),
                TUI_COPY.build_action_purpose_label('ops_ping_redis'),
            ),
        )
