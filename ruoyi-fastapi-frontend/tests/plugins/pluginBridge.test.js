import assert from 'node:assert/strict'
import {
  createPluginClient,
  createPluginHostBridge,
  normalizePluginBase,
  PLUGIN_BRIDGE_MAX_BYTES,
  validatePluginApiPath,
  validatePluginRoute,
  validatePluginSession,
} from '../../src/utils/pluginBridge.js'
import { normalizeTransportPath } from '../../src/utils/transportPath.js'

const ORIGIN = 'https://example.test'
const sessionData = {
  pluginId: 'demo',
  bridgeVersion: 1,
  uiBase: '/apps/demo/ui/',
  apiBase: '/apps/demo/api/',
  csrfToken: 'csrf-token-for-tests-only',
  expiresIn: 300,
}
const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((a, b) => {
    resolve = a
    reject = b
  })
  return { promise, resolve, reject }
}
const flush = () => new Promise((resolve) => setImmediate(resolve))

function windowPair() {
  const makeWindow = () => {
    const listeners = new Set()
    return {
      messages: [],
      listeners,
      addEventListener(type, listener) {
        if (type === 'message') listeners.add(listener)
      },
      removeEventListener(type, listener) {
        if (type === 'message') listeners.delete(listener)
      },
      dispatch(event) {
        for (const listener of [...listeners]) listener(event)
      },
    }
  }
  const hostWindow = makeWindow()
  const childWindow = makeWindow()
  for (const [target, source] of [
    [hostWindow, childWindow],
    [childWindow, hostWindow],
  ]) {
    target.postMessage = (data, targetOrigin) => {
      assert.equal(targetOrigin, ORIGIN, 'all messages must name an exact origin')
      target.messages.push(data)
      queueMicrotask(() => target.dispatch({ data, source, origin: ORIGIN }))
    }
  }
  return { hostWindow, childWindow }
}

async function setup({
  request = async () => ({ code: 200, data: 'ok' }),
  now = Date.now,
  timeoutMs = 15000,
} = {}) {
  const { hostWindow, childWindow } = windowPair()
  let target = childWindow
  let theme = 'light'
  const routes = []
  const host = createPluginHostBridge({
    pluginId: 'demo',
    session: validatePluginSession(sessionData, 'demo', '', now()),
    getTarget: () => target,
    request,
    getContext: () => ({
      theme: { mode: theme },
      language: 'zh-CN',
      timeZone: 'Asia/Shanghai',
      route: '/',
    }),
    onRoute: (route) => routes.push(route),
    eventTarget: hostWindow,
    origin: ORIGIN,
    now,
    timeoutMs,
  })
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: childWindow,
    parentWindow: hostWindow,
    origin: ORIGIN,
  })
  await child.ready
  return {
    hostWindow,
    childWindow,
    host,
    child,
    routes,
    replaceTarget: () => {
      target = {}
    },
    changeTheme: () => {
      theme = 'dark'
      host.updatePreferences()
    },
    destroy: () => {
      host.destroy()
      child.destroy()
    },
  }
}

assert.equal(normalizePluginBase('/deployment/'), '/deployment')
for (const base of ['//evil.test', 'https://evil.test', '/a/../b', '/%2e', '/x\\y', '/x//y']) {
  assert.throws(() => normalizePluginBase(base))
}
assert.equal(validatePluginSession(sessionData, 'demo', '', 100).expiresAt, 300100)
assert.equal(
  validatePluginSession(
    { ...sessionData, uiBase: '/prefix/apps/demo/ui/', apiBase: '/prefix/apps/demo/api/' },
    'demo',
    '/prefix'
  ).apiBase,
  '/prefix/apps/demo/api/'
)
for (const changes of [
  { uiBase: '//evil.test/apps/demo/ui/' },
  { uiBase: 'https://example.test/apps/demo/ui/' },
  { apiBase: '/apps/other/api/' },
  { apiBase: '/prefix/apps/demo/api/' },
  { apiBase: '/apps/demo/api/../' },
  { pluginId: 'other' },
  { expiresIn: 0 },
  { expiresIn: 5000 },
  { bridgeVersion: 2 },
  { csrfToken: 'bad\nheader' },
])
  assert.throws(() => validatePluginSession({ ...sessionData, ...changes }, 'demo'))
