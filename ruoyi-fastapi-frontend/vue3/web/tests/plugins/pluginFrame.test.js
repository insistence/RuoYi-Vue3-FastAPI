import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { effectScope, nextTick, reactive, ref, watch } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'

// 使用 Vue 调度器执行组件的真实会话监听逻辑。
// 仅查询参数变化导致 router.meta 重建时，不应重新打开已有页面。
const source = readFileSync(
  new URL('../../src/components/PluginFrame/index.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'plugin-frame-watch-test' })
const sessionWatch = compiled.scriptSetupAst.find(
  (statement) =>
    statement.type === 'ExpressionStatement' &&
    statement.expression.type === 'CallExpression' &&
    statement.expression.callee.name === 'watch'
).expression
const installWatcher = new Function(
  'watch',
  'route',
  'userStore',
  'cleanup',
  'error',
  'active',
  'openPlugin',
  `return ${descriptor.scriptSetup.content.slice(sessionWatch.start, sessionWatch.end)}`
)
const route = reactive({ meta: { pluginId: 'demo' }, query: { pluginRoute: '/' } })
const userStore = reactive({ token: 'host-session' })
const error = ref('')
const cleanupCalls = []
let reopened = 0
const scope = effectScope()
scope.run(() =>
  installWatcher(
    watch,
    route,
    userStore,
    (logout) => cleanupCalls.push(logout),
    error,
    true,
    () => {
      reopened += 1
    }
  )
)

route.meta = { pluginId: 'demo' }
route.query = { pluginRoute: '/details' }
await nextTick()
assert.equal(
  reopened,
  0,
  'same plugin + same token must preserve the frame across query navigation'
)
assert.deepEqual(cleanupCalls, [])

route.meta = { pluginId: 'another_demo' }
await nextTick()
assert.equal(reopened, 1, 'switching plugin must open a new session')
userStore.token = 'new-host-session'
await nextTick()
assert.equal(reopened, 2, 'a changed host login must not reuse the previous plugin session')
userStore.token = ''
await nextTick()
assert.deepEqual(cleanupCalls, [true], 'logout must destroy the bridge and notify the frame')
assert.match(error.value, /登录状态已失效/)
scope.stop()
