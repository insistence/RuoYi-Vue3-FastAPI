const assert = require('node:assert/strict')
const test = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { createRequire } = require('node:module')
const Vue = require('vue')
const { transformSync } = require('@babel/core')
const compiler = require('vue/compiler-sfc')
const transformModules = require('@babel/plugin-transform-modules-commonjs')

const sourceRoot = path.resolve(__dirname, '../../src')
const settle = async () => {
  await Vue.nextTick()
  await new Promise((resolve) => setImmediate(resolve))
}
const normalize = (value) => JSON.parse(JSON.stringify(value))

// Exercise real Vue 2 instances; API and browser resources are isolated per test.
function createLoader(mocks = {}, globals = {}) {
  const cache = new Map()
  function load(filename) {
    filename = path.resolve(filename)
    if (!path.extname(filename)) {
      filename = ['.js', '.vue', '/index.js', '/index.vue']
        .map((suffix) => filename + suffix)
        .find(fs.existsSync)
    }
    if (cache.has(filename)) return cache.get(filename).exports
    let source = fs.readFileSync(filename, 'utf8')
    if (filename.endsWith('.vue')) {
      const descriptor = compiler.parse({ source, filename })
      assert.ok(descriptor.script || descriptor.scriptSetup, filename)
      // Vue 2.7 supports the setup components already present in this project.
      source = descriptor.scriptSetup
        ? compiler.compileScript(descriptor, { id: filename }).content
        : descriptor.script.content
    }
    const code = transformSync(source, {
      filename,
      configFile: false,
      babelrc: false,
      plugins: [transformModules],
    }).code
    const module = { exports: {} }
    cache.set(filename, module)
    const nativeRequire = createRequire(filename)
    const requireModule = (specifier) => {
      if (Object.prototype.hasOwnProperty.call(mocks, specifier)) return mocks[specifier]
      if (specifier.startsWith('@/')) return load(path.resolve(sourceRoot, specifier.slice(2)))
      if (specifier.startsWith('.')) return load(path.resolve(path.dirname(filename), specifier))
      return nativeRequire(specifier)
    }
    vm.runInNewContext(
      code,
      {
        module,
        exports: module.exports,
        require: requireModule,
        console,
        setTimeout,
        clearTimeout,
        AbortController,
        Intl,
        ...globals,
      },
      { filename }
    )
    return module.exports
  }
  return (relative) => {
    const result = load(path.join(sourceRoot, relative))
    return result.default || result
  }
}

function fakeTimers() {
  let id = 0
  const pending = new Map()
  return {
    pending,
    setTimeout(callback) {
      pending.set(++id, callback)
      return id
    },
    clearTimeout(timer) {
      pending.delete(timer)
    },
    runNext() {
      const [timer, callback] = pending.entries().next().value
      pending.delete(timer)
      return callback()
    },
  }
}

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}

test('Vue 2 computed date text reacts immediately to account timezone changes', async () => {
  const time = createLoader()('utils/time.js')
  time.setUserTimezone('America/New_York')
  const instance = new Vue({
    computed: {
      display() {
        return time.formatBusinessTime('2026-01-01T00:00:00Z')
      },
    },
  })
  assert.equal(instance.display, '2025-12-31 19:00:00')
  time.setUserTimezone('UTC')
  await settle()
  assert.equal(instance.display, '2026-01-01 00:00:00')
  instance.$destroy()
})

test('Cron preview cancels obsolete requests and ignores responses after destruction', async () => {
  const timers = fakeTimers()
  const requests = []
  const component = createLoader(
    {
      '@/api/monitor/job': {
        previewJob(payload, signal) {
          const response = deferred()
          requests.push({ payload, signal, ...response })
          return response.promise
        },
      },
    },
    timers
  )('components/Crontab/result.vue')
  const instance = new Vue({
    ...component,
    propsData: { ex: '0 0 9 * * ?', timeZone: 'Asia/Shanghai' },
  })
  assert.equal(timers.pending.size, 1)
  const first = timers.runNext()
  instance.ex = '0 0 10 * * ?'
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  requests[0].resolve({ data: { nextRunTimes: ['stale'], timeZone: 'UTC' } })
  await first
  assert.deepEqual(normalize(instance.resultList), [])
  const second = timers.runNext()
  assert.equal(requests[1].payload.cronExpression, '0 0 10 * * ?')
  instance.$destroy()
  assert.equal(requests[1].signal.aborted, true)
  requests[1].resolve({ data: { nextRunTimes: ['late'], timeZone: 'UTC' } })
  await second
  assert.deepEqual(normalize(instance.resultList), [])
  assert.equal(timers.pending.size, 0)
})

