# 插件开发手册

本文档面向插件开发者，说明如何在当前插件系统中创建、安装、启用、调试和发布插件。

本文覆盖 v1 源码插件和 v2 显式入口插件。未特别注明的权限、菜单、配置、依赖和迁移规则两者共用；自动扫描控制器及默认 `create` 模板属于 v1。按开发目标选择入口：

| 开发目标 | 使用说明 | 可运行示例 |
| --- | --- | --- |
| 沿用宿主源码页面和控制器扫描 | [快速开始](#2-快速开始)、[源码前端](#71-v1--source-页面) | [内置 AI 插件](../plugins/ai/README.md) |
| 显式 Router 或 ASGI 子应用 | [v2 清单](#510-v2-清单与能力组合)、[显式入口与 SDK](#66-v2-显式入口与宿主-sdk) | [Python ASGI](../plugins/examples/python/asgi_demo/README.md) |
| Rust 原生后端 | [原生插件](#68-rust-原生插件)、[项目脚手架与构建](#16-v2-项目脚手架与完整构建) | [Rust 示例](../plugins/examples/rust/rust_demo/README.md) |
| 独立构建的插件页面 | [bundle 页面](#72-v2-独立-bundle-页面)、[浏览器 SDK](#73-bundle-浏览器-sdk) | [Python bundle](../plugins/examples/python/bundle_demo/README.md) |
| 持久化业务与升级 | [受控 Python 交付](#162-python-业务模块与迁移交付)、[显式事务](#66-v2-显式入口与宿主-sdk) | [任务 CRUD 示例](../plugins/examples/python/task_demo/README.md) |
| 签名交付与生产维护 | [制品与发布](#15-v2-签名制品与维护发布)、[真实服务验收](#17-本地真实服务验收与-ci) | [Rust 签名发布示例](../plugins/examples/rust/rust_demo/README.md#签名制品与维护发布) |

目录插件与签名制品不能同时使用相同插件 ID。两种方式均遵守进程重启边界，不提供原生模块热替换。

后端命令使用已安装项目依赖的 Python 3.10–3.13 环境；创建与激活步骤见 [CLI 环境准备](cli_usage.md#22-安装依赖)。下文的 `python` 指向已激活环境，命令默认在后端目录执行。通用命令同时适用于 Windows PowerShell、macOS 和 Linux；环境变量等 Shell 语法分别列出。

## 1. 基本模型

插件由后端插件和可选前端插件组成。默认源码布局如下：

```text
ruoyi-fastapi-backend/plugins/<plugin_id>/
ruoyi-fastapi-frontend/<framework>/web/plugins/<plugin_id>/
```

`<framework>` 是前端框架标识。当前仓库提供 `vue2`、`vue3` 工程，各框架的源码页面分别维护，共用一份后端代码与 `plugin.yaml`。移动端位于 `ruoyi-fastapi-frontend/<framework>/mobile`，不作为 Web 插件的宿主构建目录。目录和依赖分类可以扩展到 `react` 等框架标识，但当前没有 React 工程。

开发示例统一位于后端 `plugins/examples/`，按实现语言分类：`python/` 保存 Python 示例，`rust/` 保存 Rust 原生插件工程。
该目录不参与插件发现和启动代际计算。使用示例时，按各自 README 构建后部署到 `plugins/<plugin_id>/`，或通过签名制品发布流程安装。

插件系统优先使用显式传入的目录，其次读取 `RUOYI_PLUGIN_BACKEND_ROOT`/`RUOYI_BACKEND_ROOT` 和 `RUOYI_PLUGIN_FRONTEND_ROOT`/`RUOYI_FRONTEND_ROOT`。默认框架为 `vue3`，对应 `ruoyi-fastapi-frontend/vue3/web`；设置 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2` 可选择 `vue2/web`，未设置该变量时也可使用 `RUOYI_FRONTEND_FRAMEWORK`。前端根目录变量可以指向具体 Web 工程，也可以指向 `ruoyi-fastapi-frontend` 聚合目录，由框架标识继续定位。旧版包含 `package.json` 的平铺前端目录仍受支持。非默认目录名的项目应优先配置根目录变量。

脚手架和 SDK 命令的 `--frontend-framework` 当前固定可选 `auto`、`vue2`、`vue3`，默认值为 `auto`。框架身份按以下顺序确定：显式选择 `vue2` 或 `vue3` 优先；`auto` 模式先读取标准目录 `ruoyi-fastapi-frontend/<framework>/{web,mobile}` 中的框架标识；独立工程再根据 `package.json` 依赖识别框架。标准目录标识不会被底层依赖覆盖。独立工程无法识别时会报错，不会退回 Vue3；未指定目标的目录选择仍默认定位 `vue3/web`。

CLI 选项的固定取值不改变底层通用框架目录与依赖分类结构。此前按版本命名的选择变量和命令选项不再提供别名，已有脚本需同步更新。

以下命令切换当前终端的宿主选择，后续依赖检查、安装及插件测试都针对该 Web 工程；不改变 HTTP 业务接口或插件生命周期状态。

```powershell
# Windows PowerShell
$env:RUOYI_PLUGIN_FRONTEND_FRAMEWORK = 'vue2'
```

```bash
# macOS / Linux
export RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2
```

切回 Vue3 时将变量值设为 `vue3`。每个 Web 工程需要单独安装前端依赖和构建，但后端插件只安装、启用一次。

后端插件必须包含 `plugin.yaml`。插件发现、安装、菜单、依赖、配置、迁移、种子数据和定时任务都以这个文件为入口。

`plugin.yaml` 只描述插件能力和资源。安装、启用、停用、升级等运行态由管理端或 CLI 生命周期命令维护；生命周期状态只使用 `discovered`、`installed`、`pending_upgrade`、`error`。

## 2. 快速开始

本节使用默认 v1 模板。创建 v2 工程时，直接使用[第 16 节](#16-v2-项目脚手架与完整构建)的 `python-asgi`、`python-bundle`、`rust-asgi` 或 `rust-bundle` 模板。

进入后端项目目录：

```bash
cd ruoyi-fastapi-backend
```

使用脚手架创建插件：

```bash
ruoyi plugin create demo --env=dev --template=full-stack
```

脚手架的 `--frontend-framework` 当前固定可选 `auto`、`vue2`、`vue3`，默认以 `auto` 识别目标框架。当前 v1 源码前端模板只提供 Vue 2（Element UI、Options API、CommonJS 测试）和 Vue 3（Element Plus、Composition API、ESM 测试）实现；`auto` 解析到其他框架时，生成源码页面会明确报错，提示该框架模板尚未支持。在聚合目录下，显式选择 `vue2` 或 `vue3` 还会选择对应的 `vue2/web` 或 `vue3/web` 输出目录：

```bash
ruoyi plugin create demo --env=dev --template=crud-page --frontend-framework=vue2
ruoyi plugin create demo --env=dev --template=crud-page --frontend-framework=vue3
```

脚手架结果中的 `frontendFramework` 记录所选前端框架。各框架工程共用后端实现和 `plugin.yaml`，前端依赖必须分别完整写入 `dependencies.frontend.<framework>` 的 `npm/npmDev`；多个框架都使用的包也需在各自分类中声明。检查和安装时根据目标 Web 工程选择对应分类，不跨分类合并。当前 Vue2、Vue3 页面分别使用 `vue2`、`vue3` 分类，并各自测试。字段规则见[依赖声明](#56-dependencies)。

常用模板：

- `minimal`：最小插件。
- `backend-only`：只生成后端插件。
- `full-stack`：生成后端和前端插件。
- `scheduled-job`：包含定时任务示例。
- `crud-page`：包含 CRUD 页面示例。

以上为 v1 模板。v2 独立源码工程可选择 `python-asgi`、`python-bundle`、`rust-asgi`、`rust-bundle`，生成位置和完整构建步骤见[第 16 节](#16-v2-项目脚手架与完整构建)。

先预览写入计划：

```bash
ruoyi plugin create demo --env=dev --template=full-stack --dry-run
```

开发过程常用命令：

```bash
ruoyi plugin check demo --env=dev
ruoyi plugin check-deps demo --env=dev
ruoyi plugin allowlist-example --env=dev --dry-run
ruoyi plugin allowlist-example --env=dev --output-path config/plugin_dependency_allowlist.yaml --overwrite
ruoyi plugin lock-deps demo --env=dev --dry-run
ruoyi plugin lock-deps demo --env=dev --offline-dir artifacts/plugin-dependencies --overwrite
ruoyi plugin install-deps demo --env=dev --dry-run
ruoyi plugin install-deps demo --env=dev --yes
ruoyi plugin install demo --env=dev --yes
ruoyi plugin enable demo --env=dev --yes
ruoyi plugin health demo --env=dev
ruoyi plugin test demo --env=dev
```

## 3. 目录结构

推荐后端结构：

```text
plugins/demo/
  plugin.yaml
  controller/
    demo_controller.py
  service/
    demo_service.py
  dao/
  entity/
    do/
    vo/
  hooks.py
  jobs.py
  migrations/
    mysql/001_init.sql
    postgresql/001_init.sql
  seeds/
    mysql/001_seed.sql
    postgresql/001_seed.sql
  README.md
```

推荐前端结构：

```text
<frontend-project>/plugins/demo/
  api/
    demo.js
  views/
    index.vue
  README.md
```

后端 Python 模块路径必须与插件 ID 对齐。例如插件 ID 为 `demo` 时，`backend.module` 必须是 `plugins.demo`。

## 4. plugin.yaml 示例

以下为 v1 清单示例；v2 的完整清单及差异见[第 5.10 节](#510-v2-清单与能力组合)。

```yaml
manifestVersion: 1
id: demo
name: 演示插件
version: 0.1.0
description: Demo plugin.

metadata:
  category: demo
  tags:
    - demo
    - sample
  author: RuoYi
  license: MIT
  homepage: ""
  repository: ""
  documentation: ""

backend:
  module: plugins.demo
  routers:
    autoScan: true
  migrations:
    - migrations/mysql/001_init.sql
    - migrations/postgresql/001_init.sql
  seeds:
    - seeds/mysql/001_seed.sql
    - seeds/postgresql/001_seed.sql
  hooks:
    onInstall: plugins.demo.hooks:on_install
    onStartup: plugins.demo.hooks:on_startup
  jobs:
    - id: cleanup
      name: 演示清理任务
      callable: plugins.demo.jobs.cleanup
      trigger: cron
      cronExpression: "0 0 * * * ?"
      enabled: true
      misfirePolicy: "3"
      concurrent: "1"

frontend:
  basePath: demo
  pluginId: demo
  viewsPath: views
  apiPath: api
  delivery:
    type: source
    buildRequired: true
  menus:
    - name: 演示插件
      path: demo
      component: Layout
      perms: ""
      type: M
      orderNum: 10
      icon: example
      children:
        - name: 演示页面
          path: index
          component: plugin/demo/index
          routeName: DemoIndex
          query: ""
          isFrame: 1
          isCache: 0
          perms: demo:list
          type: C
          orderNum: 1

permissions:
  - code: demo:list
    name: 演示列表
    description: 查看演示页面
  - code: demo:add
    name: 新增演示
  - code: demo:edit
    name: 修改演示
  - code: demo:remove
    name: 删除演示

dependencies:
  python:
    - requests>=2.32.0
  frontend:
    vue2:
      npm:
        - dayjs>=1.11.0
      npmDev: []
    vue3:
      npm:
        - dayjs>=1.11.0
      npmDev: []
  plugins:
    - id: ai
      version: ">=0.1.0"
      description: 依赖 AI 插件能力

compatibility:
  databases:
    - mysql
    - postgresql

config:
  items:
    - key: api_url
      label: API 地址
      type: string
      default: ""
      required: true
    - key: audit_log
      label: 记录日志
      type: boolean
      default: true
```

注意事项：

- `id` 只能使用小写字母、数字、下划线和中划线，并且必须以小写字母开头。
- `admin`、`system`、`monitor`、`tool` 是保留插件 ID。
- `permissions` 中必须声明菜单使用到的权限标识。
- 菜单权限格式使用小写冒号分隔，例如 `demo:list`。
- 插件组件路径必须使用 `plugin/<plugin_id>/<view_path>`。

## 5. plugin.yaml 参数说明

### 5.1 顶层字段

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `manifestVersion` | `number` | `1` | 插件清单版本，支持 `1` 和 `2`；显式入口必须声明 `2`。 |
| `id` | `string` | 必填 | 插件唯一标识。只能包含小写字母、数字和下划线，长度 2-64，必须以小写字母开头。不能使用 `admin`、`system`、`monitor`、`tool`。 |
| `name` | `string` | 必填 | 插件展示名称。 |
| `version` | `string` | 必填 | 插件源码版本，用于安装版本记录和升级判断。 |
| `description` | `string` | `""` | 插件说明。 |
| `metadata` | `object` | `{}` | 插件展示元数据。 |
| `backend` | `object` | 必填 | 后端能力声明。 |
| `frontend` | `object` | `{}` | 前端资源、菜单和交付声明。 |
| `permissions` | `object[] \| string[]` | `[]` | 插件权限声明列表。推荐对象写法；字符串简写会按 `code` 处理。 |
| `dependencies` | `object` | `{}` | Python、npm 和插件间依赖声明。 |
| `compatibility` | `object` | `{}` | 平台兼容性版本约束。 |
| `resources` | `object` | `{}` | 插件静态、上传、临时资源目录声明。 |
| `config` | `object` | `{}` | 插件配置项声明。 |

### 5.2 metadata

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `category` | `string` | `""` | 插件分类。 |
| `tags` | `string[]` | `[]` | 插件标签，不能重复。 |
| `author` | `string` | `""` | 插件作者。 |
| `license` | `string` | `""` | 插件许可证。 |
| `homepage` | `string` | `""` | 插件主页地址。 |
| `repository` | `string` | `""` | 插件代码仓库地址。 |
| `documentation` | `string` | `""` | 插件文档地址。 |

### 5.3 backend

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `module` | `string` | 必填 | Python 插件为 `plugins.<plugin_id>`；v2 native 插件为 `ruoyi_plugin_<plugin_id>`。 |
| `routers` | `object` | v1 为 `{ autoScan: true }` | 控制器自动扫描声明；v2 必须为 `false`，见第 5.10 节。 |
| `health` | `object` | `{}` | 健康检查声明。 |
| `migrations` | `string[]` | `[]` | 数据库迁移 SQL 脚本相对路径列表。 |
| `seeds` | `string[]` | `[]` | 初始化数据 SQL 脚本相对路径列表。 |
| `hooks` | `object` | `{}` | 生命周期钩子声明。 |
| `jobs` | `object[]` | `[]` | 插件定时任务声明。 |

`backend.routers`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `autoScan` | `boolean` | v1 为 `true`，v2 为 `false` | 是否按插件模块自动扫描并注册控制器；v2 只能由显式入口返回路由。 |

`backend.health`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `checker` | `string \| null` | `null` | 健康检查 callable，格式为 `<module_path>:<callable_name>`，例如 `plugins.demo.health:check`。 |

`backend.hooks`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `onInstall` | `string \| null` | `null` | 插件安装完成后的钩子。 |
| `onUpgrade` | `string \| null` | `null` | 插件升级完成后的钩子。 |
| `onStartup` | `string \| null` | `null` | 应用启动加载插件时执行的钩子。 |
| `onShutdown` | `string \| null` | `null` | 应用关闭插件时执行的钩子。 |
| `onPurge` | `string \| null` | `null` | 插件物理清理时执行的钩子。 |

钩子路径格式统一为 `<module_path>:<callable_name>`，例如 `plugins.demo.hooks:on_startup`。

`backend.jobs[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `id` | `string` | 必填 | 插件内任务唯一标识。只能包含小写字母、数字和下划线，长度 2-64，必须以小写字母开头。 |
| `name` | `string \| null` | `id` | 任务展示名称。 |
| `callable` | `string` | 必填 | 任务函数路径，格式为 `<module_path>.<callable_name>`。 |
| `trigger` | `"cron"` | `"cron"` | 任务触发器类型。 |
| `cronExpression` | `string` | 必填 | cron 表达式，不能为空。 |
| `args` | `string[]` | `[]` | 位置参数列表。 |
| `kwargs` | `object` | `{}` | 关键字参数。 |
| `enabled` | `boolean` | `true` | 任务安装后的默认状态。 |
| `description` | `string` | `""` | 任务说明。 |
| `misfirePolicy` | `"1" \| "2" \| "3"` | `"3"` | 计划执行错误策略。`1` 立即执行，`2` 执行一次，`3` 放弃执行。 |
| `concurrent` | `"0" \| "1"` | `"1"` | 是否允许并发执行。`0` 允许，`1` 禁止。 |
| `executor` | `"default" \| "processpool"` | `"default"` | v1 任务执行器；v2 只允许 `default`。 |
| `timeoutSeconds` | `number` | `30` | 仅 v2：异步任务超时秒数，必须大于 0 且不超过 86400。 |

### 5.4 frontend

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pluginId` | `string \| null` | `id` | 前端插件目录名，必须与插件 ID 一致。 |
| `basePath` | `string \| null` | `id` | 前端基础路径。只能包含小写字母、数字、下划线、中划线和正斜杠。 |
| `viewsPath` | `string` | `"views"` | 前端视图目录。 |
| `apiPath` | `string` | `"api"` | 前端 API 目录。 |
| `delivery` | `object` | `{}` | 前端交付声明。 |
| `menus` | `object[]` | `[]` | 插件菜单树。 |

`frontend.delivery`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `type` | `"none" \| "source" \| "bundle"` | `"none"` | v1 支持 `none/source`，v2 增加 `bundle`。未显式选择 bundle 时，存在菜单或 npm 依赖会按源码交付处理。 |
| `buildRequired` | `boolean` | `false` | 前端资源是否需要构建后生效。源码交付时会自动视为需要构建。 |

`frontend.menus[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `string` | 必填 | 菜单名称。 |
| `path` | `string` | 必填 | 菜单路由路径。普通菜单只能包含小写字母、数字、下划线、中划线和正斜杠，必须以小写字母开头；外链菜单必须使用 `http://` 或 `https://` 地址。 |
| `component` | `string` | `"Layout"` | 核心布局允许 `Layout`、`ParentView`、`InnerLink`；源码页面使用 `plugin/<plugin_id>/<view_path>`，v2 bundle 页面使用 `PluginFrame`。 |
| `perms` | `string` | `""` | 权限标识。非空时必须在顶层 `permissions` 中声明。 |
| `icon` | `string` | `"#"` | 菜单图标。 |
| `type` | `"M" \| "C" \| "F"` | `"C"` | 菜单类型。`M` 目录，`C` 菜单，`F` 按钮。 |
| `orderNum` | `number` | `0` | 菜单排序值。 |
| `query` | `string \| null` | `null` | 路由参数。 |
| `routeName` | `string \| null` | `null` | 路由名称。 |
| `isFrame` | `0 \| 1` | `1` | 是否为外链。沿用系统菜单字段约定，`0` 是，`1` 否。 |
| `isCache` | `0 \| 1` | `0` | 是否缓存。沿用系统菜单字段约定，`0` 缓存，`1` 不缓存。 |
| `visible` | `"0" \| "1"` | `"0"` | 菜单是否显示。沿用系统菜单字段约定。 |
| `status` | `"0" \| "1"` | `"0"` | 菜单状态。沿用系统菜单字段约定。 |
| `children` | `object[]` | `[]` | 子菜单列表，结构同 `frontend.menus[]`。 |

### 5.5 permissions

`permissions` 是插件声明的权限列表。菜单 `perms` 使用到的权限必须出现在这里。

```yaml
permissions:
  - code: demo:list
    name: 演示列表
    description: 查看演示页面
  - code: demo:add
    name: 新增演示
```

也支持字符串简写：

```yaml
permissions:
  - demo:list
  - demo:add
```

`permissions[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `code` | `string` | 必填 | 权限标识。也兼容使用 `perms` 或 `permission` 字段名。 |
| `name` | `string \| null` | `null` | 权限展示名称。未显式声明为菜单的权限会自动生成按钮菜单，此字段会作为按钮菜单名称。 |
| `description` | `string` | `""` | 权限说明。 |

要求：

- 权限不能重复。
- 权限格式为小写冒号分隔，例如 `demo:list`、`demo:item:add`。

### 5.6 dependencies

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `python` | `string[]` | `[]` | Python 依赖声明，例如 `requests>=2.32.0`。 |
| `frontend` | `object` | `{}` | 以安全的小写框架标识为键，完整声明各框架的前端依赖，如 `vue2`、`vue3`、`react`。 |
| `frontend.<framework>.npm` | `string[]` | `[]` | 对应框架的全部前端运行依赖，例如 `dayjs>=1.11.0`。 |
| `frontend.<framework>.npmDev` | `string[]` | `[]` | 对应框架的全部前端开发依赖。 |
| `plugins` | `object[]` | `[]` | 插件间依赖声明。 |

同一个后端插件的前端依赖按框架分类声明，以下是当前 Vue2、Vue3 实现的示例：

```yaml
dependencies:
  frontend:
    vue2:
      npm:
        - dayjs>=1.11.0
        - markstream-vue2==0.0.50
      npmDev: []
    vue3:
      npm:
        - dayjs>=1.11.0
        - markstream-vue==1.0.9-beta.2
        - stream-diffs==0.0.2
      npmDev:
        - vite-plugin-monaco-editor-esm==2.0.2
```

`frontend` 的键不限于 `vue2`、`vue3`，也接受 `react` 等安全的小写框架标识。新增分类只声明该框架的依赖，不会自动生成对应前端工程或源码模板。

插件系统解析选定 Web 工程的框架，仅使用对应分类内的 `npm/npmDev`，不会读取其他框架的依赖。未声明目标框架分类时，该宿主没有 npm 依赖；未声明 `frontend` 时，插件没有宿主前端依赖。多个框架都需要的包必须在各自分类中分别列出，不设公共依赖层。

旧顶层 `dependencies.npm`、`dependencies.npmDev` 已移除，清单校验会拒绝，不会自动迁移或合并。升级已有插件时，请将原前端依赖完整迁入对应框架分类；同时支持多个框架的插件需分别维护完整列表。这里的框架标识与 `manifestVersion: 1/2` 无关。

`dependencies.plugins[]` 支持对象写法：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `id` | `string` | 必填 | 依赖插件 ID。 |
| `version` | `string \| null` | `null` | 依赖插件版本约束，例如 `>=1.0.0`。 |
| `description` | `string` | `""` | 依赖说明。 |

也支持字符串简写：

```yaml
dependencies:
  plugins:
    - ai>=0.1.0
```

### 5.7 compatibility

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `backendVersion` | `string \| null` | `null` | 后端版本约束。 |
| `hostApiVersion` | `string` | `^1.0.0` | 仅 v2：宿主插件 SDK 版本约束，独立于应用版本；当前 Host API 为 `1.4.0`。bundle 至少使用 `^1.2.0`；请求 DTO、显式事务、字典及缓存服务使用 `^1.3.0`；按需配置读取使用 `^1.4.0`。 |
| `frontendVersion` | `string \| null` | `null` | 前端工程的语义版本约束，保留此字段名；不是框架标识。 |
| `pythonVersion` | `string \| null` | `null` | Python 版本约束。 |
| `nodeVersion` | `string \| null` | `null` | Node.js 版本约束。 |
| `databases` | `("mysql" \| "postgresql")[]` | `[]` | 插件支持的数据库类型声明，不能重复。 |

版本约束可以是版本号，也可以带比较操作符，例如 `>=3.10`、`^20.0.0`。

`compatibility.frontendVersion` 约束前端工程的发行版本，与脚手架结果、依赖记录和锁文件中的 `frontendFramework` 不同；后者取 `vue2`、`vue3` 等框架标识，不能填入版本约束。

### 5.8 resources

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `static` | `string[]` | `[]` | 插件静态资源相对路径列表。 |
| `uploads` | `string[]` | `[]` | 插件上传资源相对路径列表。 |
| `temp` | `string[]` | `[]` | 插件临时资源相对路径列表。 |

资源路径只能使用安全相对路径，不能重复。

### 5.9 config

`config` 推荐使用 `items` 写法：

```yaml
config:
  items:
    - key: api_url
      label: API 地址
      type: string
      default: ""
```

也支持列表写法：

```yaml
config:
  - key: api_url
    label: API 地址
    default: ""
```

也支持对象简写：

```yaml
config:
  api_url:
    label: API 地址
    default: ""
  timeout_seconds: 30
```

`config.items[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `string` | 必填 | 配置键。只能包含小写字母、数字、下划线、中划线和点号，必须以小写字母开头。 |
| `label` | `string \| null` | `key` | 配置展示名称。 |
| `type` | `string` | `"string"` | 配置类型。支持 `string`、`number`、`boolean`、`select`、`textarea`、`password`、`json`。`text` 会按 `string` 处理，`switch` 会按 `boolean` 处理。 |
| `default` | JSON 值 | `null` | 默认值。支持字符串、数字、布尔、对象、数组和 `null`。`boolean`、`number`、`json` 会校验默认值类型。 |
| `required` | `boolean` | `false` | 是否必填。更新配置时会校验非空；必填但无默认值会产生检查提示。 |
| `group` | `string` | `"default"` | 配置分组，会作为配置元数据返回。 |
| `order` | `number` | `0` | 配置排序值，会作为配置元数据返回。 |
| `placeholder` | `string` | `""` | 输入占位提示，会作为配置元数据返回。 |
| `min` | `number \| null` | `null` | 数字配置最小值，仅 `number` 类型更新时生效。 |
| `max` | `number \| null` | `null` | 数字配置最大值，仅 `number` 类型更新时生效。 |
| `pattern` | `string \| null` | `null` | 字符串、文本、密码配置的正则校验表达式，仅 `string`、`textarea`、`password` 类型更新时生效。 |
| `description` | `string` | `""` | 配置说明，会在管理端配置表单中作为帮助文本展示。 |
| `options` | `object[]` | `[]` | `select` 类型选项列表，仅 `select` 类型生效。 |
| `secret` | `boolean` | `false` | 是否敏感配置。敏感配置导出时默认不输出明文。 |

`config.items[].options[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `label` | `string` | 必填 | 选项展示名称。 |
| `value` | JSON 值 | 必填 | 选项值。 |

`select` 类型必须声明 `options`，并且 `default` 必须位于 `options.value` 中。

配置校验和展示规则：

- `password` 类型建议同时声明 `secret: true`，便于输入、导出和审计时统一脱敏。
- `secret: true` 的配置不建议声明非空默认值。
- `required: true` 会在更新配置时校验非空。
- `min`、`max` 只对 `number` 生效，其他类型声明后会产生检查提示。
- `pattern` 只对 `string`、`textarea`、`password` 生效，其他类型声明后会产生检查提示。
- `options` 只对 `select` 生效，其他类型声明后会产生检查提示。
- `group`、`order`、`placeholder` 会进入配置接口和导出元数据，可供插件自定义页面消费。

### 5.10 v2 清单与能力组合

v2 将后端运行时、Web 接入方式和前端交付分开声明：

| 维度 | 可选值 | 使用方式 |
| --- | --- | --- |
| `backend.runtime` | `python`、`native` | Python 源码或预编译原生扩展，默认 `python` |
| `backend.integration` | `router`、`asgi` | 返回宿主 Router 或创建独立子应用，默认 `router` |
| `frontend.delivery.type` | `none`、`source`、`bundle` | 无页面、参与宿主构建的源码页面或独立前端构建产物 |

Python Router、Native Router、Python ASGI、Native ASGI 均通过显式入口加载。`bundle` 必须配合 `asgi`；签名 `.rpk` 只接受 `none/bundle`，`source` 沿用目录插件及宿主前端构建流程。

下面以 Python ASGI 与独立 bundle 为例。代码入口见第 6.6 节，前端构建见第 7.2 节；实际交付目录必须包含 `web/dist/index.html`。

```yaml
manifestVersion: 2
id: report_center
name: 报表中心
version: 1.0.0
backend:
  runtime: python
  integration: asgi
  module: plugins.report_center
  entrypoint: plugins.report_center:create_plugin
  asgi:
    mountPath: /apps/report_center
    lifespan: managed
frontend:
  delivery:
    type: bundle
    buildRequired: false
  bundle:
    directory: web/dist
    entry: index.html
    spaFallback: true
  menus:
    - name: 报表中心
      path: report_center
      component: PluginFrame
      type: C
      perms: report_center:view
permissions:
  - code: report_center:view
    name: 查看报表
compatibility:
  hostApiVersion: ^1.2.0
  pythonVersion: '>=3.10'
  databases: [mysql, postgresql]
```

v2 新增或改变的字段如下，其余迁移、菜单、配置及插件依赖继续使用本章已有定义。

| 字段 | 默认值或要求 | 说明 |
| --- | --- | --- |
| `backend.entrypoint` | 必填 | `<module_path>:<callable_name>`，模块必须属于当前插件；返回 `PluginDefinition` |
| `backend.routers.autoScan` | `false` | v2 不扫描 `controller/`，不能改为 `true` |
| `backend.native.distribution` | native 必填 | wheel 的发行包名，例如 `ruoyi-plugin-report-center`；Python 运行时不能声明 `native` |
| `backend.native.moduleRoot` | `native` | 已展开发行包的安全相对目录 |
| `backend.asgi.mountPath` | `/apps/<id>` | 仅 ASGI 使用，不能改成其他路径 |
| `backend.asgi.lifespan` | `managed` | `managed` 由宿主驱动生命周期；`none` 用于不实现 lifespan 协议的应用 |
| `frontend.bundle.directory` | `web/dist` | 相对插件根目录的前端构建目录；选择 bundle 时必须声明 `frontend.bundle` |
| `frontend.bundle.entry` | `index.html` | 相对构建目录的 HTML 入口，必须以 `.html` 结尾 |
| `frontend.bundle.spaFallback` | `true` | 允许符合条件的 HTML 页面导航回落到入口，具体边界见第 7.2 节 |

改用 Rust 时，将 `runtime` 改为 `native`、`module` 改为 `ruoyi_plugin_report_center`、`entrypoint` 改为 `ruoyi_plugin_report_center._native:create_plugin`，并声明 `native.distribution: ruoyi-plugin-report-center`。入口必须来自该发行包内的原生扩展，不能用另一个宿主模块或 Python 业务入口代替。发行包版本必须与插件 `version` 一致。

`entrypoint`、Hook、健康检查都使用插件自身模块的完整路径；任务使用 `<module_path>.<callable_name>`。ASGI 插件不能同时声明 `hooks.onStartup/onShutdown`，启动和关闭统一写入 lifespan。资源路径使用 `/` 分隔的相对路径，不允许绝对路径、反斜杠、`.` 或 `..` 目录。

bundle 不因存在菜单而变为源码前端，`buildRequired` 必须为 `false`，构建依赖由插件自己的 `package.json` 管理，不写入清单的 `dependencies.frontend`。清单校验和静态预检不会导入插件代码；通过预检仍需进行实际加载、权限与生命周期测试。

## 6. 后端开发约定

### 6.1 控制器

v1 在应用启动时按 `backend.module` 自动扫描已启用插件的控制器。推荐将接口放在 `controller/` 目录，并保持与项目原有 FastAPI 控制器风格一致。v2 返回显式路由或子应用，见第 6.6 节。

后端插件路由采用启动期挂载模型：

- 新启用插件的后端 controller 需要重启应用后才会挂载到当前 FastAPI app。
- 停用插件后，已挂载的插件路由仍保留在 app 路由表中，但请求会经过插件启用状态依赖拦截。
- 插件 controller 的 `prefix` 必须位于当前插件命名空间内，例如 `/demo`、`/demo/items`、`/plugin/demo` 或 `/plugin/demo/items`，不能占用 `/system`、`/monitor` 等平台核心路径。

示例：

```python
from fastapi import APIRouter

demo_controller = APIRouter(prefix='/demo', tags=['demo'])


@demo_controller.get(
    '/ping',
    summary='获取插件连通状态接口',
    description='用于检查插件接口是否可访问',
)
async def ping() -> dict[str, object]:
    return {'code': 200, 'msg': 'success', 'data': 'pong'}
```

控制器对象需要能被自动扫描发现，命名上建议延续现有 `xxx_controller` 风格。

### 6.2 数据模型、DAO 和 Service

插件业务代码尽量放在插件目录内：

- `entity/do/`：数据库模型。
- `entity/vo/`：请求和响应模型。
- `dao/`：数据库访问。
- `service/`：业务编排。

插件代码可以复用项目已有的数据库 session、响应模型、权限装饰器和工具函数，但不要修改核心模块来服务单个插件。确实需要通用能力时，先沉淀到 `plugins/core` 或项目公共层。

### 6.3 Migration 和 Seed

`backend.migrations` 和 `backend.seeds` 支持声明 SQL 脚本。推荐按数据库方言拆分目录：

```text
migrations/mysql/001_init.sql
migrations/postgresql/001_init.sql
seeds/mysql/001_seed.sql
seeds/postgresql/001_seed.sql
```

要求：

- migration 用于表结构。
- seed 用于字典、默认配置等初始化数据。
- migration 和 seed 都必须可重复执行。MySQL DDL 会隐式提交，后续 hook 或状态写入失败时平台无法自动回滚已应用的结构变更。
- migration 执行前会先记录 `status=running`；成功后记录 `status=success`；失败后记录 `status=failed` 和错误摘要。
- `running` 表示上次执行已开始但未记录成功或失败，平台会阻断自动重跑，需要人工确认数据库结构后标记为成功或失败。
- migration 成功历史只认 `status=success`；已成功执行的 migration 文件不能修改，checksum 变化时必须恢复原文件或新增后续 migration。
- SQL migration 应优先使用 `CREATE TABLE IF NOT EXISTS` 等幂等写法；复杂 DDL、存储过程或需要条件判断的变更建议改用 Python migration。
- SQL migration 应尽量拆小，避免单个文件包含大量不可回滚 DDL；`ALTER TABLE`、索引和初始化数据尤其要考虑重复执行安全。
- SQL 文件路径必须位于插件目录内。
- MySQL 和 PostgreSQL 差异较大时分别维护脚本。

故障恢复入口：

- CLI 查看历史：`ruoyi plugin migration-list <plugin_id> --status running`
- CLI 标记成功：`ruoyi plugin mark-success <plugin_id> <migration_path> --note "已人工确认结构完成"`
- CLI 标记失败：`ruoyi plugin mark-failed <plugin_id> <migration_path> --note "未完成，允许修复后重试"`
- Web 管理页：插件详情的“依赖 / 执行历史”中查看 migration 状态，并执行人工标记。

详细排障流程见 [插件 Migration 故障处理手册](plugin_migration_failure_runbook.md)。

### 6.4 生命周期钩子

支持的钩子：

- `onInstall`
- `onUpgrade`
- `onStartup`
- `onShutdown`
- `onPurge`

声明格式：

```yaml
backend:
  hooks:
    onInstall: plugins.demo.hooks:on_install
```

v1 钩子必须使用 `async def`，可以不接收参数，也可以接收 `context`；普通同步函数会被拒绝。v2 钩子固定接收一个 `PluginHookContext`，调用后必须立即返回可等待对象，Python 实现通常同样使用 `async def`。ASGI 插件的启动和关闭使用 lifespan，不重复声明运行时 Hook：

```python
async def on_startup(context):
    if not context.startup_write_enabled:
        return
    # 只在启动期单写者中执行全局写操作
```

`context` 常用字段：

- `plugin_id`
- `hook_name`
- `discovered_plugin`
- `app`
- `query_db`
- `startup_write_enabled`

多 worker 启动时，所有 worker 都会加载运行时能力，但只有启动期单写者适合执行全局写操作。钩子里如果要写菜单、任务、配置、外部资源，应检查 `context.startup_write_enabled`。

### 6.5 定时任务

定时任务在 `backend.jobs` 中声明：

```yaml
jobs:
  - id: cleanup
    name: 清理任务
    callable: plugins.demo.jobs.cleanup
    trigger: cron
    cronExpression: "0 0 * * * ?"
    enabled: true
    misfirePolicy: "3"
    concurrent: "1"
```

`callable` 使用 `<module_path>.<callable_name>` 格式。任务会写入系统任务表，由调度器按原系统机制执行。

v2 只支持 `executor: default`，回调签名为 `callback(context, *args, **kwargs)`，其中 `context` 是 `PluginTaskContext(host, job_id)`。回调必须返回 awaitable，`timeoutSeconds` 默认 30 秒；后台上下文没有请求用户，不能调用要求登录用户身份的服务。建议示例任务先设为 `enabled: false`，验证后再启用。

v2 调度记录保存宿主分发函数及插件 ID、任务 ID、版本，不直接持久化原生 callable。执行前检查当前 worker 就绪、版本一致、任务仍存在及插件已启用；任务在所属宿主事件循环执行，不支持进程池。多 worker 的调度选主沿用宿主调度器。

运行时关闭先将全部显式插件标记为未激活，再按依赖逆序回收各插件：关闭长连接、取消定时任务、释放 lifespan 资源。每个插件的运行任务整批并发取消，等待最多 5 秒；超时记录告警并继续后续清理，不按任务数量逐个累加等待。残留任务保留强引用，结束后回收异常；同进程中该插件的旧任务全部退出前，不允许重新绑定同名任务。关闭期间的状态查询即使迟到返回成功，也不会再启动业务回调。

未退出的任务仍计入在途，实际退出后才记录终态；关闭后迟到的成功结果按取消处理。`timeoutSeconds` 和任务取消都是协作式约束，不能强制终止吞掉取消或阻塞事件循环的代码，也不能撤销已经执行的写操作。超出关闭等待后，业务代码仍可能继续运行，而其依赖资源可能已释放；插件必须在 `finally` 中清理并传播取消，生产维护仍需全部 worker 退出。

### 6.6 v2 显式入口与宿主 SDK

清单中的 `create_plugin(host)` 必须同步、快速地返回 `PluginDefinition`；它只声明能力，不打开连接、启动线程或创建后台任务。当前 `PluginDefinition.api_version` 为 `1`，与清单版本 `2`、Host API 版本 `1.4.0` 是三个不同的版本号。

| 定义字段 | 使用方式 |
| --- | --- |
| `routers` | Router 模式返回 `APIRouter` 实例序列，路由必须位于当前插件命名空间 |
| `app_factory` | ASGI 模式提供同步 `factory(host)`，返回 ASGI callable；不能同时返回 routers |
| `register_models` | 可选同步 `callback(host)`，仅注册 ORM 元数据，不执行数据库读写 |

以下代码可作为第 5.10 节 Python 插件的 `__init__.py`，提供受权限保护的 `/api/info`。宿主 SDK 从 `plugins.core.sdk` 导入。

```python
from fastapi import FastAPI

from plugins.core.sdk import PluginDefinition, PluginHostContext, PluginRequestContext, plugin_endpoint


async def info(context: PluginRequestContext) -> dict[str, str]:
    return {'pluginId': context.host.plugin_id, 'hostApiVersion': context.host.api_version}


def create_app(host: PluginHostContext) -> FastAPI:
    """
    创建插件子应用并声明接口。

    :param host: 宿主提供的插件上下文
    :return: 插件 ASGI 子应用
    """
    app = FastAPI(title=host.plugin_id, docs_url=None, redoc_url=None)
    app.add_api_route(
        '/api/info',
        plugin_endpoint(info, permission='report_center:view'),
        summary='获取报表插件信息接口',
        description='用于获取当前插件标识和宿主API版本',
        response_model=dict[str, str],
    )
    return app


def create_plugin(host: PluginHostContext) -> PluginDefinition:
    """
    声明插件显式入口。

    :param host: 宿主提供的插件上下文
    :return: 插件能力声明
    """
    return PluginDefinition(app_factory=create_app)
```

Router 模式将清单的 `integration` 改为 `router`，移除 `backend.asgi`；创建带 `/report_center` 等合法插件前缀的 `APIRouter`，注册接口后返回 `PluginDefinition(routers=(router,))`。若原清单使用 bundle，还需改为 `none/source` 并移除 `frontend.bundle`；同一插件 ID 不能同时启用两种接入方式。

宿主上下文按以下边界使用：

| 对象 | 当前提供的能力 | 使用边界 |
| --- | --- | --- |
| `PluginHostContext` | `plugin_id`、`resource_root`、只读 `config`、`config_revision`、`services`、`session_factory`、`redis`、`logger`、`startup_write_enabled`、`api_version` | `config` 为启动快照；`await read_config()` 主动读取最新配置，不自动应用到业务资源；不保存请求身份或请求数据库会话 |
| `PluginRequestContext` | `host`、当前 `user`、`permissions`、`require_permission()`、`request_id`、`transaction()`；适配器提供 `request` | `query_db` 只在显式事务块内有效；数据权限仍由具体服务处理 |
| `PluginTaskContext` | `host`、`job_id`、本次执行的 `request_id` | 后台任务身份，不隐式获得用户或管理员权限 |

普通 FastAPI 接口可从 `request.state.plugin_context` 获取请求上下文；WebSocket 对应 `websocket.state.plugin_context`。入口门禁验证用户能访问插件，具体 API 仍须调用 `require_permission()` 或使用 `plugin_endpoint(callback, permission=...)`。权限应同时声明在清单并授予使用者，仅有菜单可见性不代表 API 已鉴权。

`host.resource(relative_path)` 将资源定位在插件根目录内；资源、配置或当前请求对象不能跨插件混用。数据库连接池可共享，`AsyncSession` 必须通过 `async with host.session_factory() as db` 按操作创建并释放，不能在并发任务或线程间共用。签名制品的业务表通过维护迁移创建，`register_models` 不能用来绕过该流程。

版本化业务服务通过 `await host.service('服务名称')(context, ...)` 调用。服务再次核对插件归属、当前登录用户和接口权限，仅返回普通数据，不返回密码或 ORM 对象。权限须同时声明在清单并授予用户。

| 服务 | 参数（context 之后） | 权限 | 返回值与边界 |
| --- | --- | --- | --- |
| `users.current_profile.v1` | 无 | `<id>:profile` | `userId/userName/nickName/avatar/postGroup/roleGroup` |
| `dictionaries.items.v1` | `dict_type` | `<id>:dict` | 已启用选项的 `label/value/cssClass/listClass/isDefault`；字典类型为字母开头的字母、数字、下划线，最长 100 字符 |
| `cache.get.v1` | `key` | `<id>:cache` | JSON 数据；不存在时为 `None` |
| `cache.set.v1` | `key, value, ttl_seconds=300` | `<id>:cache` | JSON UTF-8 数据最多 64 KiB；TTL 为 1–86400 秒 |
| `cache.delete.v1` | `key` | `<id>:cache` | 是否删除已有缓存 |

缓存键以字母或数字开头，允许字母、数字、`_ . : -`，最长 128 字符。宿主自动添加 `plugin:sdk:cache:<id>:` 前缀；不提供扫描、通配删除或任意 Redis 命令。缓存按插件共享，不自动按用户隔离，需要用户隔离时将当前用户 ID 纳入业务键。缓存写入不参与数据库事务。

`plugin_endpoint` 把固定参数的插件回调转换为 FastAPI 端点；`plugin_lifespan(host, startup, shutdown)` 把两个接收 host 的异步回调转换为 lifespan，startup 可返回共享状态字典或 `None`。`await_plugin_callback` 统一等待 Python 协程或原生返回的 awaitable。v2 Hook 接收 `PluginHookContext`，健康检查接收 `PluginHealthContext`，两者并非 `PluginHostContext`。

Python 回调在宿主事件循环执行，不能在其中调用 `asyncio.run()` 或阻塞等待已有循环；Rust 同步导出函数应快速返回 awaitable，CPU 密集工作应脱离事件循环线程。超时和取消不能强制终止阻塞的原生代码，插件应配合取消并对写操作实现幂等。不要关闭宿主提供的 Redis 或数据库连接池。

#### 6.6.1 请求数据与校验

`plugin_endpoint` 保持 `callback(context)` 调用方式。回调中的 `context.request` 是 `PluginHttpRequest`：`method/path/path_params/query/body`；`query` 保留同名多值，`to_payload()` 返回独立的 JSON 副本，其中路径参数字段名为 `pathParams`。不传递原始 Request、Cookie 或认证头。未经该适配器包装的普通 Router/ASGI 端点仍直接使用 FastAPI Request，不保证 `context.request` 已填充。

默认不读取请求体；传入 `json_body=True` 或 Pydantic `body_model` 才启用 JSON 解析。默认上限为 1 MiB，可通过 `max_body_bytes` 调整。权限检查先于读取请求体；类型错误返回 415、实际接收字节超限返回 413、无效 JSON 返回 400、模型校验失败返回 422。校验错误不回显输入值。`timeout` 分别限制请求体读取和业务回调，每一阶段默认 30 秒。

```python
from pydantic import BaseModel, Field
from plugins.core.sdk import PluginRequestContext, plugin_endpoint


class MessageBody(BaseModel):
    message: str = Field(min_length=1, max_length=200)


async def echo(context: PluginRequestContext) -> dict:
    return {**context.request.to_payload(), 'requestId': context.request_id}


app.add_api_route(
    '/api/echo/{item_id}',
    plugin_endpoint(echo, permission='report_center:view', body_model=MessageBody),
    methods=['POST'],
    summary='验证请求上下文接口',
    description='返回校验后的路径参数、多值查询参数、请求体和追踪标识',
    response_model=dict,
)
```

Python 与 Rust 实例均提供 `POST /api/echo/{item_id}`；Rust 通过 PyO3 读取同一 DTO，见对应示例 README。

#### 6.6.2 显式请求事务

默认每次数据库服务调用创建独立会话。需要连续调用共享事务时，使用以下形式：

```python
async with context.transaction() as transaction_context:
    profile = await context.host.service('users.current_profile.v1')(transaction_context)
    options = await context.host.service('dictionaries.items.v1')(transaction_context, 'sys_normal_disable')
```

事务正常结束时提交，异常或任务取消时回滚，最后关闭会话。业务 DAO 可使用块内的 `transaction_context.query_db`；不得自行提交、关闭或把该会话传给其他任务。宿主服务拒绝嵌套事务、块外继续使用事务上下文、手动注入的会话及跨 `asyncio` 任务复用；因此块内服务调用应顺序等待，不能用 `gather/create_task` 并发共享事务。该事务仅覆盖当前宿主数据库，不覆盖 Redis、外部 HTTP 或后台任务，也不自动提供行级数据权限。

### 6.7 ASGI 子应用与生命周期

宿主把子应用挂载到固定 `/apps/<plugin_id>`。子应用声明相对路由，并通过 ASGI `root_path` 处理代理部署前缀，不要在子应用路由中再次写完整挂载地址。

| 对外地址 | 子应用或交付声明 |
| --- | --- |
| `/apps/<id>/api/...` | 子应用中的 `/api/...` 路由 |
| `/apps/<id>/ui/`、`/apps/<id>/ui/assets/...` | 仅 bundle：宿主提供已构建前端资源 |
| `/apps/<id>/ws/...` | 可选：插件自行声明 WebSocket 路由，握手仍经过宿主门禁 |
| `/apps/<id>/docs`、`/apps/<id>/openapi.json` | 取决于子应用自身配置，不自动合并到宿主 OpenAPI |

外层网关检查插件启用状态、当前 worker 就绪状态和身份，再注入请求上下文；HTTP、静态资源和 WebSocket 握手均经过该边界。父应用的路由依赖、异常处理器和全部 state 不会自动继承；FastAPI 子应用由宿主显式提供 `app.state.plugin_host` 和共享 `app.state.redis`。具体 API 的权限与错误处理由插件声明，不要重复安装宿主的传输加密层。

`lifespan: managed` 是默认值。宿主显式发送 ASGI startup/shutdown，等待启动及清单健康检查通过后才挂载，不依赖 `app.mount()` 自动运行子应用生命周期。`lifespan: none` 只适用于不需要宿主发送生命周期事件的 ASGI callable；需要初始化和释放资源的应用应保留 managed。

每个 worker 都创建并启动自己的子应用实例。共享的迁移、菜单和安装操作由维护流程或相应单写者负责，不能放进每个 worker 都执行的资源初始化。目录插件需要全局启动写入时检查对应上下文的 `startup_write_enabled`；签名制品在普通 worker 中该能力为关闭状态。

应用按依赖顺序启动、逆序关闭。插件只释放自己创建的资源；启动中途失败也应清理已建立的资源，shutdown 应可重复调用。使用 `@asynccontextmanager` 时，返回类型写为 `AsyncGenerator[状态类型, None]`；也可复用 `plugin_lifespan`，其 shutdown 在 startup 失败后同样会调用。

宿主串行处理同一实例的启动和关闭，避免并发 shutdown 重复发送协议消息。协议确认及 shutdown 确认后的任务退出各等待最多 30 秒，取消回收每次最多 5 秒；未响应取消的任务继续保留并告警，不会无限等待。该任务退出前，生命周期管理器和显式运行时均拒绝为其启动重叠实例；退出后重试使用新的协议队列和状态，旧确认消息不会污染下一次启动。ASGI callable 可返回任意 awaitable，不要求直接返回协程。

子应用自行取消属于生命周期失败，不会被误当作整个宿主被取消。一个插件的连接、任务或 lifespan 清理报错后，仍会尝试其他清理步骤和其他插件；激活失败后的清理异常单独记录，保留最初的激活错误。运行时进入关闭后不再接受激活，进行中的健康检查也不能在关闭后重新发布路由。已关闭的运行时不能直接复用，重新启动应创建新的宿主运行时。宿主调用者自身的取消仍向上传播；这些等待上限也无法约束阻塞整个事件循环的同步代码。

ASGI 网关在响应声明 `text/event-stream` 或 WebSocket 接受握手后，开始周期复核。首次及每次复核之间等待 15 秒，单次鉴权设置 5 秒超时；每次使用独立数据库会话，复核结束即关闭，不因长连接长期占用会话。复核检查主登录、插件 Cookie（使用 Cookie 时）、插件启用状态、当前 worker 就绪状态和用户权限；复核请求不会续期主登录。

主登录失效、插件停用、身份变化或原权限集合中的任一权限被移除时，关闭连接。采用保守的权限减配策略，即使被移除的权限与当前接口无关，也需要重新连接；权限增加不修改已有 `plugin_context` 的快照。接口和数据权限仍由插件自身校验。复核查询出错或超时也会关闭连接，不能在无法确认权限时持续发送数据。撤销是周期检测，并非即时广播；已发出的数据无法撤回。

SSE 使用保留事件 `ruoyi.plugin.closed` 通知关闭，随后结束响应。完整关闭事件的 `data` 提供 `code` 和 `reason`，固定原因包括 `session_expired`、`access_revoked`、`authorization_unavailable`、`authorization_timeout` 和 `plugin_shutdown`，不返回底层异常详情。业务不能使用这一事件名；自写 SSE 客户端必须先按事件名识别并结束处理，不能把该 EOF 当作业务成功。如果关闭时业务事件尚未发送完整，宿主会覆盖其事件类型，`data` 可能含有未完成的业务内容，因此不能依赖 JSON 解析成功后才识别关闭。宿主浏览器适配器会拦截该事件并拒绝 `stream()`，不会交给插件的 `onEvent`。更新后端时需同步更新宿主前端，旧适配器不能识别这一关闭语义。WebSocket 的身份或权限失效使用关闭码 `1008`，复核不可用或超时使用 `1011`，运行时关闭使用 `1012`。

显式运行时进入 shutdown 后先拒绝新连接、并发取消当前插件的流，再释放其 lifespan 资源。业务任务的取消等待和关闭消息的发送超时均为 5 秒；发送超时后会取消发送任务并限时回收。忽略取消的任务会记录告警并隔离后续输出，Python 无法强制终止任意业务代码。插件应在 `finally` 中清理资源，不能吞掉取消后继续运行。这一机制覆盖 v2 **ASGI** 的 SSE/WebSocket；普通 HTTP、任意字节流、v2 Router 和 v1 路由不增加周期复核。ASGI 服务器可能先等待在途请求、再进入 lifespan shutdown，部署时仍须配置有限的优雅停机等待时间；网关不接管该服务器阶段。

新启用或更新代码仍需要重启。修改发布目标或撤销签名密钥不会热卸载已加载模块，也不会触发即时的跨 worker 关闭；正式升级仍须停止全部宿主 worker，并按第 15 节完成维护发布。

### 6.8 Rust 原生插件

Rust 使用 PyO3 暴露 Python 扩展，并通过 maturin 构建 wheel；Windows 交付 `.pyd`，Linux 交付 `.so`。部署端只需匹配的运行环境和已构建产物，无需 Rust 编译工具链。原生代码与宿主同进程，适用于可信扩展；二进制交付不等于不可逆向，也不提供 Python 依赖或进程隔离。

原生 wheel 在构建或维护环境中验证并展开到 `backend.native.moduleRoot`，默认 `native/`。宿主检查发行包名称、插件版本、Python 要求、wheel tag、已安装依赖及完整 RECORD SHA256；扩展只能从当前插件目录加载，不能覆盖宿主模块。RECORD 用于检查文件一致性，发布者信任仍需第 15 节的签名流程。

构建机需安装 Rust、maturin 和目标平台编译工具：Windows 使用 MSVC Build Tools 的 C++ 工具及 Windows SDK，macOS 使用 Xcode Command Line Tools，Linux 使用 GCC 或 Clang 等编译工具。先选择 `rust-asgi` 或 `rust-bundle` 脚手架，再按第 16 节构建。`abi3` 可减少 Python ABI 构建数量，但不能跨操作系统或架构复用制品；按实际目标平台及 Python 3.10–3.13 的测试结果验证兼容性。

Rust 通过 `PluginHostContext`、`plugin_endpoint`、`plugin_lifespan` 和版本化服务复用宿主能力，完整实现见 [Rust 示例](../plugins/examples/rust/rust_demo/README.md)。不要覆盖已加载的原生模块或依赖 `reload` 完成更新，发布后必须重启全部相关进程。

## 7. 前端开发约定

### 7.1 v1 / source 页面

插件前端代码放在：

```text
ruoyi-fastapi-frontend/<framework>/web/plugins/<plugin_id>/
```

当前 Vue2、Vue3 实现中，菜单组件路径和真实 Vue 文件的映射关系如下，`<framework>` 分别替换为 `vue2` 或 `vue3`：

```text
plugin/demo/index -> ruoyi-fastapi-frontend/<framework>/web/plugins/demo/views/index.vue
plugin/demo/report/list -> ruoyi-fastapi-frontend/<framework>/web/plugins/demo/views/report/list.vue
```

只允许两类组件值：

- 核心布局组件：`Layout`、`ParentView`、`InnerLink`。
- 插件视图组件：`plugin/<plugin_id>/<view_path>`。

前端 API 建议放在 `plugins/<plugin_id>/api/`，视图放在 `plugins/<plugin_id>/views/`。插件页面不需要加入主工程内置路由，菜单安装后由后端返回动态路由，前端 resolver 会自动定位插件视图。

### 7.2 v2 独立 bundle 页面

v2 ASGI 插件可声明 `frontend.delivery.type: bundle` 和 `frontend.bundle.directory: web/dist`，菜单组件使用 `PluginFrame`。`backend.runtime` 仍独立选择 `python` 或 `native`：bundle 只改变前端交付方式，不会保护 Python 后端源码；原生非源码交付参见 Rust 示例。此模式需要 Host API `^1.2.0`，不声明宿主 npm 依赖，也不参与宿主前端构建。首次升级宿主以加入 `PluginFrame` 时仍需构建宿主前端，之后新增或更新插件只构建插件自己的前端。

后端通过 `sys_plugin_menu.menu_id` 的可信归属输出路由 `meta.pluginId`，不接受菜单 query、URL 或插件名称代替该标识。`PluginFrame` 先以宿主 Bearer 调用 `POST /plugin/runtime/<id>/session`，取得服务端校验的固定入口和短期插件会话，然后打开 `/apps/<id>/ui/`。不要手写任意 iframe 地址，也不要把主 token 放入 URL 或传给插件。

插件浏览器 Cookie 使用 `HttpOnly`、`SameSite=Strict`，HTTPS 下为 `Secure`，路径限定为 `<root_path>/apps/<id>/`。会话最多 300 秒并受主登录有效期限制，同一主会话的多标签续期复用 Cookie 与 CSRF。每次 API、页面和资源访问都会检查主会话、插件状态和权限；退出、主登录替换、插件禁用或版本变化会使后续访问失效。写请求还要求同源 Origin 与 CSRF。插件 Cookie 不能用于其他宿主 API。已建立的 ASGI SSE/WebSocket 按[生命周期说明](#67-asgi-子应用与生命周期)周期复核并关闭失效连接，不承诺即时撤销。

浏览器 SDK 位于前端 `src/utils/pluginBridge.js`，配套类型位于 `pluginBridge.d.ts`，无 Vue/Axios 依赖。示例通过构建别名引入；独立插件仓库可将这两个文件作为版本化依赖复制到自己的源码中。SDK 提供 `ready`、`request`、`upload`、`download`、`stream`、`navigate`、`subscribe` 和 `destroy`，具体用法见 [bundle_demo README](../plugins/examples/python/bundle_demo/README.md)。请求只允许当前插件 API 下的相对 `path`；JSON 与文件由主页面使用原有请求客户端代理，SSE 使用宿主专用 fetch 适配器；两者自动附加插件 CSRF，不发送主 Bearer。主 token、插件 Cookie 和 CSRF 值不进入桥消息。

JSON 请求、响应和文件元数据每条最多 64 KiB，所有请求合计最多 8 个待处理任务；JSON 默认 15 秒超时，文件传输默认 120 秒。`upload/download` 的文件内容使用 Blob 结构化克隆，单次最多 10 MiB，支持进度和取消。协议仍为 bridge v1，通过握手 `capabilities.files.version=1` 协商文件能力、`capabilities.streams.version=1` 协商 SSE 能力；旧宿主明确拒绝其未公布的能力，旧 JSON 客户端仍可工作。SSE 每个页面最多 2 条连接，默认且最长 5 分钟，单条事件最多 64 KiB、单次连接累计最多 10 MiB。当前不代理任意字节流或 WebSocket。通信桥不能替代后端具体 API 的 `require_permission`/`plugin_endpoint` 权限检查。

UI GET/HEAD 使用普通 HTTPS，仍经过插件身份门禁；`/apps/<id>/api/...` 与会话签发接口保留宿主传输加密，不能整体加入加密排除列表。加密 AAD 保留 `/apps/<id>/api/...` 完整插件命名空间，只按宿主规则剥离部署前缀；加密的会话响应仍保留 `Set-Cookie`。

HTML 注入有效 `uiBase`、`apiBase` 与 `<base>`。SPA 回退仅接受 UI GET/HEAD 中带 `Accept: text/html` 的无扩展名页面导航；缺失脚本、API、保留路径和非 HTML 请求不能返回首页。静态服务拒绝路径越界和链接逃逸，并限制为同源 iframe 嵌入。HTML 当前 `no-store`，其他静态资源 `no-cache`，不自动启用 immutable 缓存。

Vue3 Web 各环境已显式配置 `VITE_APP_PLUGIN_BASE`，Vue2 Web 使用 `VUE_APP_PLUGIN_BASE`：development 为 `/dev-api`、production 为 `/prod-api`、docker 为 `/docker-api`、staging 为 `/stage-api`，分别与各环境的 `VITE_APP_BASE_API`、`VUE_APP_BASE_API` 一致。开发、生产、Docker 分别对齐后端 `.env.dev`、`.env.prod`、`.env.dockermy`/`.env.dockerpg` 的 `APP_ROOT_PATH`；仓库未提供独立的后端 staging 环境文件，部署 staging 时需将后端 `APP_ROOT_PATH` 配为 `/stage-api`。以开发环境为例，插件使用同源 `/dev-api/apps/` 和 `/dev-api/plugin/runtime/`，Cookie Path 和会话响应也包含此前缀。

自定义部署时，宿主前端的 `VITE_APP_PLUGIN_BASE`（Vue3）或 `VUE_APP_PLUGIN_BASE`（Vue2）必须与后端 `APP_ROOT_PATH` 一致；只有后端前缀为空时，前端才留空并使用 `/apps/` 和 `/plugin/runtime/`。浏览器侧保留部署前缀，代理转发至通过 `app.py` 启动的 Uvicorn 时剥离此前缀一次，由 Uvicorn 补回 ASGI `root_path`；保留外部 Host，HTTPS 的原始 scheme 由可信代理配置传递。两个 Web 工程的开发代理已按此规则改写插件路径；各自的 Docker Nginx 配置也已提供 `/docker-api/apps/` 和 `/docker-api/plugin/runtime/` 专用代理，并在转发时剥离 `/docker-api`。生产、staging 或自定义反向代理须配套设置相同前缀、专用代理入口及转发路径，保留 WebSocket 升级和 SSE 非缓冲配置，并验证 Cookie Path、Origin、Secure 和加密 AAD。独立页面属于同源可信代码；iframe 提供布局和依赖隔离，不提供对恶意插件的安全隔离。

### 7.3 bundle 浏览器 SDK

插件前端通过构建别名或复制的 SDK 模块引入 `createPluginClient`。宿主在 HTML 的 `ruoyi-plugin-config` 中注入插件标识及包含真实部署前缀的运行基址；不要硬编码 UI 或 API 的绝对地址。

```javascript
import { createPluginClient } from '@ruoyi/plugin-bridge'

const config = JSON.parse(document.getElementById('ruoyi-plugin-config').textContent)
const client = createPluginClient({ pluginId: config.pluginId })
const context = await client.ready
// context 包含 theme、language、timeZone、route、uiBase 和 apiBase。
const info = await client.request({ method: 'GET', path: 'info' })
console.log(info.pluginId)

const unsubscribe = client.subscribe(({ type, payload }) => {
  // 根据 preferences、route、refresh、logout 事件更新插件自身界面。
  console.log(type, payload)
})

window.addEventListener('pagehide', () => {
  unsubscribe()
  client.destroy()
}, { once: true })
```

`request` 的 `path` 相对本插件 `apiBase`，例如 `info`、`reports/month`；不允许完整 URL、前导 `/`、`..` 或自行拼接查询串。查询参数放在 `params`，JSON 请求体放在 `data`，`GET/HEAD` 不带请求体。可在第二个参数传入 `{ signal: controller.signal }` 取消请求，不能传入任意请求头或 Axios 配置。

```javascript
const controller = new AbortController()
const options = {
  signal: controller.signal,
  onProgress: ({ phase, loaded, total }) => {
    // total 为 null 时显示已传输字节或不确定进度；进度 100% 不代表服务端处理完成。
    console.log(phase, loaded, total)
  },
}
const inspected = await client.upload({
  path: 'files/inspect', file: selectedFile,
  // method 默认 POST，也支持 PUT/PATCH；file 为浏览器 File 或 Blob。
  fieldName: 'file', filename: selectedFile.name, fields: { category: 'report' },
}, options)
const report = await client.download({ path: 'files/report', params: { month: '2026-10' } }, options)
// report 是 Blob，由插件决定保存名称和时机；使用 URL.createObjectURL 后必须释放 URL。
```

`upload` 由宿主重建 multipart 表单，`fields` 仅接受字符串字段，返回 JSON；不能直接向 `request` 传入 `FormData`。`download` 默认 GET，也可使用允许的其他方法和 JSON `data`，只返回 Blob，不暴露响应头或宿主请求对象。下载时收到小于等于 64 KiB 且包含非 200 数字 `code` 的 JSON 错误响应会被拒绝；普通 JSON 文件仍可下载。进度按字节报告，上传进度可能包含 multipart 开销；返回的 Promise 成功才表示响应处理完成。取消、超时、重载和退出后，迟到的进度与结果不会交付给旧页面。

文件传输沿用宿主已有的二进制请求策略，不使用 JSON 加密信封；HTTPS、插件 Cookie、Origin、CSRF 和接口权限校验仍然执行。部署处于传输加密 `required` 模式时，须将**具体文件接口**加入 `TRANSPORT_CRYPTO_EXCLUDE_PATHS`，如 `/apps/bundle_demo/api/files/inspect,/apps/bundle_demo/api/files/report`，追加到已有列表并保留原有配置。路径按后端规则不带代理前缀。未配置时请求会被拒绝，不自动旁路；不要排除整个 `/apps` 或插件 API 命名空间。服务端与反向代理也应限制上传大小；示例后端会独立检查文件 10 MiB 和表单附加 64 KiB 的实际字节上限。

SSE 使用 `stream` 发起只读 GET 请求；必须提供 `onEvent`，其中 `data` 是原始字符串，由业务决定是否解析 JSON：

```javascript
const controller = new AbortController()
let lastEventId = ''
async function receive() {
  await client.stream({ path: 'events', params: { count: 10 }, lastEventId }, {
    signal: controller.signal,
    onEvent: async ({ event, data, id }) => {
      await saveEvent({ event, data }) // 由插件实现；处理成功后再记下游标。
      lastEventId = id
    },
  })
}
receive().catch(showStreamError) // 由插件实现错误提示和重新连接入口。
// 用户停止时调用 controller.abort()；重试时创建新的 AbortController，并传回 lastEventId。
```

宿主增量解析 UTF-8、跨分片换行、多行 data 和 id；只分发以空行结尾的完整事件。每次等待 `onEvent` 返回的 Promise 完成后才继续交付，回调超过 15 秒或失败会取消连接。`stream()` 在正常 EOF 后完成，取消、超时或网络错误时拒绝；不自动重连，也不使用服务端的 `retry` 字段。重试间隔、持久化游标、事件去重及断线补发由插件与服务端共同实现，不能据此承诺不丢失或只处理一次。`lastEventId` 仅接受最多 1024 个可打印 ASCII 字符，通过 `Last-Event-ID` 请求头发送；业务服务应选择符合这一约束的游标。取消、重载、退出和 `destroy()` 会终止宿主连接，丢弃迟到事件；已开始的业务回调仍需自行处理取消。

事件接口必须返回 `text/event-stream`，禁止跨源地址和重定向。SSE 不使用 JSON 加密信封，依赖 HTTPS；若当前传输策略会加密该端点，需将**精确事件路径**（如 `/apps/bundle_demo/api/events`，不含部署前缀）追加到既有 `TRANSPORT_CRYPTO_EXCLUDE_PATHS`，宿主不会自动绕过策略。建立请求时仍校验插件 Cookie、主登录和接口权限；宿主会附加 CSRF 头，后端沿用只读 GET 的门禁规则，强制 Origin/CSRF 校验针对写请求。ASGI 网关会周期复核已建立连接；收到宿主关闭通知时 `stream()` 拒绝，业务应保留已处理游标并按新的登录及权限状态决定是否重试。反向代理应关闭该事件接口的响应缓冲，并配置相应超时；示例返回 `X-Accel-Buffering: no`。

本地开发可运行 `npm --prefix plugins/examples/python/bundle_demo/web run dev`（从后端目录）。`/dev.html` 使用真实桥协议和内存模拟请求，支持文件与逐条事件，可切换主题、延迟、故障、重载及退出；不连接实际账号、数据库或 Redis。模拟宿主和开发配置注入只用于 Vite 开发服务，默认生产构建只有插件 `index.html`，不含模拟宿主。它便于开发交互，实际会话、权限与代理仍应在宿主集成环境验证。

`client.navigate('/details')` 同步插件内部路由，宿主保存在 `pluginRoute` 查询参数中；插件通过 `route` 事件更新自己的页面。使用 Vite 时采用相对资源基址，如 `base: './'`，前端路由基址使用注入的 `uiBase`。

桥校验同源 origin、消息 source、插件 ID、协议版本和页面连接实例。重载、卸载、退出及超时会清理待处理请求；`destroy()` 用于插件自身清理。响应与宿主请求客户端的 JSON 结构一致，不额外解包 `data`，因此插件接口若返回 `{ code, data, msg }`，页面应按此结构读取。完整的请求、导航和偏好更新示例见 [bundle_demo](../plugins/examples/python/bundle_demo/README.md)。

## 8. 配置项

插件配置写在 `config.items` 中。支持类型：

- `string`
- `number`
- `boolean`
- `select`
- `textarea`
- `password`
- `json`

示例：

```yaml
config:
  items:
    - key: provider
      label: 默认供应商
      type: select
      default: openai
      required: true
      options:
        - label: OpenAI
          value: openai
        - label: Mistral
          value: mistral
    - key: api_key
      label: API Key
      type: password
      default: ""
      secret: true
```

配置命令：

```bash
ruoyi plugin config demo get --env=dev
ruoyi plugin config demo set api_url=https://example.com --env=dev --yes
ruoyi plugin config demo export --env=dev --output-file=demo-config.json
ruoyi plugin config demo import --env=dev --input-file=demo-config.json --yes
```

敏感配置使用 `secret: true`，导出时默认不输出明文。

配置值会按类型进行序列化和反序列化：`boolean` 返回布尔值，`number` 返回数字，`json` 返回对象或数组。更新配置时，未在 `plugin.yaml` 中声明的配置键会被拒绝。

内置管理页会根据 `type` 渲染基础控件，支持必填校验、下拉选项、敏感输入和配置说明；更复杂的分组、排序或提示布局可以在插件自定义页面中消费配置元数据后自行实现。

### 8.1 启动快照、按需读取与生效状态

v2 的 `host.config` 在加载时读取，`host.config_revision` 标识该启动快照。保存配置不会热替换此对象，也不会自动重建连接池、任务或子应用。需要变更这些启动资源时，应保存配置后按部署流程重启所有相关 worker。

Host API `^1.4.0` 提供 `await host.read_config()`，返回 `PluginConfigSnapshot(values, revision)`。每次调用创建独立数据库会话，按**当前进程已加载清单**读取本插件已提交配置并合并默认值，敏感项在插件服务端解密；不接受其他插件 ID，不复用请求事务，不改变 `host.config`。请求、任务或健康检查均可主动调用。数据库故障会抛出异常，不以旧值冒充最新配置；业务代码负责缓存策略和应用失败的处理。一次操作应复用同一个快照，避免中途重复读取导致设置不一致。

```python
async def summary(context: PluginRequestContext) -> dict[str, str]:
    snapshot = await context.host.read_config()
    # 只选取明确可公开的字段，不向浏览器返回整个 values。
    return {'greeting': str(snapshot.values.get('greeting', '欢迎使用'))}
```

`bundle_demo` 的欢迎语按上例每次请求读取，因此保存后点击“刷新状态”即可看到新文案。对于需要异步重建资源的配置，插件应先完成资源校验和替换，再更新自己的业务状态；SDK 的最近读取版本仅证明读取完成，不能证明这些操作成功。

管理页配置弹窗在保存后保留打开，并刷新 `GET /system/plugin/<id>/config/status`。该只读接口要求登录和 `system:plugin:query`，返回保存版本 `desiredRevision`、各进程 `startupRevision`、最近 `lastReadRevision/lastReadAt`，不返回配置值。版本使用绑定插件 ID 的 HMAC，不能按顺序比较；相同有效配置的版本稳定，敏感值变化也会改变版本，宿主 JWT 密钥变化会使版本改变。

`state=restart_required` 表示至少一个已观测活跃进程的启动快照不同；`observed_match` 仅表示已观测到匹配进程且未观测到活跃差异；`unobserved` 表示尚不能确认，包括未启动、v1 或旧宿主。`unknownWorkers` 表示已上报运行指标却未上报配置版本的进程数量。最近按需读取版本不会把旧启动快照标记为已生效。远程数据复用运行观测的 15 秒采样、60 秒 TTL 和读取上限；始终结合 `scope`、缺失/过期/无效计数判断范围，不能把局部匹配当作整个集群一致。

## 9. 依赖管理

插件依赖声明在 `dependencies` 中：

- `python`：Python 包。
- `frontend.<framework>.npm`：对应框架 Web 工程的全部前端运行依赖。
- `frontend.<framework>.npmDev`：对应框架 Web 工程的全部前端开发依赖。
- `plugins`：插件间依赖。

未声明目标框架分类时，该宿主没有 npm 依赖。清单不再接受顶层 `dependencies.npm/npmDev`；迁移时需将依赖完整移入目标分类，同时支持多个框架的包需分别列出。

依赖检查、安装和锁文件生成均针对当前选定的 Web 宿主。默认是 `vue3/web`；验证 Vue2 时，按[基本模型](#1-基本模型)设置 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2`，或通过根目录变量选择具体工程，再运行相同命令。各框架工程不共享 `node_modules`。

检查和安装：

```bash
ruoyi plugin check-deps demo --env=dev
ruoyi plugin allowlist-example --env=dev --dry-run
ruoyi plugin allowlist-example --env=dev --output-path config/plugin_dependency_allowlist.yaml --overwrite
ruoyi plugin lock-deps demo --env=dev --dry-run
ruoyi plugin lock-deps demo --env=dev --offline-dir artifacts/plugin-dependencies --overwrite
ruoyi plugin install-deps demo --env=dev --dry-run
ruoyi plugin install-deps demo --env=dev --yes
```

`allowlist-example` 按需生成插件依赖允许列表示例，默认输出到 `config/plugin_dependency_allowlist.yaml`；仓库不再默认携带 `.example` 文件。建议先用 `--dry-run` 查看模板，再写入正式 allowlist 并按团队实际批准范围调整。

`lock-deps` 默认生成锁文件模板，输出到 `plugins/<plugin_id>/plugin.lock.yaml`；如文件已存在，需要传 `--overwrite` 才会覆盖。默认模式不会联网解析真实版本，也不会写入 hash/integrity；如果传入 `--offline-dir`，命令会从已有本地 wheel/tgz 反填 `resolvedVersion`、Python `hashes` 和 npm/npmDev `integrity`。它仍不会下载、安装或访问 registry，未能反填的项发布前应由人工审核或 CI 流水线补齐。

清单声明 `dependencies.frontend` 时，锁模板只包含当前宿主分类的前端依赖，并记录 `frontendFramework`；安装策略会拒绝框架标识与宿主不一致的锁文件。锁文件产物仍使用顶层 `npm/npmDev` 列表，检查报告的依赖类型也仍为 `npm/npmDev`，它们与 `plugin.yaml` 清单格式不同。

包含旧框架字段 `frontendVersion` 的锁文件会被明确拒绝，不做静默迁移，应按目标框架重新生成并审核锁文件。既没有 `frontendFramework` 也没有旧框架字段的旧锁文件，仍沿用原有依赖项校验。这里的旧锁字段与仍受支持的 `compatibility.frontendVersion` 语义版本约束不同。

建议用 `--output-path` 分别维护各框架的锁文件，安装时用 `--lockfile` 选择。例如先切换到 Vue2，再执行：

```bash
ruoyi plugin lock-deps ai --env=dev --output-path plugins/ai/plugin.vue2.lock.yaml
# 发布流程补齐并审核锁文件中的 resolvedVersion、hash/integrity 后再安装
ruoyi plugin install-deps ai --env=dev --lockfile plugins/ai/plugin.vue2.lock.yaml --dry-run
```

Vue3 使用相同流程，将宿主框架和文件名改为 `vue3`。各框架分别维护宿主依赖锁，不要通过覆盖同一文件共享锁内容。

如果当前终端是交互式 TTY，且输出格式为 text，也可以不传 `--yes`：

```bash
ruoyi plugin install-deps demo --env=dev
```

CLI 会先输出 dry-run 预览和策略判定，再询问是否执行真实安装。非 TTY、JSON 输出和 CI 场景不会进入交互确认，真实安装应显式传 `--yes`。

应用启动时只做默认启用插件的依赖门禁，不会提示安装，也不会执行 `pip install` 或 `npm install`。缺少依赖时应先使用 `ruoyi plugin install-deps` 显式处理。

## 10. 安装、启用、升级和清理

生命周期命令：

```bash
ruoyi plugin list --env=dev
ruoyi plugin info demo --env=dev
ruoyi plugin check demo --env=dev
ruoyi plugin precheck install demo --env=dev
ruoyi plugin install demo --env=dev --yes
ruoyi plugin enable demo --env=dev --yes
ruoyi plugin disable demo --env=dev --yes
ruoyi plugin upgrade demo --env=dev --yes
ruoyi plugin uninstall demo --env=dev --yes
ruoyi plugin purge demo --env=dev --yes
```

批量计划和批量执行：

```bash
ruoyi plugin plan install demo --env=dev
ruoyi plugin batch install demo --env=dev --yes
ruoyi plugin batch enable --env=dev --yes
```

命令语义：

- `install`：执行 migration、seed、菜单、配置、任务安装，并记录 `installed_version`。
- `enable`：启用插件，并恢复菜单和任务状态。
- `disable`：停用插件，并停用菜单和任务。
- `uninstall`：安全卸载，保留可恢复数据。
- `purge`：清理插件平台元数据，属于高风险操作。

生产环境执行危险操作需要显式传入 `--allow-prod --yes`；这两个参数不会绕过服务模式的生命周期限制。v2 签名制品应使用第 15 节的独立维护发布命令，不要通过切换到 dev 环境操作生产数据库。

## 11. 默认启用内置插件

内置插件自动初始化名单写在环境配置中：

```env
APP_DEFAULT_ENABLED_PLUGINS=ai,demo
```

规则：

- 多个插件用英文逗号分隔。
- 留空表示不自动初始化默认启用插件。
- 启动期只会初始化当前环境配置中的默认启用插件。
- 用户在管理端停用或卸载插件后，数据库状态优先。

如果插件只作为可选能力，不要加入 `APP_DEFAULT_ENABLED_PLUGINS`。

## 12. 健康检查和诊断

可在 `backend.health.checker` 声明健康检查：

```yaml
backend:
  health:
    checker: plugins.demo.health:check
```

格式为 `<module_path>:<callable_name>`。健康检查命令：

```bash
ruoyi plugin health demo --env=dev
ruoyi plugin diagnose demo --env=dev --output-file=demo-diagnose.json
ruoyi plugin docs demo --env=dev --output-file=demo.md
```

v2 检查器必须返回 `True` / `False`，或包含布尔字段 `ok` 的字典，例如 `{'ok': True, 'message': '就绪', 'details': {'database': True}}`。`None`、空字典、字符串、数字以及 `{'ok': 'false'}` 都属于契约错误，检查结果为 `ok=False, status=error`，启动时会阻止该插件激活。`message`、`status`、`details` 是可选诊断信息，是否通过始终由 `ok` 决定。未声明检查器时仍返回 `unknown`，表示未执行健康探测；v1 保留原有返回值兼容行为。

### 12.1 v2 运行观测

管理端“插件详情 → 运行观测”可手动刷新。只读接口 `GET /system/plugin/runtime/metrics?pluginId=<id>` 要求宿主登录和 `system:plugin:query`。支持显式 Router、ASGI 的 HTTP/WebSocket 以及宿主分发的 v2 定时任务；v1 扫描路由不纳入本指标。

指标按实际加载的插件、版本、digest、generation 和操作（`http/websocket/job:<id>`）分组，记录调用、在途、成功、拒绝、失败、取消、超时、失败率、平均耗时、最大耗时和近似 P95。失败率为失败次数除以已完成次数（成功、拒绝、失败、取消之和），超时计入失败；P95 是固定直方图区间的上界估计，不是精确分位数。HTTP 耗时覆盖完整响应，WebSocket 耗时覆盖连接生命周期；ASGI 组也包含静态资源和门禁拒绝，因此不能直接理解为某个业务接口的延迟。

ASGI 长连接因登录或权限撤销而关闭时计入“拒绝”，复核不可用计入“失败”，复核超时同时计入“超时”，客户端断开或运行时关闭计入“取消”。SSE 即使已经发送 HTTP 200，也按实际关闭原因分类，错误类型显示 `PluginConnection:<reason>`，不记录用户凭证或异常详情。

每个 worker 从启动开始累计，重启归零，不提供持久历史。每 15 秒向 Redis 发布一次快照，60 秒过期，正常退出仅删除自身快照。接口返回 `scope=reporting_workers` 表示本次有效采样中的进程，并不保证包含全部预期 worker；Redis 不可用时明确返回 `scope=current_worker`。首次启动的远程进程可能需等待一个采样周期才出现。当前进程使用即时快照，远程进程使用最近一次快照。

返回数据包含 `observedWorkers`、采样时间、`invalidSnapshots/staleSnapshots/workerLimitReached` 和各进程的 `droppedSeries`，用于判断采样是否完整。单次最多读取 64 个远程快照，每个进程最多 1024 条指标序列。该页面不替代 `release status` 的发布一致性确认。

请求和任务均设置追踪标识；日志上下文附带插件 ID、版本、制品摘要、代际、worker 和操作。指标只保存最近异常类型、时间和追踪标识，不采集 URL、请求体、认证头或异常消息。可用 `lastErrorRequestId` 关联宿主日志排查。

### 12.2 统一运行诊断

管理端“诊断包 → 原始数据”、`GET /system/plugin/{plugin_id}/diagnose` 和 `ruoyi plugin diagnose` 的 JSON 包中，`runtime` 汇集发布目标、worker 实际加载状态与运行快照。Web 接口要求宿主登录和 `system:plugin:query`。现有页面会保留并显示整个 JSON；诊断弹窗没有文件下载按钮，需要导出时使用 CLI：

```bash
ruoyi plugin diagnose demo --env=dev --output=json
ruoyi plugin diagnose demo --env=dev --output-file=demo-diagnose.json
```

诊断包顶层 `ok` 仍表示原有静态诊断结果，页面的“正常/异常”也读取该字段。已经生成的诊断包通过成功响应返回，检查发现问题时仍保留 `data.ok=false`；插件不存在或诊断包生成失败仍返回失败响应。接口成功不表示全部 worker 已加载目标制品、实时健康或资源已经释放。运行态状态应单独查看 `runtime.state` 和各 worker 的 `freshness/observation`。`runtime.release.summary` 中的目标与 `runtime.workers[].actual` 中实际加载的 `version/digest/generation` 分开记录；`releaseReport` 是发布上报记录，不能代替当前 `actual`。源码插件没有制品摘要和发布代际，对应值为 `null`。

`runtime.state=observed` 表示取得新鲜 worker 快照，不保证该 worker 已加载目标插件；`partial` 表示存在已知采样缺口，`unobserved` 表示没有新鲜快照，`unavailable` 表示运行观测不可用。这些状态均不等同 `healthy`。

诊断进程扫描不到制品 manifest 时，保留 `database_only` 信息并标记静态检查未完成，仍可查看发布与运行快照；此路径不导入制品代码，也不会将尚未检查的配置或结构标记为正常。

采集只观察宿主已经维护的状态，不启动插件、不重新执行健康检查器，也不触发迁移、停用或资源清理。有效快照的 `workers[].actual` 包含以下插件信息，worker 整体清理总数单独放在 worker 行：

| 信息 | 含义与边界 |
| --- | --- |
| `active/ready/closing` | 当前 worker 中实际加载插件的运行与关闭状态。 |
| `lifespan` | ASGI 的 `managed/started/ready/taskActive`；Router 没有 ASGI lifespan，此项为 `null`。 |
| `connections`、`activeJobs` | 宿主登记的 SSE/WebSocket 连接数量和当前任务数量；不枚举插件内部任意协程、线程或原生任务。 |
| `pendingConnectionTasks/pendingJobTasks` | 宿主发出取消后仍未退出、仍保留用于清理的已知任务数量。 |
| `workerPendingCleanupTasks` | 整个 worker 的去重清理任务总数，包含插件子项，不能与上述数量相加。 |
| `activationHealth` | 激活时已执行检查的 `status/checkedAt/durationMs` 历史摘要。未声明或尚未执行检查时为 `unknown`，不等同持续健康探测。 |
| `config` | `startupRevision` 是启动配置，`lastReadRevision/lastReadAt` 是最近一次按需读取，读取完成不表示业务已经应用新配置；修订标识使用 HMAC，不包含运行配置值。 |
| `lastError` | 已有观测记录中的异常类型、`requestId` 和时间；不包含异常消息、堆栈、URL、请求体或凭证。 |

每个 worker 最多报告 1024 个显式加载的插件，超限通过 `droppedPlugins` 表达。`observedTotals` 仅合计本次新鲜 `actual` 中的连接、任务及插件清理计数，其 `totalsScope` 固定为 `fresh_observed_workers`，没有可用观测时为 `null`。`workerPendingCleanupTasks` 不计入这些合计。`observedWorkers` 是包含目标插件新鲜观测的 worker 数量；预期数量和存活报告基线都不可得时，`missingWorkers` 为 `null`。没有采集到的项目使用 `null` 或未知状态，不能把缺失快照解释成连接数为 0、清理完成或插件健康。

配置修订标识在同一插件、相同宿主密钥下可跨 worker 和重启比较；不同环境或密钥轮换后的摘要不能直接用于判断业务配置差异。运行配置的摘要脱敏只针对新增快照，诊断包原有 `config` 区域继续遵循其配置脱敏规则。采集时间、健康检查完成时间、配置读取时间与最近错误时间使用 epoch 秒，耗时 `durationMs` 使用毫秒。

运行快照每 15 秒写入独立的 Redis 诊断命名空间，TTL 为 60 秒；该命名空间以宿主 ready key 加 `:diagnostics:v1` 为前缀，不修改既有运行观测指标的 schema，也不新增数据库表。聚合最多读取 64 个 worker，每份快照最大 512 KiB；返回采样范围、`collectedAt/ageSeconds`，并通过 `invalidSnapshots/staleSnapshots/workerLimitReached` 标记损坏、过期与采样上限。worker 的 `source=current_worker` 表示即时本地采样，`source=redis` 表示周期快照。过期或损坏数据不会作为当前 `actual` 或计入 `observedTotals`，远程结果仅代表最近一次有效采样。

诊断快照按 `runtime.sampleTtlSeconds` 判断新鲜度；数据库中的宿主和插件发布上报按 `runtime.release.workerTtlSeconds` 判断 `host.fresh/releaseReport.fresh`。两种时效独立，发布心跳仍有效不代表运行快照仍可用。

远端快照必须包含完整的协议字段，缺少字段或含非法 UTF-8 的记录按损坏处理，不使用模型默认值补成零计数，也不影响其他有效 worker。最终聚合时会重新校验快照时间，避免将查询过程中已经过期的记录计入结果。

Redis 不可用且本地采样可用时，Web 诊断退回处理当前请求的 worker 的真实本地状态，范围为 `current_worker`；CLI 没有正在服务请求的宿主 worker，运行快照标记为 `unavailable`，不能用 CLI 进程的空状态代替服务器。采样缺失、部分上报和不可用都不表示全部 worker 健康。需要确认发布一致性时，还应结合 `release status` 的目标、存活上报及缺失/陈旧/失败 worker 信息；本诊断不改变发布状态。

## 13. 测试和发布前检查

后端单插件测试：

```bash
ruoyi plugin test demo --env=dev
```

直接运行 pytest：

```bash
pytest tests/plugins/demo
```

代码格式和 lint：

```bash
ruff format plugins/demo tests/plugins/demo
ruff check plugins/demo tests/plugins/demo
```

发布前建议至少执行：

```bash
ruoyi plugin check demo --env=dev
ruoyi plugin check-deps demo --env=dev
ruoyi plugin precheck install demo --env=dev
ruoyi plugin install demo --env=dev --dry-run
ruoyi plugin test demo --env=dev
```

全栈插件还应执行前端构建检查：

```bash
cd ../ruoyi-fastapi-frontend/vue3/web
# Vue2 工程改为：cd ../ruoyi-fastapi-frontend/vue2/web
npm run build:prod
```

## 14. 开发规范清单

提交前确认：

- 插件 ID、后端模块、前端插件目录三者一致。
- 菜单权限全部声明在顶层 `permissions`。
- source 菜单组件路径能映射到实际 Vue 文件；bundle 页面使用 `PluginFrame` 且 HTML 入口存在。
- SQL seed 可重复执行。
- migration 和 seed 不写插件目录外文件。
- 生命周期钩子中的全局写操作检查 `startup_write_enabled`；v2 ASGI 资源使用 lifespan 初始化及释放。
- 依赖声明完整，并通过 `check-deps`。
- 插件状态只使用 `status` 的四个生命周期值。
- v2 显式入口同步返回 `PluginDefinition`，异步回调符合 SDK 参数和 awaitable 约定。
- 原生扩展及 bundle 已在目标环境验证；签名制品的运行期文件写到制品目录之外。

## 15. v2 签名制品与维护发布

### 15.1 制品目录与信任配置

`.rpk` 是受约束的 ZIP。它只接受 `manifestVersion: 2`，前端交付类型为 `none` 或 `bundle`；目录名必须等于清单中的插件 ID。先构建 Rust wheel、独立前端和其他部署资源，再对准备好的插件目录签名。原生插件使用已展开且通过 wheel 校验的 `native/` 目录；制品导入不会替你执行 Cargo、maturin、npm、pip 或插件入口。

```text
sample.rpk
  artifacts.json
  signature.json
  payload/
    <plugin_id>/
      plugin.yaml
      native/...       # 原生插件的预编译模块与发行包元数据
      web/dist/...     # bundle 插件的前端构建产物
      migrations/...  # 清单声明的资源，按需交付
      plugin.lock.yaml
```

Python 插件仍交付自身 Python 文件；`.rpk` 的签名不提供源码加密。打包目录不能包含 Rust/前端开发工程、`.env`、版本库、`node_modules` 或构建缓存。构建器忽略 Python/测试缓存，已导入目录的复验则拒绝任何额外文件，包括新增的 `__pycache__`。插件运行期文件、日志、上传和缓存必须存放在制品目录之外。

签名私钥由发布者保管，使用 Ed25519 PKCS8 PEM，必须放在插件源码及预构建目录之外；不要交付给宿主运行进程。加密私钥可通过 `artifact build --password-env <环境变量名>` 读取密码。宿主只配置经过独立可信渠道取得的公钥，并为每个 keyId 指定可发布的插件 ID。包内 `signature.json` 的 keyId 只用于查询宿主信任配置，包内自带的公钥不能建立信任。

宿主环境配置示例，路径相对于后端项目目录：

```env
PLUGIN_ARTIFACT_ENABLED=true
PLUGIN_ARTIFACT_STORE=vf_admin/plugin_artifacts
PLUGIN_ARTIFACT_TRUST_FILE=config/plugin_publishers.json
PLUGIN_ARTIFACT_HEARTBEAT_SECONDS=15
PLUGIN_ARTIFACT_WORKER_TTL_SECONDS=60
```

功能默认关闭。存储目录不能是后端项目本身、其上级或 `plugins/` 内部；它及其路径组件不能使用符号链接或 Windows 重解析点。TTL 至少为心跳间隔的三倍。启用前先按宿主数据库升级流程准备新增的制品、发布目标和 worker 状态表，不能把插件的业务 migration 当作宿主表升级。

目录隔离不提供同进程 Python 依赖隔离。原生发行包和插件缺少或冲突的依赖应在维护环境处理，导入及 worker 启动不会隐式安装依赖。

新建数据库使用的 [MySQL 初始化 SQL](../sql/ruoyi-fastapi.sql) 和 [PostgreSQL 初始化 SQL](../sql/ruoyi-fastapi-pg.sql) 已包含这三张宿主状态表。已有数据库按 [CLI 数据库迁移流程](cli_usage.md#43-数据库迁移)生成迁移文件，补齐并审查这三张表的建表、索引和约束后执行升级，不要在已有数据库上直接重跑完整初始化 SQL。普通 worker 不会隐式创建签名插件的业务表，业务结构由维护准备的迁移负责。

`config/plugin_publishers.json` 格式如下；`publicKey` 占位符必须替换为真实 Ed25519 公钥的 PEM 字符串或 32 字节原始公钥的标准 Base64：

```json
{
  "schemaVersion": 1,
  "keys": [
    {
      "keyId": "publisher",
      "publicKey": "<通过可信渠道取得的公钥>",
      "pluginIds": ["rust_demo", "asgi_demo", "bundle_demo"],
      "enabled": true
    }
  ]
}
```

`pluginIds: ["*"]` 表示明确授权所有插件，应按实际发布职责配置范围。删除发布者或设置 `enabled: false` 后，后续验签、导入、维护准备和启动读取均按当前信任配置拒绝该签名；已经导入过不构成永久信任。已运行的代码不会因为编辑信任文件而自动热卸载，需要停止进程并完成维护处置。

### 15.2 构建、校验和导入

以下命令在后端目录执行，示例采用已构建好的 Rust 交付目录。私钥路径为示例，需替换为发布者实际管理的路径。

```bash
ruoyi plugin artifact build target/native-package/rust_demo target/rust_demo-1.0.0.rpk --key-file ../signing-keys/publisher.pem --key-id publisher --env=dev --output=json
ruoyi plugin artifact verify target/rust_demo-1.0.0.rpk --env=prod --output=json
ruoyi plugin artifact import target/rust_demo-1.0.0.rpk --env=prod --dry-run --output=json
ruoyi plugin artifact import target/rust_demo-1.0.0.rpk --env=prod --allow-prod --yes --output=json
ruoyi plugin artifact list --plugin-id rust_demo --env=prod --output=json
```

`build` 不覆盖已有输出。`verify` 只检查签名、全部文件摘要和发布者授权；`import --dry-run` 还检查源码目录冲突，但不展开目录，因此不代替正式导入的平台和结构检查。正式导入先接收私有快照，验签后展开到临时目录，完成兼容性与结构检查，再原子发布并登记数据库索引。所有路径、文件大小、解压数量和库存均受校验，链接与特殊文件会被拒绝。导入成功只代表制品可供维护流程选择，不执行 migration、seed 或 Hook，也不修改当前发布目标。

已导入目录固定为：

```text
<PLUGIN_ARTIFACT_STORE>/<plugin_id>/<version>/<digest>/
  artifacts.json
  signature.json
  payload/<plugin_id>/...
```

同 ID 的 `plugins/<plugin_id>` 源码目录会阻止制品导入和使用。迁移部署方式时应先在维护窗口备份并移出旧目录，保留数据库安装状态；不能留下旧源码并期待制品覆盖它。原有版本已经安装但没有对应制品的准备证据时，需要发布更高版本，不能根据版本号猜测对应 digest。

重复导入不会覆盖现有对象；每次使用仍校验当前信任、文件库存和摘要。文件落盘与数据库登记不共享事务：登记失败时保留已验签对象，修复数据库后重试同一导入可完成登记。不要修改已导入目录来修复代码或权限；修改内容应生成新的制品。

### 15.3 停机维护、准备证据与目标选择

流程为：导入 → 查看计划 → 停止全部宿主 worker → 独立维护进程准备 → 读取发布代际 → 选择目标 → 启动全部 worker → 查看实际加载状态。第一版采用完整维护窗口，不提供二进制热替换或自动滚动发布。

下面命令中的 `DIGEST` 和 `GENERATION` 是占位符，执行前必须替换：`DIGEST` 原样取自导入或列表结果；`GENERATION` 取自本次准备后最新的 `status` 结果，不能自造、使用空值或根据版本推断。

```bash
ruoyi plugin release plan rust_demo DIGEST --env=prod --output=json
ruoyi plugin release prepare rust_demo DIGEST --env=prod --dry-run --output=json
```

计划及 dry-run 不执行 migration 或 Hook。确认计划和依赖后，通过现有进程管理器停止全部宿主 worker，再执行：

```bash
ruoyi plugin release prepare rust_demo DIGEST --maintenance --env=prod --allow-prod --yes --output=json
ruoyi plugin release status --plugin-id rust_demo --env=prod --output=json
ruoyi plugin release select rust_demo DIGEST --expected-generation GENERATION --expected-workers 2 --maintenance --env=prod --allow-prod --yes --output=json
```

`--expected-workers 2` 只是示例，必须填写本次实际部署的宿主 worker 数。CLI 不负责停止或启动宿主。`--maintenance` 是操作者已停机的声明；服务还会检查当前有效心跳，发现存活 worker 时拒绝执行。心跳过期不是进程已停止的充分证据，不能仅等 TTL 而保持旧进程运行。

每次维护使用新 CLI 进程。`prepare` 复用安装/升级生命周期，执行需要的 migration、seed、菜单、配置、任务及 Hook。成功后记录精确的 `preparedDigest` 和 `preparedVersion`；`preparedVersion` 对应数据库的 `installedVersion`。相同版本只有已有准备证据同时匹配 digest 和数据库版本时才能复用；同版本换包、仅手工修改安装版本或缺失证据均不能跳过准备，应提升版本重新发布。准备失败不代表数据库 DDL 已自动回滚，应检查错误及迁移记录，修复后采用明确的新版本处理。

`select` 只接受已准备的指定 digest，并以 `--expected-generation` 做并发条件更新；代际已变化时拒绝覆盖，应重新查询和审阅。首次 `plan` 可能尚无 generation，因此应在成功 `prepare` 后读取 `status`。选择目标不修改 `installedVersion`，也不代替启用操作：首装沿用生命周期默认开关，升级保留原有 enabled 状态，已停用插件不会因为选择新制品自动启用。

启动全部 worker 后再执行 `release status`。`targetDigest` 是选择目标，`workers[].digest/version/generation/state` 才是各进程报告。`installedVersion` 是数据安装版本，不能据此判断进程实际加载的代码。

| 发布状态 | 含义 |
| --- | --- |
| `no_target` | 尚未选择运行目标 |
| `pending_restart` | 目标已选择，尚无足够且匹配的就绪报告 |
| `partial` | 部分 worker 已就绪或确认停用，其他 worker 尚未满足发布目标 |
| `failed` | 尚无匹配成功的 worker，且存在失败报告 |
| `active` | 存活宿主数量达到预期，所有存活宿主均报告目标 digest 和 generation 已就绪 |
| `disabled` | 停用目标已被足够且全部存活宿主确认，插件报告同一代际的 stopped 状态 |

诊断同时检查 `prepareStatus`、`enabled`、`restartRequired`、`missingWorkers`、`mismatchWorkers`、`staleWorkers`、`failedWorkers` 和 `workers[].error`。例如插件已停用会阻止业务激活，不能仅因没有 `active` 就反复重启。状态汇总依赖宿主级心跳，不会只统计已经成功加载该插件的进程。真实数据库、多 worker、反向代理及运维进程管理仍需在部署环境验收。

流水线可通过 `release wait` 等待精确目标收敛。保存刚才 `select` 返回的 `generation` 为 `SELECTED_GENERATION`；如果随后执行 `enable` 或 `rollback`，改用该操作返回的新代际。通过进程管理器启动全部 worker 后执行：

```bash
ruoyi plugin release wait rust_demo DIGEST --generation SELECTED_GENERATION --expected-workers 2 --timeout 300 --interval 2 --env prod --output json
```

四个固定目标均必填：插件 ID、64 位小写 SHA256 digest、32 位小写十六进制 generation 和正整数 expected-workers。等待使用的 generation 是变更后返回的新值，与 `select/enable/rollback` 的 `--expected-generation` 变更前并发令牌不同。预期 worker 数量必须与当前发布记录一致；等待期间目标摘要、代际或预期数量变化都会立即失败，不会自动追踪另一次发布。

仅当目标处于启用状态、所有有效存活宿主均报告相同 digest 和 generation 已就绪，且存活数量达到固定的预期下限时，结果才是 `converged`。超过预期数量的存活宿主也必须全部就绪；缺失或过期报告不能补足数量。已经退出的历史 worker 的陈旧记录不会阻止足够的新 worker 收敛。部分成功的摘要可能同时含失败 worker，因此不能只用 `status=partial` 继续等待而忽略失败计数。

命令只查询已有发布状态，不选择目标、执行 Hook、迁移、重启或创建诊断采样，不接受 `--maintenance`、`--allow-prod`、`--yes` 或 `--dry-run`。默认轮询 300 秒、间隔 2 秒；超时必须为有限非负数，间隔必须为有限正数。`--timeout 0` 只进行一次状态查询，适合已完成外部等待后的断言：

```bash
ruoyi plugin release wait rust_demo DIGEST --generation SELECTED_GENERATION --expected-workers 2 --timeout 0 --env prod --output json
```

超时约束核心轮询，不包含此前的配置初始化和模块导入。单次状态查询上限为 10 秒，非零等待还受剩余轮询预算约束；查询取消采用异步协作机制。`timeout 0` 也有单次查询上限，不表示跳过查询。

JSON 标准输出只包含一个最终对象：`ok`、`operation=release_wait`、`reason`、`message`、固定 `target`、`lastObserved`、`attempts`、`elapsedSeconds`、`timeoutSeconds` 和 `intervalSeconds`。`lastObserved` 仅保留发布摘要的白名单字段，不带 `workers[].error`、`lastError` 或原始异常正文。没有有效观测时它为 `null`；CLI 取消或初始化失败无法确认查询进度时，`attempts` 也为 `null`。`target` 包含 `pluginId/digest/generation/expectedWorkers`，不会被后续查询改写。

`lastObserved` 是最后一次可用观测；`timeout` 或 `unavailable` 时可能保留前一轮已经过期的摘要。自动决策应以最终 `ok/reason` 和退出码为准，不能因为其中仍有 `status=active` 就认定本次等待成功。

| `reason` | 含义与退出码 |
| --- | --- |
| `converged` | 固定目标已收敛，退出 `0`。 |
| `not_converged` | 单次断言获得有效状态，但尚未收敛，退出 `50`。 |
| `timeout` | 非零轮询预算耗尽仍未收敛，退出 `50`。 |
| `target_missing` | 没有指定插件的发布目标，退出 `50`。 |
| `target_changed` | 当前摘要、代际或预期数量与固定目标不同，退出 `50`。 |
| `target_disabled` | 当前发布目标已停用，退出 `50`。 |
| `worker_failed` | 已观测到当前发布的 worker 故障，退出 `50`。 |
| `unavailable` | 配置初始化、状态读取或有界查询不可用，退出 `50`。 |
| `invalid_observation` | 返回状态结构不完整或不符合观测契约，退出 `50`。 |
| `invalid_arguments` | CLI 在服务创建前拒绝无效固定目标或时间参数，退出 `2`。缺少参数或未知选项由解析器直接以 `2` 拒绝。 |
| `cancelled` | CLI 收到异步取消或键盘中断，输出固定脱敏结果并退出 `50`。 |

`release status` 的顶层 `ok` 保持“状态查询成功”的含义，即使目标尚未生效也可能是 `true`。流水线应判断 `release wait` 的退出码与原因；就绪报告仍不能代替插件业务接口验收。

管理页提供制品与发布状态的只读查看入口，签名制品使用上述维护 CLI 完成变更。对应 HTTP 查询均要求宿主登录及 `system:plugin:query` 权限：

| 接口 | 参数与用途 |
| --- | --- |
| `GET /system/plugin/artifacts/list` | 可选 `pluginId`，查询已验证制品 |
| `GET /system/plugin/release/status` | 可选 `pluginId`，查询目标及各 worker 的实际报告 |
| `GET /system/plugin/release/plan` | 必填 `pluginId`、`digest`，读取静态发布预检计划 |
| `GET /system/plugin/runtime/metrics` | 可选 `pluginId`，按实际运行版本读取请求、连接和任务累计指标 |
| `GET /system/plugin/<id>/config/status` | 比较保存配置与已观测进程的启动快照，显示按需读取版本，不返回敏感值 |

当前宿主未启用制品发布监控时，管理页显示状态不可确认。worker 心跳只报告已加载的目标快照，不会自动选择新目标；选择目标成功也不代表运行中的进程已更新。

### 15.4 维护启停、代码回滚与签名轮换

已选择且具备完整准备证据的制品可通过独立维护命令启停。先停止全部宿主 worker，读取最新 `release status` 的 generation，再根据需要执行下面其中一个命令：

```bash
ruoyi plugin release disable rust_demo --expected-generation GENERATION --maintenance --env=prod --allow-prod --yes --output=json
ruoyi plugin release enable rust_demo --expected-generation GENERATION --maintenance --env=prod --allow-prod --yes --output=json
```

每次成功操作都会生成新 generation，不能共用旧代际连续启停。命令先做依赖预检，再在一个数据库事务中更新 enabled、关联菜单、插件拥有的任务、发布代际和审计；任一步失败整体回滚。启用时仍尊重任务自身的 `enabled: false` 声明，不会误改同名前缀的人工任务。当前目标、上一目标和数据库安装版本保持不变，`previousDigest` 仍可供代码回滚使用。命令成功后启动全部 worker；停用和启用都不通过热卸载/热挂载实现。

回滚只选择 `previousDigest` 指向的上一代码制品。先确认旧代码兼容当前数据库结构，停止全部宿主 worker，再读取最新 `status` 的 generation：

```bash
ruoyi plugin release rollback rust_demo --expected-generation GENERATION --schema-compatible --maintenance --env=prod --allow-prod --yes --output=json
```

命令会重新验签并静态检查上一制品，重建其菜单、配置和任务声明；不执行旧版 migration、seed 或 Hook，不倒退 `installedVersion`。`--schema-compatible` 是运维人员的兼容性确认，不是自动推导出的数据库降级方案。随后启动全部 worker 并检查 `release status`。若旧代码不能使用当前数据结构，应制定数据库恢复方案，不能用代码回滚命令替代。

当前没有自动停止进程或热卸载。ASGI SSE/WebSocket 支持周期权限复核及当前 worker 的运行时关闭回收，但这不代替维护窗口和全部进程退出。修改 enabled、选择目标或撤销签名密钥均不能卸载进程中已加载的 Python/Rust 模块，发布目标和签名状态也不属于连接的周期复核内容。制品清理与签名轮换使用下面的独立维护命令。

制品 digest 是规范化 `artifacts.json` 的 SHA256，覆盖每个有效载荷文件的路径、大小和摘要，不包含签名或 keyId。普通重复导入仍不覆盖原对象。需要保持同一内容轮换密钥时：先把新公钥加入外部信任文件并授权该插件；用新私钥对原构建目录重新打包；停止全部 worker，读取当前 `artifact list` 的 keyId，再执行：

```bash
ruoyi plugin artifact build target/native-package/rust_demo target/rust_demo-rotated.rpk --key-file ../signing-keys/publisher-next.pem --key-id publisher-next --env=dev --output=json
ruoyi plugin artifact rotate-signature target/rust_demo-rotated.rpk --expected-key-id publisher --maintenance --env=prod --allow-prod --yes --output=json
```

命令以新可信签名核对原目录的全部字节，再原子替换签名、CAS 更新索引并记录审计；digest、版本、发布引用和 generation 保持不变。旧密钥已撤销也可执行，因为新签名必须独立证明现有内容。新制品内容或版本不同、发布者越权、原目录篡改、原 keyId 变化均拒绝操作。成功后检查制品并重启全部 worker，再移除不再需要的旧公钥；无需重跑迁移。

### 15.5 制品检查、保留策略与中断恢复

只读检查规范存储目录与数据库索引，显示 `registered/orphan/missing/invalid`、引用保护原因和候选清理摘要：

```bash
ruoyi plugin artifact inspect --env=prod --output=json
ruoyi plugin artifact prune --keep-last 2 --min-age-days 7 --env=prod --output=json
```

`prune` 默认只预演。默认保留每个插件最近导入的 2 个制品以及未满 7 天的对象；按导入时间排序，不按语义版本排序。同版本的不同平台构建分别计数。当前目标、上一目标、已准备制品，以及未报告 stopped 的进程所引用的摘要始终保护，过期心跳也不会自动解除引用。缺失、无效、已撤销签名或静态检查不通过的对象只报告问题，不自动删除；`.staging/.locks` 等内部目录不属于该清理计划。

核对完整 `objects/protectedBy/candidates` 和 `planId` 后，停止全部宿主进程，使用同一保留参数执行：

```bash
ruoyi plugin artifact prune --keep-last 2 --min-age-days 7 --expected-plan PLAN_ID --execute --maintenance --env=prod --allow-prod --yes --output=json
```

清理、导入、签名轮换和发布共用全局生命周期锁。正式执行会重新检查计划与进程报告；计划变化必须重新预演。每个候选先移入存储内部隔离目录，再提交索引删除和审计，最后验证并清理隔离对象。多对象操作按对象提交，后续对象失败不会撤销已经完成的清理。

文件与数据库不共享事务，因此 `.maintenance` 保存中断恢复日志。存在未完成日志时拒绝导入与制品加载，先保持停机并执行：

```bash
ruoyi plugin artifact reconcile --maintenance --env=prod --allow-prod --yes --output=json
```

恢复以已提交索引为准：清理未提交时恢复原目录，已提交时完成隔离对象删除；签名轮换按索引中的新旧 keyId 恢复相应签名。恢复同样检查路径、摘要和当前信任，不执行插件代码、迁移或 Hook。若日志损坏、文件丢失或删除中途发生文件系统故障，命令保留证据并报错，需要根据备份人工处理，不能通过删除日志强行启动。恢复旧签名后若该密钥已撤销，仍需再次完成新签名轮换才可加载。

## 16. v2 项目脚手架与完整构建

现有 `create` 默认仍为 v1 `full-stack`。下列显式模板创建独立源码工程，统一位于后端 `plugin-projects/<id>/`；创建工程不安装、启用或导入插件。该目录与运行中的 `plugins/`、不可变制品存储分开，避免原生开发工程参与运行时扫描或与同 ID 制品冲突。

| 模板 | 后端 | 前端 | 交付准备 |
| --- | --- | --- | --- |
| `python-asgi` | Python ASGI | 无 | 生成的 `build_release.py` |
| `python-bundle` | Python ASGI | 独立 Vite bundle | 先构建 `web/`，再运行 `build_release.py` |
| `rust-asgi` | Rust PyO3 ASGI | 无 | 宿主 `scripts/build_native_plugin.py` |
| `rust-bundle` | Rust PyO3 ASGI | 独立 Vite bundle | 先构建 `web/`，再运行原生构建器 |

```bash
ruoyi plugin create report_center --template rust-bundle --env dev --dry-run
ruoyi plugin create report_center --template rust-bundle --env dev
```

每个工程包含 v2 清单、受 `<id>:view` 权限保护的 `/api/info`、显式入口、健康检查、lifespan、构建与发布 README，以及 SDK 合约测试。Rust 模板固定 `ruoyi_plugin_<id>` Python 命名空间，包含锁定的 Cargo 依赖。bundle 复制当前宿主的 bridge SDK 及配套 `.d.ts`，使用相对资源基址和专用插件会话，不内嵌主登录 token。独立 bundle 与宿主前端框架解耦，v2 模板的 `--frontend-framework` 只允许默认值 `auto`；bundle 也不能配合 `--backend-only`。

bundle 安装 npm 依赖后，可运行 `npm --prefix plugin-projects/report_center/web run dev`，自动打开生成的 `/dev.html`。`dev.js` 提供 `/api/info` 的内存模拟、主题、延迟、故障、重载和退出，可按业务扩展；默认模板未实现文件或 SSE 业务接口。模拟配置仅在开发服务注入，生产构建不包含开发宿主。文件与 SSE 的完整示例见 `bundle_demo`。

以下以 Rust bundle 为例，在后端目录及已激活的 Python 环境执行。构建机需具备前述 Rust、maturin、平台编译工具和 Node.js，运行宿主只接收构建产物。构建命令三种平台通用：

```bash
npm --prefix plugin-projects/report_center/web install
npm --prefix plugin-projects/report_center/web run build
python scripts/build_native_plugin.py --source plugin-projects/report_center --output target/report_center-package
```

随后指定交付目录并测试。Windows PowerShell：

```powershell
$env:RUOYI_PLUGIN_DIRECTORY = (Resolve-Path 'target/report_center-package/report_center').Path
python -m pytest plugin-projects/report_center/tests -q
```

macOS / Linux（Bash、Zsh）：

```bash
export RUOYI_PLUGIN_DIRECTORY="$(pwd)/target/report_center-package/report_center"
python -m pytest plugin-projects/report_center/tests -q
```

首次 `npm install` 产生的 `package-lock.json` 应随源码提交，后续构建可用 `npm ci`。原生构建器不会代替你运行 npm；缺少 bundle HTML 入口时在编译前报错。它只组装原生发行包、清单声明的迁移/seed 文件或目录、可选插件锁文件和已构建 bundle，拒绝链接、重解析点、硬链接、开发工程及敏感配置进入交付。`target/report_center-package/report_center` 才是签名输入，不是 wheel 所在目录或源码工程。

Python 模板将上一例中的原生构建步骤替换为：

```bash
python plugin-projects/report_center/build_release.py --output target/report_center-package
```

Python 打包器固定复制 `plugin.yaml`，按生成的 `release-files.json` 纳入显式业务 `.py/.sql` 文件，再复制构建后的 bundle；新增业务模块与 SQL 时维护该清单，规则见第 16.2 节。Python 插件仍以 Python 源码交付。Rust 交付不包含 `.rs`、Cargo 或前端开发工程；两种方式均需按第 15 节签名、导入、维护准备、选择目标及重启验收。所有构建输出必须使用新目录，不能覆盖已加载版本。

### 16.1 桥接 SDK 溯源与显式更新

bundle 工程的 `web/vendor/pluginBridge.sdk.json` 记录独立 `sdkVersion`、桥协议 `bridgeVersion`、可选文件/SSE 能力版本、来源位置及 JS/类型声明摘要。SDK 的初始版本为 `1.0.0`，与宿主 Host API 版本和桥协议 v1 分开管理；只读导出 `PLUGIN_BRIDGE_SDK_VERSION` 不增加消息字段。纯 API 模板不生成前端 SDK。

摘要算法为 `sha256-utf8-lf`：按 UTF-8 读取、去掉可选的 UTF-8 BOM，再将 CRLF/CR 统一为 LF 后计算 SHA256，因此 Windows 和 Linux 的正常换行转换不会被判为业务修改。该记录用于源码追踪和修改检测，不提供签名可信性；同一 SDK 版本下来源内容变化也会被检出，SDK 维护者仍应按变更发布新的版本。

在后端目录使用离线命令：

```bash
ruoyi plugin sdk check plugin-projects/report_center --output=json
ruoyi plugin sdk update plugin-projects/report_center --dry-run --output=json
ruoyi plugin sdk update plugin-projects/report_center
npm --prefix plugin-projects/report_center/web run build
```

SDK 命令的 `--frontend-framework` 当前固定可选 `auto`、`vue2`、`vue3`，默认值为 `auto`。默认来源为 `ruoyi-fastapi-frontend/vue3/web`；可用 `--frontend-framework=vue2` 选择 Vue2 Web，`auto` 则跟随框架环境变量和显式根目录选择。通用来源目录为 `ruoyi-fastapi-frontend/<framework>/web`，所选工程必须提供对应 bridge SDK 文件；指定框架不会生成这些文件。独立检出时可传 `--frontend-root PATH`，或设置 `RUOYI_PLUGIN_FRONTEND_ROOT`。命令只静态读取工程清单和固定 SDK 文件，不导入插件、不读取宿主运行环境、不连接数据库或 registry。清单检查仅确认 YAML 可读、`manifestVersion: 2` 和 bundle 工程类型，不执行完整插件清单校验；完整检查与业务测试仍按第 13 节执行。

| `check` 状态 | 含义与处理 |
| --- | --- |
| `current` | 记录、版本及文件摘要与选定来源一致，退出码为 0。 |
| `outdated` | 本地 SDK 与其记录一致，但与选定来源不同；返回非零，可显式更新。来源可能比本地旧，命令不替你决定是否降级。 |
| `modified` | SDK 文件与本地记录不一致；先审阅自己的改动。 |
| `untracked` | 旧工程缺少溯源记录，不能假定原副本未修改。 |
| `invalid` | 工程、文件或元数据无效；按错误信息修复。 |
| `incompatible` | 桥协议不同，需要先完成协议迁移；`--force` 不会绕过。 |

`protocolCompatible` 仅表示桥协议版本一致；可选能力可增减，不能据此推断所有业务功能都能运行。前端测试固定保留上轮 SDK 客户端，验证旧客户端与当前宿主的 JSON、文件和 SSE 调用；当前客户端遇到旧宿主未公布或不支持的能力时明确拒绝，并保留可用的 JSON 通道。

更新只处理 `pluginBridge.js`、`pluginBridge.d.ts` 和 `pluginBridge.sdk.json`。写入前将原文件保存到工程 `.plugin-sdk-backups/<唯一目录>/`，写入异常会尝试恢复原内容，溯源记录最后替换；同一工程并发更新被拒绝，符号链接和越界路径也被拒绝。正在构建时应先停止构建再更新，三个文件不构成跨文件系统原子事务；进程被强制终止后需先核对备份与文件状态，再人工处理遗留更新锁，不能把删除锁当作已完成恢复。

本地修改、旧副本或可安全备份的损坏溯源记录，默认不会被覆盖。确需用选定来源重新纳管时，先执行 `update --force --dry-run`，审阅结果后再执行 `update --force`；非法 YAML、非 v2 bundle 工程、无效来源 SDK 或不安全路径不能通过此选项绕过。业务源码不受影响，已构建的 `web/dist` 也不会自动改变；更新后要重建、回归，再按正式流程发布。

### 16.2 Python 业务模块与迁移交付

新生成的 Python 工程包含 `release-files.json`，初始为 `{"schemaVersion": 1, "files": ["__init__.py"]}`。该文件供独立构建脚本使用，不属于运行时插件清单，也不进入制品。示例扩展：

```json
{
  "schemaVersion": 1,
  "files": [
    "__init__.py",
    "models.py",
    "service.py",
    "migrations/mysql/001_init.sql",
    "migrations/postgresql/001_init.sql"
  ]
}
```

文件必须显式列出，使用插件源码根目录下的相对路径，仅接受 `.py/.sql`；不接受目录、通配符、路径跳转、隐藏路径、开发目录、重复或大小写冲突以及链接、重解析点和硬链接。配置最多 64 KiB、1024 项。`plugin.yaml` 固定复制，bundle 的 `web/dist` 沿用静态扩展名白名单及链接检查。构建器先校验全部输入再创建输出目录，不导入插件、不安装依赖、不执行迁移。新增 SQL 还须加入 `plugin.yaml` 的迁移声明，并测试清单与实际制品一致；制品预检仍负责验证插件结构与迁移引用。

已生成的旧构建脚本不会自动改变，可以继续按原有约定交付；采用新脚本时应一并迁入文件清单，再验证完整交付目录。不要直接将整个 Python 工程、凭据、前端源码或依赖目录签名发布。

[`task_demo`](../plugins/examples/python/task_demo/README.md) 展示完整的共享任务业务：独立 bundle 表单、分页与状态筛选、`view/write` 分权、SDK 显式事务、参数校验、MySQL/PostgreSQL SQL，以及从 1.0 数据结构到 1.1 优先级字段的数据保留。示例源码与生成工程使用同一构建器契约；数据库写入不发生在插件启动阶段。

## 17. 本地真实服务验收与 CI

本节用于插件交付前的自动化回归和部署环境验收。插件自身的测试与静态检查见[第 13 节](#13-测试和发布前检查)，v2 工程构建及合约测试见[第 16 节](#16-v2-项目脚手架与完整构建)，签名交付与维护操作按[第 15 节](#15-v2-签名制品与维护发布)执行。

### 17.1 本地自动化回归

在后端目录、已安装宿主依赖的 Python 环境中执行。下面的命令适用于 Windows PowerShell、macOS 和 Linux：

```bash
python -m pip install pytest pytest-asyncio aiosqlite
python -m pytest tests/cli/runtime/plugin/test_runtime_scaffold.py tests/cli/runtime/plugin/test_runtime_scaffold_v2.py -q
python -m pytest tests/plugins/examples/test_task_demo.py tests/plugins/core/deployment/test_task_delivery.py -q
python -m pytest tests/plugins/core/artifacts tests/plugins/core/deployment tests/plugins/core/management/test_release_dao.py tests/plugins/core/management/test_artifact_views.py tests/module_plugin/controller/test_plugin_release_controller.py tests/cli/root/test_plugin_artifact_commands.py tests/cli/root/test_plugin_release_wait.py tests/sql/test_plugin_release_schema.py -q
```

上述回归覆盖脚手架、签名制品、维护发布、固定目标等待与单次断言、状态查询及数据库脚本约束。原生插件还应在目标平台构建后执行[原生示例的集成验证](../plugins/examples/rust/rust_demo/README.md#本地集成验证)；测试因缺少原生制品而跳过时，不能据此确认原生交付可用。

bundle 插件完成独立前端构建后，还应执行宿主桥接测试（在后端目录执行，三种平台通用）：

```bash
npm --prefix ../ruoyi-fastapi-frontend/vue2/web run test:plugin
npm --prefix ../ruoyi-fastapi-frontend/vue3/web run test:plugin
```

### 17.2 真实服务与多 worker 验收

准备独立的测试数据库、Redis、制品存储和发布者密钥，配置与目标部署一致的数据库类型、代理前缀、TLS 和 worker 数量。记录初始插件版本、数据库安装版本、目标 digest 和 generation；验收中的导入、迁移、目标选择及重启沿用第 15 节的正式维护流程。

按下表逐项确认结果：

| 场景 | 验收要求 |
| --- | --- |
| 首次发布 | 验签与导入成功，完成维护准备和目标选择；重启后所有预期 worker 报告同一 digest、generation，汇总状态为 `active`。 |
| 升级 | 停止全部 worker 后准备新版本；迁移成功记录不重复执行，重启后全部 worker 加载新目标。 |
| 代码回滚 | 确认旧代码兼容当前数据结构后选择上一目标并重启；运行代码回退，数据库安装版本和迁移历史保持不变。 |
| 维护互斥 | 存在有效 worker 心跳时，维护准备被拒绝；并发维护操作不能绕过生命周期锁。 |
| 部分启动失败 | 某个 worker 的初始化或健康检查失败时，发布状态及错误可诊断，不能把该 worker 计为已就绪。 |
| 进程退出与重启 | 正常退出后释放资源；异常退出后的陈旧报告不再计入存活数量，新进程按当前目标加载。 |
| 登录与权限 | 未登录、缺少插件权限或会话退出后的请求被拒绝；已授权用户能调用插件 API。bundle 页面另外验证会话、CSRF、资源路径和代理前缀。 |
| 制品完整性 | 加载前后的签名与文件摘要检查通过，运行时未向不可变制品目录写入业务数据或缓存。 |

保留每次操作的输出、发布状态和各 worker 的错误信息。成功依据是预期 worker 的实际就绪报告及业务接口验证，不能仅以导入成功、目标已选择或单进程测试通过判定部署完成。

### 17.3 数据隔离与清理

验收前明确本次使用的数据库、Redis 命名空间、制品目录和进程范围。结束后停止本次启动的进程、关闭连接并按记录清理临时资源；清理失败时保留资源标识供后续处理。插件自身的 migration 和回滚兼容性需要结合真实业务数据验证。

反向代理、TLS、跨机器网络、既有 WebSocket 或长连接排空仍需在实际部署拓扑中验收。自动化回归不替代这些检查。

### 17.4 CI 覆盖

仓库的原生插件工作流配置 Windows/Linux、Python 3.10、3.11、3.12、3.13 构建测试矩阵，覆盖 v1/v2 脚手架、SDK 溯源与离线更新命令、原生扩展以及签名制品与维护发布回归。

发布集成工作流在 Python 3.10、3.11、3.12、3.13 上使用临时 MySQL、PostgreSQL 和 Redis 服务验证多 worker 发布行为。工作流配置不代表已经执行成功；发布前应核对对应提交的实际 CI 结果，并完成目标平台的部署验收。

`scripts/plugin_release_integration.py` 还检查双 worker 首次发布、升级和代码回滚后的固定目标收敛，无 worker 时单次断言不收敛，旧目标代际被拒绝、单 worker 故障立即失败，以及报告过期、缺员和遗留陈旧记录下的等待结果。足够的新 worker 全部就绪后，遗留陈旧记录不应造成永久等待；失败结果保留退出码和固定原因供流水线判断。脚本还针对两种数据库启动独立的完整 CLI 进程，验证标准输出可整体解析为一个 JSON 对象，并核对未就绪时退出 `50`、就绪后退出 `0`。

该工作流还实际构建 `task_demo` 的 bundle，并通过 `scripts/plugin_task_integration.py` 验证 Python 受控目录打包、签名、导入、维护准备、目标选择、旧结构数据保留以及当前业务 CRUD/读写分权。旧版本是仅承载 001 迁移的测试夹具；当前版本从真实签名制品加载。业务 HTTP 验收使用已认证上下文和 ASGI 适配器，不代替浏览器登录验收。运行真实发布集成脚本前须先按任务示例 README 构建 `web/dist`；本地 SQLite 交付回归使用最小 HTML 夹具，单独验证维护链路。

[`plugin-frontend.yml`](../../.github/workflows/plugin-frontend.yml) 在 Node.js 22 上按前端框架矩阵分别进入 `ruoyi-fastapi-frontend/<framework>/web` 执行 `npm run test:plugin`，当前矩阵包含 `vue2`、`vue3`；相关源码、测试、SDK、构建配置及依赖变更会触发检查。当前两个 Web 工程不提交 npm 锁文件，因此使用 `npm install --package-lock=false`，依赖解析仍遵循各自 `package.json` 的版本范围。

[`plugin-network-smoke.yml`](../../.github/workflows/plugin-network-smoke.yml) 在 Linux、Python 3.12、Node.js 22 与 Chromium 上执行真实网络 smoke。链路为宿主 Vue `PluginFrame` → iframe SDK → 临时 HTTPS Vite 代理 → Uvicorn → 生产插件会话与门禁，使用 `/gateway` 部署前缀。覆盖未登录拒绝、限定路径的 Secure/HttpOnly/SameSite Cookie、JSON POST、CSRF/Origin 拒绝、SSE 增量接收与取消后游标恢复、SSE/WebSocket 在权限及主会话撤销后的关闭，以及 runtime drain 后连接和 lifespan 回收。工作流保留截图、Playwright trace、代理日志与 JUnit 结果。

本地复现（在后端目录执行，三个平台通用）：

```bash
python -m pip install pytest pytest-asyncio aiosqlite playwright
python -m playwright install chromium
npm --prefix ../ruoyi-fastapi-frontend/vue3/web install --no-audit --no-fund --package-lock=false
python -c "import os,pytest; os.environ['RUOYI_PLUGIN_NETWORK_SMOKE']='1'; raise SystemExit(pytest.main(['tests/plugins/integration/test_network_smoke.py','-q']))"
```

常规 pytest 不设置 `RUOYI_PLUGIN_NETWORK_SMOKE=1` 时跳过此项，不要求安装浏览器。显式启用后，缺少浏览器或 Node 依赖会直接失败。可通过 `RUOYI_SMOKE_BROWSER_EXECUTABLE` 指定已有 Chromium 浏览器，通过 `RUOYI_SMOKE_OUTPUT` 指定诊断目录；默认输出在后端 `target/plugin-network-smoke/`。测试仅绑定 loopback 随机端口，临时证书不加入系统信任库，结束时回收浏览器和服务。

该 smoke 的账号查询、数据库会话、插件启用状态和 Redis 使用隔离夹具，传输加密为 off；它验证真实网络上的生产会话协议，不覆盖真实账号登录、Redis 故障、required 加密、生产证书信任或进程信号触发的停机。runtime drain 之后才让 Uvicorn 正常退出，SIGTERM、完整宿主 lifespan 及目标部署代理仍按 17.2 节另行验收。
