import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// 根据脚本位置定位仓库，支持任意检出目录和调用目录。
const root = fileURLToPath(new URL('../../', import.meta.url))
const frameworks = process.argv.slice(2)
if (frameworks.some((framework) => !['vue2', 'vue3'].includes(framework))) {
  console.error('Usage: node run-host-timezones.mjs [vue2] [vue3]')
  process.exit(1)
}
const paths = (frameworks.length ? frameworks : ['vue2', 'vue3']).flatMap((framework) => {
  const base = `ruoyi-fastapi-frontend/${framework}`
  const extension = framework === 'vue2' ? 'mjs' : 'js'
  return [
    `${base}/web/tests/time/time.test.${extension}`,
    `${base}/mobile/tests/time.test.${extension}`,
    `${base}/mobile/tests/time-polyfill.test.${extension}`
  ]
})
for (const zone of ['UTC', 'Asia/Shanghai', 'America/New_York']) {
  const result = spawnSync(process.execPath, ['--test', ...paths], {
    cwd: root,
    env: { ...process.env, TZ: zone },
    encoding: 'utf8'
  })
  console.log(`${zone}: ${result.status === 0 ? 'PASS' : 'FAIL'}`)
  if (result.status !== 0) {
    if (result.error) console.error(result.error.message)
    if (result.signal) console.error(`Test process terminated by ${result.signal}`)
    console.error(result.stdout, result.stderr)
    process.exit(result.status || 1)
  }
}
