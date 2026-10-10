import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import {
  createPluginClient,
  createPluginHostBridge,
  PLUGIN_BRIDGE_SDK_VERSION,
  PLUGIN_BRIDGE_VERSION,
  validatePluginSession,
} from '../../src/utils/pluginBridge.js'
import * as legacySdk from './fixtures/bridge-b0d16a3e/pluginBridge.js'
import { createJsonOnlyHost } from './fixtures/json-only-host.js'

const ORIGIN = 'https://compatibility.test'
const metadata = JSON.parse(
  readFileSync(new URL('../../src/utils/pluginBridge.sdk.json', import.meta.url))
)
const declarations = readFileSync(
  new URL('../../src/utils/pluginBridge.d.ts', import.meta.url),
  'utf8'
)
const sourceCommit = 'b0d16a3eae1979afabb838245c00e1f816aa59e9'
const legacyRoot = new URL('./fixtures/bridge-b0d16a3e/', import.meta.url)
const provenance = JSON.parse(readFileSync(new URL('provenance.json', legacyRoot)))

// 完整快照保留提交中的原始字节，由目录内 .gitattributes 禁止自动换行转换。
assert.equal(provenance.sourceCommit, sourceCommit)
assert.equal(provenance.sourcePath, 'ruoyi-fastapi-frontend/src/utils/pluginBridge.js')
assert.equal(provenance.sdkVersion, null, '该历史快照没有独立 SDK 版本号')
assert.equal(provenance.bridgeVersion, 1)
assert.equal(
  createHash('sha256')
    .update(readFileSync(new URL('pluginBridge.js', legacyRoot)))
    .digest('hex'),
  provenance.sha256
)
assert.equal(Object.hasOwn(legacySdk, 'PLUGIN_BRIDGE_SDK_VERSION'), false)
assert.deepEqual(metadata, {
  schemaVersion: 1,
  sdkVersion: PLUGIN_BRIDGE_SDK_VERSION,
  bridgeVersion: PLUGIN_BRIDGE_VERSION,
  capabilities: { files: 1, streams: 1 },
})
assert.equal(PLUGIN_BRIDGE_SDK_VERSION, '1.0.0')
assert.equal(PLUGIN_BRIDGE_VERSION, 1, '源码交付版本不能改变 bridge v1 消息协议')
assert.ok(declarations.includes(`export const PLUGIN_BRIDGE_SDK_VERSION: '${metadata.sdkVersion}'`))
assert.ok(declarations.includes(`export const PLUGIN_BRIDGE_VERSION: ${metadata.bridgeVersion}`))

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
    target.postMessage = (value, targetOrigin) => {
      assert.equal(targetOrigin, ORIGIN)
      const data = structuredClone(value)
      target.messages.push(data)
      queueMicrotask(() => target.dispatch({ data, source, origin: ORIGIN }))
    }
  }
  return { hostWindow, childWindow }
}

function clientOptions({ hostWindow, childWindow }) {
  return {
    pluginId: 'demo',
    eventTarget: childWindow,
    parentWindow: hostWindow,
    origin: ORIGIN,
    timeoutMs: 1000,
  }
}

