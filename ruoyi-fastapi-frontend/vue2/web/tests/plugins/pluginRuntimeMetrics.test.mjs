import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

// 执行组件的真实监听与请求逻辑，只替换网络边界和卸载钩子。
const source = readFileSync(
  new URL('../../src/views/system/plugin/components/PluginRuntimeMetrics.vue', import.meta.url),
  'utf8'
)
const descriptor = parse({ source, filename: 'PluginComponent.vue' })
const compiled = compileScript(descriptor, { id: 'plugin-runtime-metrics-test' })
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
  'getPluginRuntimeMetrics',
  `${script}\nreturn { data, loading, error, refresh }`
)
const props = reactive({ pluginId: 'first_plugin' })
const requests = []
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
        requests.push({ pluginId, signal, resolve, reject })
      })
  )
)
assert.equal(state.loading.value, true)
assert.equal(requests[0].pluginId, 'first_plugin')

props.pluginId = 'second_plugin'
await nextTick()
assert.equal(requests[0].signal.aborted, true)
requests[1].resolve({ data: { series: [{ version: 'second' }] } })
await nextTick()
requests[0].resolve({ data: { series: [{ version: 'stale' }] } })
await nextTick()
assert.equal(
  state.data.value.series[0].version,
  'second',
  'late response must not replace the selected plugin'
)
assert.equal(state.loading.value, false)

const failed = state.refresh()
requests[2].reject(new Error('network unavailable'))
await failed
assert.match(state.error.value, /查询失败/)
assert.equal(state.loading.value, false)
const retry = state.refresh()
assert.equal(state.error.value, '')
requests[3].resolve({ data: { supported: false, series: [] } })
await retry
assert.equal(state.data.value.supported, false)

const closing = state.refresh()
unmount()
scope.stop()
assert.equal(requests[4].signal.aborted, true)
requests[4].reject(new Error('cancelled'))
await closing
assert.equal(state.error.value, '', 'closing the dialog must not report a failed query')
