import assert from 'node:assert/strict'

import { resolvePluginViewPath } from '../src/utils/pluginViewResolver.js'

const cases = [
  {
    view: 'plugin/ai/model/index',
    expected: '../../../plugins/ai/views/model/index.vue'
  },
  {
    view: 'plugin/ai/chat/index',
    expected: '../../../plugins/ai/views/chat/index.vue'
  },
  {
    view: 'plugin/demo/index',
    expected: '../../../plugins/demo/views/index.vue'
  },
  {
    view: 'system/user/index',
    expected: ''
  },
  {
    view: 'plugin/ai',
    expected: ''
  }
]

cases.forEach(({ view, expected }) => {
  assert.equal(resolvePluginViewPath(view), expected)
})

console.log('plugin view resolver tests passed')
