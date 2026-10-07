import assert from 'node:assert/strict'
import {
  createPluginClient,
  createPluginHostBridge,
  normalizePluginBase,
  PLUGIN_BRIDGE_MAX_BYTES,
  PLUGIN_BRIDGE_MAX_FILE_BYTES,
  validatePluginApiPath,
  validatePluginRoute,
  validatePluginSession,
} from '../../src/utils/pluginBridge.js'
import { normalizeTransportPath } from '../../src/utils/transportPath.js'

// 文件通过真实结构化克隆进入宿主，表单由宿主重建且仍使用受限会话。
async function checkFileTransfers() {
  const requests = []
  const events = []
  const pair = await setup({
    request: async (config) => {
      requests.push(config)
      if (config.responseType === 'blob') {
        config.onDownloadProgress({ loaded: 6, total: 6 })
        return new Blob(['报告'], { type: 'text/plain' })
      }
      assert.equal(config.data.get('category'), 'test')
      const file = config.data.get('attachment')
      assert.equal(file.name, '报告.txt')
      assert.equal(await file.text(), '报告')
      config.onUploadProgress({ loaded: 3, total: 6 })
      config.onUploadProgress({ loaded: 6, total: 6 })
      return { received: file.size }
    },
  })
  try {
    const result = await pair.child.upload(
      {
        path: 'files/upload',
        file: new Blob(['报告']),
        filename: '报告.txt',
        fieldName: 'attachment',
        fields: { category: 'test' },
      },
      {
        onProgress: (event) => {
          events.push(event)
          throw new Error('插件回调错误')
        },
      }
    )
    assert.deepEqual(result, { received: 6 })
    assert.deepEqual(events.at(-1), { phase: 'upload', loaded: 6, total: 6 })
    const blob = await pair.child.download(
      { path: 'files/report', params: { month: '10' } },
      { onProgress: (event) => events.push(event) }
    )
    assert.equal(await blob.text(), '报告')
    assert.equal(blob.type, 'text/plain')
    assert.deepEqual(events.at(-1), { phase: 'download', loaded: 6, total: 6 })
    for (const config of requests) {
      assert.equal(config.headers.isToken, false)
      assert.equal(config.headers['X-Plugin-CSRF'], sessionData.csrfToken)
      assert.equal(config.headers.Authorization, undefined)
      assert.equal(config.headers.encrypt, false)
      assert.equal(config.timeout, 120000)
      assert.equal(config.pluginBridge, true)
    }
    assert.equal(requests[0].headers['Content-Type'], undefined)
    assert.equal(requests[0].url, '/apps/demo/api/files/upload')
    assert.equal(pair.child.context.capabilities.files.maxBytes, PLUGIN_BRIDGE_MAX_FILE_BYTES)
  } finally {
    pair.destroy()
  }
}

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
      data = structuredClone(data)
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
  transferTimeoutMs = 120000,
  stream,
  streamTimeoutMs = 300000,
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
    stream,
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
    transferTimeoutMs,
    streamTimeoutMs,
  })
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: childWindow,
    parentWindow: hostWindow,
    origin: ORIGIN,
    transferTimeoutMs,
    streamTimeoutMs,
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

await checkFileTransfers()

