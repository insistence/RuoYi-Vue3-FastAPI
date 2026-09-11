import assert from 'node:assert/strict'
import test from 'node:test'
import { buildJobPayload, parseJobParameter } from '../../src/views/monitor/job/jobForm.js'

test('JSON参数保持嵌套值类型和字符串内逗号，提交时转换为数组和对象', () => {
  const form = {
    jobArgs: '["tenant,a", 3, true, {"nested": [null, 2]}]',
    jobKwargs: '{"enabled": false, "limit": 30}',
    misfireGraceTime: null,
    coalesce: true,
    maxInstances: 2,
    jobGroup: '报表',
    jobStore: 'redis'
  }
  const payload = buildJobPayload(form)
  assert.deepEqual(payload.jobArgs, ['tenant,a', 3, true, { nested: [null, 2] }])
  assert.deepEqual(payload.jobKwargs, { enabled: false, limit: 30 })
  assert.equal(payload.misfireGraceTime, null)
  assert.equal(payload.jobGroup, '报表')
  assert.equal(payload.jobStore, 'redis')
  assert.equal(typeof form.jobArgs, 'string')
})

test('无参数使用空数组和空对象', () => {
  assert.deepEqual(buildJobPayload({ jobArgs: '[]', jobKwargs: '{}' }), { jobArgs: [], jobKwargs: {} })
})

test('错误的JSON格式和参数结构返回对应字段提示', () => {
  for (const value of ['', 'a,b', '{broken', '{}', 'true', 'null']) {
    assert.throws(() => parseJobParameter(value, 'jobArgs'), /位置参数必须是JSON数组/)
  }
  for (const value of ['', '[1]', 'true', 'null', '{broken']) {
    assert.throws(() => parseJobParameter(value, 'jobKwargs'), /关键字参数必须是JSON对象/)
  }
  assert.throws(() => parseJobParameter('[1e999]', 'jobArgs'), /数字超出可表示范围/)
})
