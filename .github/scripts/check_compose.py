import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIGURATIONS = (
    ('docker.env', 'docker-compose.my.yml', 'my'),
    ('docker.env', 'docker-compose.pg.yml', 'pg'),
    ('ruoyi-fastapi-test/docker.env', 'ruoyi-fastapi-test/docker-compose.test.my.yml', 'my'),
    ('ruoyi-fastapi-test/docker.env', 'ruoyi-fastapi-test/docker-compose.test.pg.yml', 'pg'),
)


def validate_configuration(config: dict[str, Any], framework: str, engine: str, root: Path) -> None:
    """
    核对 Compose 实际解析后的前后端框架及 nginx 来源。

    :param config: docker compose config 的 JSON 结果
    :param framework: 本次选择的框架
    :param engine: my 或 pg
    :param root: 仓库根目录
    :return: None
    """
    expected = (root / 'ruoyi-fastapi-frontend' / framework / 'web').resolve()
    services = config['services']
    frontend = services['ruoyi-frontend']
    build = frontend['build']
    if Path(build['context']).resolve() != expected:
        raise ValueError(f'{framework}: 前端构建目录不一致')
    if not (expected / build.get('dockerfile', 'Dockerfile')).is_file():
        raise ValueError(f'{framework}: 前端 Dockerfile 不存在')
    volumes = [
        volume for volume in frontend.get('volumes', []) if volume.get('target') == '/etc/nginx/conf.d/default.conf'
    ]
    nginx = expected / 'bin' / f'nginx.docker{engine}.conf'
    if len(volumes) != 1 or Path(volumes[0]['source']).resolve() != nginx or not nginx.is_file():
        raise ValueError(f'{framework}: nginx 配置未选择同一框架')
    backend = services[f'ruoyi-backend-{engine}']
    if backend['environment'].get('RUOYI_PLUGIN_FRONTEND_FRAMEWORK') != framework:
        raise ValueError(f'{framework}: 后端插件框架与前端不一致')


def main() -> None:
    """
    使用两种框架解析全部生产和测试 Compose，无需启动容器。

    :return: None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker', default='docker')
    args = parser.parse_args()
    for framework in ('vue2', 'vue3'):
        for env_file, compose_file, engine in CONFIGURATIONS:
            result = subprocess.run(
                [args.docker, 'compose', '--env-file', env_file, '-f', compose_file, 'config', '--format', 'json'],
                cwd=ROOT,
                env={**os.environ, 'FRONTEND_FRAMEWORK': framework},
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=60,
            )
            validate_configuration(json.loads(result.stdout), framework, engine, ROOT)
            print(f'{framework}: {compose_file} PASS')


if __name__ == '__main__':
    main()
