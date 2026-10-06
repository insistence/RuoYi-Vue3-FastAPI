# 插件开发手册

本文档面向插件开发者，说明如何在当前插件系统中创建、安装、启用、调试和发布插件。

本文覆盖 v1 源码插件和 v2 显式入口插件。未特别注明的权限、菜单、配置、依赖和迁移规则两者共用；自动扫描控制器及默认 `create` 模板属于 v1。按开发目标选择入口：

| 开发目标 | 使用说明 | 可运行示例 |
| --- | --- | --- |
| 沿用宿主源码页面和控制器扫描 | [快速开始](#2-快速开始)、[源码前端](#71-v1--source-页面) | [内置 AI 插件](../plugins/ai/README.md) |
| 显式 Router 或 ASGI 子应用 | [v2 清单](#510-v2-清单与能力组合)、[显式入口与 SDK](#66-v2-显式入口与宿主-sdk) | [Python ASGI](../plugins/examples/python/asgi_demo/README.md) |
| Rust 原生后端 | [原生插件](#68-rust-原生插件)、[项目脚手架与构建](#16-v2-项目脚手架与完整构建) | [Rust 示例](../plugins/examples/rust/rust_demo/README.md) |
| 独立构建的插件页面 | [bundle 页面](#72-v2-独立-bundle-页面)、[浏览器 SDK](#73-bundle-浏览器-sdk) | [Python bundle](../plugins/examples/python/bundle_demo/README.md) |
| 签名交付与生产维护 | [制品与发布](#15-v2-签名制品与维护发布)、[真实服务验收](#17-本地真实服务验收与-ci) | [Rust 签名发布示例](../plugins/examples/rust/rust_demo/README.md#签名制品与维护发布) |

目录插件与签名制品不能同时使用相同插件 ID。两种方式均遵守进程重启边界，不提供原生模块热替换。

后端命令使用已安装项目依赖的 Python 3.10–3.13 环境；创建与激活步骤见 [CLI 环境准备](cli_usage.md#22-安装依赖)。下文的 `python` 指向已激活环境，命令默认在后端目录执行。通用命令同时适用于 Windows PowerShell、macOS 和 Linux；环境变量等 Shell 语法分别列出。

## 1. 基本模型

插件由后端插件和可选前端插件组成。默认源码布局如下：

```text
ruoyi-fastapi-backend/plugins/<plugin_id>/
ruoyi-fastapi-frontend/plugins/<plugin_id>/
```

开发示例统一位于后端 `plugins/examples/`，按实现语言分类：`python/` 保存 Python 示例，`rust/` 保存 Rust 原生插件工程。
该目录不参与插件发现和启动代际计算。使用示例时，按各自 README 构建后部署到 `plugins/<plugin_id>/`，或通过签名制品发布流程安装。

运行时不会把前后端仓库名写死在各操作入口中。插件系统优先使用显式传入的目录，其次读取
`RUOYI_PLUGIN_BACKEND_ROOT`/`RUOYI_BACKEND_ROOT` 和
`RUOYI_PLUGIN_FRONTEND_ROOT`/`RUOYI_FRONTEND_ROOT`，再尝试从后端同级目录中识别前端工程；
最后才按后端目录名把 `backend` 推断为 `frontend`。非默认目录名的项目，应优先配置上述环境变量或在运行时注入目录。

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

脚手架默认使用 `--frontend-version=auto`，会读取目标前端 `package.json` 的 `vue` 依赖，并自动生成 Vue 2（Element UI、Options API、CommonJS 测试）或 Vue 3（Element Plus、Composition API、ESM 测试）模板。通常无需传参；识别失败或需要覆盖时可显式指定：

```bash
ruoyi plugin create demo --env=dev --template=crud-page --frontend-version=vue2
ruoyi plugin create demo --env=dev --template=crud-page --frontend-version=vue3
```

后端实现应在 Vue 2/3 项目间保持一致。`plugin.yaml` 通常只声明两个前端都使用的业务依赖；如果插件确实依赖不同的 Vue 绑定库或构建插件，允许各项目保留不同清单，但应分别提供 Vue 2/3 测试，并根据目标前端 `package.json` 自动选择执行。

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
| `npm` | `string[]` | `[]` | 前端运行依赖声明，例如 `dayjs>=1.11.0`。 |
| `npmDev` | `string[]` | `[]` | 前端开发依赖声明。 |
| `plugins` | `object[]` | `[]` | 插件间依赖声明。 |

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
| `hostApiVersion` | `string` | `^1.0.0` | 仅 v2：宿主插件 SDK 版本约束，独立于应用版本；当前 Host API 为 `1.3.0`。bundle 至少使用 `^1.2.0`；请求 DTO、显式事务、字典及缓存服务使用 `^1.3.0`。 |
| `frontendVersion` | `string \| null` | `null` | 前端版本约束。 |
| `pythonVersion` | `string \| null` | `null` | Python 版本约束。 |
| `nodeVersion` | `string \| null` | `null` | Node.js 版本约束。 |
| `databases` | `("mysql" \| "postgresql")[]` | `[]` | 插件支持的数据库类型声明，不能重复。 |

版本约束可以是版本号，也可以带比较操作符，例如 `>=3.10`、`^20.0.0`。

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

bundle 不因存在菜单而变为源码前端，`buildRequired` 必须为 `false`，构建依赖由插件自己的 `package.json` 管理，不写入清单的 `dependencies.npm/npmDev`。清单校验和静态预检不会导入插件代码；通过预检仍需进行实际加载、权限与生命周期测试。

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

v2 调度记录保存宿主分发函数及插件 ID、任务 ID、版本，不直接持久化原生 callable。执行前检查当前 worker 就绪、版本一致、任务仍存在及插件已启用；任务在所属宿主事件循环执行，不支持进程池。关闭时先停止分发、取消并等待运行中的任务，再关闭插件资源。多 worker 的调度选主沿用宿主调度器。

### 6.6 v2 显式入口与宿主 SDK

清单中的 `create_plugin(host)` 必须同步、快速地返回 `PluginDefinition`；它只声明能力，不打开连接、启动线程或创建后台任务。当前 `PluginDefinition.api_version` 为 `1`，与清单版本 `2`、Host API 版本 `1.3.0` 是三个不同的版本号。

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
| `PluginHostContext` | `plugin_id`、`resource_root`、只读 `config`、`services`、`session_factory`、`redis`、`logger`、`startup_write_enabled`、`api_version` | 配置为加载时快照，修改后重启读取；不保存请求身份或请求数据库会话 |
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

新启用或更新代码需要重启。停用检查会拒绝后续新请求，但不会自动终止已建立的 WebSocket 或正在处理的请求；正式升级应停止全部宿主 worker 并按第 15 节完成维护发布。

### 6.8 Rust 原生插件

Rust 使用 PyO3 暴露 Python 扩展，并通过 maturin 构建 wheel；Windows 交付 `.pyd`，Linux 交付 `.so`。部署端只需匹配的运行环境和已构建产物，无需 Rust 编译工具链。原生代码与宿主同进程，适用于可信扩展；二进制交付不等于不可逆向，也不提供 Python 依赖或进程隔离。

原生 wheel 在构建或维护环境中验证并展开到 `backend.native.moduleRoot`，默认 `native/`。宿主检查发行包名称、插件版本、Python 要求、wheel tag、已安装依赖及完整 RECORD SHA256；扩展只能从当前插件目录加载，不能覆盖宿主模块。RECORD 用于检查文件一致性，发布者信任仍需第 15 节的签名流程。

构建机需安装 Rust、maturin 和目标平台编译工具：Windows 使用 MSVC Build Tools 的 C++ 工具及 Windows SDK，macOS 使用 Xcode Command Line Tools，Linux 使用 GCC 或 Clang 等编译工具。先选择 `rust-asgi` 或 `rust-bundle` 脚手架，再按第 16 节构建。`abi3` 可减少 Python ABI 构建数量，但不能跨操作系统或架构复用制品；按实际目标平台及 Python 3.10–3.13 的测试结果验证兼容性。

Rust 通过 `PluginHostContext`、`plugin_endpoint`、`plugin_lifespan` 和版本化服务复用宿主能力，完整实现见 [Rust 示例](../plugins/examples/rust/rust_demo/README.md)。不要覆盖已加载的原生模块或依赖 `reload` 完成更新，发布后必须重启全部相关进程。

## 7. 前端开发约定

### 7.1 v1 / source 页面

插件前端代码放在：

```text
ruoyi-fastapi-frontend/plugins/<plugin_id>/
```

菜单组件路径和真实 Vue 文件的映射关系：

```text
plugin/demo/index -> ruoyi-fastapi-frontend/plugins/demo/views/index.vue
plugin/demo/report/list -> ruoyi-fastapi-frontend/plugins/demo/views/report/list.vue
```

只允许两类组件值：

- 核心布局组件：`Layout`、`ParentView`、`InnerLink`。
- 插件视图组件：`plugin/<plugin_id>/<view_path>`。

前端 API 建议放在 `plugins/<plugin_id>/api/`，视图放在 `plugins/<plugin_id>/views/`。插件页面不需要加入主工程内置路由，菜单安装后由后端返回动态路由，前端 resolver 会自动定位插件视图。

### 7.2 v2 独立 bundle 页面

v2 ASGI 插件可声明 `frontend.delivery.type: bundle` 和 `frontend.bundle.directory: web/dist`，菜单组件使用 `PluginFrame`。`backend.runtime` 仍独立选择 `python` 或 `native`：bundle 只改变前端交付方式，不会保护 Python 后端源码；原生非源码交付参见 Rust 示例。此模式需要 Host API `^1.2.0`，不声明宿主 npm 依赖，也不参与宿主前端构建。首次升级宿主以加入 `PluginFrame` 时仍需构建宿主前端，之后新增或更新插件只构建插件自己的前端。

后端通过 `sys_plugin_menu.menu_id` 的可信归属输出路由 `meta.pluginId`，不接受菜单 query、URL 或插件名称代替该标识。`PluginFrame` 先以宿主 Bearer 调用 `POST /plugin/runtime/<id>/session`，取得服务端校验的固定入口和短期插件会话，然后打开 `/apps/<id>/ui/`。不要手写任意 iframe 地址，也不要把主 token 放入 URL 或传给插件。

插件浏览器 Cookie 使用 `HttpOnly`、`SameSite=Strict`，HTTPS 下为 `Secure`，路径限定为 `<root_path>/apps/<id>/`。会话最多 300 秒并受主登录有效期限制，同一主会话的多标签续期复用 Cookie 与 CSRF。每次 API、页面和资源访问都会检查主会话、插件状态和权限；退出、主登录替换、插件禁用或版本变化会使后续访问失效。写请求还要求同源 Origin 与 CSRF。插件 Cookie 不能用于其他宿主 API。已经建立的长连接不会因此自动排空。

浏览器 SDK 位于前端 `src/utils/pluginBridge.js`，无 Vue/Axios 依赖。示例通过构建别名引入；独立插件仓库可把这一模块作为版本化依赖复制到自己的源码中。SDK 提供 `ready`、`request`、`navigate`、`subscribe` 和 `destroy`，具体用法见 [bundle_demo README](../plugins/examples/python/bundle_demo/README.md)。请求只允许当前插件 API 下的相对 `path`、JSON `params/data`；主页面使用原有加密请求客户端代理，自动附加插件 CSRF，并禁用主 Bearer。主 token、插件 Cookie 和 CSRF 值不进入桥消息。

当前 JSON 桥每条消息最多 64 KiB、最多 8 个待处理请求、默认 15 秒超时，支持取消；不支持上传、二进制下载、streaming、SSE 或 WebSocket 代理。它不能替代后端具体 API 的 `require_permission`/`plugin_endpoint` 权限检查。

UI GET/HEAD 使用普通 HTTPS，仍经过插件身份门禁；`/apps/<id>/api/...` 与会话签发接口保留宿主传输加密，不能整体加入加密排除列表。加密 AAD 保留 `/apps/<id>/api/...` 完整插件命名空间，只按宿主规则剥离部署前缀；加密的会话响应仍保留 `Set-Cookie`。

HTML 注入有效 `uiBase`、`apiBase` 与 `<base>`。SPA 回退仅接受 UI GET/HEAD 中带 `Accept: text/html` 的无扩展名页面导航；缺失脚本、API、保留路径和非 HTML 请求不能返回首页。静态服务拒绝路径越界和链接逃逸，并限制为同源 iframe 嵌入。HTML 当前 `no-store`，其他静态资源 `no-cache`，不自动启用 immutable 缓存。

默认 `VITE_APP_PLUGIN_BASE` 为空，插件走同源 `/apps/` 和 `/plugin/runtime/`。若后端 `APP_ROOT_PATH=/prefix`，宿主前端需设置 `VITE_APP_PLUGIN_BASE=/prefix`，代理也要保留相同前缀及外部 Host；HTTPS 的原始 scheme 由可信代理配置传递。仓库 Vite 与 Docker Nginx 已提供对应代理入口，生产环境应验证 Cookie Path、Origin、Secure 和加密 AAD。独立页面属于同源可信代码；iframe 提供布局和依赖隔离，不提供对恶意插件的安全隔离。

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

## 9. 依赖管理

插件依赖声明在 `dependencies` 中：

- `python`：Python 包。
- `npm`：前端运行依赖。
- `npmDev`：前端开发依赖。
- `plugins`：插件间依赖。

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

### 12.1 v2 运行观测

管理端“插件详情 → 运行观测”可手动刷新。只读接口 `GET /system/plugin/runtime/metrics?pluginId=<id>` 要求宿主登录和 `system:plugin:query`。支持显式 Router、ASGI 的 HTTP/WebSocket 以及宿主分发的 v2 定时任务；v1 扫描路由不纳入本指标。

指标按实际加载的插件、版本、digest、generation 和操作（`http/websocket/job:<id>`）分组，记录调用、在途、成功、拒绝、失败、取消、超时、失败率、平均耗时、最大耗时和近似 P95。失败率为失败次数除以已完成次数（成功、拒绝、失败、取消之和），超时计入失败；P95 是固定直方图区间的上界估计，不是精确分位数。HTTP 耗时覆盖完整响应，WebSocket 耗时覆盖连接生命周期；ASGI 组也包含静态资源和门禁拒绝，因此不能直接理解为某个业务接口的延迟。

每个 worker 从启动开始累计，重启归零，不提供持久历史。每 15 秒向 Redis 发布一次快照，60 秒过期，正常退出仅删除自身快照。接口返回 `scope=reporting_workers` 表示本次有效采样中的进程，并不保证包含全部预期 worker；Redis 不可用时明确返回 `scope=current_worker`。首次启动的远程进程可能需等待一个采样周期才出现。当前进程使用即时快照，远程进程使用最近一次快照。

返回数据包含 `observedWorkers`、采样时间、`invalidSnapshots/staleSnapshots/workerLimitReached` 和各进程的 `droppedSeries`，用于判断采样是否完整。单次最多读取 64 个远程快照，每个进程最多 1024 条指标序列。该页面不替代 `release status` 的发布一致性确认。

请求和任务均设置追踪标识；日志上下文附带插件 ID、版本、制品摘要、代际、worker 和操作。指标只保存最近异常类型、时间和追踪标识，不采集 URL、请求体、认证头或异常消息。可用 `lastErrorRequestId` 关联宿主日志排查。

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
cd ../ruoyi-fastapi-frontend
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

管理页提供制品与发布状态的只读查看入口，签名制品使用上述维护 CLI 完成变更。对应 HTTP 查询均要求宿主登录及 `system:plugin:query` 权限：

| 接口 | 参数与用途 |
| --- | --- |
| `GET /system/plugin/artifacts/list` | 可选 `pluginId`，查询已验证制品 |
| `GET /system/plugin/release/status` | 可选 `pluginId`，查询目标及各 worker 的实际报告 |
| `GET /system/plugin/release/plan` | 必填 `pluginId`、`digest`，读取静态发布预检计划 |
| `GET /system/plugin/runtime/metrics` | 可选 `pluginId`，按实际运行版本读取请求、连接和任务累计指标 |

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

当前没有自动停止进程、热卸载或存量连接排空。修改 enabled、选择目标或撤销签名密钥均不能卸载进程中已加载的 Python/Rust 模块；处理仍需维护窗口和进程退出。制品清理与签名轮换使用下面的独立维护命令。

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

每个工程包含 v2 清单、受 `<id>:view` 权限保护的 `/api/info`、显式入口、健康检查、lifespan、构建与发布 README，以及 SDK 合约测试。Rust 模板固定 `ruoyi_plugin_<id>` Python 命名空间，包含锁定的 Cargo 依赖。bundle 复制当前宿主的 bridge SDK，使用相对资源基址和专用插件会话，不内嵌主登录 token。它与宿主 Vue 版本独立，v2 模板不接受 `--frontend-version`；bundle 也不能配合 `--backend-only`。

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

Python 打包器仅复制模板清单、入口和构建后的 bundle；增加业务模块、SQL 或其他资源时，应显式扩展复制清单并测试。Python 插件仍以 Python 源码交付。Rust 交付不包含 `.rs`、Cargo 或前端开发工程；两种方式均需按第 15 节签名、导入、维护准备、选择目标及重启验收。所有构建输出必须使用新目录，不能覆盖已加载版本。

## 17. 本地真实服务验收与 CI

本节用于插件交付前的自动化回归和部署环境验收。插件自身的测试与静态检查见[第 13 节](#13-测试和发布前检查)，v2 工程构建及合约测试见[第 16 节](#16-v2-项目脚手架与完整构建)，签名交付与维护操作按[第 15 节](#15-v2-签名制品与维护发布)执行。

### 17.1 本地自动化回归

在后端目录、已安装宿主依赖的 Python 环境中执行。下面的命令适用于 Windows PowerShell、macOS 和 Linux：

```bash
python -m pip install pytest pytest-asyncio aiosqlite
python -m pytest tests/cli/runtime/plugin/test_runtime_scaffold.py tests/cli/runtime/plugin/test_runtime_scaffold_v2.py -q
python -m pytest tests/plugins/core/artifacts tests/plugins/core/deployment tests/plugins/core/management/test_release_dao.py tests/plugins/core/management/test_artifact_views.py tests/module_plugin/controller/test_plugin_release_controller.py tests/cli/root/test_plugin_artifact_commands.py tests/sql/test_plugin_release_schema.py -q
```

上述回归覆盖脚手架、签名制品、维护发布、状态查询及数据库脚本约束。原生插件还应在目标平台构建后执行[原生示例的集成验证](../plugins/examples/rust/rust_demo/README.md#本地集成验证)；测试因缺少原生制品而跳过时，不能据此确认原生交付可用。

bundle 插件完成独立前端构建后，还应执行宿主桥接测试（在后端目录执行，三种平台通用）：

```bash
npm --prefix ../ruoyi-fastapi-frontend run test:plugin
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

仓库的原生插件工作流配置 Windows/Linux、Python 3.10、3.11、3.12、3.13 构建测试矩阵，覆盖 v1/v2 脚手架、原生扩展以及签名制品与维护发布回归。

发布集成工作流在 Python 3.10、3.11、3.12、3.13 上使用临时 MySQL、PostgreSQL 和 Redis 服务验证多 worker 发布行为。工作流配置不代表已经执行成功；发布前应核对对应提交的实际 CI 结果，并完成目标平台的部署验收。
