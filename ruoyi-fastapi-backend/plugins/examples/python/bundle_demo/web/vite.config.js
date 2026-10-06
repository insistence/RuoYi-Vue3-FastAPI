import { fileURLToPath, URL } from 'node:url'

// 桥接 SDK 没有外部依赖，独立插件仓库可复制该模块并核对宿主版本兼容性。
export default {
  base: './',
  resolve: {
    alias: {
      '@ruoyi/plugin-bridge': fileURLToPath(
        new URL(
          '../../../../../../ruoyi-fastapi-frontend/src/utils/pluginBridge.js',
          import.meta.url,
        ),
      ),
    },
  },
  build: { sourcemap: false },
}
