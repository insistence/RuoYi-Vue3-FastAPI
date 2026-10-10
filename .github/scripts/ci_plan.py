import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FRAMEWORKS = ('vue2', 'vue3')
PYTHON_VERSIONS = ('3.10', '3.11', '3.12', '3.13')
CATEGORIES = ('quality', 'backend', 'frontend', 'integration', 'e2e', 'native')
FRONTEND_FILE_PATH_PARTS = 4


# 将影响范围规则集中列出，便于逐条审核；拆散分支会掩盖任务之间的联动。
def build_plan(paths: list[str], *, full: bool = False) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
    """
    根据源码、共享依赖及测试的影响范围生成 CI 执行计划。

    :param paths: 变更文件，重命名需要同时传入旧路径和新路径
    :param full: 是否执行完整兼容矩阵
    :return: 分类开关、矩阵和必跑任务
    """
    projects: set[tuple[str, str]] = set()
    browsers: set[str] = set()
    networks: set[str] = set()
    backend = native = database = release = False
    normalized = [path.replace('\\', '/').removeprefix('./') for path in paths]
    shared = full or any(
        path.startswith(('.github/', 'ruoyi-fastapi-backend/requirements'))
        or path
        in (
            'ruoyi-fastapi-backend/pyproject.toml',
            'ruoyi-fastapi-backend/tests/conftest.py',
            'ruoyi-fastapi-test/requirements.txt',
            '.gitignore',
        )
        for path in normalized
    )
    if shared:
        projects.update((framework, target) for framework in FRAMEWORKS for target in ('web', 'mobile'))
        browsers.update(FRAMEWORKS)
        networks.update(FRAMEWORKS)
        backend = native = database = release = True
    for path in normalized:
        if path.lower().endswith('.md'):
            continue
        parts = path.split('/')
        if path.startswith('ruoyi-fastapi-backend/'):
            backend = True
            relative = path.removeprefix('ruoyi-fastapi-backend/')
            if not relative.startswith(('tests/', 'ruff.toml')):
                browsers.update(FRAMEWORKS)
            if relative.startswith(('common/', 'config/', 'utils/', 'sql/', 'scripts/verify_timezone_database')):
                database = True
            if relative.startswith(
                (
                    'plugins/',
                    'module_plugin/',
                    'cli/',
                    'tests/plugins/',
                    'tests/cli/',
                    'tests/module_plugin/',
                    'tests/sql/',
                )
            ):
                native = release = True
            if relative == 'scripts/build_native_plugin.py':
                native = True
            if relative.startswith(
                ('plugins/', 'module_plugin/', 'common/', 'config/', 'middlewares/', 'utils/')
            ) or relative in ('server.py', 'app.py', 'module_admin/service/login_service.py'):
                networks.update(FRAMEWORKS)
            if relative.startswith(('config/', 'sql/', 'scripts/plugin_', 'tests/server/')) or relative in (
                'server.py',
                'app.py',
            ):
                release = True
            if relative.startswith('tests/plugins/integration/') or relative in (
                'tests/scheduler_helpers.py',
                'tests/plugins/core/runtime/test_browser_session.py',
            ):
                networks.update(FRAMEWORKS)
            if relative in (
                'plugins/core/frontend.py',
                'plugins/core/environment.py',
                'plugins/core/manifest/schema.py',
            ):
                projects.update((framework, target) for framework in FRAMEWORKS for target in ('web', 'mobile'))
            if relative.startswith('plugins/examples/python/bundle_demo/web/'):
                projects.update((framework, 'web') for framework in FRAMEWORKS)
        elif (
            len(parts) >= FRONTEND_FILE_PATH_PARTS
            and parts[0] == 'ruoyi-fastapi-frontend'
            and parts[1] in FRAMEWORKS
            and parts[2] in ('web', 'mobile')
        ):
            framework, target = parts[1:3]
            projects.add((framework, target))
            if target == 'web':
                browsers.add(framework)
                networks.add(framework)
            if target == 'web' and (parts[-1].startswith('pluginBridge') or parts[-1] == 'package.json'):
                backend = native = release = True
        elif path.startswith('ruoyi-fastapi-frontend/'):
            projects.update((framework, target) for framework in FRAMEWORKS for target in ('web', 'mobile'))
            browsers.update(FRAMEWORKS)
            networks.update(FRAMEWORKS)
        elif path.startswith('ruoyi-fastapi-test/frontend/'):
            projects.update((framework, 'mobile') for framework in FRAMEWORKS)
        elif path.startswith('ruoyi-fastapi-test/time-contract/'):
            projects.update((framework, target) for framework in FRAMEWORKS for target in ('web', 'mobile'))
            database = True
            browsers.update(FRAMEWORKS)
        elif path.startswith('ruoyi-fastapi-test/') or path in (
            'docker.env',
            'docker-compose.my.yml',
            'docker-compose.pg.yml',
        ):
            browsers.update(FRAMEWORKS)
            if 'docker' in path or path.endswith('.sql'):
                database = True

    required = {
        'quality': True,
        'backend': backend,
        'frontend': bool(projects),
        'integration': database or release or bool(networks),
        'e2e': bool(browsers),
        'native': native,
    }
    return {
        'full': full,
        'required': required,
        'frontend_matrix': {
            'include': [{'framework': framework, 'target': target} for framework, target in sorted(projects)]
        },
        'e2e_matrix': {
            'include': [
                {'framework': framework, 'database': engine, 'python': version}
                for framework in sorted(browsers)
                for engine in ('mysql', 'postgresql')
                for version in (PYTHON_VERSIONS if full else ('3.12',))
            ]
        },
        'network_frameworks': sorted(networks),
        'database': database,
        'release': release,
        'paths': normalized,
    }


