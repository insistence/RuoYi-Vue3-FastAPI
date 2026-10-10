const assert = require('node:assert/strict')
const { readdirSync, readFileSync } = require('node:fs')
const { join, resolve } = require('node:path')
const compiler = require('vue/compiler-sfc')
const { transformSync } = require('@babel/core')
const transformModules = require('@babel/plugin-transform-modules-commonjs')

const frontend = resolve(__dirname, '../..')
const components = join(frontend, 'src/views/system/plugin/components')
const files = [
  join(frontend, 'src/components/PluginFrame/index.vue'),
  join(frontend, 'src/views/system/plugin/index.vue'),
  ...readdirSync(components)
    .filter((name) => name.endsWith('.vue'))
    .map((name) => join(components, name)),
]

// 同时编译真实 Vue 2 模板、setup 脚本和 scoped 样式，避免仅通过脚本逻辑测试。
for (const filename of files) {
  const source = readFileSync(filename, 'utf8')
  const descriptor = compiler.parse({ source, filename })
  const script = compiler.compileScript(descriptor, { id: filename })
  const template = compiler.compileTemplate({
    source: descriptor.template.content,
    filename,
    compilerOptions: { bindingMetadata: script.bindings },
  })
  assert.deepEqual(template.errors, [], `${filename}: template must compile with Vue 2`)
  assert.ok(template.code.includes('render'), `${filename}: render function must exist`)
  assert.doesNotThrow(() =>
    transformSync(script.content, {
      filename,
      configFile: false,
      babelrc: false,
      plugins: [transformModules],
    })
  )
  for (const style of descriptor.styles) {
    const result = compiler.compileStyle({
      source: style.content,
      filename,
      id: 'data-v-plugin',
      scoped: style.scoped,
    })
    assert.deepEqual(result.errors, [], `${filename}: styles must compile with Vue 2`)
  }
  assert.doesNotMatch(
    source,
    /from ['"](?:element-plus|@vue\/compiler-sfc)['"]|VITE_APP_PLUGIN_BASE/
  )
}
