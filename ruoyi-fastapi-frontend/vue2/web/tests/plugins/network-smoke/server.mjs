import { readFile, rename, writeFile } from 'node:fs/promises'
import { createServer } from 'node:https'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const Service = require('@vue/cli-service/lib/Service')
const webpack = require('webpack')
const MemoryFileSystem = require('memory-fs')
const requireDevServer = createRequire(require.resolve('webpack-dev-server'))
const express = requireDevServer('express')
// Resolve the same proxy version as Vue CLI's server, independent of npm hoisting.
const proxyFactory = requireDevServer('http-proxy-middleware')
const createProxyMiddleware = proxyFactory.createProxyMiddleware || proxyFactory
const root = fileURLToPath(new URL('../../../', import.meta.url))
const [upstream, certificate, key, readyFile] = process.argv.slice(2)
if (!upstream || !certificate || !key || !readyFile) {
  throw new Error('upstream, certificate, key and ready-file are required')
}

process.chdir(root)
process.env.NODE_ENV = 'development'
process.env.BABEL_ENV = 'development'
process.env.VUE_APP_BASE_API = '/dev-api'
process.env.VUE_APP_PLUGIN_BASE = '/gateway'

// Compile the real Vue2 application, including its router, Vuex and PluginFrame.
// Fixed test configuration never reads .env files or writes a production dist.
const service = new Service(root)
service.loadEnv = () => {}
service.init('development')
const configuredProxy = service.projectOptions.devServer.proxy
const appProxy = configuredProxy['/gateway/apps/']
const runtimeProxy = configuredProxy['/gateway/plugin/runtime/']
const apiProxy = configuredProxy['/dev-api']
if (!appProxy || !runtimeProxy || !apiProxy || typeof appProxy.onProxyRes !== 'function') {
  throw new Error('The real Vue2 plugin proxy configuration is required')
}
const config = service.resolveWebpackConfig()
config.devtool = 'cheap-module-source-map'
const compiler = webpack(config)
const output = new MemoryFileSystem()
compiler.outputFileSystem = output
const outputRoot = config.output.path
let server
let closing = false
const sockets = new Set()
async function close(exitCode = 0) {
  if (closing) return
  closing = true
  const deadline = setTimeout(() => process.exit(1), 5000)
  deadline.unref()
  for (const socket of sockets) socket.destroy()
  if (server?.listening) await new Promise((resolve) => server.close(resolve))
  clearTimeout(deadline)
  process.exit(exitCode)
}
process.stdin.resume()
process.stdin.on('data', () => void close())
process.stdin.on('end', () => void close())
process.on('SIGTERM', () => void close())
process.on('SIGINT', () => void close())

try {
  // A single compilation finishes before listening. Watch rebuilds must not
  // stall TLS handshakes or long-connection assertions during the smoke test.
  await new Promise((resolve, reject) => {
    compiler.run((error, stats) => {
      if (error) return reject(error)
      if (stats.hasErrors()) {
        return reject(new Error(stats.toString({ all: false, errors: true })))
      }
      console.log(`Vue2 smoke host compiled successfully in ${stats.endTime - stats.startTime}ms`)
      resolve()
    })
  })
  const app = express()
  const proxy = {
    target: upstream,
    changeOrigin: false,
    headers: { 'x-forwarded-proto': 'https' },
    logLevel: 'warn',
  }
  // Reuse real path rewriting and SSE cleanup; only override the isolated upstream.
  const apps = createProxyMiddleware('/gateway/apps/', { ...appProxy, ...proxy })
  app.use(apps)
  app.use(createProxyMiddleware('/gateway/plugin/runtime/', { ...runtimeProxy, ...proxy }))
  app.use(
    createProxyMiddleware('/dev-api', {
      ...apiProxy,
      ...proxy,
    })
  )
  app.use(express.static(path.join(root, 'public'), { index: false }))
  app.use((request, response) => {
    if (!['GET', 'HEAD'].includes(request.method)) return response.sendStatus(405)
    let asset
    try {
      asset = path.resolve(outputRoot, '.' + decodeURIComponent(request.path))
    } catch {
      return response.sendStatus(400)
    }
    const relative = path.relative(outputRoot, asset)
    if (relative.startsWith('..') || path.isAbsolute(relative)) return response.sendStatus(403)
    if (!output.existsSync(asset) || !output.statSync(asset).isFile()) {
      if (path.extname(request.path) || !request.accepts('html')) return response.sendStatus(404)
      asset = path.join(outputRoot, 'index.html')
    }
    response.type(path.extname(asset)).send(output.readFileSync(asset))
  })
  server = createServer({ cert: await readFile(certificate), key: await readFile(key) }, app)
  server.on('upgrade', (request, socket, head) => {
    // HPM 0.19 auto-subscribes apps.upgrade after the first HTTP request.
    // Avoid invoking that same handler twice, while supporting WS-first clients.
    if (!server.listeners('upgrade').includes(apps.upgrade)) {
      apps.upgrade(request, socket, head)
    }
  })
  server.on('connection', (socket) => {
    sockets.add(socket)
    socket.on('close', () => sockets.delete(socket))
  })
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  // Publish readiness atomically: the Python observer must never see an empty file.
  await writeFile(readyFile + '.tmp', JSON.stringify({ port: server.address().port }))
  await rename(readyFile + '.tmp', readyFile)
} catch (error) {
  console.error(error)
  await close(1)
}
