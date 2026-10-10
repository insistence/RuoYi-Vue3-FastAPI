const { readdirSync } = require('node:fs')
const { join, relative } = require('node:path')
const { pathToFileURL } = require('node:url')

const collectTestFiles = (root) => {
  const entries = readdirSync(root, { withFileTypes: true })
  const testFiles = []
  for (const entry of entries) {
    const entryPath = join(root, entry.name)
    if (entry.isDirectory()) testFiles.push(...collectTestFiles(entryPath))
    else if (entry.isFile() && /\.test\.(?:js|cjs|mjs)$/.test(entry.name)) testFiles.push(entryPath)
  }
  return testFiles.sort()
}

async function run() {
  const testFiles = collectTestFiles(__dirname)
  if (testFiles.length === 0) throw new Error('No plugin tests found')
  let failedCount = 0
  for (const testFile of testFiles) {
    const testName = relative(__dirname, testFile)
    try {
      // 等待 ESM 顶层 await，同时兼容旧 CommonJS 测试导出的 Promise。
      const loaded = await import(pathToFileURL(testFile).href)
      await loaded.default
      console.log(`ok ${testName}`)
    } catch (error) {
      failedCount += 1
      console.error(`not ok ${testName}`)
      console.error(error && error.stack ? error.stack : error)
    }
  }
  if (failedCount > 0) throw new Error(`Plugin tests failed: ${failedCount}/${testFiles.length}`)
  console.log(`Plugin tests passed: ${testFiles.length}`)
}

run().catch((error) => {
  console.error(error && error.stack ? error.stack : error)
  process.exitCode = 1
})
