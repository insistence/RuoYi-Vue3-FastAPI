from dataclasses import dataclass


@dataclass(frozen=True)
class PluginScaffoldOptions:
    """
    插件模板生成选项。

    :param backend: 是否生成后端模板
    :param frontend: 是否生成前端模板
    :param migration: 是否生成 migration 示例
    :param seed: 是否生成 seed 示例
    :param job: 是否生成定时任务示例
    :param config: 是否生成配置项示例
    :param test: 是否生成测试样例
    :param crud: 是否生成 CRUD 页面示例
    """

    backend: bool = True
    frontend: bool = True
    migration: bool = True
    seed: bool = True
    job: bool = True
    config: bool = True
    test: bool = True
    crud: bool = False


class PluginScaffoldTemplateResolver:
    """
    插件模板预设解析器。

    使用 Resolver 模式将模板名称转换为稳定的模板生成选项。
    """

    SUPPORTED_TEMPLATES = {'minimal', 'backend-only', 'full-stack', 'scheduled-job', 'crud-page'}
    DEFAULT_TEMPLATE = 'full-stack'

    @classmethod
    def resolve(cls, template: str) -> PluginScaffoldOptions:
        """
        解析插件模板预设。

        :param template: 插件模板名称
        :return: 插件模板生成选项
        """
        normalized_template = (template or cls.DEFAULT_TEMPLATE).strip() or cls.DEFAULT_TEMPLATE
        if normalized_template == 'minimal':
            return PluginScaffoldOptions(
                backend=True,
                frontend=False,
                migration=False,
                seed=False,
                job=False,
                config=False,
                test=True,
            )
        if normalized_template == 'backend-only':
            return PluginScaffoldOptions(backend=True, frontend=False)
        if normalized_template == 'full-stack':
            return PluginScaffoldOptions()
        if normalized_template == 'scheduled-job':
            return PluginScaffoldOptions(
                backend=True,
                frontend=False,
                migration=False,
                seed=False,
                job=True,
                config=False,
                test=True,
            )
        if normalized_template == 'crud-page':
            return PluginScaffoldOptions(
                backend=True,
                frontend=True,
                migration=True,
                seed=True,
                job=False,
                config=True,
                test=True,
                crud=True,
            )
        supported_templates = ', '.join(sorted(cls.SUPPORTED_TEMPLATES))
        raise ValueError(f'插件模板只支持：{supported_templates}')