// 无效文件在子页面和宿主两侧分别拒绝，下载也不能返回错误信封或过大响应。
{
  let calls = 0
  const pair = await setup({
    request: async () => {
      calls += 1
      return {}
    },
  })
  const valid = { path: 'upload', file: new Blob(['test']) }
  for (const changes of [
    { file: 'not a file' },
    { file: new Blob([new Uint8Array(PLUGIN_BRIDGE_MAX_FILE_BYTES + 1)]) },
    { filename: '../secret' },
    { filename: 'bad\nname' },
    { fieldName: 'a\r\nb' },
    { fields: { file: 'duplicate' } },
    { fields: { number: 1 } },
    { params: null },
    { path: '//outside.test' },
    { method: 'GET' },
    { headers: { Authorization: 'forged' } },
  ])
    await assert.rejects(pair.child.upload({ ...valid, ...changes }))
  await assert.rejects(pair.child.download({ path: '../outside' }))
  await assert.rejects(pair.child.download({ path: 'ok' }, { onProgress: true }))
  const init = pair.childWindow.messages.find((message) => message.type === 'initialize')
  pair.hostWindow.dispatch({
    origin: ORIGIN,
    source: pair.childWindow,
    data: {
      namespace: 'ruoyi.plugin',
      version: 1,
      pluginId: 'demo',
      instance: init.instance,
      type: 'upload',
      id: 'forged-file',
      payload: {
        method: 'POST',
        path: 'upload',
        file: 'bad',
        fieldName: 'file',
        filename: 'x',
        fields: {},
      },
    },
  })
  await flush()
  assert.equal(calls, 0)
  assert.equal(
    pair.childWindow.messages.find((message) => message.id === 'forged-file').payload.ok,
    false
  )
  pair.destroy()
}
for (const body of [
  new Blob([new Uint8Array(PLUGIN_BRIDGE_MAX_FILE_BYTES + 1)]),
  new Blob(['{"code":401,"msg":"secret token"}'], { type: 'application/json' }),
  { headers: { authorization: 'secret' } },
]) {
  const pair = await setup({ request: async () => body })
  await assert.rejects(pair.child.download({ path: 'report' }), /插件请求失败/)
  assert.equal(JSON.stringify(pair.childWindow.messages).includes('secret'), false)
  pair.destroy()
}
{
  const pair = await setup({
    request: async () => new Blob(['{"report":true}'], { type: 'application/json' }),
  })
  assert.equal(await (await pair.child.download({ path: 'report' })).text(), '{"report":true}')
  pair.destroy()
}

// 超限进度立即取消传输；取消和超时之后，迟到进度及响应均被丢弃。
for (const mode of ['oversize', 'cancel', 'timeout', 'reload']) {
  const delayed = deferred()
  let config
  const events = []
  const pair = await setup({
    transferTimeoutMs: mode === 'timeout' ? 10 : 120000,
    request: (value) => {
      config = value
      return delayed.promise
    },
  })
  const controller = new AbortController()
  const promise = pair.child.download(
    { path: 'report' },
    { signal: controller.signal, onProgress: (event) => events.push(event) }
  )
  const rejected = assert.rejects(promise)
  await flush()
  if (mode === 'oversize') config.onDownloadProgress({ loaded: PLUGIN_BRIDGE_MAX_FILE_BYTES + 1 })
  if (mode === 'cancel') controller.abort()
  if (mode === 'reload') {
    pair.hostWindow.dispatch({
      origin: ORIGIN,
      source: pair.childWindow,
      data: {
        namespace: 'ruoyi.plugin',
        version: 1,
        pluginId: 'demo',
        instance: '',
        type: 'ready',
        payload: { clientId: 'new-file-document' },
      },
    })
    pair.child.destroy()
  }
  await rejected
  await flush()
  assert.equal(config.signal.aborted, true)
  config.onDownloadProgress({ loaded: 3, total: 3 })
  delayed.resolve(new Blob(['old']))
  await flush()
  assert.equal(events.length, 0)
  pair.destroy()
}

// 未公布文件能力的旧宿主立即报兼容错误；握手前调用仍可正常排队。
for (const filesSupported of [false, true]) {
  const pair = windowPair()
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: pair.childWindow,
    parentWindow: pair.hostWindow,
    origin: ORIGIN,
  })
  const pending = child.download({ path: 'report' })
  const clientId = pair.hostWindow.messages[0].payload.clientId
  pair.childWindow.dispatch({
    origin: ORIGIN,
    source: pair.hostWindow,
    data: {
      namespace: 'ruoyi.plugin',
      version: 1,
      pluginId: 'demo',
      type: 'initialize',
      instance: 'host-instance',
      payload: { clientId, ...(filesSupported ? { capabilities: { files: { version: 1 } } } : {}) },
    },
  })
  if (filesSupported) {
    await flush()
    const request = pair.hostWindow.messages.find((message) => message.type === 'download')
    assert.ok(request)
    const rejected = assert.rejects(pending, /关闭/)
    child.destroy()
    await rejected
  } else {
    await assert.rejects(pending, /不支持文件传输/)
    child.destroy()
  }
}

