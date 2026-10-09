import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadConfigFromFile, loadEnv } from 'vite'
import { normalizePluginBase, validatePluginSession } from '../../src/utils/pluginBridge.js'
import { normalizeTransportPath } from '../../src/utils/transportPath.js'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const originalEnvironment = { ...process.env }
const originalDirectory = process.cwd()

/**
 * 加载指定环境的实际配置，并恢复 Vite 读取配置时涉及的进程环境。
 *
 * @param {string} mode Vite 环境名称
 * @param {string|undefined} pluginBase 显式前缀；未指定时使用该环境默认值
 * @returns {Promise<Object>} 实际代理配置与客户端使用的环境值
 */
async function loadConfiguration(mode, pluginBase) {
  const environment = { ...process.env }
  const directory = process.cwd()
  try {
    process.chdir(frontendRoot)
    delete process.env.VITE_APP_PLUGIN_BASE
    delete process.env.VITE_APP_BASE_API
    if (pluginBase !== undefined) process.env.VITE_APP_PLUGIN_BASE = pluginBase
    const env = loadEnv(mode, frontendRoot)
    const loaded = await loadConfigFromFile(
      { command: 'serve', mode },
      resolve(frontendRoot, 'vite.config.js'),
      frontendRoot,
      'silent'
    )
    assert.ok(loaded, '实际 Vite 配置必须成功加载')
    return {
      proxy: loaded.config.server.proxy,
      pluginBase: env.VITE_APP_PLUGIN_BASE || '',
      baseApi: env.VITE_APP_BASE_API || '',
    }
  } finally {
    process.chdir(directory)
    for (const key of Object.keys(process.env)) {
      if (!Object.hasOwn(environment, key)) delete process.env[key]
    }
    Object.assign(process.env, environment)
  }
}

/**
 * 验证真实代理保留 SSE 上下游异常与退出清理。
 *
 * @param {Object} appProxy 插件应用的实际 Vite 代理配置
 * @returns {void}
 */
function checkStreamCleanup(appProxy) {
  const proxy = new EventEmitter()
  appProxy.configure(proxy)
  const pair = (contentType = 'text/event-stream; charset=utf-8') => {
    const upstream = new EventEmitter()
    const response = new EventEmitter()
    upstream.headers = { 'content-type': contentType }
    upstream.complete = false
    upstream.destroy = () => {
      upstream.destroyed = true
    }
    response.destroy = () => {
      response.destroyed = true
    }
    proxy.emit('proxyRes', upstream, {}, response)
    return { upstream, response }
  }
  for (const event of ['aborted', 'error']) {
    const { upstream, response } = pair()
    upstream.emit(event)
    assert.equal(response.destroyed, true, `SSE 上游 ${event} 必须结束下游`)
  }
  const disconnected = pair()
  disconnected.response.emit('close')
  assert.equal(disconnected.upstream.destroyed, true)
  const complete = pair()
  complete.upstream.complete = true
  complete.response.emit('close')
  assert.equal(complete.upstream.destroyed, undefined)
  const json = pair('application/json')
  assert.equal(json.upstream.listenerCount('aborted'), 0)
  assert.equal(json.upstream.listenerCount('error'), 0)
  assert.equal(json.response.listenerCount('close'), 0)
}

/**
 * 验证浏览器会话、专用代理与加密 AAD 使用同一个部署前缀。
 *
 * @param {Object} configuration 实际加载的环境配置
 * @returns {void}
 */
function checkPluginPaths({ proxy, pluginBase, baseApi }) {
  const prefix = normalizePluginBase(pluginBase)
  const appProxy = proxy[`${prefix}/apps/`]
  const sessionProxy = proxy[`${prefix}/plugin/runtime/`]
  assert.ok(appProxy, '插件应用必须走独立代理')
  assert.ok(sessionProxy, '插件会话必须走独立代理')
  assert.equal(appProxy.changeOrigin, false)
  assert.equal(sessionProxy.changeOrigin, false)
  assert.equal(appProxy.ws, true)
  for (const [entry, path] of [
    [appProxy, '/apps/bundle_demo/ui/index.html?asset=main.js'],
    [appProxy, '/apps/task_demo/api/events?tag=first&tag=second&next=%2Fdev-api%2F'],
    [sessionProxy, '/plugin/runtime/bundle_demo/session?mode=preview'],
  ]) {
    assert.equal(typeof entry.rewrite, 'function')
    assert.equal(entry.rewrite(`${prefix}${path}`), path, '只剥离外部前缀并完整保留查询串')
    assert.equal(
      normalizeTransportPath(`${prefix}${path}`, baseApi, pluginBase),
      path.split('?')[0],
      'AAD 使用后端接收到的无前缀路径'
    )
  }
  for (const pluginId of ['bundle_demo', 'task_demo']) {
    const session = {
      pluginId,
      bridgeVersion: 1,
      uiBase: `${prefix}/apps/${pluginId}/ui/`,
      apiBase: `${prefix}/apps/${pluginId}/api/`,
      csrfToken: 'test-plugin-csrf-token',
      expiresIn: 300,
    }
    assert.deepEqual(validatePluginSession(session, pluginId, pluginBase, 100), {
      ...session,
      expiresAt: 300100,
    })
  }
  checkStreamCleanup(appProxy)
}

