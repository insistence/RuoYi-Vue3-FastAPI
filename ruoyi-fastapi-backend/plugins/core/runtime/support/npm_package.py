import json
from pathlib import Path

from plugins.core.validation.dependencies import DependencyInstallPlanItem, DependencyRequirementParser

from .payload.dependencies import DependencyInstallReturnCodePayload


class PluginNpmPackageJsonSynchronizer:
    """
    插件 npm 依赖声明同步器。

    npm install 可能会把 package.json 写成 npm 自己解析后的版本形式，这里按 plugin.yaml
    中声明的约束回写根 package.json，确保依赖声明与插件 manifest 保持一致。
    """

    @classmethod
    def sync_successful_items(
        cls,
        install_plan_items: list[DependencyInstallPlanItem],
        install_results: list[DependencyInstallReturnCodePayload],
    ) -> None:
        """
        同步安装成功的 npm 依赖声明。

        :param install_plan_items: 依赖安装计划项
        :param install_results: 依赖安装执行结果
        :return: None
        """
        for item, result in zip(install_plan_items, install_results, strict=False):
            if item.kind not in {'npm', 'npmDev'} or result['returnCode'] != 0:
                continue
            cls.sync_item(item)

    @staticmethod
    def sync_item(item: DependencyInstallPlanItem) -> None:
        """
        同步单个 npm 依赖版本声明。

        :param item: 依赖安装计划项
        :return: None
        """
        package_json_path = Path(item.workdir) / 'package.json'
        if not package_json_path.is_file():
            return

        package_json = json.loads(package_json_path.read_text(encoding='utf-8'))
        dependency_field = 'devDependencies' if item.kind == 'npmDev' else 'dependencies'
        dependencies = package_json.setdefault(dependency_field, {})
        parsed_dependency = DependencyRequirementParser.parse(item.requirement)
        version = parsed_dependency.required_version
        if version:
            if version.startswith('=='):
                version = version[2:]
            elif version.startswith('='):
                version = version[1:]
            dependencies[parsed_dependency.name] = version
        else:
            dependencies.setdefault(parsed_dependency.name, '*')

        package_json_path.write_text(
            json.dumps(package_json, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )


__all__ = ['PluginNpmPackageJsonSynchronizer']
