import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

const source = readFileSync(
  new URL('../../src/views/system/plugin/components/PluginConfigStatus.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const compiled = compileScript(descriptor, { id: 'config-status-test' })
const script = compiled.scriptSetupAst
  .filter((statement) => statement.type !== 'ImportDeclaration')
  .map((statement) => descriptor.scriptSetup.content.slice(statement.start, statement.end))
  .join('\n')
const setup = new Function(
  'computed',
  'ref',
  'watch',
  'onBeforeUnmount',
  'defineProps',
  'getPluginConfigStatus',
  `${script}\nreturn { data, loading, error, refresh, statusText }`
)
const props = reactive({ pluginId: 'first_plugin', refreshKey: 0 })
const calls = []
let unmount
const scope = effectScope()
const state = scope.run(() =>
  setup(
    computed,
    ref,
    watch,
    (callback) => {
      unmount = callback
    },
    () => props,
    (pluginId, signal) =>
      new Promise((resolve, reject) => {
        calls.push({ pluginId, signal, resolve, reject })
      })
  )
)
assert.equal(calls[0].pluginId, 'first_plugin')
props.pluginId = 'second_plugin'
await nextTick()
assert.equal(calls[0].signal.aborted, true)
calls[1].resolve({ data: { state: 'restart_required', pendingWorkers: 2 } })
await nextTick()
calls[0].resolve({ data: { state: 'observed_match', matchedWorkers: 1 } })
await nextTick()
assert.match(state.statusText.value, /2 个已观测进程.*待重启/)

// 保存成功后主动重查，不用旧状态冒充最新保存版本。
props.refreshKey++
await nextTick()
assert.equal(state.data.value, null)
calls[2].resolve({ data: { state: 'observed_match', matchedWorkers: 2 } })
await nextTick()
assert.match(state.statusText.value, /已观测进程.*匹配/)
assert.equal(state.loading.value, false)
const failed = state.refresh()
calls[3].reject(new Error('unavailable'))
await failed
assert.equal(state.data.value, null)
assert.match(state.error.value, /查询失败/)
const retry = state.refresh()
calls[4].resolve({ data: { state: 'unobserved' } })
await retry
assert.match(state.statusText.value, /尚不能确认|尚未观测/)
const closing = state.refresh()
unmount()
scope.stop()
assert.equal(calls[5].signal.aborted, true)
calls[5].reject(new Error('cancelled'))
await closing
assert.equal(state.error.value, '')