// 实时事件按回调 Promise 确认逐条传递，查询、游标与会话信息只交给宿主适配器。
{
  const gate = deferred()
  const events = []
  let produced = 0
  let config
  const pair = await setup({
    stream: async function* (value) {
      config = value
      for (let i = 1; i <= 3; i++) {
        produced++
        yield { event: 'tick', data: String(i), id: String(i) }
      }
    },
  })
  const result = pair.child.stream(
    { path: 'events', params: { count: 3 }, lastEventId: '0' },
    {
      onEvent: async (event) => {
        events.push(event)
        if (event.id === '1') await gate.promise
      },
    }
  )
  await flush()
  assert.equal(produced, 1)
  assert.equal(events.length, 1)
  assert.equal(config.url, '/apps/demo/api/events')
  assert.deepEqual(config.params, { count: 3 })
  assert.equal(config.lastEventId, '0')
  assert.equal(config.csrfToken, sessionData.csrfToken)
  assert.equal(pair.child.context.capabilities.streams.maxConcurrent, 2)
  const streamMessage = pair.hostWindow.messages.find((message) => message.type === 'stream')
  for (const payload of [{ sequence: 2 }, { sequence: 1, extra: true }]) {
    pair.hostWindow.dispatch({
      origin: ORIGIN,
      source: pair.childWindow,
      data: { ...streamMessage, type: 'stream-ack', payload },
    })
  }
  await flush()
  assert.equal(produced, 1, '无效确认不能提前读取下一条事件')
  gate.resolve()
  assert.equal(await result, undefined)
  await flush()
  assert.deepEqual(
    events.map((event) => event.id),
    ['1', '2', '3']
  )
  assert.equal(config.signal.aborted, true)
  pair.destroy()
}

// 绕过 SDK 直接发送消息仍受宿主路径、字段和连接数校验。
{
  let opened = 0
  const pair = await setup({
    stream: async function* ({ signal }) {
      opened++
      await new Promise((resolve) => signal.addEventListener('abort', resolve, { once: true }))
    },
  })
  const initialize = pair.childWindow.messages.find((message) => message.type === 'initialize')
  const sendStream = (id, payload) =>
    pair.hostWindow.dispatch({
      origin: ORIGIN,
      source: pair.childWindow,
      data: { ...initialize, type: 'stream', id, payload },
    })
  sendStream('malformed-stream', { path: 'events', headers: { Authorization: 'forbidden' } })
  await flush()
  assert.equal(opened, 0)
  assert.equal(pair.childWindow.messages.at(-1).payload.ok, false)
  for (const id of ['stream-one', 'stream-two', 'stream-three']) sendStream(id, { path: 'events' })
  await flush()
  assert.equal(opened, 2)
  assert.match(
    pair.childWindow.messages.find((message) => message.id === 'stream-three').payload.message,
    /连接过多/
  )
  pair.destroy()
}

// 初始化尚未完成时也计入实时连接数；取消排队请求后可重新排队。
{
  const pair = windowPair()
  const child = createPluginClient({
    pluginId: 'demo',
    eventTarget: pair.childWindow,
    parentWindow: pair.hostWindow,
    origin: ORIGIN,
  })
  const controller = new AbortController()
  const first = child.stream({ path: 'events' }, { onEvent() {}, signal: controller.signal })
  const second = child.stream({ path: 'events' }, { onEvent() {} })
  const firstRejected = assert.rejects(first, /取消/)
  const secondRejected = assert.rejects(second, /关闭/)
  await assert.rejects(child.stream({ path: 'events' }, { onEvent() {} }), /连接过多/)
  controller.abort()
  await firstRejected
  const replacement = assert.rejects(child.stream({ path: 'events' }, { onEvent() {} }), /关闭/)
  child.destroy()
  await Promise.all([secondRejected, replacement])
}