test('Runtime dialog applies initial filters, cancels changed requests and stops on destroy', async () => {
  const requests = []
  const fetch = (query, options) => {
    const response = deferred()
    requests.push({ query, ...options, ...response })
    return response.promise
  }
  const component = createLoader(
    {
      '@/api/monitor/job': { listJobExecutions: fetch, listJobSync: fetch },
    },
    { document: { hidden: false, removeEventListener() {} } }
  )('views/monitor/job/runtime.vue')
  const instance = new Vue({
    ...component,
    propsData: { visible: true, initialTab: 'executions', jobId: '7', executionId: 'exec-1' },
  })
  assert.equal(requests[0].query.jobId, 7)
  assert.equal(requests[0].query.executionId, 'exec-1')
  instance.initialTab = 'sync'
  await settle()
  assert.equal(requests[0].signal.aborted, true)
  assert.equal(requests[1].query.executionId, undefined)
  requests[0].resolve({ rows: [{ status: 'running' }], total: 1 })
  requests[1].resolve({ rows: [{ syncStatus: 'applied' }], total: 1 })
  await settle()
  assert.equal(instance.rows[0].syncStatus, 'applied')
  const visibility = []
  instance.$on('update:visible', (value) => visibility.push(value))
  instance.dialogVisible = false
  assert.deepEqual(visibility, [false])
  instance.$destroy()
  assert.equal(requests[1].signal.aborted, true)
})

test('Job log initializes from stable IDs and follows route and display timezone changes', async () => {
  const queries = []
  const load = createLoader({
    './detail': {},
    '@/api/monitor/jobLog': {
      listJobLog: async (query) => {
        queries.push(query)
        return { rows: [], total: 0 }
      },
    },
  })
  const time = load('utils/time.js')
  time.setUserTimezone('UTC')
  const route = Vue.observable({ params: { jobId: '7' }, query: { executionId: 'exec-1' } })
  const component = load('views/monitor/job/log.vue')
  const instance = new Vue({
    ...component,
    beforeCreate() {
      this.$route = route
    },
    methods: { ...component.methods, addDateRange: (query) => query },
  })
  await settle()
  assert.equal(queries[0].jobId, '7')
  assert.equal(queries[0].executionId, 'exec-1')
  route.params.jobId = '8'
  route.query.executionId = ''
  await settle()
  assert.equal(queries.at(-1).jobId, '8')
  assert.equal(queries.at(-1).executionId, undefined)
  instance.dateRange = ['2026-01-01', '2026-01-02']
  const before = queries.length
  time.setUserTimezone('Asia/Shanghai')
  await settle()
  assert.equal(queries.length, before + 1)
  instance.$destroy()
})

test('Plugin config dynamic fields stay reactive and JSON values submit with their original types', async () => {
  const component = createLoader({
    'element-ui': { Message: { error: assert.fail } },
    '@/api/system/plugin': {
      getPluginConfigStatus: () => assert.fail('Closed config status must not request data'),
    },
  })('views/system/plugin/components/PluginConfigDialog.vue')
  const instance = new Vue({
    ...component,
    propsData: {
      items: [
        { key: 'enabled', value: false, type: 'switch' },
        { key: 'options', value: { limit: 3 }, type: 'json' },
      ],
      formatConfigDefaultValue: () => '-',
      formatConfigConstraint: () => '-',
    },
  })
  const state = instance._setupState || instance
  let updates = 0
  const stopWatchingEnabled = instance.$watch(
    () => state.configForm.values.enabled,
    () => updates++
  )
  state.configForm.values.enabled = true
  await settle()
  assert.equal(updates, 1)
  const values = state.buildConfigSubmitValues()
  assert.equal(values.enabled, true)
  assert.deepEqual(normalize(values.options), { limit: 3 })
  stopWatchingEnabled()
  instance.items = [{ key: 'anotherKey', value: 'initial', type: 'string' }]
  await settle()
  instance.$watch(
    () => state.configForm.values.anotherKey,
    () => updates++
  )
  state.configForm.values.anotherKey = 'updated'
  await settle()
  assert.equal(updates, 2)
  assert.equal(state.configForm.values.enabled, undefined)
  instance.$destroy()
})

