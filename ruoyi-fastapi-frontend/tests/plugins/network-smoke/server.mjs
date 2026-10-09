import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createServer } from 'vite'

// 复用宿主 Vite 配置，只替换隔离测试的端口、TLS 和代理目标。
const root = fileURLToPath(new URL('../../../', import.meta.url))
const [upstream, certificate, key, readyFile] = process.argv.slice(2)
process.chdir(root)
process.env.VITE_APP_PLUGIN_BASE = '/gateway'
const proxy = () => ({
  target: upstream,
  changeOrigin: false,
  headers: { 'x-forwarded-proto': 'https' },
})
const server = await createServer({
  root,
  configFile: resolve(root, 'vite.config.js'),
  server: {
    host: '127.0.0.1',
    port: 0,
    open: false,
    https: { cert: readFileSync(certificate), key: readFileSync(key) },
    proxy: {
      // 直接复用 Vite 配置的路径改写，避免测试覆盖掩盖实际代理配置错误。
      '/gateway/apps/': { ...proxy(), ws: true },
      '/gateway/plugin/runtime/': proxy(),
      '/dev-api': proxy(),
    },
  },
})
await server.listen()
writeFileSync(readyFile, JSON.stringify({ port: server.httpServer.address().port }))
let stopping = false
async function stop() {
  if (stopping) return
  stopping = true
  await server.close()
  process.exit(0)
}
process.stdin.resume()
process.stdin.on('data', stop)
process.stdin.on('end', stop)
process.on('SIGTERM', stop)
process.on('SIGINT', stop)