for (const path of ['', 'status', 'model/v1.2', 'reports/2026-10/'])
  assert.equal(validatePluginApiPath(path), path)
for (const path of [
  '/status',
  '//evil.test',
  'https://evil.test',
  '..',
  'a/../b',
  'a/./b',
  'a//b',
  'a\\b',
  '%2e%2e/admin',
  '%252e%252e',
  'a%2fb',
  'a?x=1',
  'a#hash',
  'a\n',
]) {
  assert.throws(() => validatePluginApiPath(path), path)
}
assert.equal(validatePluginRoute('/reports/today'), '/reports/today')
assert.throws(() => validatePluginRoute('//outside'))
assert.throws(() => validatePluginRoute('/../admin'))
assert.equal(
  normalizeTransportPath('/root/apps/demo/api/status', '/dev-api', '/root'),
  '/apps/demo/api/status'
)
assert.equal(
  normalizeTransportPath('/root/plugin/runtime/demo/session', '/dev-api', '/root'),
  '/plugin/runtime/demo/session'
)
assert.equal(normalizeTransportPath('/dev-api/system/user', '/dev-api'), '/system/user')
assert.equal(normalizeTransportPath('/dev-api-other/user', '/dev-api'), '/dev-api-other/user')
assert.equal(
  normalizeTransportPath('/rooted/apps/demo/api/status', '/dev-api', '/root'),
  '/rooted/apps/demo/api/status'
)

// 验证握手、接口请求和上下文同步，不向子页面传递宿主令牌或 CSRF 令牌。
{
  const requests = []
  const pair = await setup({
    request: async (config) => {
      requests.push(config)
      return { code: 200, data: [1, 2] }
    },
  })
  assert.equal(pair.child.context.apiBase, '/apps/demo/api/')
  assert.equal(pair.child.context.csrfToken, undefined)
  const result = await pair.child.request({
    method: 'POST',
    path: 'status',
    data: { value: 3 },
    params: { page: 1 },
  })
  assert.deepEqual(result, { code: 200, data: [1, 2] })
  assert.equal(requests[0].url, '/apps/demo/api/status')
  assert.equal(requests[0].baseURL, '')
  assert.deepEqual(requests[0].headers, {
    isToken: false,
    'X-Plugin-CSRF': sessionData.csrfToken,
    repeatSubmit: false,
  })
  assert.equal(requests[0].headers.Authorization, undefined)
  assert.equal(requests[0].pluginBridge, true)
  pair.changeTheme()
  await flush()
  assert.equal(pair.child.context.theme.mode, 'dark')
  pair.child.navigate('/details')
  await flush()
  assert.deepEqual(pair.routes, ['/details'])
  pair.host.updateRoute('/back')
  await flush()
  assert.equal(pair.child.context.route, '/back')
  const events = []
  pair.child.subscribe((event) => events.push(event.type))
  pair.host.refresh()
  await flush()
  assert.deepEqual(events, ['refresh'])
  pair.destroy()
  assert.equal(pair.hostWindow.listeners.size, 0)
  assert.equal(pair.childWindow.listeners.size, 0)
}

