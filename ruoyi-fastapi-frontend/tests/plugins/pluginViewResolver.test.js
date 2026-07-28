import assert from 'node:assert/strict'

import { resolvePluginViewPath } from '../../src/utils/pluginViewResolver.js'

assert.equal(resolvePluginViewPath('plugin/demo/index'), '../../../plugins/demo/views/index.vue')
assert.equal(resolvePluginViewPath('/plugin/demo/detail/list'), '../../../plugins/demo/views/detail/list.vue')
assert.equal(resolvePluginViewPath('system/user/index'), '')
assert.equal(resolvePluginViewPath('plugin/demo'), '')
assert.equal(resolvePluginViewPath('plugin/demo/../admin'), '')
assert.equal(resolvePluginViewPath('plugin/demo//index'), '')
assert.equal(resolvePluginViewPath('plugin/Demo/index'), '')
assert.equal(resolvePluginViewPath('plugin/demo/index.vue'), '')
assert.equal(resolvePluginViewPath('plugin/demo/detail\\list'), '')
assert.equal(resolvePluginViewPath(null), '')
