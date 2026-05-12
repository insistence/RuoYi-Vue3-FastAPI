from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENVIRONMENTS = ('dev', 'prod', 'dockermy', 'dockerpg')


@dataclass(frozen=True)
class EnvironmentOptionService:
    """
    CLI 环境选项服务。

    该服务负责发现当前项目下可用的环境名称集合，供 completion、
    wizard 和诊断信息等场景复用。

    :param default_environments: 默认内置环境名称列表
    """

    default_environments: tuple[str, ...] = DEFAULT_ENVIRONMENTS

    def discover_env_names(self, project_dir: Path | None = None) -> list[str]:
        """
        发现当前项目可用的环境名称列表。

        :param project_dir: 后端项目目录，默认使用当前工作目录
        :return: 去重且排序后的环境名称列表
        """
        resolved_project_dir = (project_dir or Path.cwd()).resolve()
        env_names = set(self.default_environments)
        for env_file in resolved_project_dir.glob('.env.*'):
            suffix = env_file.name.removeprefix('.env.').strip()
            if suffix:
                env_names.add(suffix)
        return sorted(env_names)


ENVIRONMENT_OPTION_SERVICE = EnvironmentOptionService()
