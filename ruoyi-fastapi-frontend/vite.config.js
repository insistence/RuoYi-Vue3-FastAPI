import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import createVitePlugins from './vite/plugins'
import { normalizePluginBase } from './src/utils/pluginBridge.js'

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd())
  const { VITE_APP_ENV } = env
  const pluginBase = normalizePluginBase(env.VITE_APP_PLUGIN_BASE || '')
  return {
    // 部署生产环境和开发环境下的URL。
    // 默认情况下，vite 会假设你的应用是被部署在一个域名的根路径上
    // 例如 https://www.ruoyi.vip/。如果应用被部署在一个子路径上，你就需要用这个选项指定这个子路径。例如，如果你的应用被部署在 https://www.ruoyi.vip/admin/，则设置 baseUrl 为 /admin/。
    base: VITE_APP_ENV === 'production' ? '/' : '/',
    plugins: createVitePlugins(env, command === 'build'),
    resolve: {
      // https://cn.vitejs.dev/config/#resolve-alias
      alias: {
        // 设置路径
        '~': path.resolve(__dirname, './'),
        // 设置别名
        '@': path.resolve(__dirname, './src'),
      },
      // https://cn.vitejs.dev/config/#resolve-extensions
      extensions: ['.mjs', '.js', '.ts', '.jsx', '.tsx', '.json', '.vue'],
    },
    // 打包配置
    build: {
      // https://vite.dev/config/build-options.html
      sourcemap: command === 'build' ? false : 'inline',
      outDir: 'dist',
      assetsDir: 'assets',
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          chunkFileNames: 'static/js/[name]-[hash].js',
          entryFileNames: 'static/js/[name]-[hash].js',
          assetFileNames: 'static/[ext]/[name]-[hash].[ext]',
        },
      },
    },
    // vite 相关配置
    server: {
      port: 80,
      host: true,
      open: true,
      proxy: {
        [`${pluginBase}/apps/`]: {
          target: 'http://127.0.0.1:9099',
          changeOrigin: false,
          ws: true,
          configure(proxy) {
            proxy.on('proxyRes', (upstream, _request, response) => {
              if (
                upstream.headers['content-type']?.split(';')[0].trim().toLowerCase() !==
                'text/event-stream'
              )
                return
              // pipe 不会转发上游异常关闭；及时结束下游，让插件可以报告失败并重连。
              upstream.once('aborted', () => response.destroy())
              upstream.once('error', () => response.destroy())
              response.once('close', () => {
                if (!upstream.complete) upstream.destroy()
              })
            })
          },
        },
        [`${pluginBase}/plugin/runtime/`]: {
          target: 'http://127.0.0.1:9099',
          changeOrigin: false,
        },
        // https://cn.vitejs.dev/config/#server-proxy
        '/dev-api': {
          target: 'http://127.0.0.1:9099',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/dev-api/, ''),
        },
        '/.well-known': {
          target: 'http://127.0.0.1:9099',
          changeOrigin: true,
        },
        '/oauth2': {
          target: 'http://127.0.0.1:9099',
          changeOrigin: true,
        },
        '/auth/interaction': {
          target: 'http://127.0.0.1:9099',
          changeOrigin: true,
        },
      },
    },
    //fix:error:stdin>:7356:1: warning: "@charset" must be the first rule in the file
    css: {
      postcss: {
        plugins: [
          {
            postcssPlugin: 'internal:charset-removal',
            AtRule: {
              charset: (atRule) => {
                if (atRule.name === 'charset') {
                  atRule.remove()
                }
              },
            },
          },
        ],
      },
    },
  }
})
