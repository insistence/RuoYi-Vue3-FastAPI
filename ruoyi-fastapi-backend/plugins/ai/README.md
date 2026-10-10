# AI 管理后端插件

AI 管理插件提供模型配置、供应商字典、会话对话和流式输出能力。插件保留原有接口前缀和权限标识，安装后会在系统菜单中生成「AI 管理」目录，以及「模型管理」「AI 对话」两个页面。各前端框架共用此后端插件及同一份 `plugin.yaml`，页面目录约定为 `ruoyi-fastapi-frontend/<framework>/web/plugins/ai`；当前提供 Vue2、Vue3 页面，分别位于 `vue2/web/plugins/ai` 和 `vue3/web/plugins/ai`。

## 功能

- 模型管理：维护模型编码、供应商、API Key、Base URL、温度、Token 限制、推理能力、图片能力和启停状态。
- AI 对话：基于已启用模型发起对话，支持历史会话、系统提示词、温度配置、深度思考开关、图片输入和 SSE 流式返回。
- 字典数据：安装时写入 `ai_provider_type` 字典，用于模型供应商下拉选择。
- 多数据库脚本：内置 MySQL 和 PostgreSQL 的建表脚本与字典种子脚本。
- 依赖声明：Python 与前端 npm 依赖统一声明在 `plugin.yaml`，由插件依赖检查与安装流程处理。

## 接口与权限

后端接口：

- `/ai/model`
- `/ai/chat`

权限标识：

- `ai:model:list`：模型列表
- `ai:model:add`：新增模型
- `ai:model:edit`：修改模型
- `ai:model:remove`：删除模型
- `ai:model:query`：查询模型
- `ai:chat:list`：AI 对话

## 目录说明

```text
plugins/ai/
  plugin.yaml
  controller/
  service/
  dao/
  entity/
  utils/
  migrations/
    mysql/001_init.sql
    postgresql/001_init.sql
  seeds/
    mysql/ai_provider_type.sql
    postgresql/ai_provider_type.sql
  README.md
```

- `plugin.yaml`：插件清单，声明菜单、权限、依赖、迁移脚本和种子脚本。
- `controller/`：FastAPI 控制器，由插件运行时自动扫描注册。
- `service/`：AI 业务逻辑，包括模型解析、对话流式输出、历史会话和用户配置。
- `dao/`：数据库访问层。
- `entity/`：数据库模型与请求响应模型。
- `utils/`：模型工厂、存储引擎等 AI 辅助能力。
- `migrations/`：插件安装时执行的表结构脚本。
- `seeds/`：插件安装时执行的初始化数据脚本。

## 配置来源

AI 插件不声明插件级默认配置。实际对话使用以下业务配置：

- 模型管理：维护供应商、模型编码、API Key、Base URL、温度、Token 限制和模型能力。
- AI 对话配置：维护用户维度的系统提示词、历史上下文、温度和视觉输入等偏好。

模型凭证按模型单独维护，API Key 会加密存储；不要把模型密钥写入插件清单或环境文件。

## 启用方式

AI 插件作为内置插件随项目提供。默认启用列表由环境变量 `APP_DEFAULT_ENABLED_PLUGINS` 控制，标准环境文件中已包含 `ai`。

常用命令：

```bash
ruoyi plugin check ai --env=dev
ruoyi plugin install ai --env=dev --yes
ruoyi plugin enable ai --env=dev --yes
ruoyi plugin disable ai --env=dev --yes
```

首次在新环境启动或安装前，请先执行插件检查，确认 Python 依赖、前端依赖、菜单冲突、数据库脚本和目录结构都满足要求。

## 依赖说明

后端主要依赖由 `plugin.yaml` 声明，包括：

- `agno`
- `openai`
- `anthropic`
- `cohere`
- `google-genai`
- `groq`
- `litellm`
- `mistralai`
- `ollama`
- 以及其他供应商 SDK

应用启动时只做默认启用插件的依赖门禁，不会自动安装或提示安装依赖。缺失依赖时，应在启动前显式执行 `ruoyi plugin install-deps ai --env=dev`；生产环境应在发布阶段提前准备依赖。

前端依赖按宿主框架完整声明，当前 AI 插件提供以下分类：

- `dependencies.frontend.vue2.npm`：Vue2 所需的全部运行依赖，包括 `markstream-vue2` 以及 Markdown、代码高亮、图表等依赖。
- `dependencies.frontend.vue3.npm`：Vue3 所需的全部运行依赖，包括 `markstream-vue`、`stream-diffs` 以及 Markdown、代码高亮、图表等依赖。
- `dependencies.frontend.vue3.npmDev`：Vue3 构建使用的 `vite-plugin-monaco-editor-esm`。

多个框架都使用的包也在各自分类中列出，不设公共依赖层。`dependencies.frontend` 接受 `react` 等安全的小写框架标识，但新增分类不会生成对应页面；当前 AI 插件仅提供 Vue2、Vue3 实现。旧顶层 `dependencies.npm/npmDev` 已移除，清单校验会拒绝；未声明目标框架分类时，该宿主没有 npm 依赖。

插件系统解析选定 Web 工程的框架，只检查、安装匹配框架分类中的依赖。默认选择 `vue3/web`；检查或安装 Vue2 依赖时，先在当前终端设置 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2`（PowerShell：`$env:RUOYI_PLUGIN_FRONTEND_FRAMEWORK = 'vue2'`；Bash：`export RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2`），再执行同样的插件命令。未设置该变量时也可使用 `RUOYI_FRONTEND_FRAMEWORK`，或用 `RUOYI_PLUGIN_FRONTEND_ROOT` 指向具体 Web 工程。各框架工程分别安装依赖和构建，后端插件仅需安装、启用一次。完整规则见[插件开发手册](../../docs/plugin_development.md#9-依赖管理)。

## 数据库

安装插件时会执行当前数据库类型对应的脚本：

- MySQL：`migrations/mysql/001_init.sql`、`seeds/mysql/ai_provider_type.sql`
- PostgreSQL：`migrations/postgresql/001_init.sql`、`seeds/postgresql/ai_provider_type.sql`

脚本按插件生命周期执行，支持重复检查和按数据库类型过滤。

## 开发注意

- 后端模块路径必须保持为 `plugins.ai`，与插件 ID 对齐。
- 控制器文件放在 `controller/` 下，保持自动扫描可发现。
- 菜单组件路径需要与前端插件目录保持一致，例如 `plugin/ai/model/index`。
- 新增权限时，需要同时更新 `plugin.yaml` 的 `permissions` 和相关菜单或按钮权限。
- 涉及 API Key、Token、凭证的配置应使用敏感配置和加密存储，不要写入日志。
