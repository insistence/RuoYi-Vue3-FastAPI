from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .payload import PluginScaffoldPlanPayload


class PluginV2ScaffoldBuilder:
    """
    独立 v2 插件源码工程模板构建器。
    """

    def __init__(self, backend_root: Path, frontend_root: Path) -> None:
        """
        初始化独立 v2 工程模板构建器。

        :param backend_root: 宿主后端项目根目录
        :param frontend_root: 宿主前端项目根目录，用于读取桥接 SDK
        :return: None
        """
        self.backend_root = backend_root
        self.frontend_root = frontend_root

    def build_plan(
        self, plugin_id: str, *, template: str, backend: bool, frontend: bool, test: bool, frontend_version: str
    ) -> dict[str, Any]:
        """
        生成独立源码工程的文件计划，不安装、启用或导入插件。

        :param plugin_id: 插件 ID
        :param template: v2 模板名称
        :param backend: 是否创建后端工程
        :param frontend: 是否创建前端工程
        :param test: 是否生成本地合约测试
        :param frontend_version: 旧版前端选项，v2 模板仅接受 auto
        :return: 包含生成文件、目标目录与冲突信息的计划
        """
        native = template.startswith('rust-')
        bundle = template.endswith('-bundle')
        if not backend:
            raise ValueError('v2 ASGI 模板需要后端，不能使用 --frontend-only')
        if bundle and not frontend:
            raise ValueError('bundle 模板不能使用 --backend-only；仅 API 请使用 python-asgi 或 rust-asgi')
        if frontend_version != 'auto':
            raise ValueError('v2 模板不使用 --frontend-version；独立 bundle 与宿主 Vue 版本无关')

        root = self.backend_root / 'plugin-projects' / plugin_id
        replacements = {
            '__PLUGIN_ID__': plugin_id,
            '__DISTRIBUTION__': 'ruoyi-plugin-' + plugin_id.replace('_', '-'),
            '__RUNTIME__': 'rust' if native else 'python',
            '__BUNDLE__': str(bundle),
            '__NATIVE__': str(native),
        }
        entries = [
            (root / 'plugin.yaml', self._manifest(plugin_id, native=native, bundle=bundle)),
            (root / 'README.md', self._readme(plugin_id, native=native, bundle=bundle, test=test)),
            (root / '.gitignore', self._render('gitignore', replacements)),
        ]
        if native:
            for name in ('Cargo.toml', 'Cargo.lock', 'pyproject.toml', 'src/lib.rs'):
                resource = name.replace('src/', '')
                entries.append((root / name, self._render(f'native/{resource}', replacements)))
            entries.append(
                (
                    root / 'python' / f'ruoyi_plugin_{plugin_id}' / '__init__.py',
                    '',
                )
            )
        else:
            entries.extend(
                (root / name, self._render(f'python/{name}', replacements))
                for name in ('__init__.py', 'build_release.py')
            )
        if test:
            entries.append((root / 'tests' / 'test_plugin.py', self._render('test_plugin.py', replacements)))
        if bundle:
            sdk_path = self.frontend_root / 'src' / 'utils' / 'pluginBridge.js'
            if not sdk_path.is_file():
                raise ValueError(f'缺少宿主桥接 SDK：{sdk_path}；请配置正确的 RUOYI_PLUGIN_FRONTEND_ROOT')
            entries.append((root / 'web' / 'vendor' / 'pluginBridge.js', sdk_path.read_text(encoding='utf-8')))
            entries.extend(
                (root / 'web' / name, self._render(f'web/{name.removeprefix("src/")}', replacements))
                for name in ('index.html', 'package.json', 'vite.config.js', 'src/main.js', 'src/style.css')
            )

        payload = PluginScaffoldPlanPayload(
            template=template,
            backend=True,
            frontend=bundle,
            migration=False,
            seed=False,
            job=False,
            config=False,
            crud=False,
            test=test,
            backend_test=test,
            frontend_test=False,
            frontend_version=None,
            target_dirs=[str(root)],
            files=entries,
            conflicts=[str(root)] if root.exists() else [],
        ).to_payload()
        payload.update(manifestVersion=2, runtime='native' if native else 'python', sourceDir=root.as_posix())
        return payload

    @staticmethod
    def _render(resource: str, replacements: dict[str, str]) -> str:
        """
        读取打包在 CLI 中的模板资源并替换占位符。

        :param resource: 相对于模板资源目录的文件名，不含 .tmpl 后缀
        :param replacements: 模板占位符及其替换内容
        :return: 完成占位符替换的模板内容
        """
        content = files('cli.runtime.plugin.scaffold').joinpath(f'assets/{resource}.tmpl').read_text(encoding='utf-8')
        for key, value in replacements.items():
            content = content.replace(key, value)
        return content

    @staticmethod
    def _manifest(plugin_id: str, *, native: bool, bundle: bool) -> str:
        """
        生成显式 ASGI 入口、权限与前端交付声明。

        :param plugin_id: 插件 ID
        :param native: 是否生成 Rust 原生插件
        :param bundle: 是否包含独立前端 bundle
        :return: manifest v2 的 YAML 内容
        """
        module = f'ruoyi_plugin_{plugin_id}' if native else f'plugins.{plugin_id}'
        entry_module = f'{module}._native' if native else module
        backend = {
            'runtime': 'native' if native else 'python',
            'integration': 'asgi',
            'module': module,
            'entrypoint': f'{entry_module}:create_plugin',
            'asgi': {'mountPath': f'/apps/{plugin_id}', 'lifespan': 'managed'},
            'health': {'checker': f'{entry_module}:health'},
        }
        if native:
            backend['native'] = {'distribution': 'ruoyi-plugin-' + plugin_id.replace('_', '-')}
        frontend: dict[str, Any] = {'delivery': {'type': 'bundle' if bundle else 'none'}}
        if bundle:
            frontend.update(
                bundle={'directory': 'web/dist', 'entry': 'index.html', 'spaFallback': True},
                menus=[
                    {
                        'name': plugin_id,
                        'path': plugin_id,
                        'component': 'PluginFrame',
                        'type': 'C',
                        'icon': 'component',
                        'perms': f'{plugin_id}:view',
                    }
                ],
            )
        return yaml.safe_dump(
            {
                'manifestVersion': 2,
                'id': plugin_id,
                'name': plugin_id,
                'version': '1.0.0',
                'description': '独立构建、通过宿主身份与权限访问的 ASGI 插件。',
                'backend': backend,
                'frontend': frontend,
                'permissions': [{'code': f'{plugin_id}:view', 'name': '访问插件'}],
                'compatibility': {'hostApiVersion': '^1.2.0', 'pythonVersion': '>=3.10'},
            },
            allow_unicode=True,
            sort_keys=False,
        )

    @staticmethod
    def _readme(plugin_id: str, *, native: bool, bundle: bool, test: bool) -> str:
        """
        生成与模板类型匹配的构建、测试及维护发布说明。

        :param plugin_id: 插件 ID
        :param native: 是否生成 Rust 原生插件
        :param bundle: 是否包含独立前端 bundle
        :param test: 是否生成本地合约测试
        :return: 工程 README 内容
        """
        root = f'plugin-projects/{plugin_id}'
        output = f'target/{plugin_id}-package'
        build = (
            f'python scripts/build_native_plugin.py --source {root} --output {output}'
            if native
            else f'python {root}/build_release.py --output {output}'
        )
        frontend_steps = (
            f'```bash\nnpm --prefix {root}/web install\nnpm --prefix {root}/web run build\n```\n\n'
            '提交生成的 package-lock.json；后续可用 `npm ci` 重现前端依赖。构建器只复制已构建的 '
            '`web/dist`，不会自动执行 npm。桥接 SDK 已从生成时的宿主复制到 `web/vendor`，升级宿主时应核对兼容性。\n\n'
            if bundle
            else ''
        )
        native_steps = (
            '需预先安装 Rust 工具链和匹配目标平台的编译工具，以及 `maturin>=1.15,<2`。'
            '模板包含 Cargo.lock，构建使用 `--locked`。二进制必须匹配部署系统、架构、Python ABI。\n\n'
            if native
            else 'Python 交付目录包含业务 Python 源码；签名验证不提供源码保护。\n\n'
        )
        packaging_note = (
            '原生打包器复制扩展、发行包元数据、清单及声明的交付资源；不复制 Rust 工程。'
            if native
            else 'Python 打包脚本只复制本模板的清单、入口和已构建 bundle；'
            '增加业务模块、SQL 或资源后，应明确扩展该复制清单并测试。'
        )
        tests = (
            'Windows PowerShell：\n\n'
            f'```powershell\n$env:RUOYI_PLUGIN_DIRECTORY = (Resolve-Path "{output}/{plugin_id}").Path\n'
            f'python -m pytest {root}/tests -q\n```\n\n'
            'macOS / Linux（Bash、Zsh）：\n\n'
            f'```bash\nexport RUOYI_PLUGIN_DIRECTORY="$(pwd)/{output}/{plugin_id}"\n'
            f'python -m pytest {root}/tests -q\n```\n\n'
            '测试使用宿主 SDK 和本地请求上下文替身，不连接数据库。Rust 模板未指定构建产物时明确跳过，'
            'Python 模板也可直接测试源码目录。测试不代替真实登录、数据库和多 worker 发布验收。\n\n'
            if test
            else ''
        )
        return f"""# {plugin_id}

这是 manifest v2 的 {'Rust native' if native else 'Python'} ASGI 源码工程{'，包含独立前端 bundle' if bundle else ''}。
源码位于 `{root}`，创建工程不会安装、启用或导入插件。下面的命令均在宿主后端根目录执行。

先创建并激活 Python 3.10–3.13 环境；已有宿主环境可直接激活并使用，无需重复创建。

Windows PowerShell：

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

macOS / Linux（Bash、Zsh）：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

随后按宿主数据库类型安装依赖：MySQL 使用 `python -m pip install -r requirements.txt`，
PostgreSQL 使用 `python -m pip install -r requirements-pg.txt`。下文 `python` 指向已激活环境。
通用构建与发布命令适用于 Windows PowerShell、macOS 和 Linux；Shell 语法不同的步骤分别列出。

## 构建与测试

{frontend_steps}{native_steps}```bash
{build}
```

每次使用不存在的新输出目录。交付目录为 `{output}/{plugin_id}`；不要签名整个源码工程、wheel 输出目录或 Cargo 工程。
{packaging_note}

{tests}## 签名与维护发布

先在宿主启用 `PLUGIN_ARTIFACT_ENABLED`，设置制品存储位置和外部信任公钥文件；公钥必须授权 `{plugin_id}`。
发布者 Ed25519 PKCS8 私钥放在源码及交付目录之外。以下路径和大写占位符需要替换为实际值。

```bash
ruoyi plugin artifact build {output}/{plugin_id} target/{plugin_id}-1.0.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher
ruoyi plugin artifact verify target/{plugin_id}-1.0.0.rpk --env prod
ruoyi plugin artifact import target/{plugin_id}-1.0.0.rpk --env prod --allow-prod --yes
ruoyi plugin release plan {plugin_id} DIGEST --env prod
```

确认计划后停止全部宿主 worker，再执行以下维护操作。`DIGEST` 使用导入结果；`GENERATION` 使用 prepare 后 status 返回的值。

```bash
ruoyi plugin release prepare {plugin_id} DIGEST --maintenance --env prod --allow-prod --yes
ruoyi plugin release status --plugin-id {plugin_id} --env prod
ruoyi plugin release select {plugin_id} DIGEST --expected-generation GENERATION --expected-workers 1 --maintenance --env prod --allow-prod --yes
```

将 expected-workers 改为实际数量，重启全部 worker 后再次查询 status；仅所有预期 worker 均就绪才算完成。
`installedVersion` 是数据准备状态，选择目标不会立即切换运行代码。更新版本时同步清单{'、Cargo.toml、Cargo.lock 和 pyproject.toml' if native else ''}。
旧代码回滚必须兼容当前数据库，不撤销迁移。不要覆盖已加载二进制或修改不可变制品目录。

`plugins/{plugin_id}` 如有同名源码目录，会与制品发布冲突；在维护窗口备份并移出后才能导入。
原生插件与同源 iframe 均为可信扩展，不构成安全沙箱。

## 访问

权限为 `{plugin_id}:view`，接口为 `GET /apps/{plugin_id}/api/info`。请求沿用宿主认证与传输加密策略。
{'由宿主 PluginFrame 打开页面；前端通过 createPluginClient.ready 建立会话，再 request({method: "GET", path: "info"})，不得读取或保存管理员 token。桥仅支持有大小限制的 JSON 请求，不支持上传、流式响应或任意外部 URL。' if bundle else '先给角色授予插件权限，再通过宿主认证调用 API；子应用不提供独立登录。'}
"""
