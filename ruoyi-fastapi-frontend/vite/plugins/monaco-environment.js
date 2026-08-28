const monacoEnvironmentScript = /<script>\s*self\["MonacoEnvironment"\][\s\S]*?<\/script>/

export default function createMonacoEnvironment() {
    return {
        name: 'vite-plugin-monaco-environment',
        transformIndexHtml: {
            order: 'post',
            handler(html) {
                return html.replace(monacoEnvironmentScript, '<script type="module" src="/monaco-environment.js"></script>')
            }
        }
    }
}
