const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { createRequire } = require('node:module')
const { transformSync } = require('@babel/core')
const transformModules = require('@babel/plugin-transform-modules-commonjs')
const compiler = require('vue/compiler-sfc')

// 编译真实 Vue 2.7 组件，只隔离 API 和浏览器资源。
function createLoader(mocks = {}, globals = {}) {
  const cache = new Map()
  function loadModule(filename) {
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
      if (specifier.startsWith('@/'))
        return loadModule(path.resolve(__dirname, '../../src', specifier.slice(2)))
      if (specifier.startsWith('.'))
        return loadModule(path.resolve(path.dirname(filename), specifier))
      return nativeRequire(specifier)
    }
    const execute = vm.compileFunction(
      code,
      ['module', 'exports', 'require', ...Object.keys(globals)],
      { filename }
    )
    execute(module, module.exports, requireModule, ...Object.values(globals))
    return module.exports
  }
  return loadModule
}

module.exports = { createLoader, loadModule: createLoader() }
