import { testTimeContract } from '../../ruoyi-fastapi-test/time-contract/contract.mjs'
// 在独立测试进程中模拟缺少原生 Intl 的运行时，再加载 App 时间工具。
globalThis.Intl = undefined
const time = await import('../src/utils/time.js')
testTimeContract(time)
