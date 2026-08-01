# AI 管理前端插件

AI 管理前端插件提供模型管理页面和 AI 对话页面。页面源码放在前端插件目录下，由后端插件清单 `plugins/ai/plugin.yaml` 声明菜单、组件路径和 npm 依赖。

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

前端运行依赖在后端 `plugin.yaml` 中声明，包括 Markdown 渲染、代码高亮、图表和 Monaco 编辑器相关包。插件检查和依赖安装流程会读取这些声明。

涉及的主要依赖：

- `markstream-vue`
- `stream-diffs`
- `stream-markdown`
- `stream-monaco`
- `shiki`
- `mermaid`
- `katex`
- `@antv/infographic`
- `@terrastruct/d2`
- `vite-plugin-monaco-editor-esm`

## 开发约定

- 插件页面必须放在 `plugins/ai/views` 下，组件路径使用 `plugin/ai/...`。
- 插件接口封装放在 `plugins/ai/api` 下，保持与页面同目录管理。
- 新增页面时，需要同步更新后端 `plugins/ai/plugin.yaml` 的 `frontend.menus`。
- 新增按钮权限时，需要同步更新后端 `permissions`，并在页面中使用 `v-hasPermi`。
- 不要在前端源码中硬编码 API Key 或模型密钥；模型凭证由后端模型管理页面维护。

## 验证

前端插件没有单独的测试命令。修改页面或依赖后，建议执行项目构建验证：

```bash
npm run build:prod
```

若只修改文档，不需要执行前端构建。
