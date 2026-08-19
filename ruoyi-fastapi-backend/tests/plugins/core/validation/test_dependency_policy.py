import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import config.env as env_config
from plugins.core.validation.dependencies import DependencyInstallPlan, DependencyInstallPlanItem
from plugins.core.validation.dependency_policy import (
    DependencyInstallPolicyConfig,
    DependencyInstallPolicyEvaluator,
)

CONFIGURED_INSTALL_TIMEOUT_SECONDS = 42


def build_plan(*items: DependencyInstallPlanItem) -> DependencyInstallPlan:
    """构建测试用依赖安装计划。"""
    return DependencyInstallPlan(plugin_id='demo', items=list(items))


def build_python_item(requirement: str = 'openai>=2.0.0') -> DependencyInstallPlanItem:
    """构建测试用 Python 安装计划项。"""
    return DependencyInstallPlanItem(
        kind='python',
        requirement=requirement,
        name='openai',
        command=[sys.executable, '-m', 'pip', 'install', requirement],
        workdir='/tmp/backend',
        reason='Python 依赖未安装：openai',
    )


def build_npm_item(
    requirement: str = 'dayjs>=1.11.0,<2.0.0',
    *,
    kind: str = 'npm',
    name: str = 'dayjs',
) -> DependencyInstallPlanItem:
    """构建测试用 npm 安装计划项。"""
    return DependencyInstallPlanItem(
        kind=kind,
        requirement=requirement,
        name=name,
        command=['npm', 'install', requirement],
        workdir='/tmp/frontend',
        reason=f'npm 依赖未安装：{name}',
    )


def test_config_env_exposes_plugin_dependency_policy_config() -> None:
    """校验统一配置入口暴露插件依赖策略配置。"""
    config = env_config.get_config.get_plugin_dependency_policy_config()

    assert isinstance(config, env_config.PluginDependencyPolicySettings)
    assert isinstance(env_config.PluginDependencyPolicyConfig, env_config.PluginDependencyPolicySettings)


def test_dependency_policy_reads_unified_config_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """校验依赖策略从统一配置入口读取默认策略。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    allowlist_path = tmp_path / 'allowlist.yaml'
    offline_dir = tmp_path / 'artifacts'
    config = SimpleNamespace(
        plugin_dependency_policy_mode='prod=offline,dev=explicit',
        plugin_dependency_allow_prod_install=True,
        plugin_dependency_require_yes=False,
        plugin_dependency_require_lockfile=True,
        plugin_dependency_require_allowlist=True,
        plugin_dependency_lockfile=str(lockfile_path),
        plugin_dependency_allowlist=str(allowlist_path),
        plugin_dependency_offline_dir=str(offline_dir),
        plugin_dependency_pip_index_url='https://pypi.example/simple',
        plugin_dependency_npm_registry='https://npm.example',
        plugin_dependency_install_timeout=CONFIGURED_INSTALL_TIMEOUT_SECONDS,
    )
    monkeypatch.setattr(env_config.get_config, 'get_plugin_dependency_policy_config', lambda: config, raising=False)

    policy_config = DependencyInstallPolicyConfig.from_environment(env='prod')

    assert policy_config.mode == 'offline'
    assert policy_config.allow_prod_install is True
    assert policy_config.require_yes is False
    assert policy_config.require_lockfile is True
    assert policy_config.require_allowlist is True
    assert policy_config.lockfile_path == lockfile_path
    assert policy_config.allowlist_path == allowlist_path
    assert policy_config.offline_dir == offline_dir
    assert policy_config.pip_index_url == 'https://pypi.example/simple'
    assert policy_config.npm_registry == 'https://npm.example'
    assert policy_config.install_timeout_seconds == CONFIGURED_INSTALL_TIMEOUT_SECONDS


def test_cli_dependency_policy_separates_channel_authorization_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """校验 CLI 授权不受生产环境 Web 限制配置影响。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    allowlist_path = tmp_path / 'allowlist.yaml'
    config = SimpleNamespace(
        plugin_dependency_policy_mode='prod=plan_only,dev=explicit',
        plugin_dependency_allow_prod_install=False,
        plugin_dependency_require_yes=False,
        plugin_dependency_require_lockfile=True,
        plugin_dependency_require_allowlist=True,
        plugin_dependency_lockfile=str(lockfile_path),
        plugin_dependency_allowlist=str(allowlist_path),
        plugin_dependency_offline_dir='',
        plugin_dependency_pip_index_url='https://pypi.example/simple',
        plugin_dependency_npm_registry='',
        plugin_dependency_install_timeout=CONFIGURED_INSTALL_TIMEOUT_SECONDS,
    )
    monkeypatch.setattr(env_config.get_config, 'get_plugin_dependency_policy_config', lambda: config, raising=False)

    policy_config = DependencyInstallPolicyConfig.from_cli_environment(
        env='prod',
        allow_prod=True,
        allow_unlisted=True,
        require_lockfile=False,
    )
    decision = DependencyInstallPolicyEvaluator(policy_config).evaluate(build_plan(build_python_item()), confirmed=True)

    assert policy_config.mode == 'explicit'
    assert policy_config.allow_prod is True
    assert policy_config.allow_prod_install is True
    assert policy_config.require_yes is True
    assert policy_config.require_lockfile is False
    assert policy_config.require_allowlist is False
    assert policy_config.allowlist_path == allowlist_path
    assert policy_config.pip_index_url == 'https://pypi.example/simple'
    assert policy_config.install_timeout_seconds == CONFIGURED_INSTALL_TIMEOUT_SECONDS
    assert decision.allowed is True


