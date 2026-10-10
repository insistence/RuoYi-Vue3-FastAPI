const fs = require('fs')

// 此 uni-app 版本即使关闭独立分包，也会预加载依赖 webpack 4 GraphHelpers
// 的插件。延迟到功能启用后再加载，保证 Vue CLI 5 的普通小程序构建可用。
const filename = require.resolve('@dcloudio/uni-mp-weixin/lib/createIndependentPlugin.js')
const source = fs.readFileSync(filename, 'utf8')
const marker = '// Lazy independent plugins for webpack 5'

if (!source.includes(marker)) {
  const imports = source.match(/^const .+ = require\('.\/independent-plugins\/.+'\)\r?\n/gm)
  const guard = 'if (!independentSwitch) return []'
  if (!imports || !source.includes(guard)) {
    throw new Error('uni-app 独立分包插件结构已变化，请检查 webpack 兼容补丁')
  }
  let patched = source
  imports.forEach(line => { patched = patched.replace(line, '') })
  patched = patched.replace(guard, `${guard}\n\n  ${marker}\n${imports.map(line => `  ${line.trim()}`).join('\n')}`)
  fs.writeFileSync(filename, patched)
}
