import request from '@/utils/request'

// 查询插件列表
export function listPlugin(query) {
  return request({
    url: '/system/plugin/list',
    method: 'get',
    params: query
  })
}

// 查询插件详细
export function getPlugin(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId,
    method: 'get'
  })
}

// 启用插件
export function enablePlugin(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId + '/enable',
    method: 'put'
  })
}

// 停用插件
export function disablePlugin(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId + '/disable',
    method: 'put'
  })
}

// 检查插件
export function checkPlugin(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId + '/check',
    method: 'get'
  })
}

// 安装插件
export function installPlugin(pluginId, dryRun = false) {
  return request({
    url: '/system/plugin/' + pluginId + '/install',
    method: 'post',
    params: { dryRun }
  })
}

// 升级插件
export function upgradePlugin(pluginId, dryRun = false) {
  return request({
    url: '/system/plugin/' + pluginId + '/upgrade',
    method: 'post',
    params: { dryRun }
  })
}

// 安全卸载插件
export function uninstallPlugin(pluginId, dryRun = false) {
  return request({
    url: '/system/plugin/' + pluginId + '/uninstall',
    method: 'post',
    params: { dryRun }
  })
}

// 查询插件配置
export function getPluginConfig(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId + '/config',
    method: 'get'
  })
}

// 更新插件配置
export function updatePluginConfig(pluginId, data) {
  return request({
    url: '/system/plugin/' + pluginId + '/config',
    method: 'put',
    data
  })
}

// 检查插件依赖
export function checkPluginDependencies(pluginId) {
  return request({
    url: '/system/plugin/' + pluginId + '/dependencies',
    method: 'get'
  })
}

// 生成插件批量操作拓扑计划
export function planPlugins(operation, pluginIds = []) {
  return request({
    url: '/system/plugin/plan',
    method: 'get',
    params: {
      operation,
      pluginIds
    }
  })
}

// 批量执行插件操作
export function batchPlugins(operation, pluginIds = [], dryRun = true, continueOnError = false) {
  return request({
    url: '/system/plugin/batch',
    method: 'post',
    data: {
      operation,
      pluginIds,
      dryRun,
      continueOnError
    }
  })
}

// 查询插件操作审计日志列表
export function listPluginOperationLog(query) {
  return request({
    url: '/system/plugin/operation-log/list',
    method: 'get',
    params: query
  })
}

// 查询插件操作审计日志详情
export function getPluginOperationLog(operationId) {
  return request({
    url: '/system/plugin/operation-log/' + operationId,
    method: 'get'
  })
}

// 执行插件操作审计日志保留策略
export function retainPluginOperationLog(params) {
  return request({
    url: '/system/plugin/operation-log/retention',
    method: 'delete',
    params
  })
}

// 生成插件依赖安装计划
export function installPluginDependencies(pluginId, dryRun = true) {
  return request({
    url: '/system/plugin/' + pluginId + '/dependencies/install',
    method: 'post',
    params: { dryRun }
  })
}
