# AI 管理前端插件

AI 管理前端插件提供 Vue 2 版模型管理页面和 AI 对话页面。本工程位于 `ruoyi-fastapi-frontend/vue2/web`，与 Vue3 Web 共用后端 `ruoyi-fastapi-backend/plugins/ai/plugin.yaml`，由此清单统一声明菜单、组件路径和 npm 依赖。

## 页面

菜单与组件路径对应关系：

```text
模型管理：plugin/ai/model/index -> plugins/ai/views/model/index.vue
AI 对话：plugin/ai/chat/index  -> plugins/ai/views/chat/index.vue
```

功能入口：

- 「AI 管理 / 模型管理」：维护供应商、模型编码、模型名称、API Key、Base URL、温度、最大 Token、推理能力、图片能力和状态。
- 「AI 管理 / AI 对话」：选择已启用模型进行会话，支持会话历史、全局参数配置、系统提示词、历史上下文、图片输入和流式输出。

## 目录说明

```text
plugins/ai/
  api/
    model.js
    chat.js
  views/
    model/index.vue
    chat/index.vue
  README.md
```

- `api/model.js`：模型管理接口封装。
- `api/chat.js`：AI 对话、会话历史和用户配置接口封装。
- `views/model/index.vue`：模型管理页面。
- `views/chat/index.vue`：AI 对话页面。

## 权限

页面和按钮权限由后端插件清单写入系统菜单：

- `ai:model:list`：进入模型管理页面。
- `ai:model:add`：新增模型。
- `ai:model:edit`：修改模型。
- `ai:model:remove`：删除模型。
- `ai:model:query`：查询模型。
- `ai:chat:list`：进入 AI 对话页面。

前端页面继续使用系统原有的 `v-hasPermi` 指令控制按钮可见性。

## 依赖

前端依赖按框架完整声明在共用后端 `plugin.yaml` 的 `dependencies.frontend.<framework>.npm/npmDev` 中，本工程使用 `vue2` 分类，包括 Markdown 渲染、代码高亮、图表和 Monaco 编辑器相关包。检查与安装只读取当前框架分类，不跨分类合并；未声明该分类时没有 npm 依赖，旧顶层 `dependencies.npm/npmDev` 会被清单校验拒绝。从后端执行依赖检查或安装时，先设置 `RUOYI_PLUGIN_FRONTEND_FRAMEWORK=vue2`，或将 `RUOYI_PLUGIN_FRONTEND_ROOT` 指向本 Web 工程。

涉及的主要依赖：

- `markstream-vue2`
- `stream-markdown`
- `stream-monaco`
- `shiki`
- `mermaid`
- `katex`
- `@antv/infographic`
- `@terrastruct/d2`

## 开发约定

- 插件页面必须放在 `plugins/ai/views` 下，组件路径使用 `plugin/ai/...`。
- 插件接口封装放在 `plugins/ai/api` 下，保持与页面同目录管理。
- 新增页面时，需要同步更新后端 `plugins/ai/plugin.yaml` 的 `frontend.menus`。
- 新增按钮权限时，需要同步更新后端 `permissions`，并在页面中使用 `v-hasPermi`。
- 不要在前端源码中硬编码 API Key 或模型密钥；模型凭证由后端模型管理页面维护。

## 验证

修改插件路径解析或页面后，建议执行插件测试和项目构建验证：

```bash
# 从仓库根目录进入本工程
cd ruoyi-fastapi-frontend/vue2/web
npm run test:plugin
npm run build:prod
```

若只修改文档，不需要执行前端构建。