// 无能力协商的旧宿主不接收流请求；接口路径、任意请求头与游标注入均被拒绝。
{
  const pair = await setup()
  await assert.rejects(pair.child.stream({ path: 'events' }, { onEvent() {} }), /不支持实时/)
  for (const payload of [
    { path: '../other' },
    { path: 'events', headers: {} },
    { path: 'events', method: 'POST' },
    { path: 'events', lastEventId: 'bad\nvalue' },
  ])
    await assert.rejects(pair.child.stream(payload, { onEvent() {} }))
  await assert.rejects(pair.child.stream({ path: 'events' }), /回调/)
  pair.destroy()
}

// 第三个实时连接被拒绝，普通 JSON 请求仍可进行；取消会关闭底层迭代器。
{
  const controllers = [new AbortController(), new AbortController()]
  let closed = 0
  const pair = await setup({
    stream: async function* ({ signal }) {
      try {
        yield { event: 'tick', data: 'one', id: '1' }
        await new Promise((resolve) => signal.addEventListener('abort', resolve, { once: true }))
      } finally {
        closed++
      }
    },
  })
  const requests = controllers.map((controller) =>
    pair.child.stream({ path: 'events' }, { signal: controller.signal, onEvent() {} })
  )
  const rejected = requests.map((promise) => assert.rejects(promise, /取消/))
  await flush()
  await assert.rejects(pair.child.stream({ path: 'events' }, { onEvent() {} }), /实时连接过多/)
  assert.deepEqual(await pair.child.request({ method: 'GET', path: 'ok' }), {
    code: 200,
    data: 'ok',
  })
  for (const controller of controllers) controller.abort()
  await Promise.all(rejected)
  await flush()
  assert.equal(closed, 2)
  pair.destroy()
}

// 处理失败、超时、页面重载和退出均取消旧流，迟到事件不能更新当前页面。
for (const mode of ['callback', 'timeout', 'reload', 'logout', 'oversize']) {
  const delivered = []
  let signal
  let closed = false
  const pair = await setup({
    streamTimeoutMs: mode === 'timeout' ? 20 : 300000,
    stream: async function* (config) {
      signal = config.signal
      try {
        yield {
          event: 'tick',
          id: '1',
          data: mode === 'oversize' ? 'x'.repeat(PLUGIN_BRIDGE_MAX_BYTES) : 'one',
        }
        if (!signal.aborted)
          await new Promise((resolve) => signal.addEventListener('abort', resolve, { once: true }))
        yield { event: 'tick', id: '2', data: 'late' }
      } finally {
        closed = true
      }
    },
  })
  const request = pair.child.stream(
    { path: 'events' },
    {
      onEvent: (event) => {
        delivered.push(event.id)
        if (mode === 'callback') return Promise.reject(new Error('plugin callback failed'))
      },
    }
  )
  const rejected = assert.rejects(request)
  await flush()
  if (mode === 'logout') pair.host.destroy({ logout: true })
  if (mode === 'reload') {
    pair.hostWindow.dispatch({
      origin: ORIGIN,
      source: pair.childWindow,
      data: {
        namespace: 'ruoyi.plugin',
        version: 1,
        pluginId: 'demo',
        instance: '',
        type: 'ready',
        payload: { clientId: 'new-stream-document' },
      },
    })
    pair.child.destroy()
  }
  await rejected
  await flush()
  assert.equal(signal.aborted, true)
  assert.equal(closed, true)
  assert.deepEqual(delivered, mode === 'oversize' ? [] : ['1'])
  pair.destroy()
}
