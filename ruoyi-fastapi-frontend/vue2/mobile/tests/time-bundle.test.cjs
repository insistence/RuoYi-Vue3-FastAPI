const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const vm = require('node:vm')
const test = require('node:test')
const webpack = require('webpack')

const appRoot = path.resolve(__dirname, '..')

// Node can resolve a leaked require; a browser cannot. Execute the real bundled
// time module without Node globals and without native Intl to cover both paths.
for (const mode of ['development', 'production']) {
  test(`H5 ${mode} time bundle runs without require or native Intl`, async () => {
    const outputPath = fs.mkdtempSync(path.join(os.tmpdir(), 'ruoyi-time-bundle-'))
    const filename = path.join(outputPath, 'time-bundle.js')
    const previousPlatform = process.env.UNI_PLATFORM
    const previousMode = process.env.NODE_ENV
    process.env.UNI_PLATFORM = 'h5'
    process.env.NODE_ENV = mode
    try {
      const compiler = webpack({
        mode,
        context: appRoot,
        target: 'web',
        entry: path.join(appRoot, 'src/utils/time.js'),
        devtool: false,
        output: { path: outputPath, filename: 'time-bundle.js', library: { name: 'TimeBundle', type: 'var' } },
        optimization: { minimize: false },
        module: {
          rules: [{
            test: /\.m?js$/,
            include: /[/\\]node_modules[/\\]@formatjs[/\\]/,
            use: {
              loader: require.resolve('babel-loader'),
              options: { cwd: appRoot, configFile: path.join(appRoot, 'babel.config.js') }
            }
          }]
        }
      })
      await new Promise((resolve, reject) => {
        compiler.run((error, stats) => {
          compiler.close(closeError => {
            if (error || closeError) return reject(error || closeError)
            if (stats.hasErrors()) return reject(new Error(stats.toString({ all: false, errors: true })))
            resolve()
          })
        })
      })
      const sandbox = { Intl: undefined, console, setTimeout, clearTimeout }
      vm.runInNewContext(fs.readFileSync(filename, 'utf8'), sandbox, { timeout: 20000 })
      assert.equal(sandbox.require, undefined)
      const time = sandbox.TimeBundle
      assert.equal(
        time.formatBusinessTime('2026-01-01T00:00:00Z', 'YYYY-MM-DD HH:mm:ss', 'America/New_York'),
        '2025-12-31 19:00:00'
      )
      assert.equal(time.getWallTimeCandidates('2026-11-01 01:30:00', 'America/New_York').length, 2)
    } finally {
      if (previousPlatform === undefined) delete process.env.UNI_PLATFORM
      else process.env.UNI_PLATFORM = previousPlatform
      if (previousMode === undefined) delete process.env.NODE_ENV
      else process.env.NODE_ENV = previousMode
      if (fs.existsSync(filename)) fs.unlinkSync(filename)
      fs.rmdirSync(outputPath)
    }
  })
}
