import subprocess
import sys
from pathlib import Path

import yaml


def main() -> None:
    """
    从 AI 插件清单安装测试依赖，避免 CI 维护第二份版本列表。

    :return: None
    """
    backend = Path(__file__).resolve().parents[2] / 'ruoyi-fastapi-backend'
    manifest = yaml.safe_load((backend / 'plugins/ai/plugin.yaml').read_text(encoding='utf-8'))
    requirements = manifest['dependencies']['python']
    if not requirements or not all(isinstance(item, str) and not item.startswith('-') for item in requirements):
        raise ValueError('AI 插件 Python 依赖清单无效')
    subprocess.run([sys.executable, '-m', 'pip', 'install', *requirements], check=True, timeout=900)


if __name__ == '__main__':
    main()