/**
 * 只提取后端非敏感路径配置，避免断言和日志包含其他环境值。
 *
 * @param {string} filename 已有的后端环境文件名
 * @returns {string} 后端应用部署前缀
 */
function readBackendRootPath(filename) {
  const match = readFileSync(
    resolve(frontendRoot, '../ruoyi-fastapi-backend', filename),
    'utf8'
  ).match(/^APP_ROOT_PATH\s*=\s*['"]?([^'"\s#]*)['"]?\s*(?:#.*)?$/m)
  assert.ok(match, `${filename} 必须显式配置 APP_ROOT_PATH`)
  return match[1]
}

/**
 * 检查实际 Docker nginx 插件代理的路径替换与同源流式配置。
 *
 * @param {string} variant Docker 数据库配置名称
 * @param {string} upstream 对应的后端服务名
 * @param {string} prefix 客户端与后端共有的部署前缀
 * @returns {void}
 */
function checkDockerNginx(variant, upstream, prefix) {
  const source = readFileSync(resolve(frontendRoot, `bin/nginx.${variant}.conf`), 'utf8')
  const locations = [...source.matchAll(/^\s*location\s+\^~\s+(\S+)\s*\{([^{}]*)\}/gm)]
  const blocks = {}
  for (const route of ['/apps/', '/plugin/runtime/']) {
    const matches = locations.filter((match) => match[1] === `${prefix}${route}`)
    assert.equal(matches.length, 1, `${variant} 必须有唯一的 ${prefix}${route} 专用代理`)
    const block = matches[0][2]
    const proxyPass = block.match(/^\s*proxy_pass\s+(\S+)\s*;/m)
    assert.equal(proxyPass?.[1], `http://${upstream}:9099${route}`)
    assert.match(block, /^\s*proxy_set_header\s+Host\s+\$http_host\s*;/m)
    assert.match(block, /^\s*proxy_set_header\s+X-Forwarded-Proto\s+\$scheme\s*;/m)
    assert.ok(!locations.some((match) => match[1] === route), '不得遗留无部署前缀的专用代理')
    blocks[route] = block
  }
  assert.match(blocks['/apps/'], /^\s*proxy_http_version\s+1\.1\s*;/m)
  assert.match(blocks['/apps/'], /^\s*proxy_set_header\s+Upgrade\s+\$http_upgrade\s*;/m)
  assert.match(
    blocks['/apps/'],
    /^\s*proxy_set_header\s+Connection\s+\$plugin_connection_upgrade\s*;/m
  )
  assert.match(blocks['/apps/'], /^\s*proxy_buffering\s+off\s*;/m)
  assert.match(blocks['/apps/'], /^\s*proxy_read_timeout\s+300s\s*;/m)
  assert.match(
    blocks['/plugin/runtime/'],
    /^\s*add_header\s+Cache-Control\s+"no-store"\s+always\s*;/m
  )
  const upgradeMap = source.match(
    /^\s*map\s+\$http_upgrade\s+\$plugin_connection_upgrade\s*\{([^{}]*)\}/m
  )
  assert.ok(upgradeMap, 'WebSocket 的 Connection 请求头必须按 Upgrade 状态切换')
  assert.match(upgradeMap[1], /^\s*default\s+upgrade\s*;/m)
  assert.match(upgradeMap[1], /^\s*''\s+close\s*;/m)
}

for (const [mode, expectedBase, backendFiles] of [
  ['development', '/dev-api', ['.env.dev']],
  ['production', '/prod-api', ['.env.prod']],
  ['docker', '/docker-api', ['.env.dockermy', '.env.dockerpg']],
  ['staging', '/stage-api', []],
]) {
  const configuration = await loadConfiguration(mode)
  assert.equal(configuration.pluginBase, expectedBase)
  assert.equal(configuration.pluginBase, configuration.baseApi, `${mode} 的两种 API 前缀必须一致`)
  for (const filename of backendFiles) {
    assert.equal(configuration.pluginBase, readBackendRootPath(filename))
  }
  checkPluginPaths(configuration)
  if (mode === 'docker') {
    checkDockerNginx('dockermy', 'ruoyi-backend-my', configuration.pluginBase)
    checkDockerNginx('dockerpg', 'ruoyi-backend-pg', configuration.pluginBase)
  }
}

for (const base of ['', '/', '/gateway', '/gateway/nested-v1/']) {
  const configuration = await loadConfiguration('development', base)
  assert.equal(configuration.pluginBase, base, '显式前缀必须覆盖开发环境默认值')
  checkPluginPaths(configuration)
}
for (const base of ['https://foreign.example', '//gateway', '/gateway/../admin', '/gateway?x=1']) {
  await assert.rejects(loadConfiguration('development', base), /插件部署路径无效/)
}
assert.deepEqual({ ...process.env }, originalEnvironment)
assert.equal(process.cwd(), originalDirectory)
