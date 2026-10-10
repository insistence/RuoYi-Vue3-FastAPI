const monacoEnvironmentScript = /<script>\s*self\["MonacoEnvironment"\][\s\S]*?<\/script>/

// 使用外部模块脚本配置 Monaco Worker，避免内联脚本
export default function createMonacoEnvironment() {
  return {
    name: 'vite-plugin-monaco-environment',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        return html.replace(
          monacoEnvironmentScript,
          '<script type="module" src="/monaco-environment.js"></script>'
        )
      },
    },
  }
}
