# AI 管理后端插件

AI 管理插件提供模型配置、供应商字典、会话对话和流式输出能力。插件保留原有接口前缀和权限标识，安装后会在系统菜单中生成「AI 管理」目录，以及「模型管理」「AI 对话」两个页面。

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

插件启动期会检查已启用插件的 Python 依赖。缺失依赖时，CLI 启动流程会提示是否安装依赖；生产环境建议在发布阶段提前安装，避免运行期临时拉取依赖。

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
