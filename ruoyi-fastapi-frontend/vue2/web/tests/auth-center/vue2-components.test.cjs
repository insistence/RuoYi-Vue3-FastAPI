const assert = require('node:assert/strict')
const test = require('node:test')
const path = require('node:path')
const Vue = require('vue')
const Router = require('vue-router')
const { createLoader } = require('../support/load-module.cjs')

const root = path.resolve(__dirname, '../../src')
const settle = async () => {
  await Vue.nextTick()
  await new Promise((resolve) => setImmediate(resolve))
}
const component = (load, file) => load(path.join(root, file)).default
const notices = { msgSuccess() {}, msgError() {}, confirm: async () => {} }
Vue.use(Router)

// 直接实例化 Vue 2.7 组件，验证迁移后真实的 value/input、响应式与路由行为。
test('URI 列表使用 Vue 2 input 事件更新父表单，删除最后一行保留输入位置', async () => {
  const vm = new Vue({
    ...component(createLoader(), 'components/OAuthWorkspace/StringListInput.vue'),
    propsData: { value: ['https://one.example/cb'] },
  })
  const state = vm._setupProxy
  const values = []
  vm.$on('input', (value) => values.push(value))
  state.localItems = [' https://two.example/cb ', ' ']
  state.emitValue()
  assert.deepEqual(values[0], ['https://two.example/cb'])
  state.remove(1)
  state.remove(0)
  assert.deepEqual(values.at(-1), [])
  assert.deepEqual(Array.from(state.localItems), [''])
  vm.value = ['https://new.example/cb']
  await settle()
  assert.equal(state.localItems[0], 'https://new.example/cb')
  vm.$destroy()
})

test('密钥弹窗关闭通过 input 同步，重新打开必须重新确认已保存', async () => {
  const load = createLoader({ '@/components/OAuthWorkspace/FieldLabel.vue': {} })
  const vm = new Vue({
    ...component(load, 'views/system/oauth/client/secret.vue'),
    propsData: { value: true, secret: {} },
  })
  const state = vm._setupProxy
  const emitted = []
  vm.$on('input', (value) => emitted.push(value))
  state.confirmed = true
  state.close()
  assert.deepEqual(emitted, [false])
  vm.value = false
  await settle()
  vm.value = true
  await settle()
  assert.equal(state.confirmed, false)
  vm.$destroy()
})

test('独立访问策略可在首次授权前创建，关闭弹层会通知父组件', async () => {
  const calls = []
  const load = createLoader({
    '@/api/system/oauthSession': {
      listOAuthAccessPolicies: async () => ({ rows: [], total: 0 }),
      setOAuthClientAccess: async (...args) => {
        calls.push(args)
      },
    },
  })
  const vm = new Vue({
    ...component(load, 'views/system/oauth/grant/AccessPolicyDrawer.vue'),
    propsData: { value: true },
    beforeCreate() {
      this.$modal = notices
    },
  })
  const state = vm._setupProxy
  vm.$refs.accessRef = { clearValidate() {}, validate: async () => true }
  let changes = 0
  vm.$on('changed', () => {
    changes++
  })
  state.openAccess()
  state.accessForm.userId = ' 42 '
  state.accessForm.clientId = ' demo-client '
  state.accessForm.reason = ' 验证首次访问控制 '
  await state.saveAccess()
  assert.deepEqual(calls, [['42', 'demo-client', { blocked: true, reason: '验证首次访问控制' }]])
  assert.equal(changes, 1)
  assert.equal(state.accessOpen, false)
  const visibility = []
  vm.$on('input', (value) => visibility.push(value))
  state.visible = false
  assert.deepEqual(visibility, [false])
  vm.$destroy()
})

test('撤销已过期会话仍提交精确 sid 和原因', async () => {
  const calls = []
  const load = createLoader({
    '@/components/OAuthWorkspace/PageFrame.vue': {},
    '@/api/system/oauthSession': {
      listOAuthSessions: async () => ({ rows: [], total: 0 }),
      revokeOAuthSessions: async (...args) => {
        calls.push(args)
      },
    },
  })
  const vm = new Vue({
    ...component(load, 'views/system/oauth/session/index.vue'),
    beforeCreate() {
      this.$modal = notices
    },
  })
  const state = vm._setupProxy
  assert.equal(vm.$options.name, 'OAuthSession')
  state.openRevoke({ sid: 'expired-sid', status: 'expired' })
  state.reason = ' 结束离线访问 '
  await state.revoke()
  assert.deepEqual(calls, [['expired-sid', { reason: '结束离线访问' }]])
  assert.equal(state.revokeOpen, false)
  vm.$destroy()
})

