import assert from 'node:assert/strict'

import {
  getPlanBlockerStatusLabel,
  getPlanOperationLabel,
  getPlanReadyTagType,
  getValidationLevelLabel,
  getValidationLevelTagType,
  normalizePluginActionResult,
  normalizePluginBatchResponse,
  normalizePluginOperationLogDetail,
  normalizePluginPlanResponse
} from '../src/utils/pluginPlanFormatter.js'

const payload = normalizePluginPlanResponse({
  ok: false,
  message: '存在阻塞',
  operation: 'install',
  plan: {
    requestedPluginIds: ['app'],
    orderedPluginIds: ['base', 'app'],
    items: [{ pluginId: 'base', ready: true }],
    blockers: [{ status: 'missing' }]
  }
})

assert.equal(payload.ok, false)
assert.equal(payload.operation, 'install')
assert.deepEqual(payload.requestedPluginIds, ['app'])
assert.deepEqual(payload.orderedPluginIds, ['base', 'app'])
assert.deepEqual(payload.executablePluginIds, ['app'])
assert.equal(payload.items.length, 1)
assert.equal(payload.blockerCount, 1)
assert.equal(getPlanOperationLabel('config_set', [{ label: '配置保存', value: 'config_set' }]), '配置保存')
assert.equal(getPlanOperationLabel('config_import', [{ label: '配置导入', value: 'config_import' }]), '配置导入')
assert.equal(getPlanOperationLabel('config_set'), 'config_set')
assert.equal(getPlanOperationLabel(undefined), '-')
assert.equal(getPlanReadyTagType(true), 'success')
assert.equal(getPlanReadyTagType(false), 'danger')
assert.equal(getPlanBlockerStatusLabel('version_unsatisfied'), '版本不满足')

const batchPayload = normalizePluginBatchResponse({
  ok: false,
  message: '存在失败项',
  operation: 'install',
  dryRun: false,
  continueOnError: true,
  plan: {
    orderedPluginIds: ['base', 'app'],
    items: [{ pluginId: 'base', ready: true }],
    blockers: []
  },
  summary: { total: 2, succeeded: 1, failed: 1, skipped: 0 },
  executed: [{ pluginId: 'base', status: 'success' }],
  failed: { pluginId: 'app' }
})

assert.equal(batchPayload.continueOnError, true)
assert.equal(batchPayload.summary.failed, 1)
assert.equal(batchPayload.executed.length, 1)
assert.equal(batchPayload.failed.pluginId, 'app')

const actionPayload = normalizePluginActionResult({
  ok: true,
  checks: [
    {
      pluginId: 'demo',
      dependencies: [{ level: 'info' }],
      missingDependencies: [],
      unsatisfiedDependencies: [],
      manifestWarnings: [{ level: 'warning', kind: 'secret_config_default' }],
      structureErrors: [],
      menuConflicts: []
    }
  ]
})

assert.equal(actionPayload.pluginId, 'demo')
assert.equal(actionPayload.dependencyOk, true)
assert.equal(actionPayload.manifestWarnings[0].kind, 'secret_config_default')
assert.equal(getValidationLevelLabel('warning'), '警告')
assert.equal(getValidationLevelTagType('error'), 'danger')

const operationLogDetail = normalizePluginOperationLogDetail({
  operationId: 1,
  summary: {
    changedKeys: ['api_key'],
    changes: [{ key: 'api_key', before: '******', after: '******', secret: true }]
  },
  result: {
    actions: [{ name: 'check_dependencies', enabled: true }],
    manifestWarnings: [{ kind: 'dependency_unpinned', level: 'warning', value: 'requests' }],
    failed: { suggestion: '检查插件依赖' }
  }
})

assert.equal(operationLogDetail.actionItems.length, 1)
assert.equal(operationLogDetail.validationItems[0].category, 'Manifest 警告')
assert.equal(operationLogDetail.configChanges[0].key, 'api_key')
assert.equal(operationLogDetail.failedSuggestion, '检查插件依赖')

const installFailureLogDetail = normalizePluginOperationLogDetail({
  operationId: 2,
  operation: 'install',
  result: {
    pluginId: 'demo',
    actions: [
      { name: 'check_dependencies', label: '检查依赖', enabled: true },
      { name: 'install_menus', label: '安装菜单', enabled: false, count: 0 }
    ],
    dependencies: [{ requirement: 'openai>=2.0.0', level: 'error', message: '依赖缺失' }],
    manifestWarnings: [{ kind: 'permission_without_plugin_prefix', level: 'warning', value: 'system:user:list' }],
    structureErrors: [{ kind: 'frontend_view', path: 'plugins/demo/views/index.vue', message: '视图不存在' }],
    menuConflicts: [{ kind: 'duplicate_permission', value: 'demo:list', message: '权限重复' }],
    failed: { suggestion: '先修复依赖、视图和菜单冲突' }
  }
})

assert.equal(installFailureLogDetail.actionItems.length, 2)
assert.deepEqual(
  installFailureLogDetail.validationItems.map(item => item.category),
  ['依赖', 'Manifest 警告', '结构', '菜单冲突']
)
assert.equal(installFailureLogDetail.failedSuggestion, '先修复依赖、视图和菜单冲突')

const batchLogDetail = normalizePluginOperationLogDetail({
  operationId: 3,
  operation: 'batch_install',
  result: {
    plan: {
      items: [
        { pluginId: 'base', version: '1.0.0', ready: true, dependencies: [] },
        { pluginId: 'demo', version: '1.0.0', ready: false, dependencies: ['base'] }
      ]
    },
    executed: [
      { pluginId: 'base', operation: 'install', ok: true, status: 'success', durationMs: 12 },
      { pluginId: 'demo', operation: 'install', ok: false, status: 'failed', message: '安装失败' }
    ],
    failed: {
      pluginId: 'demo',
      result: { message: '安装失败，请查看执行记录' }
    },
    summary: { total: 2, succeeded: 1, failed: 1, skipped: 0 }
  }
})

assert.equal(batchLogDetail.planItems.length, 2)
assert.equal(batchLogDetail.executed.length, 2)
assert.equal(batchLogDetail.summary.failed, 1)
assert.equal(batchLogDetail.failedSuggestion, '安装失败，请查看执行记录')

const configImportLogDetail = normalizePluginOperationLogDetail({
  operationId: 4,
  operation: 'config_import',
  result: {
    summary: {
      changedKeys: ['api_key', 'provider']
    }
  }
})

assert.deepEqual(
  configImportLogDetail.configChanges.map(item => item.key),
  ['api_key', 'provider']
)
assert.equal(configImportLogDetail.configChanges[0].before, '-')
assert.equal(configImportLogDetail.configChanges[0].after, '-')

console.log('plugin plan formatter tests passed')