test('JSON editor uses Element UI validation and releases Monaco resources in beforeDestroy', async () => {
  let text = '[]'
  let disposals = 0
  const disposable = () => ({ dispose: () => disposals++ })
  const model = {
    updateOptions() {},
    getValue: () => text,
    setValue: (value) => {
      text = value
    },
    ...disposable(),
  }
  const editor = {
    updateOptions() {},
    onDidChangeModelContent: disposable,
    onDidBlurEditorText: disposable,
    ...disposable(),
  }
  const monaco = {
    editor: { createModel: () => model, create: () => editor, onDidChangeMarkers: disposable },
  }
  const component = createLoader(
    { '@/utils/monaco': { loadMonaco: async () => monaco } },
    {
      document: { documentElement: { classList: { contains: () => false } } },
      MutationObserver: class {
        observe() {}
        disconnect() {
          disposals++
        }
      },
    }
  )('components/JsonEditor/index.vue')
  let validations = 0
  const parent = new Vue({
    provide: {
      elFormItem: {
        validateState: 'error',
        validate() {
          validations++
        },
      },
    },
  })
  const instance = new Vue({
    ...component,
    parent,
    propsData: { value: '[]', validate: JSON.parse },
  })
  instance.$refs.editorRef = {}
  await component.mounted.call(instance)
  assert.equal(instance.editorReady, true)
  assert.equal(editor.__ob__, undefined, 'Monaco editor must not be deeply observed by Vue')
  const inputs = []
  instance.$on('input', (value) => inputs.push(value))
  instance.updateValue('[1]')
  await settle()
  assert.equal(validations, 1)
  assert.deepEqual(inputs, ['[1]'])
  instance.$destroy()
  assert.equal(disposals, 6)
  parent.$destroy()
})

test('Business date input emits the Vue 2 v-model event with the selected wall time', () => {
  const component = createLoader()('components/BusinessDateTimePicker/index.vue')
  const instance = new Vue({
    ...component,
    propsData: { value: '2026-01-01 09:00:00', timezone: 'Asia/Shanghai' },
  })
  const values = []
  instance.$on('input', (value) => values.push(value))
  instance.timeInput = '10:30'
  assert.deepEqual(values, ['2026-01-01 10:30:00'])
  instance.$destroy()
})

test('Native job form uses callback validation, submits typed fields and retains More menu dispatch', async () => {
  const payloads = []
  const notices = []
  const component = createLoader(
    {
      './detail': {},
      './runtime': {},
      '@/components/Crontab': {},
      '@/components/JsonEditor': {},
      '@/utils/permission': { checkPermi: () => true },
      '@/api/monitor/job': {
        listJob: async () => ({ rows: [], total: 0 }),
        addJob: async (payload) => {
          payloads.push(payload)
          return { msg: '配置已保存，等待同步', data: { syncStatus: 'pending' } }
        },
      },
    },
    { document: { hidden: false, removeEventListener() {} } }
  )('views/monitor/job/index.vue')
  const instance = new Vue({
    ...component,
    beforeCreate: [
      function () {
        this.$store = { state: { user: { appTimezone: 'Asia/Shanghai' } } }
        this.$modal = { msg: (message) => notices.push(message), msgSuccess: assert.fail }
      },
      component.beforeCreate,
    ],
    methods: { ...component.methods, resetForm() {} },
  })
  instance.reset()
  assert.equal(instance.form.status, '1')
  instance.form.jobName = 'native form'
  instance.form.invokeTarget = 'module_task.scheduler_test.job'
  instance.form.cronExpression = '0 0 9 * * ?'
  instance.form.jobArgs = '["tenant,a", 3, true]'
  instance.form.jobKwargs = '{"enabled":false}'
  instance.unlimitedDelay = true
  let valid = false
  instance.$refs.form = {
    validate(callback) {
      callback(valid)
    },
  }
  instance.submitForm()
  assert.equal(payloads.length, 0)
  valid = true
  instance.submitForm()
  instance.submitForm()
  await settle()
  assert.equal(payloads.length, 1)
  assert.deepEqual(normalize(payloads[0].jobArgs), ['tenant,a', 3, true])
  assert.deepEqual(normalize(payloads[0].jobKwargs), { enabled: false })
  assert.equal(payloads[0].misfireGraceTime, null)
  assert.equal(payloads[0].timeZone, 'Asia/Shanghai')
  assert.equal('misfirePolicy' in payloads[0], false)
  assert.equal(instance.submitting, false)
  assert.deepEqual(notices, ['配置已保存，等待同步'])
  const commands = []
  instance.handleRun = (row) => commands.push(['run', row.jobId])
  instance.handleJobLog = (row) => commands.push(['log', row.jobId])
  instance.handleRuntime = (tab, row) => commands.push([tab, row.jobId])
  for (const command of ['handleRun', 'handleJobLog', 'handleExecutions', 'handleSync']) {
    instance.handleCommand(command, { jobId: 7 })
  }
  assert.deepEqual(commands, [
    ['run', 7],
    ['log', 7],
    ['executions', 7],
    ['sync', 7],
  ])
  instance.$destroy()
})
