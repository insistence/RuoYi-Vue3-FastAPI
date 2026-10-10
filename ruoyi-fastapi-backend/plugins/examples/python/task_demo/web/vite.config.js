import { fileURLToPath, URL } from 'node:url'

// 开发配置只在本地服务注入，生产页面由宿主注入真实插件标识与部署基址。
export default {
  base: './',
  plugins: [
    {
      name: 'local-task-plugin-config',
      apply: 'serve',
      transformIndexHtml(html, context) {
        if (context.path !== '/index.html' && context.path !== '/') return html
        return {
          html,
          tags: [
            {
              tag: 'script',
              attrs: { id: 'ruoyi-plugin-config', type: 'application/json' },
              children: JSON.stringify({ pluginId: 'task_demo' }),
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
          '../../../../../../ruoyi-fastapi-frontend/vue3/web/src/utils/pluginBridge.js',
          import.meta.url
        )
      ),
    },
  },
  build: { sourcemap: false },
}