def check_results(plan: dict[str, Any], needs: dict[str, Any]) -> list[str]:
    """
    核验必跑任务，拒绝失败、取消、缺失和意外跳过。

    :param plan: 选路任务生成的计划
    :param needs: GitHub needs 上下文
    :return: 不满足门禁的原因
    """
    errors = []
    if needs.get('plan', {}).get('result') != 'success':
        errors.append('CI 计划未成功生成')
    required = plan.get('required', {})
    if set(required) != set(CATEGORIES) or not all(isinstance(value, bool) for value in required.values()):
        return [*errors, 'CI 计划缺少完整的任务分类']
    for category in CATEGORIES:
        result = needs.get(category, {}).get('result')
        allowed = ('success',) if required[category] else ('success', 'skipped')
        if result not in allowed:
            errors.append(f'{category}: {result or "missing"}，预期 {"/".join(allowed)}')
    return errors


def changed_paths(base: str) -> list[str]:
    """
    从 Git 获取变更文件，保留删除及重命名前后的路径。

    :param base: 已检出的比较基准提交
    :return: 相对仓库根目录的路径
    """
    result = subprocess.run(
        ['git', 'diff', '--no-renames', '--name-only', '-z', base, 'HEAD'],
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=60,
    )
    return [path for path in result.stdout.decode('utf-8').split('\0') if path]


def write_outputs(plan: dict[str, Any]) -> None:
    """
    输出 GitHub 任务参数及可审阅的执行摘要。

    :param plan: 本次运行计划
    :return: None
    """
    payload = {
        **plan['required'],
        **{key: value for key, value in plan.items() if key not in ('required', 'paths')},
        'plan_json': plan,
    }
    if output := os.environ.get('GITHUB_OUTPUT'):
        with Path(output).open('a', encoding='utf-8') as stream:
            for key, value in payload.items():
                stream.write(f'{key}={json.dumps(value, ensure_ascii=False, separators=(",", ":"))}\n')
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write('## CI 执行计划\n\n| 分类 | 执行 |\n|---|---|\n')
            for category, required in plan['required'].items():
                stream.write(f'| {category} | {"运行" if required else "无相关改动"} |\n')
            stream.write(f'\n完整矩阵：{plan["full"]}\n')
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def main() -> None:
    """
    执行变更选路或最终结果校验。

    :return: None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('plan', 'gate'))
    args = parser.parse_args()
    if args.command == 'gate':
        plan = json.loads(os.environ.get('PLAN_JSON') or '{}')
        needs = json.loads(os.environ.get('NEEDS_JSON') or '{}')
        errors = check_results(plan, needs)
        if errors:
            raise SystemExit('\n'.join(errors))
        print('所有应执行的 CI 分类均已通过。')
        return
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    event_name = os.environ['GITHUB_EVENT_NAME']
    full = event_name in ('push', 'schedule') or (
        str(event.get('inputs', {}).get('full', 'true')).lower() == 'true' and event_name == 'workflow_dispatch'
    )
    base = event.get('pull_request', {}).get('base', {}).get('sha', '')
    paths = changed_paths(base) if base else ['.github/workflows/ci.yml']
    write_outputs(build_plan(paths, full=full))


if __name__ == '__main__':
    main()