// 拒绝伪造来源、旧页面随机标识、无效字段和接口路径越界。
{
  let calls = 0
  const pair = await setup({
    request: async () => {
      calls += 1
      return {}
    },
  })
  const initialization = pair.childWindow.messages.find((message) => message.type === 'initialize')
  const message = {
    namespace: 'ruoyi.plugin',
    version: 1,
    pluginId: 'demo',
    type: 'request',
    instance: initialization.instance,
    id: 'test',
    payload: { method: 'GET', path: 'status' },
  }
  const emit = (data, origin = ORIGIN, source = pair.childWindow) =>
    pair.hostWindow.dispatch({ data, origin, source })
  emit(message, 'https://evil.test')
  emit(message, ORIGIN, {})
  emit({ ...message, instance: 'previous-frame' })
  emit({ ...message, version: 2 })
  emit({ ...message, pluginId: 'other' })
  emit({ ...message, headers: { Authorization: 'bad' } })
  await flush()
  assert.equal(calls, 0)
  for (const payload of [
    { method: 'GET', path: '/admin' },
    { method: 'GET', path: 'status', headers: { Authorization: 'bad' } },
    { method: 'GET', path: 'status', baseURL: 'https://evil.test' },
    { method: 'GET', path: 'status', data: {} },
    { method: 'TRACE', path: 'status' },
    { method: 'POST', path: 'status', data: 'x'.repeat(PLUGIN_BRIDGE_MAX_BYTES + 1) },
    { method: 'POST', path: 'status', data: JSON.parse('{"__proto__":{"bad":true}}') },
  ]) {
    emit({ ...message, payload })
    await flush()
    assert.equal(pair.childWindow.messages.at(-1).payload.ok, false)
  }
  assert.equal(calls, 0)
  pair.replaceTarget()
  emit(message)
  await flush()
  assert.equal(calls, 0)
  pair.destroy()
}

// 页面超时、销毁或会话过期后，不再返回旧请求的结果。
{
  let now = 0
  const pending = deferred()
  let captured
  const pair = await setup({
    now: () => now,
    request: (config) => {
      captured = config
      return pending.promise
    },
  })
  const promise = pair.child.request({ method: 'GET', path: 'slow' })
  const rejected = assert.rejects(promise, /失效/)
  await flush()
  pair.host.destroy({ logout: true })
  await rejected
  assert.equal(captured.signal.aborted, true)
  pending.resolve({ secret: 'late-result' })
  await flush()
  assert.equal(
    pair.childWindow.messages.some((message) => message.type === 'result'),
    false
  )
  assert.equal(pair.childWindow.listeners.size, 0)
  pair.destroy()
}
{
  const pending = deferred()
  let captured
  const pair = await setup({
    request: (config) => {
      captured = config
      return pending.promise
    },
    timeoutMs: 10,
  })
  await assert.rejects(pair.child.request({ method: 'GET', path: 'slow' }), /超时/)
  assert.equal(captured.signal.aborted, true)
  pending.resolve({ late: true })
  await flush()
  assert.equal(pair.childWindow.messages.filter((message) => message.type === 'result').length, 1)
  pair.destroy()
}
{
  let now = 0
  let calls = 0
  const pair = await setup({
    now: () => now,
    request: async () => {
      calls += 1
      return {}
    },
  })
  now = 301000
  const controller = new AbortController()
  const promise = pair.child.request(
    { method: 'GET', path: 'status' },
    { signal: controller.signal }
  )
  const rejected = assert.rejects(promise, /取消/)
  await flush()
  assert.equal(calls, 0)
  controller.abort()
  await rejected
  pair.destroy()
}

// 会话续期只更新宿主侧会话和 CSRF 令牌，不重新启动子页面 SDK。
{
  let captured
  const pair = await setup({
    request: async (config) => {
      captured = config
      return {}
    },
  })
  pair.host.setSession(
    validatePluginSession({ ...sessionData, csrfToken: 'renewed-csrf-token-test' }, 'demo')
  )
  await pair.child.request({ method: 'GET', path: 'status' })
  assert.equal(captured.headers['X-Plugin-CSRF'], 'renewed-csrf-token-test')
  assert.equal(
    pair.childWindow.messages.filter((message) => message.type === 'initialize').length,
    1
  )
  assert.throws(() => pair.host.setSession({ ...sessionData, apiBase: '/apps/other/api/' }))
  pair.destroy()
}

