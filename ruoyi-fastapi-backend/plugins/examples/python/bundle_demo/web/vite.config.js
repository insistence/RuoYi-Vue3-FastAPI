import { fileURLToPath, URL } from 'node:url'

// 桥接 SDK 没有外部依赖，独立插件仓库可复制该模块并核对宿主版本兼容性。
export default {
  base: './',
  plugins: [
    {
      name: 'local-plugin-config',
      apply: 'serve',
      transformIndexHtml(html, context) {
        if (context.path !== '/index.html' && context.path !== '/') return html
        return {
          html,
          tags: [
            {
              tag: 'script',
              attrs: { id: 'ruoyi-plugin-config', type: 'application/json' },
              children: JSON.stringify({ pluginId: 'bundle_demo' }),
              injectTo: 'head',
            },
          ],
        }
      },
    },
  ],
  resolve: {
    alias: {
      '@ruoyi/plugin-bridge': fileURLToPath(
        new URL(
          '../../../../../../ruoyi-fastapi-frontend/src/utils/pluginBridge.js',
          import.meta.url
        )
      ),
    },
  },
  build: { sourcemap: false },
}
