from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
from pathlib import Path


def isolate_compose(config: dict, project: str, python_version: str) -> dict:
    """从已解析的测试配置生成独立项目，保留应用和数据库的真实配置。"""
    if not re.fullmatch(r'ruoyi-ci-[a-z0-9][a-z0-9_-]*', project):
        raise ValueError('测试项目名必须以 ruoyi-ci- 开头且仅包含小写字母、数字、下划线或连字符')
    config = copy.deepcopy(config)
    config['name'] = project
    for name, service in config['services'].items():
        service.pop('container_name', None)
        service.pop('restart', None)
        service['ports'] = []
        for volume in service.get('volumes', []):
            if volume.get('type') == 'bind':
                volume['read_only'] = True
        if 'build' in service:
            service['image'] = f'{project}-{name}:ci'
        if name == 'ruoyi-frontend' or name.startswith('ruoyi-backend-'):
            port = 80 if name == 'ruoyi-frontend' else 9099
            service['ports'] = [{'target': port, 'published': '0', 'host_ip': '127.0.0.1', 'protocol': 'tcp'}]
        if name.startswith('ruoyi-backend-'):
            service['build'].setdefault('args', {}).update(
                {'PYTHON_VERSION': python_version, 'PIP_INDEX_URL': 'https://pypi.org/simple'}
            )
            service['healthcheck'] = {
                'test': [
                    'CMD',
                    'python',
                    '-c',
                    "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:9099/captchaImage',timeout=5)); assert data['captchaEnabled'] is False",
                ],
                'interval': '5s',
                'timeout': '10s',
                'retries': 36,
                'start_period': '30s',
            }
        if name == 'ruoyi-frontend':
            service['healthcheck'] = {
                'test': [
                    'CMD-SHELL',
                    'curl --fail --silent --show-error --max-time 5 http://127.0.0.1/login -o /dev/null && curl --fail --silent --show-error --max-time 5 http://127.0.0.1/docker-api/captchaImage -o /dev/null',
                ],
                'interval': '5s',
                'timeout': '10s',
                'retries': 36,
            }
        if name in {'ruoyi-mysql', 'ruoyi-pg'}:
            query = "SELECT config_value FROM sys_config WHERE config_key='sys.account.captchaEnabled'"
            command = (
                f'mysql --protocol=TCP -h 127.0.0.1 -u root -proot -D ruoyi-fastapi -Nse "{query}"'
                if name == 'ruoyi-mysql'
                else f'PGPASSWORD=root psql -h 127.0.0.1 -U postgres -d ruoyi-fastapi -tAc "{query}"'
            )
            service['healthcheck'] = {
                'test': ['CMD-SHELL', f'{command} | grep -qx false'],
                'interval': '5s',
                'timeout': '10s',
                'retries': 36,
            }
    for name, network in config.get('networks', {}).items():
        network.pop('external', None)
        network['name'] = f'{project}-{name}'
    for name, volume in config.get('volumes', {}).items():
        volume.pop('external', None)
        volume['name'] = f'{project}-{name}'
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description='生成 CI 专用的独立 Compose 项目，不修改开发配置。')
    parser.add_argument('--database', choices=['mysql', 'postgresql'], required=True)
    parser.add_argument('--framework', choices=['vue2', 'vue3'], required=True)
    parser.add_argument('--python-version', choices=['3.10', '3.11', '3.12', '3.13'], default='3.12')
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--docker', default='docker')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    suffix = 'my' if args.database == 'mysql' else 'pg'
    result = subprocess.run(
        [
            args.docker,
            'compose',
            '--env-file',
            str(root / 'docker.env'),
            '-f',
            str(root / f'docker-compose.test.{suffix}.yml'),
            'config',
            '--format',
            'json',
        ],
        env={**os.environ, 'FRONTEND_FRAMEWORK': args.framework},
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
        timeout=30,
    )
    config = isolate_compose(json.loads(result.stdout), args.project, args.python_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2), encoding='utf-8')
    print(f'已生成 {args.project}：{args.output.resolve()}')


if __name__ == '__main__':
    main()
