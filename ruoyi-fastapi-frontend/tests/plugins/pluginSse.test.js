import assert from 'node:assert/strict'
import { readPluginSse, createPluginSseTransport } from '../../src/utils/pluginSse.js'
import {
  PLUGIN_BRIDGE_MAX_BYTES,
  PLUGIN_BRIDGE_MAX_STREAM_BYTES,
} from '../../src/utils/pluginBridge.js'

const encoder = new TextEncoder()
const collect = async (source) => {
  const output = []
  for await (const event of source) output.push(event)
  return output
}
const chunks = (values, onCancel = () => {}) =>
  new ReadableStream({
    start(controller) {
      for (const value of values) controller.enqueue(value)
      controller.close()
    },
    cancel: onCancel,
  })
const input =
  '\uFEFF: heartbeat\r\nid: 1\r\nevent: tick\r\ndata: 你好😀\r\ndata: second\r\n\r\n' +
  'id: ignored\0id\ndata:\n\n' +
  'id:\revent:\rdata: reset\r\r' +
  'data: unfinished'
const bytes = encoder.encode(input)
const expected = [
  { id: '1', event: 'tick', data: '你好😀\nsecond' },
  { id: '1', event: 'message', data: '' },
  { id: '', event: 'message', data: 'reset' },
]
for (const size of [1, 2, 7, bytes.length]) {
  const split = []
  for (let offset = 0; offset < bytes.length; offset += size)
    split.push(bytes.slice(offset, offset + size))
  assert.deepEqual(await collect(readPluginSse(chunks(split))), expected)
}
await assert.rejects(collect(readPluginSse(chunks([new Uint8Array([0xff])]))))
await assert.rejects(collect(readPluginSse(chunks([new Uint8Array([0xe4, 0xb8])]))))
await assert.rejects(
  collect(readPluginSse(chunks([encoder.encode('data: ' + 'a'.repeat(PLUGIN_BRIDGE_MAX_BYTES))]))),
  /64 KiB/
)
await assert.rejects(
  collect(readPluginSse(chunks([encoder.encode('data: a\n'.repeat(9000))]))),
  /64 KiB/
)
await assert.rejects(
  collect(readPluginSse(chunks([new Uint8Array(PLUGIN_BRIDGE_MAX_STREAM_BYTES + 1)]))),
  /10 MiB/
)
let cancelled = false
const infinite = new ReadableStream({
  start(controller) {
    controller.enqueue(encoder.encode('data: one\n\ndata: two\n\n'))
  },
  cancel() {
    cancelled = true
  },
})
for await (const event of readPluginSse(infinite)) {
  assert.equal(event.data, 'one')
  break
}
assert.equal(cancelled, true)
assert.equal(infinite.locked, false)

// 读取中断不能伪装成正常 EOF；异常结束仍释放字节流锁。
let interrupt
const brokenBody = new ReadableStream({
  start(controller) {
    interrupt = () => controller.error(new Error('network disconnected'))
    controller.enqueue(encoder.encode('data: first\n\n'))
  },
})
const brokenStream = readPluginSse(brokenBody)
assert.equal((await brokenStream.next()).value.data, 'first')
interrupt()
await assert.rejects(brokenStream.next(), /network disconnected/)
assert.equal(brokenBody.locked, false)

let fetched = []
let encrypted = false
let response = () =>
  new Response('id: 5\ndata: result\n\n', {
    headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
  })
const stream = createPluginSseTransport({
  loadPolicy: async () => ({ active: encrypted }),
  shouldEncryptRequest: (_, policy) => policy.active,
  serializeParams: (params) => new URLSearchParams(params).toString(),
  getTimezone: () => 'Asia/Shanghai',
  origin: 'https://test',
  fetchImpl: async (...args) => {
    fetched.push(args)
    return response()
  },
})
const config = {
  url: '/prefix/apps/demo/api/events',
  params: { count: 5 },
  lastEventId: '4',
  csrfToken: 'host-only',
  signal: new AbortController().signal,
}
assert.deepEqual(await collect(stream(config)), [{ id: '5', event: 'message', data: 'result' }])
assert.equal(fetched[0][0], 'https://test/prefix/apps/demo/api/events?count=5')
assert.deepEqual(fetched[0][1].headers, {
  Accept: 'text/event-stream',
  'X-Plugin-CSRF': 'host-only',
  'X-Timezone': 'Asia/Shanghai',
  'Last-Event-ID': '4',
})
assert.equal(fetched[0][1].credentials, 'same-origin')
assert.equal(fetched[0][1].redirect, 'error')
encrypted = true
await assert.rejects(collect(stream(config)), /策略例外/)
assert.equal(fetched.length, 1)
encrypted = false
for (const url of [
  'https://evil.test/api',
  '//evil.test/api',
  '/apps/demo/api?x=1',
  '/apps/demo/api#x',
])
  await assert.rejects(collect(stream({ ...config, url })), /地址无效/)
const aborted = new AbortController()
aborted.abort()
await assert.rejects(collect(stream({ ...config, signal: aborted.signal })), /取消/)
assert.equal(fetched.length, 1)
for (const value of [
  new Response('{}', { headers: { 'Content-Type': 'application/json' } }),
  new Response('error', { status: 401 }),
  new Response(null, { status: 204 }),
]) {
  response = () => value
  await assert.rejects(collect(stream(config)), /响应无效/)
}

// 宿主保留的关闭事件必须转换为失败，不能交给业务或当作正常 EOF。
response = () =>
  new Response(
    'id: 1\ndata: first\n\nevent: ruoyi.plugin.closed\ndata: {"code":403,"reason":"access_revoked"}\n\n',
    {
      headers: { 'Content-Type': 'text/event-stream' },
    }
  )
const revoked = stream(config)
assert.equal((await revoked.next()).value.data, 'first')
await assert.rejects(revoked.next(), (error) => error.name === 'PluginStreamClosedError')
for (const partial of [
  'data: unfinished\n',
  'data: unfinished\r',
  'data: unfinished\n\nevent: custom\ndata: partial\n',
]) {
  response = () =>
    new Response(partial + 'event: ruoyi.plugin.closed\ndata: {"code":403}\n\n', {
      headers: { 'Content-Type': 'text/event-stream' },
    })
  const values = []
  await assert.rejects(
    async () => {
      for await (const event of stream(config)) values.push(event.data)
    },
    (error) => error.name === 'PluginStreamClosedError'
  )
  assert.deepEqual(values, partial.includes('\n\n') ? ['unfinished'] : [])
}
