// 按语言映射构建产物中的 Worker 文件
const workerPaths = {
  editorWorkerService: 'editor.worker..bundle.js',
  css: 'css.worker..bundle.js',
  html: 'html.worker..bundle.js',
  json: 'json.worker..bundle.js',
  typescript: 'ts.worker..bundle.js',
}

workerPaths.javascript = workerPaths.typescript
workerPaths.less = workerPaths.css
workerPaths.scss = workerPaths.css
workerPaths.handlebars = workerPaths.html
workerPaths.razor = workerPaths.html

globalThis.MonacoEnvironment = {
  globalAPI: false,
  // 按当前模块地址解析 Worker 路径
  getWorkerUrl(moduleId, label) {
    const workerPath = workerPaths[label]
    return workerPath
      ? new URL(`./monacoeditorwork/${workerPath}`, import.meta.url).toString()
      : workerPath
  },
}
