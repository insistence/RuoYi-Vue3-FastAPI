import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, extname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createContext, SourceTextModule, SyntheticModule } from 'node:vm'

const copy = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)))

// Execute the actual ESM sources in an isolated uni runtime. Only platform I/O,
// backend APIs and transport encryption are substituted; stores, auth, storage,
// request handling, route guards and timezone restoration remain production code.
export async function createMobileHarness(
  root,
  framework,
  { token = '', savedTimezone, confirm = true } = {}
) {
  const project = fileURLToPath(root)
  const nativeRequire = createRequire(new URL('package.json', root))
  const values = new Map([['device-theme', 'dark']])
  if (token) values.set('App-Token', token)
  if (savedTimezone) values.set('storage_data', { timezone: copy(savedTimezone) })
  const calls = { requests: [], modals: [], toasts: [], navigations: [], login: [], logout: [] }
  const responses = []
  const interceptors = new Map()
  const uni = {
    getStorageSync: (key) => copy(values.get(key)),
    setStorageSync: (key, value) => values.set(key, copy(value)),
    removeStorageSync: (key) => values.delete(key),
    addInterceptor: (method, handler) => interceptors.set(method, handler),
    reLaunch: (options) => calls.navigations.push(copy(options)),
    showToast: (options) => calls.toasts.push(copy(options)),
    showModal(options) {
      calls.modals.push(options.content)
      queueMicrotask(() => options.success({ confirm, cancel: !confirm }))
    },
    request(options) {
      calls.requests.push(copy(options))
      const response = responses.shift() || { statusCode: 200, data: { code: 200, data: 'ok' } }
      queueMicrotask(() =>
        response.failure ? options.fail(response.failure) : options.success(response)
      )
    },
  }
  const context = createContext({
    uni,
    console,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    URL,
  })
  const mocks = {
    '@/config': { default: { baseUrl: 'https://api.example.test' } },
    '@/static/images/profile.jpg': { default: '/static/profile.jpg' },
    '@/api/login': {
      login: async (...args) => {
        calls.login.push(args)
        return { token: 'fresh-token' }
      },
      logout: async (value) => {
        calls.logout.push(value)
      },
      getInfo: async () => ({
        appTimezone: 'Asia/Shanghai',
        user: { userId: 7, userName: 'tester', avatar: '', timeZone: 'America/New_York' },
        roles: ['operator'],
        permissions: ['system:user:query'],
      }),
    },
    '@/utils/transportCrypto': {
      encryptTransportRequest: async (config) => config,
      decryptTransportResponse: async (response) => response,
      decryptTransportErrorResponse: async (error) => error,
      shouldRetryTransportWithFreshKey: () => false,
      invalidateTransportKeyMeta() {},
      resetTransportRequestConfig() {},
    },
  }
  const modules = new Map()
  function synthetic(key, namespace) {
    return new SyntheticModule(
      Object.keys(namespace),
      function () {
        for (const [name, value] of Object.entries(namespace)) this.setExport(name, value)
      },
      { context, identifier: key }
    )
  }
  async function getModule(specifier, parent = resolve(project, 'src', 'index.js')) {
    if (Object.hasOwn(mocks, specifier)) {
      if (!modules.has(specifier)) modules.set(specifier, synthetic(specifier, mocks[specifier]))
      return modules.get(specifier)
    }
    if (
      !specifier.startsWith('@/') &&
      !specifier.startsWith('.') &&
      !specifier.startsWith('/') &&
      !/^[A-Za-z]:[\\/]/.test(specifier)
    ) {
      if (!modules.has(specifier)) {
        modules.set(
          specifier,
          import(pathToFileURL(nativeRequire.resolve(specifier)).href).then((namespace) =>
            synthetic(specifier, namespace)
          )
        )
      }
      return modules.get(specifier)
    }
    let filename = specifier.startsWith('@/')
      ? resolve(project, 'src', specifier.slice(2))
      : resolve(dirname(parent), specifier)
    if (!extname(filename))
      filename = [filename + '.js', resolve(filename, 'index.js')].find(existsSync)
    if (!filename) throw new Error(`Cannot resolve ${specifier} from ${parent}`)
    if (!modules.has(filename)) {
      modules.set(
        filename,
        readFile(filename, 'utf8').then(
          (source) => new SourceTextModule(source, { context, identifier: filename })
        )
      )
    }
    return modules.get(filename)
  }
  async function load(specifier) {
    const module = await getModule(specifier)
    if (module.status === 'unlinked')
      await module.link((dependency, parent) => getModule(dependency, parent.identifier))
    if (module.status === 'linked') await module.evaluate()
    return module.namespace
  }
  let state, login, getInfo, logout
  if (framework === 'vue2') {
    const store = (await load('@/store')).default
    state = store.state.user
    login = (value) => store.dispatch('Login', value)
    getInfo = () => store.dispatch('GetInfo')
    logout = () => store.dispatch('LogOut')
  } else {
    const pinia = await load('pinia')
    pinia.setActivePinia(pinia.createPinia())
    state = (await load('@/store/modules/user')).useUserStore()
    login = (value) => state.login(value)
    getInfo = () => state.getInfo()
    logout = () => state.logOut()
  }
  const time = await load('@/utils/time')
  const auth = await load('@/utils/auth')
  const request = (await load('@/utils/request')).default
  await load('@/permission')
  return {
    state,
    login,
    getInfo,
    logout,
    time,
    auth,
    request,
    values,
    responses,
    calls,
    interceptors,
  }
}

export const settle = () => new Promise((resolve) => setImmediate(resolve))
export const snapshot = copy
