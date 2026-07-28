# 插件开发手册

本文档面向插件开发者，说明如何在当前插件系统中创建、安装、启用、调试和发布插件。

## 1. 基本模型

插件由后端插件和可选前端插件组成。默认源码布局如下：

```text
ruoyi-fastapi-backend/plugins/<plugin_id>/
ruoyi-fastapi-frontend/plugins/<plugin_id>/
```

运行时不会把前后端仓库名写死在各操作入口中。插件系统优先使用显式传入的目录，其次读取
`RUOYI_PLUGIN_BACKEND_ROOT`/`RUOYI_BACKEND_ROOT` 和
`RUOYI_PLUGIN_FRONTEND_ROOT`/`RUOYI_FRONTEND_ROOT`，再尝试从后端同级目录中识别前端工程；
最后才按后端目录名把 `backend` 推断为 `frontend`。非默认目录名的项目，应优先配置上述环境变量或在运行时注入目录。

后端插件必须包含 `plugin.yaml`。插件发现、安装、菜单、依赖、配置、迁移、种子数据和定时任务都以这个文件为入口。

`plugin.yaml` 只描述插件能力和资源。安装、启用、停用、升级等运行态由管理端或 CLI 生命周期命令维护；生命周期状态只使用 `discovered`、`installed`、`pending_upgrade`、`error`。

## 2. 快速开始

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
| `manifestVersion` | `number` | `1` | 插件清单版本。当前支持 `1`。 |
| `id` | `string` | 必填 | 插件唯一标识。只能包含小写字母、数字、下划线和中划线，长度 2-64，必须以小写字母开头。不能使用 `admin`、`system`、`monitor`、`tool`。 |
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
| `module` | `string` | 必填 | 插件后端 Python 模块路径，必须是 `plugins.<plugin_id>`。 |
| `routers` | `object` | `{ autoScan: true }` | 控制器自动扫描声明。 |
| `health` | `object` | `{}` | 健康检查声明。 |
| `migrations` | `string[]` | `[]` | 数据库迁移 SQL 脚本相对路径列表。 |
| `seeds` | `string[]` | `[]` | 初始化数据 SQL 脚本相对路径列表。 |
| `hooks` | `object` | `{}` | 生命周期钩子声明。 |
| `jobs` | `object[]` | `[]` | 插件定时任务声明。 |

`backend.routers`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `autoScan` | `boolean` | `true` | 是否按插件模块自动扫描并注册控制器。 |

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
| `id` | `string` | 必填 | 插件内任务唯一标识。只能包含小写字母、数字、下划线和中划线，必须以小写字母开头。 |
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
| `executor` | `"default" \| "processpool"` | `"default"` | 任务执行器。 |

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
| `type` | `"none" \| "source"` | `"none"` | 前端交付类型。存在菜单或 npm 依赖时会自动按源码交付处理。 |
| `buildRequired` | `boolean` | `false` | 前端资源是否需要构建后生效。源码交付时会自动视为需要构建。 |

`frontend.menus[]`：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `string` | 必填 | 菜单名称。 |
| `path` | `string` | 必填 | 菜单路由路径。普通菜单只能包含小写字母、数字、下划线、中划线和正斜杠，必须以小写字母开头；外链菜单必须使用 `http://` 或 `https://` 地址。 |
| `component` | `string` | `"Layout"` | 组件路径。核心组件允许 `Layout`、`ParentView`、`InnerLink`；插件页面使用 `plugin/<plugin_id>/<view_path>`。 |
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

## 6. 后端开发约定

### 6.1 控制器

应用启动时会按 `backend.module` 自动扫描已启用插件的控制器。推荐将接口放在 `controller/` 目录，并保持与项目原有 FastAPI 控制器风格一致。

后端插件路由采用启动期挂载模型：

- 新启用插件的后端 controller 需要重启应用后才会挂载到当前 FastAPI app。
- 停用插件后，已挂载的插件路由仍保留在 app 路由表中，但请求会经过插件启用状态依赖拦截。
- 插件 controller 的 `prefix` 必须位于当前插件命名空间内，例如 `/demo`、`/demo/items`、`/plugin/demo` 或 `/plugin/demo/items`，不能占用 `/system`、`/monitor` 等平台核心路径。

示例：

```python
from fastapi import APIRouter

demo_controller = APIRouter(prefix='/demo', tags=['demo'])


@demo_controller.get('/ping')
async def ping():
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

钩子函数可以同步或异步，可以不接收参数，也可以接收 `context`：

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

## 7. 前端开发约定

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

生产环境执行危险操作需要显式传入 `--allow-prod --yes`。

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
- 菜单组件路径能映射到实际 Vue 文件。
- SQL seed 可重复执行。
- migration 和 seed 不写插件目录外文件。
- 生命周期钩子中的全局写操作检查 `startup_write_enabled`。
- 依赖声明完整，并通过 `check-deps`。
- 插件状态只使用 `status` 的四个生命周期值。
