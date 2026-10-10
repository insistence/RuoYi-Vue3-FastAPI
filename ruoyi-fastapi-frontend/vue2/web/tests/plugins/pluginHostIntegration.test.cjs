const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const { readFileSync } = require('node:fs')
const path = require('node:path')
const Service = require('@vue/cli-service/lib/Service')
const { createLoader } = require('../support/load-module.cjs')

const root = path.resolve(__dirname, '../..')
const originalEnvironment = { ...process.env }
const originalDirectory = process.cwd()
const loadUtility = createLoader()
const { normalizePluginBase, validatePluginSession } = loadUtility(
  path.join(root, 'src/utils/pluginBridge.js')
)
const { normalizeTransportPath } = loadUtility(path.join(root, 'src/utils/transportPath.js'))

/**
 * 使用 Vue CLI 自带环境加载器读取实际配置，完整恢复环境与配置缓存。
 *
 * @param {string} mode Vue CLI 环境名称
 * @param {string|undefined} pluginBase 显式前缀；未指定时使用环境文件默认值
 * @returns {Object} 实际代理配置和客户端环境值
 */
function loadProxyConfiguration(mode, pluginBase) {
  const environment = { ...process.env }
  const directory = process.cwd()
  const configPath = require.resolve(path.join(root, 'vue.config.js'))
  const cachedConfiguration = require.cache[configPath]
  try {
    process.chdir(root)
    for (const key of Object.keys(process.env)) {
      if (key.startsWith('VUE_APP_') || key === 'NODE_ENV' || key === 'BABEL_ENV') {
        delete process.env[key]
      }
    }
    if (pluginBase !== undefined) process.env.VUE_APP_PLUGIN_BASE = pluginBase
    // 复用真实 mode 与通用 .env 加载顺序，不初始化服务或 Webpack 编译。
    Service.prototype.loadEnv.call({ context: root }, mode)
    Service.prototype.loadEnv.call({ context: root })
    delete require.cache[configPath]
    return {
      proxy: require(configPath).devServer.proxy,
      pluginBase: process.env.VUE_APP_PLUGIN_BASE || '',
      baseApi: process.env.VUE_APP_BASE_API || '',
    }
  } finally {
    process.chdir(directory)
    for (const key of Object.keys(process.env)) {
      if (!Object.hasOwn(environment, key)) delete process.env[key]
    }
    Object.assign(process.env, environment)
    if (cachedConfiguration) require.cache[configPath] = cachedConfiguration
    else delete require.cache[configPath]
  }
}

/**
 * 验证真实代理保留 SSE 上下游异常与退出清理。
 *
 * @param {Object} appProxy 插件应用的实际 Vue CLI 代理配置
 * @returns {void}
 */
function checkStreamCleanup(appProxy) {
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
    appProxy.onProxyRes(upstream, {}, response)
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
  assert.equal(proxy[baseApi].pathRewrite[`^${baseApi}`], '')
  for (const [entry, requestPath] of [
    [appProxy, '/apps/bundle_demo/ui/index.html?asset=main.js'],
    [appProxy, '/apps/task_demo/api/events?tag=first&tag=second&next=%2Fdev-api%2F'],
    [sessionProxy, '/plugin/runtime/bundle_demo/session?mode=preview'],
  ]) {
    assert.equal(typeof entry.pathRewrite, 'function')
    assert.equal(
      entry.pathRewrite(`${prefix}${requestPath}`),
      requestPath,
      '只剥离一次外部前缀，并完整保留查询串'
    )
    assert.equal(
      normalizeTransportPath(`${prefix}${requestPath}`, baseApi, pluginBase),
      requestPath.split('?')[0],
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
 * 仅提取后端非敏感路径配置，断言和日志不包含其他环境值。
 *
 * @param {string} filename 已有的后端环境文件名
 * @returns {string} 后端应用部署前缀
 */
function readBackendRootPath(filename) {
  const match = readFileSync(
    path.resolve(root, '../../../ruoyi-fastapi-backend', filename),
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
  const source = readFileSync(path.join(root, `bin/nginx.${variant}.conf`), 'utf8')
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

module.exports = (async () => {
  for (const [mode, expectedBase, backendFiles] of [
    ['development', '/dev-api', ['.env.dev']],
    ['production', '/prod-api', ['.env.prod']],
    ['docker', '/docker-api', ['.env.dockermy', '.env.dockerpg']],
    ['staging', '/stage-api', []],
  ]) {
    const configuration = loadProxyConfiguration(mode)
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
    const configuration = loadProxyConfiguration('development', base)
    assert.equal(configuration.pluginBase, base, '显式前缀必须覆盖开发环境默认值')
    checkPluginPaths(configuration)
  }
  for (const base of [
    'https://foreign.example',
    '//gateway',
    '/gateway/../admin',
    '/gateway?x=1',
  ]) {
    assert.throws(() => loadProxyConfiguration('development', base), /插件部署路径无效/)
  }
  assert.equal(
    normalizeTransportPath('/dev-api/system/user', '/dev-api', '/gateway'),
    '/system/user'
  )
  assert.equal(
    normalizeTransportPath('/dev-api-other/system/user', '/dev-api', '/gateway'),
    '/dev-api-other/system/user'
  )

  let responseHandler
  let hostLoginPrompts = 0
  const axios = {
    defaults: { headers: {} },
    create: () => ({
      interceptors: {
        request: { use() {} },
        response: {
          use(handler) {
            responseHandler = handler
          },
        },
      },
    }),
    isCancel: () => false,
  }
  const load = createLoader({
    axios,
    'element-ui': {
      Notification: { error() {} },
      MessageBox: {
        confirm() {
          hostLoginPrompts += 1
          return new Promise(() => {})
        },
      },
      Message() {},
      Loading: {},
    },
    '@/store': { dispatch: async () => {} },
    '@/utils/auth': { getToken: () => 'test-main-session' },
    '@/utils/time': { getDisplayTimezone: () => 'UTC' },
    '@/utils/errorCode': {},
    '@/utils/ruoyi': { tansParams: () => '', blobValidate: () => true },
    '@/plugins/cache': {},
    'file-saver': { saveAs() {} },
    '@/utils/transportCrypto': { decryptTransportResponse: async (response) => response },
  })
  load(path.join(root, 'src/utils/request.js'))
  const result = (code, pluginBridge) => ({
    data: { code, msg: 'session status' },
    request: { responseType: 'json' },
    config: { pluginBridge },
  })
  await assert.rejects(responseHandler(result(401, true)), /插件请求失败/)
  await assert.rejects(responseHandler(result(403, true)), /插件请求失败/)
  assert.equal(hostLoginPrompts, 0)
  assert.deepEqual(await responseHandler(result(200, true)), { code: 200, msg: 'session status' })
  await assert.rejects(responseHandler(result(401, false)))
  assert.equal(hostLoginPrompts, 1)
  assert.deepEqual({ ...process.env }, originalEnvironment)
  assert.equal(process.cwd(), originalDirectory)
})()