def test_cli_dependency_policy_still_requires_explicit_prod_authorization() -> None:
    """校验 CLI 生产安装仍必须显式传入 allow-prod。"""
    policy_config = DependencyInstallPolicyConfig.from_cli_environment(
        env='prod',
        allow_unlisted=True,
        require_lockfile=False,
    )

    decision = DependencyInstallPolicyEvaluator(policy_config).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '需要 --allow-prod 确认生产环境安装' in decision.requirements


def test_dependency_policy_reads_require_lockfile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验策略配置会读取锁文件要求环境变量。"""
    monkeypatch.setenv('PLUGIN_DEPENDENCY_REQUIRE_LOCKFILE', 'true')

    config = DependencyInstallPolicyConfig.from_environment(env='dev')

    assert config.require_lockfile is True
    assert config.resolved_require_lockfile is True


def test_dependency_policy_rejects_invalid_mode_from_unified_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验依赖安装策略拒绝非法策略模式，而不是静默回退默认值。"""
    config = SimpleNamespace(
        plugin_dependency_policy_mode='prod=lockd',
        plugin_dependency_allow_prod_install=False,
        plugin_dependency_require_yes=True,
        plugin_dependency_require_lockfile=None,
        plugin_dependency_require_allowlist=None,
        plugin_dependency_lockfile=None,
        plugin_dependency_allowlist=None,
        plugin_dependency_offline_dir=None,
        plugin_dependency_pip_index_url=None,
        plugin_dependency_npm_registry=None,
        plugin_dependency_install_timeout=600,
    )
    monkeypatch.setattr(env_config.get_config, 'get_plugin_dependency_policy_config', lambda: config, raising=False)

    with pytest.raises(ValueError, match='非法插件依赖安装策略模式'):
        DependencyInstallPolicyConfig.from_environment(env='prod')


def test_dependency_policy_rejects_invalid_bool_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验依赖安装策略拒绝非法布尔配置，而不是把未知字符串当作 False。"""
    monkeypatch.setenv('PLUGIN_DEPENDENCY_REQUIRE_LOCKFILE', 'fales')

    with pytest.raises(ValueError, match='非法插件依赖策略布尔配置'):
        DependencyInstallPolicyConfig.from_environment(env='dev')


def test_dependency_policy_plan_only_blocks_real_install() -> None:
    """校验 plan_only 策略只允许生成计划，不允许真实安装。"""
    decision = DependencyInstallPolicyEvaluator(DependencyInstallPolicyConfig(mode='plan_only', env='dev')).evaluate(
        build_plan(build_python_item()), confirmed=True
    )

    assert decision.allowed is False
    assert decision.mode == 'plan_only'
    assert '当前策略仅允许生成依赖安装计划' in decision.reasons
    assert decision.items[0].allowed is False


def test_dependency_policy_explicit_requires_confirmation_before_install() -> None:
    """校验 explicit 策略执行真实安装前必须显式确认。"""
    evaluator = DependencyInstallPolicyEvaluator(DependencyInstallPolicyConfig(mode='explicit', env='dev'))

    blocked = evaluator.evaluate(build_plan(build_python_item()), confirmed=False)
    allowed = evaluator.evaluate(build_plan(build_python_item()), confirmed=True)

    assert blocked.allowed is False
    assert '需要显式确认 --yes' in blocked.requirements
    assert allowed.allowed is True
    assert allowed.reasons == []


def test_dependency_policy_locked_mode_requires_matching_lockfile_and_rewrites_command(tmp_path: Path) -> None:
    """校验 locked 策略要求锁文件匹配，并使用锁定版本生成安装命令。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0
    resolvedVersion: 2.17.0
    hashes:
      - sha256:demo
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is True
    assert decision.install_plan_items[0].command[-1] == 'openai==2.17.0'
    assert decision.items[0].locked_version == '2.17.0'


