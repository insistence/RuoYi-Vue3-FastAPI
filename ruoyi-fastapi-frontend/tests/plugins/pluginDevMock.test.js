import assert from 'node:assert/strict'
import { createMockPluginRequest } from '../../../ruoyi-fastapi-backend/plugins/examples/python/bundle_demo/web/dev/mockRequest.js'

const request = createMockPluginRequest({ getDelay: () => 0 })
const config = (path, options = {}) => ({
  url: '/apps/bundle_demo/api/' + path,
  method: 'get',
  ...options,
})
assert.equal((await request(config('summary'))).userName, '本地模拟用户')
assert.equal(
  (await request(config('echo', { method: 'post', data: { message: 'test' } }))).message,
  'test'
)
const form = new FormData()
form.append('file', new Blob(['test']), 'test.txt')
const events = []
const file = await request(
  config('files/inspect', {
    method: 'post',
    data: form,
    onUploadProgress: (event) => events.push(event),
  })
)
assert.deepEqual(file, {
  filename: 'test.txt',
  size: 4,
  sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
})
assert.deepEqual(
  events.map((event) => event.loaded),
  [2, 4]
)
const report = await request(config('files/report'))
assert.match(await report.text(), /local-mock/)
await assert.rejects(request(config('unknown')), /未实现/)
await assert.rejects(request({ url: 'https://outside.test', method: 'get' }), /当前插件/)
const fail = createMockPluginRequest({ getDelay: () => 0, shouldFail: () => true })
await assert.rejects(fail(config('summary')), /模拟接口失败/)
const controller = new AbortController()
const slow = createMockPluginRequest({ getDelay: () => 5000 })
const pending = slow(config('summary', { signal: controller.signal }))
const rejected = assert.rejects(pending, /取消/)
controller.abort()
await rejected
await assert.rejects(slow(config('summary', { signal: controller.signal })), /取消/)
