const assert = require('node:assert/strict')
const test = require('node:test')
const path = require('node:path')
const { loadModule } = require('../support/load-module.cjs')
const { checkAuthCenterAccess } = loadModule(
  path.resolve(__dirname, '../../src/utils/authCenterAccess.js')
)

test('公共认证页面按最新开关准入，故障拒绝进入且错误页保持可访问', async () => {
  const route = {
    path: '/auth-center/login',
    meta: { requiresAuthCenter: true },
    query: { interaction: 'private-interaction' },
    hash: '#csrf=private-csrf',
  }
  let enabled = true
  let calls = 0
  const loadStatus = async () => {
    calls++
    return { data: { enabled } }
  }
  assert.equal(await checkAuthCenterAccess(route, loadStatus), undefined)
  enabled = false
  assert.deepEqual(await checkAuthCenterAccess(route, loadStatus), {
    path: '/auth-center/error',
    query: { reason: 'disabled' },
    replace: true,
  })
  enabled = true
  assert.equal(await checkAuthCenterAccess(route, loadStatus), undefined)
  assert.equal(calls, 3, '每次进入都检查开关，不沿用上次结果')

  for (const path of ['/auth-center/error', '/login', '/system/user']) {
    assert.equal(await checkAuthCenterAccess({ path, meta: {} }, loadStatus), undefined)
  }
  assert.equal(calls, 3, '错误说明页与普通页面不请求认证状态')

  const unavailable = {
    path: '/auth-center/error',
    query: { reason: 'unavailable' },
    replace: true,
  }
  for (const response of [{}, { data: {} }, { data: { enabled: 'false' } }, null]) {
    assert.deepEqual(await checkAuthCenterAccess(route, async () => response), unavailable)
  }
  assert.deepEqual(
    await checkAuthCenterAccess(route, async () => {
      throw new Error('network unavailable')
    }),
    unavailable
  )
})
