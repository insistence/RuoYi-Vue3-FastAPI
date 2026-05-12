from dataclasses import dataclass

from cli.tui.actions.builders import TuiActionSpecFactory
from cli.tui.actions.factories.cache import CacheActionTemplateFactory
from cli.tui.actions.factories.gen import GenActionTemplateFactory
from cli.tui.actions.factories.jobs import JobActionTemplateFactory
from cli.tui.actions.factories.static import StaticActionTemplateFactory
from cli.tui.actions.registry import TuiActionRegistry, TuiActionSlotResolver


@dataclass(frozen=True)
class TuiActionRegistryBuilder:
    """
    TUI 动作注册表构建器。

    该对象负责装配各领域动作模板工厂，最终输出浏览页和详情页共用的
    动作注册表，避免模板常量继续散落在模块底部。

    :param jobs: 任务页动作模板工厂
    :param cache: 缓存页动作模板工厂
    :param gen: 代码生成页动作模板工厂
    :param static: 静态页面动作模板工厂
    :param spec_factory: 动作规格构建器
    """

    jobs: JobActionTemplateFactory
    cache: CacheActionTemplateFactory
    gen: GenActionTemplateFactory
    static: StaticActionTemplateFactory
    spec_factory: TuiActionSpecFactory

    def build(self) -> TuiActionRegistry:
        """
        构建 TUI 动作注册表。

        :return: 动作注册表
        """
        return TuiActionRegistry(
            browser_resolvers={
                'jobs': TuiActionSlotResolver(
                    slot_templates={
                        'primary': self.jobs.create_run_once_template(),
                        'secondary': self.jobs.create_toggle_template(),
                        'global': self.jobs.create_sync_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'configs': TuiActionSlotResolver(
                    slot_templates={
                        'global': self.static.create_config_sync_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'cache': TuiActionSlotResolver(
                    slot_templates={
                        'global': self.cache.create_clear_wizard_template(),
                        'utility': self.cache.create_warmup_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'gen': TuiActionSlotResolver(
                    slot_templates={
                        'primary': self.gen.create_export_wizard_template(),
                        'secondary': self.gen.create_import_wizard_template(),
                        'global': self.gen.create_export_dry_run_template(),
                        'utility': self.gen.create_sync_db_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
            },
            detail_resolvers={
                'app': TuiActionSlotResolver(
                    slot_templates={
                        'primary': self.static.create_app_run_template(),
                        'global': self.static.create_app_run_wizard_template(),
                        'utility': self.static.create_completion_install_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'database': TuiActionSlotResolver(
                    slot_templates={
                        'global': self.static.create_db_upgrade_wizard_template(),
                        'utility': self.static.create_db_init_dry_run_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'ops': TuiActionSlotResolver(
                    slot_templates={
                        'primary': self.static.create_ops_ping_db_template(),
                        'secondary': self.static.create_ops_ping_redis_template(),
                        'global': self.static.create_prod_check_wizard_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
                'crypto': TuiActionSlotResolver(
                    slot_templates={
                        'primary': self.static.create_crypto_keygen_template(),
                        'global': self.static.create_crypto_rotate_dry_run_template(),
                    },
                    spec_factory=self.spec_factory,
                ),
            },
        )