def test_dependency_policy_locked_mode_blocks_lockfile_mismatch(tmp_path: Path) -> None:
    """校验 locked 策略阻断与插件依赖声明不一致的锁文件。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai==1.0.0
    resolvedVersion: 1.0.0
    hashes:
      - sha256:demo
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '锁文件缺少匹配依赖：python openai openai>=2.0.0' in decision.reasons


def test_dependency_policy_locked_mode_blocks_resolved_version_outside_requirement(tmp_path: Path) -> None:
    """校验 locked 策略阻断锁文件 resolvedVersion 超出插件依赖声明范围。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0,<3.0.0
    resolvedVersion: 9.0.0
    hashes:
      - sha256:demo
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item('openai>=2.0.0,<3.0.0')), confirmed=True)

    assert decision.allowed is False
    assert '锁文件 resolvedVersion 不满足依赖声明：python openai 9.0.0 not in openai>=2.0.0,<3.0.0' in decision.reasons


@pytest.mark.parametrize(
    ('requirement', 'resolved_version'),
    [
        ('openai>=100; python_version >= "3"', '1.0.0'),
        ('openai~=2.0', '3.0.0'),
        ('openai===2.0', '3.0.0'),
    ],
)
def test_dependency_policy_locked_mode_uses_pep440_semantics(
    tmp_path: Path,
    requirement: str,
    resolved_version: str,
) -> None:
    """校验锁定模式使用 PEP 440 语义验证 Python 版本。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        f"""
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: '{requirement}'
    resolvedVersion: {resolved_version}
    hashes:
      - sha256:demo
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item(requirement)), confirmed=True)

    assert decision.allowed is False
    assert (
        f'锁文件 resolvedVersion 不满足依赖声明：python openai {resolved_version} not in {requirement}'
        in decision.reasons
    )


def test_dependency_policy_locked_mode_blocks_extra_lockfile_entry(tmp_path: Path) -> None:
    """校验 locked 策略阻断锁文件中的未声明依赖。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0
    resolvedVersion: 2.17.0
    hashes:
      - sha256:demo
  - name: requests
    requirement: requests>=2.32.0
    resolvedVersion: 2.32.4
    hashes:
      - sha256:demo
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '锁文件包含未声明依赖：python requests requests>=2.32.0' in decision.reasons


def test_dependency_policy_locked_mode_blocks_missing_python_hash(tmp_path: Path) -> None:
    """校验 locked 策略阻断缺少 Python 哈希的锁文件。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0
    resolvedVersion: 2.17.0
npm: []
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '锁文件缺少 Python 哈希：python openai' in decision.reasons


def test_dependency_policy_locked_mode_blocks_missing_npm_integrity(tmp_path: Path) -> None:
    """校验 locked 策略阻断缺少 npm integrity 的锁文件。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python: []
npm:
  - name: dayjs
    requirement: dayjs>=1.11.0
    resolvedVersion: 1.11.19
npmDev: []
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='locked',
            env='stage',
            lockfile_path=lockfile_path,
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_npm_item('dayjs>=1.11.0')), confirmed=True)

    assert decision.allowed is False
    assert '锁文件缺少 npm integrity：npm dayjs' in decision.reasons


def test_dependency_policy_offline_mode_uses_local_artifact_command(tmp_path: Path) -> None:
    """校验 offline 策略只生成本地离线制品安装命令。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0
    resolvedVersion: 2.17.0
    hashes:
      - sha256:ba59926159d2aa256eb8739b8da7e2b574b960e1202c6d624cbe981cef996c91
