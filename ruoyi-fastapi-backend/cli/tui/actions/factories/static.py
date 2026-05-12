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
    def build_job_sync_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建任务同步命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('job', 'sync')

    @staticmethod
    def build_config_sync_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建配置同步命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('config', 'sync-cache')

    @staticmethod
    def build_cache_warmup_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建缓存预热命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('cache', 'warmup')

    @staticmethod
    def build_db_upgrade_wizard_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建数据库升级向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record
        return (
            'wizard',
            'db-upgrade',
            '--output=text',
            f'--default-env={env}',
            '--default-revision=head',
            '--default-dry-run',
        )

    @staticmethod
    def build_db_init_dry_run_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建数据库初始化预演命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('db', 'init', '--dry-run')

    @staticmethod
    def build_app_run_wizard_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建应用启动向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('wizard', 'app-run')

    @staticmethod
    def build_completion_install_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建补全安装命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('completion', 'install', '--activate')

    @staticmethod
    def build_prod_check_wizard_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建生产巡检向导命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record
        return (
            'wizard',
            'prod-check',
            '--output=text',
            f'--default-env={env}',
            '--default-include-config',
        )

    @staticmethod
    def build_crypto_rotate_dry_run_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建加密轮换预演命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('crypto', 'rotate', '--dry-run')

    @staticmethod
    def build_app_run_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建应用直接启动命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record
        return ('app', 'run', f'--env={env}')

    @staticmethod
    def build_crypto_keygen_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建加密密钥生成命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record
        return ('crypto', 'keygen', f'--env={env}', '--output=text')

    @staticmethod
    def build_ops_ping_db_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建数据库探活命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('ops', 'ping-db')

    @staticmethod
    def build_ops_ping_redis_command(record: BrowserRecordSnapshot | None, env: str) -> tuple[str, ...]:
        """
        构建 Redis 探活命令参数。

        :param record: 当前记录
        :param env: 当前运行环境
        :return: 命令参数
        """
        del record, env
        return ('ops', 'ping-redis')

    def create_config_sync_template(self) -> TuiActionTemplate:
        """
        创建配置同步动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='config-sync-cache',
            label=TUI_COPY.build_action_label('config_sync'),
            command_builder=self.build_config_sync_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('config_sync'),
                TUI_COPY.build_action_purpose_label('config_sync'),
            ),
        )

    def create_db_upgrade_wizard_template(self) -> TuiActionTemplate:
        """
        创建数据库升级向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-db-upgrade',
            label=TUI_COPY.build_action_label('db_upgrade_wizard'),
            command_builder=self.build_db_upgrade_wizard_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境数据库升级流程',
                '进入向导后确认目标 revision、环境和 dry-run 预演',
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
        )

    def create_db_init_dry_run_template(self) -> TuiActionTemplate:
        """
        创建数据库初始化预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='db-init-dry-run',
            label=TUI_COPY.build_action_label('db_init_dry_run'),
            command_builder=self.build_db_init_dry_run_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('db_init_dry_run'),
                TUI_COPY.build_action_purpose_label('db_init_dry_run'),
            ),
            append_yes=False,
        )

    def create_app_run_wizard_template(self) -> TuiActionTemplate:
        """
        创建应用启动向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-app-run',
            label=TUI_COPY.build_action_label('app_run_wizard'),
            command_builder=self.build_app_run_wizard_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境应用启动流程',
                '进入向导后确认环境，并决定是否先执行启动前检查',
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
            refresh_view=False,
        )

    def create_completion_install_template(self) -> TuiActionTemplate:
        """
        创建补全安装动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='completion-install',
            label=TUI_COPY.build_action_label('completion_install'),
            command_builder=self.build_completion_install_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('completion_install'),
                TUI_COPY.build_action_purpose_label('completion_install'),
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('external'),
            refresh_view=False,
            preview_env_override='-',
        )

    def create_prod_check_wizard_template(self) -> TuiActionTemplate:
        """
        创建生产巡检向导动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='wizard-prod-check',
            label=TUI_COPY.build_action_label('prod_check_wizard'),
            command_builder=self.build_prod_check_wizard_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境生产巡检流程',
                '进入向导后统一检查数据库、缓存和运行配置',
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
        )

    def create_crypto_rotate_dry_run_template(self) -> TuiActionTemplate:
        """
        创建加密轮换预演动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='crypto-rotate-dry-run',
            label=TUI_COPY.build_action_label('crypto_rotate_dry_run'),
            command_builder=self.build_crypto_rotate_dry_run_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境传输加密轮换预演',
                '仅生成轮换辅助结果，不直接写入新密钥配置',
            ),
            append_yes=False,
        )

    def create_app_run_template(self) -> TuiActionTemplate:
        """
        创建应用直接启动动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='app-run',
            label=TUI_COPY.build_action_label('app_run'),
            command_builder=self.build_app_run_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境应用直接启动流程',
                '确认后会在当前终端直接启动当前 FastAPI 应用，并持续占用终端会话',
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
            refresh_view=False,
        )

    def create_crypto_keygen_template(self) -> TuiActionTemplate:
        """
        创建密钥生成动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='crypto-keygen',
            label=TUI_COPY.build_action_label('crypto_keygen'),
            command_builder=self.build_crypto_keygen_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                '当前环境新密钥生成流程',
                '在终端中直接输出新密钥材料和环境变量补丁建议',
            ),
            execution_mode='external',
            consequence_text=TUI_COPY.build_action_consequence_text('wizard'),
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
            command_builder=self.build_ops_ping_db_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('ops_ping_db'),
                TUI_COPY.build_action_purpose_label('ops_ping_db'),
            ),
            append_yes=False,
        )

    def create_ops_ping_redis_template(self) -> TuiActionTemplate:
        """
        创建 Redis 探活动作模板。

        :return: 动作模板
        """
        return TuiActionTemplate(
            action_id='ops-ping-redis',
            label=TUI_COPY.build_action_label('ops_ping_redis'),
            command_builder=self.build_ops_ping_redis_command,
            summary_builder=lambda record, env: self.support.build_scope_purpose_summary(
                TUI_COPY.build_action_scope_label('ops_ping_redis'),
                TUI_COPY.build_action_purpose_label('ops_ping_redis'),
            ),
            append_yes=False,
        )
