# 管理端前端格式化规范

本规范适用于 `ruoyi-fastapi-frontend/vue2/web`，覆盖 Vue 单文件组件、JavaScript / TypeScript、CSS / SCSS / Less、HTML、JSON、Markdown 和 YAML，包括 `src`、`plugins`、`build`、`tests` 以及自行维护的 `public` 脚本。

## 参考项目与工具

参考 [Element Plus 官方项目的 Prettier 配置](https://github.com/element-plus/element-plus/blob/dev/.prettierrc)（核对日期：2026-09-14）。当前管理端使用 Vue 2.7 和 Element UI，沿用 Vue 3 版本的排版规范，采用 `semi: false`、`singleQuote: true`、`trailingComma: 'es5'` 作为基础风格，适合现有 JavaScript 代码。

格式化统一使用 **Prettier 3.6.2**，以 `.prettierrc.json` 为规则来源。该版本与项目已有的本地安装及锁文件一致，并在 `devDependencies` 中固定版本，避免开发者因格式化器版本不同产生差异。

## 具体规则

| 项目                  | 规则                               | 说明                                                                  |
| --------------------- | ---------------------------------- | --------------------------------------------------------------------- |
| 缩进                  | 2 个空格，不使用 Tab               | 模板按嵌套层级缩进                                                    |
| 行宽                  | `printWidth: 100`                  | 本项目适配；作为自动换行参考宽度，长字符串等可以超出                  |
| JavaScript 字符串     | 优先单引号                         | 沿用 Element Plus；必要时由 Prettier 选择更少转义的引号               |
| HTML / Vue 属性、JSON | 双引号                             | JavaScript 的单引号设置不改变这些语法的属性引号                       |
| JavaScript 分号       | 不写行末分号                       | 沿用 Element Plus；Prettier 会保留避免自动分号插入歧义所需的分号      |
| 尾逗号                | `trailingComma: 'es5'`             | 沿用 Element Plus；多行对象、数组等保留尾逗号，函数参数不添加尾逗号   |
| 箭头函数              | 参数始终带括号                     | `(item) => item.id`，便于增加参数、默认值或类型                       |
| 对象字面量            | 大括号内侧加空格                   | `{ name: 'demo' }`，属性名仅在语法需要时加引号                        |
| Vue / HTML 多属性标签 | 每个属性独占一行                   | 本项目适配；减少表单、表格和权限指令挤在同一行的情况                  |
| 多行标签的 `>`        | 不紧跟最后一个属性                 | 使用 `bracketSameLine: false`                                         |
| Vue 的 script / style | 内容不额外缩进一层                 | `vueIndentScriptAndStyle: false`                                      |
| HTML 空白             | `htmlWhitespaceSensitivity: 'css'` | 保留 Prettier 默认的空白处理方式，兼顾行内文本空格语义                |
| 文本文件              | UTF-8、LF、末尾换行                | `.editorconfig` 与 `.gitattributes` 配合；Windows 批处理脚本使用 CRLF |
| 行尾空格              | 删除                               | Markdown 例外，保留用于硬换行的两个空格                               |
| Markdown 段落         | 保留原有换行                       | `proseWrap: 'preserve'`，避免中文段落被反复重排                       |

除上述项目适配外，使用 Prettier 默认行为。选项含义见 [Prettier 官方文档](https://prettier.io/docs/options)。

Vue 单文件组件沿用 `<template>` → `<script>`（或 Vue 2.7 的 `<script setup>`）→ `<style scoped>` 顺序。`<script setup>` 中显式导入 Vue API；需要组件名时使用普通 `<script>` 的 `name` 选项，保证路由缓存正确识别。这是编写约定，Prettier 不会调整区块顺序、组件名、属性顺序、import 顺序或 CSS 声明顺序。

示例：

```vue
<template>
  <el-button
    type="primary"
    :disabled="loading"
    @click="handleSubmit"
  >
    保存
  </el-button>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['submit'])
const loading = ref(false)
const form = ref({
  name: '',
  enabled: true,
})

const handleSubmit = () => {
  emit('submit', form.value)
}
</script>
```

## 日常使用

在仓库根目录进入管理端并安装依赖：

```sh
cd ruoyi-fastapi-frontend/vue2/web
npm install
```

检查整个管理端，只报告差异，不修改文件：

```sh
npm run format:check
```

格式化整个管理端：

```sh
npm run format
```

也可以在仓库根目录运行 `npm --prefix ruoyi-fastapi-frontend/vue2/web run format:check` 或 `npm --prefix ruoyi-fastapi-frontend/vue2/web run format`。

只处理本次修改的文件时，在管理端目录执行：

```sh
npm exec -- prettier --write src/views/system/user/index.vue src/api/system/user.js
npm exec -- prettier --check src/views/system/user/index.vue src/api/system/user.js
```

`format` 和 `format:check` 的范围固定为整个管理端；处理指定文件请使用上面的 `npm exec` 命令。

## 编辑器

使用 VS Code 打开本目录的 `frontend.code-workspace`，按工作区推荐安装 **Prettier - Code formatter** 和 **EditorConfig**，即可在保存时使用本地 Prettier 和项目配置。

Vue 语言服务沿用已有支持 Vue 2.7 的编辑器配置。工作区只包含管理端，使用的缩进设置与 `.editorconfig` 一致。工作区文件可随 Git 共享，也不依赖当前仓库忽略的 `.vscode` 目录。

如果继续在 VS Code 中打开整个仓库，可将 `frontend.code-workspace` 的 `settings` 合并到个人工作区设置。`prettier.requireConfig: true` 使格式化仅在有 Prettier 配置的项目中运行；格式化具体文件时会就近查找 `.prettierrc.json`。在仓库根工作区使用时，还需将 `prettier.ignorePath` 设置为 `ruoyi-fastapi-frontend/vue2/web/.prettierignore`，保持忽略范围一致。

WebStorm 等支持 Prettier / EditorConfig 的编辑器应选择管理端的本地 Prettier 包，并启用相应的保存格式化功能。

## 忽略范围与职责

管理端入口 `/public/index.html` 单独排除，由人工维护入口 HTML 的排版并保留大写 `<!DOCTYPE html>`。该规则只匹配此入口文件；按本规范配置的 Prettier 命令和编辑器会跳过它。

`.prettierignore` 排除依赖、构建输出、缓存、覆盖率、测试报告、包管理器锁文件、自动生成的声明文件、压缩文件、SVG 和 source map。Prettier 也会读取当前工作目录的 `.gitignore`；不要通过添加整个业务目录到忽略列表来掩盖格式问题。

Prettier 负责空格、换行、引号和标点排版。后续如引入 ESLint，应让它负责代码质量检查，并通过 `eslint-config-prettier` 关闭冲突的排版规则。当前规则不要求额外安装 ESLint、Stylelint 或 Git hooks。

表单设计器使用的 `js-beautify` 负责运行时生成代码的显示，不是仓库源码格式化入口。生成器导出的 Vue / JavaScript 文件纳入项目后，同样按本规范格式化。

只有布局确实具有语义、或需要保留特定排版时，才使用 `prettier-ignore`，并在附近说明原因。用法见 [Prettier 官方忽略规则](https://prettier.io/docs/ignore)。

## 历史代码迁移

历史业务源码已按本规范统一格式化。后续新增和修改的文件应继续遵循同一套规则，提交前运行 `npm run format:check` 检查整个管理端。

日常修改时先格式化所改文件。需要统一历史代码时，使用 `npm run format` 单独形成一次格式化提交，再运行 `npm run format:check`、`npm test` 和 `npm run build:prod`。全量检查通过后，可在 CI 中加入 `npm run format:check` 作为后续改动的检查步骤。