test('认证交互恢复已完成流程，失败保留凭据并拒绝非当前交互的完成地址', async () => {
  const completed = [],
    assigned = [],
    replaced = []
  const storage = new Map()
  let completionError = new Error('完成认证暂时失败')
  const load = createLoader(
    {
      '@/api/authCenter': {
        completeInteraction: async (...args) => {
          completed.push(args)
          if (completionError) throw completionError
          return { data: { redirectUrl: 'https://app.example/callback?code=opaque' } }
        },
      },
    },
    {
      sessionStorage: {
        getItem: (key) => storage.get(key),
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key),
      },
      window: {
        location: {
          hash: '#csrf=csrf-1',
          origin: 'https://issuer.example',
          assign: (url) => assigned.push(url),
        },
        history: { state: {}, replaceState: (...args) => replaced.push(args) },
      },
    }
  )
  const router = new Router({ mode: 'abstract', routes: [{ path: '/auth-center/login' }] })
  await router.push('/auth-center/login?interaction=one')
  const useContext = load(
    path.join(root, 'views/auth-center/useInteraction.js')
  ).useInteractionContext
  const vm = new Vue({ router, setup: () => useContext() })
  assert.equal(vm.interactionId, 'one')
  assert.equal(vm.csrfToken(), 'csrf-1')
  assert.equal(replaced[0][2], '/auth-center/login?interaction=one')
  await assert.rejects(vm.followServerRedirect('/auth/interaction/other/complete'))
  assert.equal(completed.length, 0)
  await assert.rejects(vm.goToAction('redirect'), /完成认证暂时失败/)
  assert.equal(vm.csrfToken(), 'csrf-1')
  assert.equal(assigned.length, 0)
  completionError = null
  await vm.goToAction('redirect')
  assert.deepEqual(completed, [
    ['one', 'csrf-1'],
    ['one', 'csrf-1'],
  ])
  assert.equal(assigned.length, 1)
  assert.equal(vm.csrfToken(), '')
  await router.replace('/auth-center/login?interaction=two')
  await settle()
  assert.equal(vm.interactionId, 'two')
  vm.$destroy()
})

test('服务应用切换用户登录方式时同步保存所需响应类型', async () => {
  const load = createLoader({
    '@/api/system/oauthClient': {
      listOAuthClients: async () => ({ rows: [], total: 0 }),
    },
    '@/api/system/oauthResource': {
      listOAuthScopes: async () => ({ rows: [] }),
      listOAuthResources: async () => ({ rows: [] }),
    },
    '@/components/OAuthWorkspace/AccessMap.vue': {},
    '@/components/OAuthWorkspace/FieldLabel.vue': {},
    '@/components/OAuthWorkspace/PageFrame.vue': {},
    '@/components/OAuthWorkspace/StringListInput.vue': {},
    './secret.vue': {},
  })
  const vm = new Vue({ ...component(load, 'views/system/oauth/client/index.vue') })
  try {
    const state = vm._setupProxy
    Object.assign(
      state.form,
      state.toEditor({
        clientId: 'machine-client',
        clientName: '服务应用',
        clientType: 'confidential',
        tokenEndpointAuthMethod: 'client_secret_basic',
        grantTypes: ['client_credentials'],
        responseTypes: [],
        scopeCodes: ['openid'],
      })
    )
    state.form.grantTypes.push('authorization_code')
    state.form.redirectUris = ['https://app.example/callback']
    await settle()
    const withLogin = state.payload()
    assert.deepEqual(withLogin.responseTypes, ['code'])
    assert.deepEqual(withLogin.grantTypes, ['client_credentials', 'authorization_code'])
    assert.deepEqual(withLogin.redirectUris, ['https://app.example/callback'])
    Object.assign(state.form, state.toEditor(withLogin))
    state.form.grantTypes = ['client_credentials']
    await settle()
    assert.deepEqual(state.payload().responseTypes, [])
    state.form.grantTypes = ['authorization_code', 'refresh_token']
    await settle()
    assert.deepEqual(state.payload().responseTypes, ['code'])
  } finally {
    vm.$destroy()
  }
})

test('Vue 2 密码规则保留原有 mixin，同时向认证页提供相同校验', () => {
  const load = createLoader({ '@/plugins/cache': { session: { get: () => '3' } } })
  const rule = load(path.join(root, 'utils/passwordRule.js'))
  const state = rule.usePasswordRule()
  assert.equal(state.pwdChrType.value, '3')
  const mixin = new Vue(rule.default)
  assert.equal(
    state.infoPwdValidator.value[2].pattern.source,
    mixin.infoPwdValidator[2].pattern.source
  )
  assert.equal(state.infoPwdValidator.value[2].pattern.test('onlyletters'), false)
  assert.equal(state.infoPwdValidator.value[2].pattern.test('valid123'), true)
  mixin.$destroy()
})