// iframe 重载会保留 WindowProxy，但必须更换文档随机标识并取消旧请求。
// 旧文档迟到的 ready 消息不能恢复旧连接。
{
  const pending = deferred()
  const captured = []
  const pair = await setup({
    request: (config) => {
      captured.push(config)
      return config.url.endsWith('/slow') ? pending.promise : Promise.resolve({ code: 200 })
    },
  })
  const oldReady = pair.hostWindow.messages.find((message) => message.type === 'ready')
  const oldInit = pair.childWindow.messages.find((message) => message.type === 'initialize')
  const oldPromise = pair.child.request({ method: 'GET', path: 'slow' })
  const oldRejected = assert.rejects(oldPromise, /关闭/)
  await flush()
  // 在同一个子窗口 WindowProxy 上模拟新文档的 SDK。
  const fresh = createPluginClient({
    pluginId: 'demo',
    eventTarget: pair.childWindow,
    parentWindow: pair.hostWindow,
    origin: ORIGIN,
  })
  await fresh.ready
  assert.equal(captured[0].signal.aborted, true)
  const newInit = pair.childWindow.messages
    .filter((message) => message.type === 'initialize')
    .at(-1)
  assert.notEqual(newInit.instance, oldInit.instance)
  pair.hostWindow.dispatch({ data: oldReady, origin: ORIGIN, source: pair.childWindow })
  pending.resolve({ data: 'from-old-page' })
  await flush()
  assert.equal(
    pair.childWindow.messages.filter((message) => message.type === 'initialize').length,
    2
  )
  assert.equal(
    pair.childWindow.messages.some((message) => message.type === 'result'),
    false
  )
  pair.child.destroy()
  await oldRejected
  assert.deepEqual(await fresh.request({ method: 'GET', path: 'status' }), { code: 200 })
  fresh.destroy()
  pair.destroy()
}

// 验证并发上限和取消行为，服务端异常只返回可展示的错误文本。
{
  const requests = []
  const pair = await setup({
    request: (config) => {
      requests.push(config)
      return new Promise(() => {})
    },
  })
  const promises = Array.from({ length: 8 }, () =>
    pair.child.request({ method: 'GET', path: 'wait' })
  )
  const rejected = promises.map((promise) => assert.rejects(promise, /关闭/))
  await flush()
  await assert.rejects(pair.child.request({ method: 'GET', path: 'extra' }), /过多/)
  pair.child.destroy()
  await Promise.all(rejected)
  await flush()
  assert.equal(requests.length, 8)
  assert.equal(
    requests.every((config) => config.signal.aborted),
    true
  )
  pair.host.destroy()
}
{
  const pair = await setup({
    request: async () => {
      throw new Error('secret master token stack trace')
    },
  })
  await assert.rejects(
    pair.child.request({ method: 'GET', path: 'failure' }),
    /^Error: 插件请求失败，请重试$/
  )
  assert.equal(JSON.stringify(pair.childWindow.messages).includes('secret master'), false)
  pair.destroy()
}

// 宿主无响应时，SDK 应在握手超时后移除监听。
{
  const pair = windowPair()
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: pair.childWindow,
    parentWindow: pair.hostWindow,
    origin: ORIGIN,
    timeoutMs: 10,
  })
  await assert.rejects(child.ready, /初始化超时/)
  assert.equal(pair.childWindow.listeners.size, 0)
}

// 首次握手期间支持取消请求，握手前后的排队请求使用相同并发上限。
{
  const pair = windowPair()
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: pair.childWindow,
    parentWindow: pair.hostWindow,
    origin: ORIGIN,
  })
  const controller = new AbortController()
  const promise = child.request({ method: 'GET', path: 'status' }, { signal: controller.signal })
  const cancelled = assert.rejects(promise, /已取消/)
  controller.abort()
  await cancelled
  assert.equal(
    pair.hostWindow.messages.some((message) => message.type === 'request'),
    false
  )

  const pending = Array.from({ length: 8 }, () => child.request({ method: 'GET', path: 'status' }))
  const rejected = pending.map((entry) => assert.rejects(entry, /关闭/))
  await assert.rejects(child.request({ method: 'GET', path: 'overflow' }), /过多/)
  child.destroy()
  await Promise.all(rejected)
  assert.equal(pair.childWindow.listeners.size, 0)
}