// 历史客户端使用固定源码；宿主使用当前源码，实际交换 JSON、Blob 与逐条 SSE 消息。
{
  const pair = windowPair()
  const requests = []
  const streams = []
  const session = validatePluginSession(
    {
      pluginId: 'demo',
      bridgeVersion: 1,
      uiBase: '/apps/demo/ui/',
      apiBase: '/apps/demo/api/',
      csrfToken: 'compatibility-csrf-only',
      expiresIn: 300,
    },
    'demo'
  )
  const host = createPluginHostBridge({
    pluginId: 'demo',
    session,
    getTarget: () => pair.childWindow,
    eventTarget: pair.hostWindow,
    origin: ORIGIN,
    request: async (config) => {
      requests.push(config)
      if (config.responseType === 'blob') return new Blob(['legacy download'])
      if (config.data instanceof FormData) {
        assert.equal(await config.data.get('file').text(), 'legacy upload')
        assert.equal(config.data.get('category'), 'compatibility')
        return { received: config.data.get('file').size }
      }
      return { code: 200, data: config.data }
    },
    stream: async function* (config) {
      streams.push(config)
      yield { event: 'tick', data: 'first', id: '5' }
      yield { event: 'tick', data: 'second', id: '6' }
    },
  })
  const client = legacySdk.createPluginClient(clientOptions(pair))
  try {
    const context = await client.ready
    assert.equal(context.capabilities.files.version, metadata.capabilities.files)
    assert.equal(context.capabilities.streams.version, metadata.capabilities.streams)
    assert.deepEqual(
      await client.request({ method: 'POST', path: 'echo', data: { value: 'legacy' } }),
      {
        code: 200,
        data: { value: 'legacy' },
      }
    )
    assert.deepEqual(
      await client.upload({
        path: 'files/upload',
        file: new Blob(['legacy upload']),
        fields: { category: 'compatibility' },
      }),
      { received: 13 }
    )
    assert.equal(await (await client.download({ path: 'files/report' })).text(), 'legacy download')
    const events = []
    await client.stream(
      { path: 'events', params: { count: 6 }, lastEventId: '4' },
      {
        async onEvent(event) {
          await Promise.resolve()
          events.push(event)
        },
      }
    )
    assert.deepEqual(events, [
      { event: 'tick', data: 'first', id: '5' },
      { event: 'tick', data: 'second', id: '6' },
    ])
    assert.deepEqual(
      requests.map((config) => config.url),
      ['/apps/demo/api/echo', '/apps/demo/api/files/upload', '/apps/demo/api/files/report']
    )
    for (const config of requests) {
      assert.equal(config.headers.isToken, false)
      assert.equal(config.headers.Authorization, undefined)
      assert.equal(config.headers['X-Plugin-CSRF'], session.csrfToken)
    }
    assert.equal(streams.length, 1)
    assert.equal(streams[0].url, '/apps/demo/api/events')
    assert.deepEqual(streams[0].params, { count: 6 })
    assert.equal(streams[0].lastEventId, '4')
    assert.equal(streams[0].csrfToken, session.csrfToken)
    for (const message of [...pair.hostWindow.messages, ...pair.childWindow.messages]) {
      assert.equal(message.version, 1)
      assert.equal(message.sdkVersion, undefined)
      assert.equal(message.payload?.csrfToken, undefined)
    }
  } finally {
    client.destroy()
    host.destroy()
  }
  assert.equal(pair.hostWindow.listeners.size, 0)
  assert.equal(pair.childWindow.listeners.size, 0)
}

// 旧 JSON 协议夹具不公布新增能力；未知版本也必须在客户端拒绝，而非先发送再失败。
for (const capabilities of [
  undefined,
  { files: { version: 2 }, streams: { version: 2 } },
  { files: { version: '1' }, streams: { version: '1' } },
]) {
  const pair = windowPair()
  const host = createJsonOnlyHost({ ...pair, origin: ORIGIN, capabilities })
  const client = createPluginClient(clientOptions(pair))
  try {
    await client.ready
    const payload = { method: 'GET', path: 'info', params: { page: 1 } }
    assert.deepEqual(await client.request(payload), { accepted: payload })
    await assert.rejects(
      client.upload({ path: 'files/upload', file: new Blob(['test']) }),
      /不支持文件传输/
    )
    await assert.rejects(client.download({ path: 'files/report' }), /不支持文件传输/)
    await assert.rejects(client.stream({ path: 'events' }, { onEvent() {} }), /不支持实时事件流/)
    assert.deepEqual(await client.request(payload), { accepted: payload })
    assert.deepEqual(
      host.calls.map((message) => message.type),
      ['request', 'request']
    )
    assert.deepEqual(
      pair.hostWindow.messages.map((message) => message.type),
      ['ready', 'request', 'request']
    )
  } finally {
    client.destroy()
    host.destroy()
  }
  assert.equal(pair.hostWindow.listeners.size, 0)
  assert.equal(pair.childWindow.listeners.size, 0)
}
