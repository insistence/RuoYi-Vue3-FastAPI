import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileFunction } from 'node:vm'
import { computed, reactive } from 'vue'
import { babelParse } from 'vue/compiler-sfc'
import * as interactionSecurity from '../../src/views/auth-center/interactionSecurity.js'

// 只隔离请求和浏览器资源，执行真实交互上下文；Vue 的响应式计算保持不变。
const source = readFileSync(
  new URL('../../src/views/auth-center/useInteraction.js', import.meta.url),
  'utf8'
)
const code = babelParse(source, { sourceType: 'module' })
  .program.body.filter((node) => node.type !== 'ImportDeclaration')
  .map((node) => {
    const declaration = node.type === 'ExportNamedDeclaration' ? node.declaration : node
    return source.slice(declaration.start, declaration.end)
  })
  .join('\n')

function createContext(completeInteraction) {
  const storage = new Map()
  const navigations = []
  const redirects = []
  const route = reactive({ path: '/auth-center/consent', query: { interaction: 'pending-1' } })
  const bindings = {
    ...interactionSecurity,
    completeInteraction,
    computed,
    useRoute: () => route,
    useRouter: () => ({ replace: async (location) => navigations.push(location) }),
    sessionStorage: {
      getItem: (key) => storage.get(key),
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    window: {
      location: {
        hash: '#csrf=csrf-1',
        origin: 'https://issuer.example',
        assign: (url) => redirects.push(url),
      },
      history: { state: {}, replaceState() {} },
    },
  }
  const context = compileFunction(
    `${code}\nreturn useInteractionContext();`,
    Object.keys(bindings)
  )(...Object.values(bindings))
  return { context, navigations, redirects }
}

const completed = []
const { context, navigations, redirects } = createContext(async (...args) => {
  completed.push(args)
  return { data: { redirectUrl: 'https://app.example/callback?code=opaque' } }
})
await context.goToAction('login')
assert.deepEqual(navigations, [{ path: '/auth-center/login', query: { interaction: 'pending-1' } }])
await assert.rejects(context.followServerRedirect('/auth/interaction/another/complete'))
assert.equal(completed.length, 0)
await context.goToAction('redirect')
assert.deepEqual(completed, [['pending-1', 'csrf-1']])
assert.deepEqual(redirects, ['https://app.example/callback?code=opaque'])
assert.equal(context.csrfToken(), '')

const failed = createContext(async () => {
  throw new Error('completion unavailable')
})
await assert.rejects(failed.context.goToAction('redirect'), /completion unavailable/)
assert.equal(failed.context.csrfToken(), 'csrf-1')
assert.deepEqual(failed.redirects, [])