npm: []
npmDev: []
""",
        encoding='utf-8',
    )
    python_artifact_dir = tmp_path / 'artifacts' / 'python'
    python_artifact_dir.mkdir(parents=True)
    (python_artifact_dir / 'openai-2.17.0-py3-none-any.whl').write_text('wheel', encoding='utf-8')

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='offline',
            env='prod',
            allow_prod=True,
            allow_prod_install=True,
            lockfile_path=lockfile_path,
            offline_dir=tmp_path / 'artifacts',
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    command = decision.install_plan_items[0].command
    assert decision.allowed is True
    assert '--no-index' in command
    assert '--find-links' in command
    assert command[-1] == 'openai==2.17.0'
    assert decision.items[0].artifact_path is not None


def test_dependency_policy_offline_mode_blocks_python_artifact_hash_mismatch(tmp_path: Path) -> None:
    """校验 offline 策略阻断离线 Python 制品哈希不匹配。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python:
  - name: openai
    requirement: openai>=2.0.0
    resolvedVersion: 2.17.0
    hashes:
      - sha256:0000000000000000000000000000000000000000000000000000000000000000
npm: []
npmDev: []
""",
        encoding='utf-8',
    )
    python_artifact_dir = tmp_path / 'artifacts' / 'python'
    python_artifact_dir.mkdir(parents=True)
    (python_artifact_dir / 'openai-2.17.0-py3-none-any.whl').write_text('wheel', encoding='utf-8')

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='offline',
            env='prod',
            allow_prod=True,
            allow_prod_install=True,
            lockfile_path=lockfile_path,
            offline_dir=tmp_path / 'artifacts',
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '离线制品哈希不匹配：python openai 2.17.0' in decision.reasons


def test_dependency_policy_offline_mode_uses_npm_artifact_with_integrity(tmp_path: Path) -> None:
    """校验 offline 策略校验 npm integrity 并生成本地 tgz 安装命令。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python: []
npm:
  - name: dayjs
    requirement: dayjs>=1.11.0
    resolvedVersion: 1.11.19
    integrity: sha512-7cLHJ5z9Zemfs6J5hlhSsEL/8lEmzySE8Hux1E19Gfdf7RnQgL5uwQeYVZzxDOFCKUaUY+5hCYRh6DcKxRRPrg==
npmDev: []
""",
        encoding='utf-8',
    )
    npm_artifact_dir = tmp_path / 'artifacts' / 'npm'
    npm_artifact_dir.mkdir(parents=True)
    artifact_path = npm_artifact_dir / 'dayjs-1.11.19.tgz'
    artifact_path.write_text('tgz', encoding='utf-8')

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='offline',
            env='prod',
            allow_prod=True,
            allow_prod_install=True,
            lockfile_path=lockfile_path,
            offline_dir=tmp_path / 'artifacts',
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_npm_item('dayjs>=1.11.0')), confirmed=True)

    assert decision.allowed is True
    assert decision.install_plan_items[0].command == ['npm', 'install', str(artifact_path), '--offline']
    assert decision.items[0].artifact_path == str(artifact_path)


def test_dependency_policy_offline_mode_blocks_npm_integrity_mismatch(tmp_path: Path) -> None:
    """校验 offline 策略阻断 npm 离线制品 integrity 不匹配。"""
    lockfile_path = tmp_path / 'plugin.lock.yaml'
    lockfile_path.write_text(
        """
plugin: demo
version: 1.0.0
python: []
npm:
  - name: dayjs
    requirement: dayjs>=1.11.0
    resolvedVersion: 1.11.19
    integrity: sha512-invalid
