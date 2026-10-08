import assert from 'node:assert/strict'
import test from 'node:test'
import { createMockTaskApi } from '../dev/mockRequest.js'

const draft = {
  title: '测试任务',
  description: '保留完整说明',
  status: 'todo',
  priority: 'normal',
}
const call = (api, method, path, extra = {}) =>
  api.request({
    method,
    url: `/apps/task_demo/api/${path}`,
    ...extra,
  })

test('内存数据支持分页、筛选、完整 CRUD 和响应副本隔离', async () => {
  const api = createMockTaskApi({ getDelay: () => 0 })
  const first = await call(api, 'get', 'tasks', {
    params: { page: 1, pageSize: 10 },
  })
  const second = await call(api, 'get', 'tasks', {
    params: { page: 2, pageSize: 10 },
  })
  assert.equal(first.total, 12)
  assert.equal(first.items.length, 10)
  assert.equal(second.items.length, 2)
  assert.equal(new Set([...first.items, ...second.items].map((task) => task.id)).size, 12)
  const created = await call(api, 'post', 'tasks', { data: draft })
  assert.equal(created.title, draft.title)
  created.title = '修改响应不能污染存储'
  assert.equal((await call(api, 'get', `tasks/${created.id}`)).title, draft.title)
  const updated = await call(api, 'put', `tasks/${created.id}`, {
    data: { ...draft, status: 'done', priority: 'high' },
  })
  assert.equal(updated.createdAt, created.createdAt)
  const done = await call(api, 'get', 'tasks', { params: { status: 'done' } })
  assert.ok(done.items.every((task) => task.status === 'done'))
  assert.ok(done.items.some((task) => task.id === created.id && task.priority === 'high'))
  assert.deepEqual(await call(api, 'delete', `tasks/${created.id}`), {
    deleted: true,
  })
  await assert.rejects(call(api, 'get', `tasks/${created.id}`), /不存在/)
})

test('只读权限在请求层拒绝所有写操作并保留数据', async () => {
  let writable = true
  const api = createMockTaskApi({
    getDelay: () => 0,
    getCanWrite: () => writable,
  })
  const task = await call(api, 'post', 'tasks', { data: draft })
  writable = false
  assert.equal((await call(api, 'get', 'info')).canWrite, false)
  assert.equal((await call(api, 'get', 'tasks')).canWrite, false)
  for (const [method, path] of [
    ['post', 'tasks'],
    ['put', `tasks/${task.id}`],
    ['delete', `tasks/${task.id}`],
  ]) {
    await assert.rejects(call(api, method, path, { data: draft }), /写入权限/)
  }
  assert.equal((await call(api, 'get', 'tasks')).total, 13)
  assert.equal((await call(api, 'get', `tasks/${task.id}`)).title, draft.title)
})

test('失败、取消及无效输入不会产生写入副作用', async () => {
  let fail = true
  const api = createMockTaskApi({ getDelay: () => 10, shouldFail: () => fail })
  await assert.rejects(call(api, 'post', 'tasks', { data: draft }), /模拟请求失败/)
  fail = false
  const controller = new AbortController()
  const pending = call(api, 'post', 'tasks', {
    data: draft,
    signal: controller.signal,
  })
  controller.abort()
  await assert.rejects(pending, /取消/)
  for (const data of [
    { ...draft, title: ' ' },
    { ...draft, description: 'x'.repeat(501) },
    { ...draft, status: 'invalid' },
  ]) {
    await assert.rejects(call(api, 'post', 'tasks', { data }))
  }
  assert.equal((await call(api, 'get', 'tasks')).total, 12)
  api.clear()
  assert.equal((await call(api, 'get', 'tasks')).total, 0)
  api.reset()
  assert.equal((await call(api, 'get', 'tasks')).total, 12)
})
