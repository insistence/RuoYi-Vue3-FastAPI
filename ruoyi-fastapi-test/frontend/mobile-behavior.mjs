import assert from 'node:assert/strict'
import test from 'node:test'
import { createMobileHarness, settle, snapshot } from './mobile-harness.mjs'

export function testMobileBehavior(root, framework) {
  test('requests use the current token and timezone while public requests omit credentials', async () => {
    const app = await createMobileHarness(root, framework, { token: 'active-token' })
    app.time.setUserTimezone('America/New_York')
    assert.equal(
      (await app.request({ url: '/private', params: { name: 'a b', page: 2 } })).code,
      200
    )
    const privateRequest = app.calls.requests[0]
    assert.equal(privateRequest.header.Authorization, 'Bearer active-token')
    assert.equal(privateRequest.header['X-Timezone'], 'America/New_York')
    assert.equal(privateRequest.url, 'https://api.example.test/private?name=a%20b&page=2')
    app.auth.setToken('rotated-token')
    await app.request({ url: '/private' })
    assert.equal(app.calls.requests[1].header.Authorization, 'Bearer rotated-token')
    await app.request({
      url: '/public',
      headers: { isToken: false },
      header: { 'X-Timezone': 'UTC' },
    })
    assert.equal(app.calls.requests[2].header.Authorization, undefined)
    assert.equal(app.calls.requests[2].header['X-Timezone'], 'UTC')
  })

  test('confirmed expired sessions reject the request, clear account state and relaunch login', async () => {
    const app = await createMobileHarness(root, framework, { token: 'expired-token' })
    await app.getInfo()
    app.responses.push({ statusCode: 200, data: { code: 401, msg: 'expired' } })
    await assert.rejects(
      app.request({ url: '/private' }),
      (error) => error.response.data.code === 401
    )
    await settle()
    assert.deepEqual(app.calls.logout, ['expired-token'])
    assert.equal(app.auth.getToken(), undefined)
    assert.equal(app.state.token, '')
    assert.deepEqual(snapshot(app.state.roles), [])
    assert.deepEqual(snapshot(app.state.permissions), [])
    assert.equal(app.time.getUserTimezone(), 'auto')
    assert.equal(app.values.has('storage_data'), false)
    assert.deepEqual(app.calls.navigations, [{ url: '/pages/login' }])
  })

  test('declining the expired-session dialog leaves the current account and page intact', async () => {
    const app = await createMobileHarness(root, framework, {
      token: 'expired-token',
      confirm: false,
    })
    app.responses.push({ statusCode: 200, data: { code: 401, msg: 'expired' } })
    await assert.rejects(app.request({ url: '/private' }))
    await settle()
    assert.equal(app.auth.getToken(), 'expired-token')
    assert.deepEqual(app.calls.logout, [])
    assert.deepEqual(app.calls.navigations, [])
  })

  test('login persists the token, profile restores permissions, and logout clears only account data', async () => {
    const app = await createMobileHarness(root, framework)
    await app.login({
      username: ' tester ',
      password: 'password',
      code: '1234',
      uuid: 'captcha-id',
    })
    assert.deepEqual(snapshot(app.calls.login), [['tester', 'password', '1234', 'captcha-id']])
    assert.equal(app.auth.getToken(), 'fresh-token')
    assert.equal(app.state.token, 'fresh-token')
    await app.getInfo()
    assert.equal(app.state.id, 7)
    assert.deepEqual(snapshot(app.state.permissions), ['system:user:query'])
    assert.equal(app.time.getDisplayTimezone(), 'America/New_York')
    assert.deepEqual(app.values.get('storage_data').timezone, {
      appTimezone: 'Asia/Shanghai',
      timeZone: 'America/New_York',
    })
    await app.logout()
    assert.deepEqual(app.calls.logout, ['fresh-token'])
    assert.equal(app.values.has('App-Token'), false)
    assert.equal(app.values.has('storage_data'), false)
    assert.equal(app.values.get('device-theme'), 'dark')
  })

  test('every navigation API blocks private pages without a token and permits public query strings', async () => {
    const app = await createMobileHarness(root, framework)
    assert.deepEqual(
      [...app.interceptors.keys()],
      ['navigateTo', 'redirectTo', 'reLaunch', 'switchTab']
    )
    for (const interceptor of app.interceptors.values()) {
      assert.equal(interceptor.invoke({ url: '/pages/mine/index?tab=profile' }), false)
      assert.equal(app.calls.navigations.at(-1).url, '/pages/login')
      assert.equal(interceptor.invoke({ url: '/pages/login?redirect=profile' }), true)
      assert.equal(interceptor.invoke({ url: '/pages/common/privacy/index?source=login' }), true)
    }
    app.auth.setToken('active-token')
    for (const interceptor of app.interceptors.values()) {
      assert.equal(interceptor.invoke({ url: '/pages/mine/index' }), true)
      for (const url of ['/pages/login', '/pages/login?redirect=profile']) {
        assert.equal(interceptor.invoke({ url }), false)
        assert.equal(app.calls.navigations.at(-1).url, '/')
      }
    }
  })

  test('cold start restores only signed-in timezones and discards invalid preferences', async () => {
    const savedTimezone = { appTimezone: 'Asia/Shanghai', timeZone: 'America/New_York' }
    const signedIn = await createMobileHarness(root, framework, {
      token: 'active-token',
      savedTimezone,
    })
    assert.equal(signedIn.time.getUserTimezone(), 'America/New_York')
    assert.equal(signedIn.time.formatBusinessTime('2026-01-01T00:00:00Z'), '2025-12-31 19:00:00')
    const signedOut = await createMobileHarness(root, framework, { savedTimezone })
    assert.equal(signedOut.time.getUserTimezone(), 'auto')
    const invalid = await createMobileHarness(root, framework, {
      token: 'active-token',
      savedTimezone: { appTimezone: 'Asia/Shanghai', timeZone: 'Invalid/Zone' },
    })
    assert.equal(invalid.time.getUserTimezone(), 'auto')
    assert.equal(invalid.values.get('storage_data').timezone, undefined)
  })

  test('non-authentication failures stay rejected without clearing the account', async () => {
    const app = await createMobileHarness(root, framework, { token: 'active-token' })
    app.responses.push({ statusCode: 429, data: { code: 429, msg: 'rate limited' } })
    await assert.rejects(
      app.request({ url: '/private' }),
      (error) => error.response.statusCode === 429
    )
    assert.equal(app.calls.toasts.at(-1).duration, 5000)
    assert.equal(app.auth.getToken(), 'active-token')
    assert.deepEqual(app.calls.logout, [])
    app.responses.push({ failure: new Error('Network Error') })
    await assert.rejects(app.request({ url: '/private' }), /Network Error/)
    assert.equal(app.calls.toasts.at(-1).title, '后端接口连接异常')
  })
}
