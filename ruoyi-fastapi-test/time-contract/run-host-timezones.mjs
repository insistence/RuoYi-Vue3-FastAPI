import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

// 根据脚本位置定位仓库，支持任意检出目录和调用目录。
const root = fileURLToPath(new URL('../../', import.meta.url))
const paths = [
  'ruoyi-fastapi-frontend/tests/time/time.test.js',
  'ruoyi-fastapi-app/tests/time.test.js',
  'ruoyi-fastapi-app/tests/time-polyfill.test.js'
]
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