npmDev: []
""",
        encoding='utf-8',
    )
    npm_artifact_dir = tmp_path / 'artifacts' / 'npm'
    npm_artifact_dir.mkdir(parents=True)
    (npm_artifact_dir / 'dayjs-1.11.19.tgz').write_text('tgz', encoding='utf-8')

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='offline',
            env='prod',
            allow_prod=True,
            allow_prod_install=True,
            lockfile_path=lockfile_path,
            offline_dir=tmp_path / 'artifacts',
            require_allowlist=False,
        )
    ).evaluate(build_plan(build_npm_item('dayjs>=1.11.0')), confirmed=True)

    assert decision.allowed is False
    assert '离线制品 integrity 不匹配：npm dayjs 1.11.19' in decision.reasons


def test_dependency_policy_allowlist_blocks_unlisted_dependency(tmp_path: Path) -> None:
    """校验要求允许列表时阻断未命中的依赖。"""
    allowlist_path = tmp_path / 'allowlist.yaml'
    allowlist_path.write_text(
        """
python:
  requests:
    versions:
      - ">=2.32.0,<3.0.0"
npm: {}
npmDev: {}
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='explicit',
            env='dev',
            require_allowlist=True,
            allowlist_path=allowlist_path,
        )
    ).evaluate(build_plan(build_python_item()), confirmed=True)

    assert decision.allowed is False
    assert '依赖未命中允许列表：python openai' in decision.reasons


def test_dependency_policy_allowlist_accepts_contained_python_range(tmp_path: Path) -> None:
    """校验允许列表接受完全落入允许范围的 Python 依赖范围。"""
    allowlist_path = tmp_path / 'allowlist.yaml'
    allowlist_path.write_text(
        """
python:
  openai:
    versions:
      - ">=2.0.0,<3.0.0"
npm: {}
npmDev: {}
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='explicit',
            env='dev',
            require_allowlist=True,
            allowlist_path=allowlist_path,
        )
    ).evaluate(build_plan(build_python_item('openai>=2.1.0,<3.0.0')), confirmed=True)

    assert decision.allowed is True


def test_dependency_policy_allowlist_ignores_applicable_python_marker(tmp_path: Path) -> None:
    """校验允许列表匹配时忽略已满足的 Python 环境标记。"""
    allowlist_path = tmp_path / 'allowlist.yaml'
    allowlist_path.write_text(
        """
python:
  openai:
    versions:
      - ">=2.0.0,<3.0.0"
npm: {}
npmDev: {}
""",
        encoding='utf-8',
    )
    requirement = 'openai>=2.1.0,<3.0.0; python_version >= "3"'

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='explicit',
            env='dev',
            require_allowlist=True,
            allowlist_path=allowlist_path,
        )
    ).evaluate(build_plan(build_python_item(requirement)), confirmed=True)

    assert decision.allowed is True


def test_dependency_policy_allowlist_blocks_unbounded_python_range(tmp_path: Path) -> None:
    """校验允许列表阻断无法证明完全落入允许范围的 Python 依赖范围。"""
    allowlist_path = tmp_path / 'allowlist.yaml'
    allowlist_path.write_text(
        """
python:
  openai:
    versions:
      - ">=2.0.0,<3.0.0"
npm: {}
npmDev: {}
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='explicit',
            env='dev',
            require_allowlist=True,
            allowlist_path=allowlist_path,
        )
    ).evaluate(build_plan(build_python_item('openai>=2.1.0')), confirmed=True)

    assert decision.allowed is False
    assert '依赖未命中允许列表：python openai' in decision.reasons


def test_dependency_policy_allowlist_accepts_npm_and_dev_ranges(tmp_path: Path) -> None:
    """校验允许列表覆盖 npm 和 npmDev 依赖范围。"""
    allowlist_path = tmp_path / 'allowlist.yaml'
    allowlist_path.write_text(
        """
python: {}
npm:
  dayjs:
    versions:
      - ">=1.11.0,<2.0.0"
npmDev:
  vitest:
    versions:
      - ">=3.0.0,<4.0.0"
""",
        encoding='utf-8',
    )

    decision = DependencyInstallPolicyEvaluator(
        DependencyInstallPolicyConfig(
            mode='explicit',
            env='dev',
            require_allowlist=True,
            allowlist_path=allowlist_path,
        )
    ).evaluate(
        build_plan(
            build_npm_item('dayjs>=1.11.1,<2.0.0'),
            build_npm_item('vitest>=3.1.0,<4.0.0', kind='npmDev', name='vitest'),
        ),
        confirmed=True,
    )

    assert decision.allowed is True
