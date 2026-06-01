import assert from 'node:assert/strict'

import { tansParams } from '../src/utils/ruoyi.js'

assert.equal(tansParams({ pluginIds: ['ai', 'demo'] }), 'pluginIds=ai&pluginIds=demo&')
assert.equal(tansParams({ query: { name: 'ai' } }), 'query%5Bname%5D=ai&')

console.log('tansParams tests passed')
