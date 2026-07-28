<template>
   <div class="app-container">
      <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px" class="plugin-query-form">
         <el-form-item label="插件ID" prop="pluginId">
            <el-input
               v-model="queryParams.pluginId"
               placeholder="请输入插件ID"
               clearable
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="插件名称" prop="pluginName">
            <el-input
               v-model="queryParams.pluginName"
               placeholder="请输入插件名称"
               clearable
               @keyup.enter="handleQuery"
            />
         </el-form-item>
         <el-form-item label="启用设置" prop="enabled">
            <el-select v-model="queryParams.enabled" placeholder="启用设置" clearable>
               <el-option label="启用" value="0" />
               <el-option label="停用" value="1" />
            </el-select>
         </el-form-item>
         <el-form-item label="插件状态" prop="status">
            <el-select v-model="queryParams.status" placeholder="插件状态" clearable>
               <el-option v-for="item in pluginStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
         </el-form-item>
         <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
            <el-button icon="Refresh" @click="resetQuery">重置</el-button>
         </el-form-item>
      </el-form>

      <el-row :gutter="10" class="mb8">
         <el-col :span="1.5">
            <el-button type="primary" plain icon="Share" :disabled="!selectedPluginIds.length" @click="handlePlan('install')" v-hasPermi="['system:plugin:query']">安装计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button type="success" plain icon="Connection" :disabled="!selectedPluginIds.length" @click="handlePlan('enable')" v-hasPermi="['system:plugin:query']">启用计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button type="warning" plain icon="Upload" :disabled="!selectedPluginIds.length" @click="handlePlan('upgrade')" v-hasPermi="['system:plugin:query']">升级计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button plain icon="Tickets" @click="handleOperationLog" v-hasPermi="['system:plugin:query']">审计记录</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-tooltip :content="formatPluginIdsForDisplay(selectedPluginIds)" :disabled="!selectedPluginIds.length" placement="top">
               <el-tag
                  :type="selectedPluginIds.length ? 'success' : 'info'"
                  :closable="!!selectedPluginIds.length"
                  :disable-transitions="true"
                  class="plugin-selection-tag"
                  @close="clearSelectedPlugins"
               >{{ planTargetSummary }}</el-tag>
            </el-tooltip>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table ref="pluginTableRef" v-loading="loading" :data="pluginList" row-key="pluginId" @selection-change="handleSelectionChange">
         <el-table-column type="selection" width="55" align="center" :selectable="canSelectForBatch" />
         <el-table-column label="插件ID" align="center" prop="pluginId" width="120" :show-overflow-tooltip="true" />
         <el-table-column label="插件名称" align="center" prop="pluginName" min-width="140" :show-overflow-tooltip="true" />
         <el-table-column label="源码版本" align="center" prop="version" width="100" />
         <el-table-column label="已安装版本" align="center" prop="installedVersion" width="110">
            <template #default="scope">
               <span>{{ scope.row.installedVersion || "-" }}</span>
            </template>
         </el-table-column>
         <el-table-column label="启用设置" align="center" width="90">
            <template #default="scope">
               <el-tooltip :content="getEnabledSwitchTooltip(scope.row)" :disabled="!isEnabledSwitchBlocked(scope.row)" placement="top">
                  <span class="plugin-switch-tooltip-target">
                     <el-switch
                        v-model="scope.row.enabled"
                        active-value="0"
                        inactive-value="1"
                        :disabled="isEnabledSwitchBlocked(scope.row)"
                        @change="handleEnabledChange(scope.row)"
                        v-hasPermi="['system:plugin:edit']"
                     />
                  </span>
               </el-tooltip>
            </template>
         </el-table-column>
         <el-table-column label="插件状态" align="center" prop="status" width="110">
            <template #default="scope">
               <el-tag :type="getStatusTagType(scope.row.status)">{{ getStatusLabel(scope.row.status) }}</el-tag>
            </template>
         </el-table-column>
         <el-table-column label="来源" align="center" prop="source" width="80" />
         <el-table-column label="更新时间" align="center" prop="updateTime" width="165">
            <template #default="scope">
               <span>{{ formatPluginTime(scope.row.updateTime) }}</span>
            </template>
         </el-table-column>
         <el-table-column label="操作" align="center" width="260" fixed="right" class-name="small-padding fixed-width">
            <template #default="scope">
               <div class="plugin-action-buttons">
                  <el-tooltip content="详情" placement="top">
                     <el-button link type="primary" icon="View" @click="handleDetail(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="配置" placement="top" v-if="!isOrphanPlugin(scope.row)">
                     <el-button link type="primary" icon="Setting" @click="handleConfig(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="依赖" placement="top" v-if="!isOrphanPlugin(scope.row)">
                     <el-button link type="primary" icon="Connection" @click="handleDependencies(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="检查" placement="top" v-if="!isOrphanPlugin(scope.row)">
                     <el-button link type="primary" icon="CircleCheck" @click="handleCheck(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="健康检查" placement="top" v-if="!isOrphanPlugin(scope.row)">
                     <el-button link type="primary" icon="FirstAidKit" @click="handleHealth(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="诊断包" placement="top" v-if="!isOrphanPlugin(scope.row)">
                     <el-button link type="primary" icon="DocumentChecked" @click="handleDiagnose(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip :content="getOperationTooltip(scope.row, 'install', '安装')" placement="top" v-if="canInstall(scope.row)">
                     <el-button link type="success" icon="Download" :disabled="isOperationBlocked(scope.row, 'install')" @click="handleInstallDryRun(scope.row)" v-hasPermi="['system:plugin:edit']" />
                  </el-tooltip>
                  <el-tooltip :content="getOperationTooltip(scope.row, 'upgrade', '升级')" placement="top" v-if="canUpgrade(scope.row)">
                     <el-button link type="warning" icon="Upload" :disabled="isOperationBlocked(scope.row, 'upgrade')" @click="handleUpgradeDryRun(scope.row)" v-hasPermi="['system:plugin:edit']" />
                  </el-tooltip>
                  <el-tooltip :content="getOperationTooltip(scope.row, 'uninstall', '卸载')" placement="top" v-if="canUninstall(scope.row)">
                     <el-button link type="danger" icon="SwitchButton" :disabled="isOperationBlocked(scope.row, 'uninstall')" @click="handleUninstallDryRun(scope.row)" v-hasPermi="['system:plugin:edit']" />
                  </el-tooltip>
                  <el-tooltip content="清理孤儿元数据" placement="top" v-if="isOrphanPlugin(scope.row)">
                     <el-button link type="danger" icon="Delete" @click="handlePurgeDryRun(scope.row)" v-hasPermi="['system:plugin:remove']" />
                  </el-tooltip>
               </div>
            </template>
         </el-table-column>
      </el-table>

      <pagination
         v-show="total > 0"
         :total="total"
         v-model:page="queryParams.pageNum"
         v-model:limit="queryParams.pageSize"
         @pagination="getList"
      />

      <plugin-detail-dialog
         v-model="detailOpen"
         :detail="detail"
         :get-status-label="getStatusLabel"
         :format-plugin-time="formatPluginTime"
         :format-config-default-value="formatConfigDefaultValue"
         :format-config-constraint="formatConfigConstraint"
         :migration-history="migrationHistory"
         :migration-loading="migrationLoading"
         @repair="handleRepairFromDetail"
         @mark-migration-success="handleMarkMigrationSuccess"
         @mark-migration-failed="handleMarkMigrationFailed"
      />

      <plugin-dependency-dialog
         v-model="dependencyOpen"
         :result="dependencyResult"
         :loading="dependencyLoading"
         :is-capability-operation-blocked="isCapabilityOperationBlocked"
         :format-boolean="formatBoolean"
         :get-dependency-tag-type="getDependencyTagType"
         :format-dependency-installed="formatDependencyInstalled"
         :format-dependency-version-satisfied="formatDependencyVersionSatisfied"
         @dry-run="handleDependencyDryRun"
         @install="handleDependencyInstall"
      />

      <plugin-diagnostic-dialog
         v-model="diagnosticOpen"
         :title="diagnosticTitle"
         :result="diagnosticResult"
         :loading="diagnosticLoading"
         :format-json="formatJson"
         :format-boolean="formatBoolean"
         :get-validation-level-label="getValidationLevelLabel"
         :get-validation-level-tag-type="getValidationLevelTagType"
      />

      <plugin-plan-dialog
         v-model="planOpen"
         v-model:continue-on-error="batchContinueOnError"
         :title="planTitle"
         :plan-result="planResult"
         :batch-result="batchResult"
         :loading="planLoading"
         :format-plugin-operation="formatPluginOperation"
         :format-plugin-ids-for-display="formatPluginIdsForDisplay"
         :format-plan-dependencies="formatPlanDependencies"
         :get-plan-ready-tag-type="getPlanReadyTagType"
         :get-plan-blocker-status-label="getPlanBlockerStatusLabel"
         @execute="handleExecuteBatch(false)"
      />

      <el-drawer title="插件操作审计" v-model="operationLogOpen" size="50%" append-to-body>
         <div class="plugin-audit-drawer">
            <div class="plugin-audit-search" v-show="operationLogShowSearch">
               <el-form :model="operationLogQueryParams" :inline="true" label-width="68px" class="plugin-query-form plugin-log-toolbar">
                  <el-form-item label="插件ID">
                     <el-input
                        v-model="operationLogQueryParams.pluginId"
                        placeholder="请输入插件ID"
                        clearable
                        @keyup.enter="handleOperationLogQuery"
                     />
                  </el-form-item>
                  <el-form-item label="操作">
                     <el-select v-model="operationLogQueryParams.operation" placeholder="操作类型" clearable>
                        <el-option v-for="item in plugin_operation_type" :key="item.value" :label="item.label" :value="item.value" />
                     </el-select>
                  </el-form-item>
                  <el-form-item label="状态">
                     <el-select v-model="operationLogQueryParams.status" placeholder="执行状态" clearable>
                        <el-option v-for="item in operationLogStatusOptions" :key="item.value" :label="item.label" :value="item.value" />
                     </el-select>
                  </el-form-item>
                  <el-form-item label="创建时间" class="plugin-audit-date-range">
                     <el-date-picker
                        v-model="operationLogDateRange"
                        value-format="YYYY-MM-DD"
                        type="daterange"
                        range-separator="-"
                        start-placeholder="开始日期"
                        end-placeholder="结束日期"
                     />
                  </el-form-item>
                  <el-form-item>
                     <el-button type="primary" icon="Search" @click="handleOperationLogQuery">搜索</el-button>
                     <el-button icon="Refresh" @click="resetOperationLogQuery">重置</el-button>
                  </el-form-item>
               </el-form>
            </div>

            <el-collapse v-model="operationLogMaintenanceActive" class="plugin-audit-maintenance">
               <el-collapse-item name="retention">
                  <template #title>
                     <span class="plugin-audit-maintenance-title">审计保留策略</span>
                     <el-tag size="small" type="info">默认 {{ operationLogRetentionDefaultDays }} 天</el-tag>
                  </template>
                  <el-form :model="operationLogRetentionForm" :inline="true" label-width="84px" class="plugin-log-toolbar">
                     <el-form-item label="保留天数">
                        <el-input-number v-model="operationLogRetentionForm.retentionDays" :min="0" :max="3650" controls-position="right" style="width: 150px" />
                     </el-form-item>
                     <el-form-item>
                        <el-button icon="DocumentChecked" :loading="operationLogRetentionLoading" @click="handleOperationLogRetentionPreview">预览清理</el-button>
                        <el-button
                           type="danger"
                           plain
                           icon="Delete"
                           :loading="operationLogRetentionLoading"
                           @click="handleOperationLogRetentionClean"
                           v-hasPermi="['system:plugin:edit']"
                        >确认清理</el-button>
                     </el-form-item>
                  </el-form>
                  <el-alert
                     v-if="operationLogRetentionResult.matchedCount !== undefined"
                     :title="formatRetentionMessage(operationLogRetentionResult)"
                     :type="operationLogRetentionResult.deletedCount ? 'success' : 'info'"
                     show-icon
                     :closable="false"
                  />
               </el-collapse-item>
            </el-collapse>

            <div class="plugin-audit-table">
               <div class="plugin-audit-table-toolbar">
                  <el-row :gutter="10" class="plugin-audit-table-actions">
                     <el-col :span="1.5">
                        <el-button
                           type="warning"
                           plain
                           icon="Download"
                           :loading="operationLogExportLoading"
                           @click="handleOperationLogExport"
                           v-hasPermi="['system:plugin:export']"
                        >导出</el-button>
                     </el-col>
                  </el-row>
                  <right-toolbar v-model:showSearch="operationLogShowSearch" @queryTable="getOperationLogList"></right-toolbar>
               </div>
               <el-table v-loading="operationLogLoading" :data="operationLogList" size="small" border>
                  <el-table-column label="日志ID" prop="operationId" width="90" align="center" />
                  <el-table-column label="操作" width="90" align="center">
                     <template #default="scope">{{ formatPluginOperation(scope.row.operation) }}</template>
                  </el-table-column>
                  <el-table-column label="状态" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getOperationLogStatusTagType(scope.row.status)">{{ getOperationLogStatusLabel(scope.row.status) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="插件" min-width="180" :show-overflow-tooltip="true">
                     <template #default="scope">{{ formatPlanDependencies(scope.row.pluginIds) }}</template>
                  </el-table-column>
                  <el-table-column label="成功" width="70" align="center">
                     <template #default="scope">{{ scope.row.summary?.succeeded ?? 0 }}</template>
                  </el-table-column>
                  <el-table-column label="失败" width="70" align="center">
                     <template #default="scope">{{ scope.row.summary?.failed ?? 0 }}</template>
                  </el-table-column>
                  <el-table-column label="创建时间" width="170" align="center">
                     <template #default="scope">{{ parseTime(scope.row.createTime) }}</template>
                  </el-table-column>
                  <el-table-column label="操作" width="70" align="center">
                     <template #default="scope">
                        <el-tooltip content="详情" placement="top">
                           <el-button link type="primary" icon="View" @click="handleOperationLogDetail(scope.row)" />
                        </el-tooltip>
                     </template>
                  </el-table-column>
               </el-table>
               <pagination
                  v-show="operationLogTotal > 0"
                  :total="operationLogTotal"
                  v-model:page="operationLogQueryParams.pageNum"
                  v-model:limit="operationLogQueryParams.pageSize"
                  @pagination="getOperationLogList"
               />
            </div>

            <div class="drawer-footer">
               <el-button @click="operationLogOpen = false">关 闭</el-button>
            </div>
         </div>
      </el-drawer>

      <el-dialog title="审计详情" v-model="operationLogDetailOpen" width="920px" append-to-body>
         <el-descriptions :column="3" border class="mb16">
            <el-descriptions-item label="日志ID">{{ operationLogDetail.operationId || "-" }}</el-descriptions-item>
            <el-descriptions-item label="操作">{{ formatPluginOperation(operationLogDetail.operation) }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ getOperationLogStatusLabel(operationLogDetail.status) }}</el-descriptions-item>
            <el-descriptions-item label="预演">{{ operationLogDetail.dryRun ? "是" : "否" }}</el-descriptions-item>
            <el-descriptions-item label="失败后继续">{{ operationLogDetail.continueOnError ? "是" : "否" }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ parseTime(operationLogDetail.createTime) || "-" }}</el-descriptions-item>
            <el-descriptions-item label="插件" :span="3">{{ formatPlanDependencies(operationLogDetail.pluginIds) }}</el-descriptions-item>
            <el-descriptions-item label="备注" :span="3">{{ operationLogDetail.remark || "-" }}</el-descriptions-item>
         </el-descriptions>
         <el-tabs>
            <el-tab-pane label="摘要">
               <el-descriptions :column="3" border class="mb16">
                  <el-descriptions-item label="成功数">{{ operationLogDetail.summary?.succeeded ?? 0 }}</el-descriptions-item>
                  <el-descriptions-item label="失败数">{{ operationLogDetail.summary?.failed ?? 0 }}</el-descriptions-item>
                  <el-descriptions-item label="跳过数">{{ operationLogDetail.summary?.skipped ?? 0 }}</el-descriptions-item>
                  <el-descriptions-item label="变更配置" :span="3">
                     {{ formatPlanDependencies(operationLogDetail.summary?.changedKeys) }}
                  </el-descriptions-item>
                  <el-descriptions-item label="失败建议" :span="3">
                     {{ operationLogDetail.failedSuggestion || "暂无" }}
                  </el-descriptions-item>
                  <el-descriptions-item label="失败步骤" :span="3">
                     {{ operationLogDetail.failedStep || operationLogDetail.result?.failedStep || operationLogDetail.result?.failed?.result?.failedStep || "暂无" }}
                  </el-descriptions-item>
               </el-descriptions>
            </el-tab-pane>
            <el-tab-pane label="检查结果">
               <el-table :data="operationLogDetail.validationItems || []" size="small" border empty-text="暂无检查结果">
                  <el-table-column label="分类" prop="category" width="120" align="center" />
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">{{ getValidationLevelLabel(scope.row.level) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="对象" prop="value" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="说明" prop="message" min-width="220" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="动作计划">
               <el-table :data="operationLogDetail.actionItems || []" size="small" border empty-text="暂无动作计划">
                  <el-table-column label="动作" prop="label" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="启用" width="80" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? "是" : "否" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="数量" prop="count" width="80" align="center">
                     <template #default="scope">{{ scope.row.count ?? "-" }}</template>
                  </el-table-column>
                  <el-table-column label="状态" min-width="160" :show-overflow-tooltip="true">
                     <template #default="scope">{{ formatActionPlanState(scope.row) }}</template>
                  </el-table-column>
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="依赖计划">
               <el-table :data="operationLogDetail.planItems || []" size="small" border empty-text="暂无依赖计划">
                  <el-table-column label="插件ID" prop="pluginId" width="150" :show-overflow-tooltip="true" />
                  <el-table-column label="版本" prop="version" width="110" align="center" />
                  <el-table-column label="就绪" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getPlanReadyTagType(scope.row.ready)">{{ scope.row.ready ? "是" : "否" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="依赖" min-width="200" :show-overflow-tooltip="true">
                     <template #default="scope">{{ formatPlanDependencies(scope.row.dependencies) }}</template>
                  </el-table-column>
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="执行记录">
               <el-table :data="operationLogDetail.result?.executed || []" size="small" border empty-text="暂无执行记录">
                  <el-table-column label="插件ID" prop="pluginId" width="140" :show-overflow-tooltip="true" />
                  <el-table-column label="操作" width="90" align="center">
                     <template #default="scope">{{ formatPluginOperation(scope.row.operation) }}</template>
                  </el-table-column>
                  <el-table-column label="状态" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.ok ? 'success' : 'danger'">{{ scope.row.status || "-" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="耗时" prop="durationMs" width="90" align="center">
                     <template #default="scope">{{ scope.row.durationMs ?? "-" }}ms</template>
                  </el-table-column>
                  <el-table-column label="失败步骤" prop="failedStep" width="150" :show-overflow-tooltip="true">
                     <template #default="scope">{{ scope.row.failedStep || scope.row.result?.failedStep || "-" }}</template>
                  </el-table-column>
                  <el-table-column label="说明" prop="message" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="建议" prop="suggestion" min-width="260" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="配置变更">
               <el-table :data="operationLogDetail.configChanges || []" size="small" border empty-text="暂无配置变更">
                  <el-table-column label="配置键" prop="key" width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="名称" prop="label" width="160" :show-overflow-tooltip="true" />
                  <el-table-column label="敏感" width="80" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.secret ? 'warning' : 'info'">{{ scope.row.secret ? "是" : "否" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="变更前" prop="before" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="变更后" prop="after" min-width="180" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="原始结果">
               <el-input :model-value="formatJson(operationLogDetail.result)" type="textarea" :rows="14" readonly />
            </el-tab-pane>
         </el-tabs>
         <template #footer>
            <div class="dialog-footer">
               <el-button @click="operationLogDetailOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>

      <plugin-config-dialog
         v-model="configOpen"
         :title="configTitle"
         :items="configItems"
         :loading="configLoading"
         :format-config-default-value="formatConfigDefaultValue"
         :format-config-constraint="formatConfigConstraint"
         @submit="submitConfig"
      />

      <el-dialog :title="actionTitle" v-model="actionOpen" width="860px" append-to-body>
         <el-alert
            v-if="actionResult.message"
            :title="actionResult.message"
            :type="actionResult.ok ? 'success' : 'warning'"
            show-icon
            :closable="false"
            class="mb16"
         />
         <el-descriptions :column="3" border class="mb16">
            <el-descriptions-item label="插件ID">{{ actionResult.pluginId || "-" }}</el-descriptions-item>
            <el-descriptions-item label="依赖检查">{{ formatBoolean(actionResult.dependencyOk) }}</el-descriptions-item>
            <el-descriptions-item label="结构检查">{{ formatBoolean(actionResult.structureOk) }}</el-descriptions-item>
            <el-descriptions-item label="菜单冲突">{{ formatBoolean(actionResult.menuConflictOk) }}</el-descriptions-item>
            <el-descriptions-item label="预演模式">{{ actionResult.dryRun ? "是" : "否" }}</el-descriptions-item>
            <el-descriptions-item label="需要升级">{{ formatBoolean(actionResult.needsUpgrade) }}</el-descriptions-item>
         </el-descriptions>

         <el-tabs>
            <el-tab-pane v-if="actionResult.error" label="错误详情">
               <el-alert
                  :title="actionResult.error.message || '插件操作失败'"
                  type="error"
                  show-icon
                  :closable="false"
                  class="mb16"
               />
               <el-descriptions :column="2" border class="mb16">
                  <el-descriptions-item label="插件ID">{{ actionResult.pluginId || pendingAction.pluginId || "-" }}</el-descriptions-item>
                  <el-descriptions-item label="操作">{{ actionResult.operation ? formatPluginOperation(actionResult.operation) : (pendingAction.label || "-") }}</el-descriptions-item>
                  <el-descriptions-item label="失败步骤">{{ actionResult.failedStep || actionResult.error.failedStep || "-" }}</el-descriptions-item>
                  <el-descriptions-item v-if="actionResult.migrationRecovery" label="Migration">
                     {{ actionResult.migrationRecovery.migrationPath || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item v-if="actionResult.migrationRecovery" label="Migration状态">
                     {{ actionResult.migrationRecovery.status || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item label="建议" :span="2">{{ actionResult.error.suggestion || "请查看后端日志或重新执行检查。" }}</el-descriptions-item>
               </el-descriptions>
               <el-input :model-value="formatJson(actionResult.error.raw)" type="textarea" :rows="10" readonly />
            </el-tab-pane>
            <el-tab-pane label="动作计划">
               <el-table :data="actionResult.actions || []" size="small" border empty-text="暂无动作计划">
                  <el-table-column label="动作" prop="label" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="启用" width="80" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? "是" : "否" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="状态" width="90" align="center">
                     <template #default="scope">
                        <el-tag v-if="scope.row.ok !== undefined" :type="scope.row.ok ? 'success' : 'danger'">
                           {{ scope.row.ok ? "通过" : "异常" }}
                        </el-tag>
                        <span v-else>-</span>
                     </template>
                  </el-table-column>
                  <el-table-column label="数量" prop="count" width="80" align="center">
                     <template #default="scope">{{ scope.row.count ?? "-" }}</template>
                  </el-table-column>
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="依赖">
               <el-table :data="actionResult.dependencies || []" size="small" border empty-text="暂无依赖声明">
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">
                           {{ getValidationLevelLabel(scope.row.level) }}
                        </el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="90" align="center" />
                  <el-table-column label="依赖" prop="requirement" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="已安装" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getDependencyTagType(scope.row)">{{ formatDependencyInstalled(scope.row) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="版本满足" width="100" align="center">
                     <template #default="scope">
                        <el-tag :type="getDependencyTagType(scope.row)">{{ formatDependencyVersionSatisfied(scope.row) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="说明" prop="message" min-width="220" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="Manifest 提示">
               <el-table :data="actionResult.manifestIssues || []" size="small" border empty-text="暂无 Manifest 提示">
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">
                           {{ getValidationLevelLabel(scope.row.level) }}
                        </el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="170" align="center" />
                  <el-table-column label="路径" prop="path" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="说明" prop="message" min-width="240" :show-overflow-tooltip="true" />
                  <el-table-column label="建议" prop="suggestion" min-width="240" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="结构错误">
               <el-table :data="actionResult.structureErrors || []" size="small" border empty-text="暂无结构错误">
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">
                           {{ getValidationLevelLabel(scope.row.level) }}
                        </el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="120" align="center" />
                  <el-table-column label="路径" prop="path" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="说明" prop="message" min-width="240" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="菜单冲突">
               <el-table :data="actionResult.menuConflicts || []" size="small" border empty-text="暂无菜单冲突">
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">
                           {{ getValidationLevelLabel(scope.row.level) }}
                        </el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="150" align="center" />
                  <el-table-column label="冲突值" prop="value" min-width="160" :show-overflow-tooltip="true" />
                  <el-table-column label="说明" prop="message" min-width="280" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
         </el-tabs>

         <template #footer>
            <div class="dialog-footer">
               <el-button
                  v-if="pendingAction.type && pendingAction.type !== 'purge'"
                  type="primary"
                  :loading="actionLoading"
                  @click="handleExecutePendingAction"
                  v-hasPermi="['system:plugin:edit']"
               >执行{{ pendingAction.label }}</el-button>
               <el-button
                  v-if="pendingAction.type === 'purge'"
                  type="danger"
                  :loading="actionLoading"
                  @click="handleExecutePendingAction"
                  v-hasPermi="['system:plugin:remove']"
               >执行{{ pendingAction.label }}</el-button>
               <el-button @click="actionOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>
   </div>
</template>

<script setup name="Plugin">
import {
  batchPlugins,
  checkPlugin,
  checkPluginDependencies,
  diagnosePlugin,
  disablePlugin,
  enablePlugin,
  getPlugin,
  getPluginConfig,
  getPluginOperationLog,
  healthPlugin,
  installPluginDependencies,
  installPlugin,
  listPlugin,
  listPluginMigrations,
  listPluginOperationLog,
  markPluginMigrationFailed,
  markPluginMigrationSuccess,
  planPlugins,
  purgePlugin,
  retainPluginOperationLog,
  uninstallPlugin,
  updatePluginConfig,
  upgradePlugin
} from "@/api/system/plugin";
import { getConfigKey } from "@/api/system/config";
import PluginConfigDialog from "./components/PluginConfigDialog.vue";
import PluginDependencyDialog from "./components/PluginDependencyDialog.vue";
import PluginDiagnosticDialog from "./components/PluginDiagnosticDialog.vue";
import PluginDetailDialog from "./components/PluginDetailDialog.vue";
import PluginPlanDialog from "./components/PluginPlanDialog.vue";
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
} from "@/utils/pluginPlanFormatter";

const { proxy } = getCurrentInstance();
const { plugin_operation_type } = proxy.useDict("plugin_operation_type");
const parseTime = proxy.parseTime;
const INVALID_PLUGIN_TIME_VALUES = new Set(["", "-", "0", "0-0-0 0:0:0", "0000-00-00 00:00:00"]);
const PLUGIN_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/;
const OPERATION_LOG_RETENTION_CONFIG_KEY = "sys.plugin.operationLogRetentionDays";

const pluginTableRef = ref(null);
const pluginList = ref([]);
const selectedPluginIds = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const detailOpen = ref(false);
const detail = ref({});
const migrationLoading = ref(false);
const migrationHistory = ref([]);
const actionOpen = ref(false);
const actionLoading = ref(false);
const actionTitle = ref("插件操作结果");
const actionResult = ref({});
const pendingAction = ref({});
const configOpen = ref(false);
const configLoading = ref(false);
const configTitle = ref("插件配置");
const configPluginId = ref("");
const configItems = ref([]);
const dependencyOpen = ref(false);
const dependencyLoading = ref(false);
const dependencyPluginId = ref("");
const dependencyResult = ref({});
const diagnosticOpen = ref(false);
const diagnosticLoading = ref(false);
const diagnosticTitle = ref("插件诊断");
const diagnosticResult = ref({});
const planOpen = ref(false);
const planLoading = ref(false);
const planTitle = ref("插件依赖计划");
const planResult = ref(normalizePluginPlanResponse({}));
const batchContinueOnError = ref(false);
const batchResult = ref(normalizePluginBatchResponse({}));
const operationLogOpen = ref(false);
const operationLogShowSearch = ref(true);
const operationLogLoading = ref(false);
const operationLogExportLoading = ref(false);
const operationLogList = ref([]);
const operationLogTotal = ref(0);
const operationLogDateRange = ref([]);
const operationLogDetailOpen = ref(false);
const operationLogDetail = ref({});
const operationLogRetentionLoading = ref(false);
const operationLogRetentionResult = ref({});
const operationLogRetentionDefaultDays = ref(180);
const operationLogMaintenanceActive = ref([]);
const operationLogRetentionForm = reactive({
  retentionDays: 180
});

function formatPluginTime(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string" && INVALID_PLUGIN_TIME_VALUES.has(value.trim())) {
    return "-";
  }

  const formatted = formatPluginIsoTime(value) || parseTime(value);
  if (!formatted || INVALID_PLUGIN_TIME_VALUES.has(String(formatted).trim())) {
    return "-";
  }

  return formatted;
}

function formatPluginIsoTime(value) {
  if (typeof value !== "string") {
    return "";
  }
  const matched = value.trim().match(PLUGIN_TIME_PATTERN);
  if (!matched) {
    return "";
  }

  return `${matched[1]}-${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}:${matched[6]}`;
}
const pluginStatusOptions = [
  { label: "已发现", value: "discovered", tagType: "info" },
  { label: "已安装", value: "installed", tagType: "success" },
  { label: "待升级", value: "pending_upgrade", tagType: "warning" },
  { label: "异常", value: "error", tagType: "danger" }
];

const operationLogStatusOptions = [
  { label: "成功", value: "success", tagType: "success" },
  { label: "失败", value: "failed", tagType: "danger" },
  { label: "阻塞", value: "blocked", tagType: "warning" },
  { label: "预演", value: "dry_run", tagType: "info" }
];

const data = reactive({
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    pluginId: undefined,
    pluginName: undefined,
    enabled: undefined,
    status: undefined,
    source: undefined
  },
  operationLogQueryParams: {
    pageNum: 1,
    pageSize: 10,
    pluginId: undefined,
    operation: undefined,
    status: undefined
  }
});

const { queryParams, operationLogQueryParams } = toRefs(data);

const planTargetSummary = computed(() => {
  return selectedPluginIds.value.length ? `已选 ${selectedPluginIds.value.length} 个插件` : "请选择插件";
});

/** 查询插件列表 */
function getList() {
  loading.value = true;
  listPlugin(queryParams.value).then(response => {
    pluginList.value = response.rows;
    total.value = response.total;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    loading.value = false;
  });
}

/** 多选框选中数据 */
function handleSelectionChange(selection) {
  selectedPluginIds.value = selection.map(item => item.pluginId).filter(Boolean);
}

function canSelectForBatch(row) {
  return !isOrphanPlugin(row);
}

/** 清空当前选择 */
function clearSelectedPlugins() {
  selectedPluginIds.value = [];
  pluginTableRef.value?.clearSelection?.();
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
  clearSelectedPlugins();
  getList();
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef");
  handleQuery();
}

/** 插件启停状态修改 */
function handleEnabledChange(row) {
  const enabled = row.enabled === "0";
  const operation = getEnabledSwitchOperation(row);
  if (isOperationBlocked(row, operation)) {
    row.enabled = row.enabled === "0" ? "1" : "0";
    proxy.$modal.msgWarning(getCapabilityReason(row.capability));
    return;
  }
  const text = enabled ? "启用" : "停用";
  proxy.$modal.confirm('确认要"' + text + '""' + row.pluginName + '"插件吗?').then(function () {
    return enabled ? enablePlugin(row.pluginId) : disablePlugin(row.pluginId);
  }).then(() => {
    proxy.$modal.msgSuccess(text + "成功");
    getList();
  }).catch(function (error) {
    row.enabled = row.enabled === "0" ? "1" : "0";
    if (isUserCancel(error)) {
      return;
    }
    showActionResult("插件" + text + "失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: enabled ? "enable" : "disable"
    }), {});
  });
}

function getEnabledSwitchOperation(row) {
  return row?.enabled === "0" ? "disable" : "enable";
}

function isEnabledSwitchBlocked(row) {
  const triesToEnableErrorPlugin = row?.status === "error" && row?.enabled !== "0";
  return triesToEnableErrorPlugin || isOperationBlocked(row, getEnabledSwitchOperation(row));
}

function getEnabledSwitchTooltip(row) {
  if (row?.status === "error") {
    return row?.enabled === "0"
      ? "插件当前被异常状态隔离；关闭开关可取消自动恢复意图"
      : "插件处于异常状态，请重新安装或升级修复，不能直接启用";
  }
  if (isOperationBlocked(row, getEnabledSwitchOperation(row))) {
    return getCapabilityReason(row.capability);
  }
  return "";
}

/** 打开详情 */
function handleDetail(row) {
  loading.value = true;
  migrationHistory.value = [];
  getPlugin(row.pluginId).then(response => {
    detail.value = response.data;
    detailOpen.value = true;
    loadPluginMigrationHistory(row.pluginId);
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    loading.value = false;
  });
}

/** 查询插件 migration 历史 */
function loadPluginMigrationHistory(pluginId) {
  if (!pluginId) {
    migrationHistory.value = [];
    return Promise.resolve();
  }
  migrationLoading.value = true;
  return listPluginMigrations(pluginId).then(response => {
    migrationHistory.value = response.data?.migrations || [];
  }).catch(error => {
    migrationHistory.value = [];
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    migrationLoading.value = false;
  });
}

/** 人工标记 migration 成功 */
function handleMarkMigrationSuccess(row) {
  const pluginId = detail.value.pluginId;
  const migrationPath = row?.migrationPath;
  if (!pluginId || !migrationPath) {
    return;
  }
  proxy.$modal.confirm('确认要将"' + migrationPath + '"标记为执行成功吗?').then(function () {
    migrationLoading.value = true;
    return markPluginMigrationSuccess(pluginId, {
      migrationPath,
      note: "管理页人工标记为成功"
    });
  }).then(response => {
    proxy.$modal.msgSuccess(response.data?.message || "migration 已标记为成功");
    return loadPluginMigrationHistory(pluginId);
  }).then(() => {
    getList();
  }).catch(error => {
    if (!isUserCancel(error)) {
      proxy.$modal.msgError(getErrorMessage(error));
    }
  }).finally(() => {
    migrationLoading.value = false;
  });
}

/** 人工标记 migration 失败 */
function handleMarkMigrationFailed(row) {
  const pluginId = detail.value.pluginId;
  const migrationPath = row?.migrationPath;
  if (!pluginId || !migrationPath) {
    return;
  }
  proxy.$modal.confirm('确认要将"' + migrationPath + '"标记为失败并允许后续重试吗?').then(function () {
    migrationLoading.value = true;
    return markPluginMigrationFailed(pluginId, {
      migrationPath,
      note: "管理页人工标记为失败"
    });
  }).then(response => {
    proxy.$modal.msgSuccess(response.data?.message || "migration 已标记为失败");
    return loadPluginMigrationHistory(pluginId);
  }).then(() => {
    getList();
  }).catch(error => {
    if (!isUserCancel(error)) {
      proxy.$modal.msgError(getErrorMessage(error));
    }
  }).finally(() => {
    migrationLoading.value = false;
  });
}

/** 打开插件配置 */
function handleConfig(row) {
  configLoading.value = true;
  configPluginId.value = row.pluginId;
  configTitle.value = row.pluginName + "配置";
  getPluginConfig(row.pluginId).then(response => {
    const configs = response.data?.configs || [];
    configItems.value = configs;
    configOpen.value = true;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    configLoading.value = false;
  });
}

/** 保存插件配置 */
function submitConfig(values) {
  configLoading.value = true;
  updatePluginConfig(configPluginId.value, { values }).then(() => {
    proxy.$modal.msgSuccess("插件配置已保存");
    configOpen.value = false;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    configLoading.value = false;
  });
}

/** 检查插件 */
function handleCheck(row) {
  actionLoading.value = true;
  checkPlugin(row.pluginId).then(response => {
    showActionResult("插件检查结果", response.data, {});
  }).catch(error => {
    showActionResult("插件检查失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: "check"
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 执行插件健康检查 */
function handleHealth(row) {
  diagnosticLoading.value = true;
  diagnosticTitle.value = row.pluginName + "健康检查";
  diagnosticResult.value = {
    pluginId: row.pluginId,
    message: "正在执行插件健康检查..."
  };
  diagnosticOpen.value = true;
  healthPlugin(row.pluginId).then(response => {
    diagnosticResult.value = response.data || {};
  }).catch(error => {
    diagnosticResult.value = {
      ok: false,
      pluginId: row.pluginId,
      message: getErrorMessage(error),
      error: serializeError(error)
    };
  }).finally(() => {
    diagnosticLoading.value = false;
  });
}

/** 生成插件诊断包 */
function handleDiagnose(row) {
  diagnosticLoading.value = true;
  diagnosticTitle.value = row.pluginName + "诊断包";
  diagnosticResult.value = {
    pluginId: row.pluginId,
    message: "正在生成插件诊断包..."
  };
  diagnosticOpen.value = true;
  diagnosePlugin(row.pluginId).then(response => {
    diagnosticResult.value = response.data || {};
  }).catch(error => {
    diagnosticResult.value = {
      ok: false,
      pluginId: row.pluginId,
      message: getErrorMessage(error),
      error: serializeError(error)
    };
  }).finally(() => {
    diagnosticLoading.value = false;
  });
}

/** 检查插件依赖 */
function handleDependencies(row) {
  dependencyLoading.value = true;
  dependencyPluginId.value = row.pluginId;
  checkPluginDependencies(row.pluginId).then(response => {
    dependencyResult.value = response.data || {};
    dependencyOpen.value = true;
  }).catch(error => {
    dependencyResult.value = {
      ok: false,
      pluginId: row.pluginId,
      message: getErrorMessage(error),
      dependencies: [],
      plan: []
    };
    dependencyOpen.value = true;
  }).finally(() => {
    dependencyLoading.value = false;
  });
}

/** 生成插件依赖安装计划 */
function handleDependencyDryRun() {
  if (isCapabilityOperationBlocked(dependencyResult.value.capability, "dependency_install")) {
    proxy.$modal.msgWarning(getCapabilityReason(dependencyResult.value.capability));
    return;
  }
  dependencyLoading.value = true;
  installPluginDependencies(dependencyPluginId.value, true).then(response => {
    dependencyResult.value = response.data || {};
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    dependencyLoading.value = false;
  });
}

/** 执行插件依赖安装 */
function handleDependencyInstall() {
  if (isCapabilityOperationBlocked(dependencyResult.value.capability, "dependency_install")) {
    proxy.$modal.msgWarning(getCapabilityReason(dependencyResult.value.capability));
    return;
  }
  if (dependencyResult.value.policy?.allowed === false) {
    proxy.$modal.msgWarning(getDependencyPolicyReason(dependencyResult.value.policy));
    return;
  }
  proxy.$modal.confirm('确认要安装"' + dependencyPluginId.value + '"插件缺失依赖吗?').then(function () {
    dependencyLoading.value = true;
    return installPluginDependencies(dependencyPluginId.value, false);
  }).then(response => {
    dependencyResult.value = response.data || {};
    proxy.$modal.msgSuccess("插件依赖安装完成");
  }).catch(error => {
    if (!isUserCancel(error)) {
      proxy.$modal.msgError(getErrorMessage(error));
    }
  }).finally(() => {
    dependencyLoading.value = false;
  });
}

/** 生成插件批量操作拓扑计划 */
function handlePlan(operation) {
  if (!selectedPluginIds.value.length) {
    proxy.$modal.msgWarning("请先选择要操作的插件");
    return;
  }
  planLoading.value = true;
  planTitle.value = "插件" + formatPluginOperation(operation) + "计划";
  const pluginIds = getBatchTargetPluginIds();
  batchResult.value = normalizePluginBatchResponse({});
  planPlugins(operation, pluginIds).then(response => {
    planResult.value = normalizePluginPlanResponse(response.data);
    planOpen.value = true;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    planLoading.value = false;
  });
}

/** 获取批量目标插件ID */
function getBatchTargetPluginIds() {
  return [...selectedPluginIds.value];
}

/** 执行插件批量操作 */
function handleExecuteBatch(dryRun) {
  if (!(planResult.value.ok && planResult.value.executablePluginIds.length > 0)) {
    return;
  }
  const operation = planResult.value.operation;
  const pluginIds = planResult.value.executablePluginIds;
  proxy.$modal.confirm('确认要批量执行插件' + formatPluginOperation(operation) + '吗? 目标：' + formatPlanDependencies(pluginIds)).then(function () {
    planLoading.value = true;
    return batchPlugins(operation, pluginIds, dryRun, batchContinueOnError.value);
  }).then(response => {
    batchResult.value = normalizePluginBatchResponse(response.data);
    planResult.value = normalizePluginPlanResponse(response.data);
    proxy.$modal.msgSuccess(response.data?.message || "插件批量操作完成");
    getList();
  }).catch(error => {
    if (isUserCancel(error)) {
      return;
    }
    batchResult.value = normalizePluginBatchResponse(buildErrorBatchResult(error, operation));
  }).finally(() => {
    planLoading.value = false;
  });
}

/** 打开插件操作审计 */
function handleOperationLog() {
  resetOperationLogSearchState();
  resetOperationLogRetentionState();
  operationLogOpen.value = true;
  loadOperationLogRetentionPolicy();
  getOperationLogList();
}

/** 搜索插件操作审计 */
function handleOperationLogQuery() {
  operationLogQueryParams.value.pageNum = 1;
  getOperationLogList();
}

/** 重置插件操作审计查询 */
function resetOperationLogQuery() {
  resetOperationLogSearchState();
  handleOperationLogQuery();
}

function resetOperationLogSearchState() {
  operationLogDateRange.value = [];
  operationLogQueryParams.value.pageNum = 1;
  operationLogQueryParams.value.pluginId = undefined;
  operationLogQueryParams.value.operation = undefined;
  operationLogQueryParams.value.status = undefined;
}

function resetOperationLogRetentionState() {
  operationLogRetentionLoading.value = false;
  operationLogRetentionResult.value = {};
  operationLogRetentionForm.retentionDays = operationLogRetentionDefaultDays.value;
}

function buildOperationLogQueryParams() {
  return proxy.addDateRange({ ...operationLogQueryParams.value }, operationLogDateRange.value);
}

function loadOperationLogRetentionPolicy() {
  getConfigKey(OPERATION_LOG_RETENTION_CONFIG_KEY).then(response => {
    const retentionDays = Number(response.msg);
    if (Number.isInteger(retentionDays) && retentionDays >= 0) {
      operationLogRetentionDefaultDays.value = retentionDays;
      operationLogRetentionForm.retentionDays = retentionDays;
    }
  }).catch(() => {});
}

/** 查询插件操作审计列表 */
function getOperationLogList() {
  operationLogLoading.value = true;
  listPluginOperationLog(buildOperationLogQueryParams()).then(response => {
    operationLogList.value = response.rows;
    operationLogTotal.value = response.total;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    operationLogLoading.value = false;
  });
}

/** 打开插件操作审计详情 */
function handleOperationLogDetail(row) {
  getPluginOperationLog(row.operationId).then(response => {
    operationLogDetail.value = normalizePluginOperationLogDetail(response.data || {});
    operationLogDetailOpen.value = true;
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  });
}

/** 导出插件操作审计 */
function handleOperationLogExport() {
  operationLogExportLoading.value = true;
  proxy.download("system/plugin/operation-log/export", {
    ...buildOperationLogQueryParams(),
    exportLimit: 5000
  }, `plugin_operation_log_${new Date().getTime()}.xlsx`).finally(() => {
    operationLogExportLoading.value = false;
  });
}

/** 预览插件操作审计保留策略 */
function handleOperationLogRetentionPreview() {
  operationLogRetentionLoading.value = true;
  retainPluginOperationLog({
    retentionDays: operationLogRetentionForm.retentionDays,
    dryRun: true
  }).then(response => {
    operationLogRetentionResult.value = response.data || {};
  }).catch(error => {
    proxy.$modal.msgError(getErrorMessage(error));
  }).finally(() => {
    operationLogRetentionLoading.value = false;
  });
}

/** 清理插件操作审计历史 */
function handleOperationLogRetentionClean() {
  proxy.$modal.confirm(buildOperationLogRetentionConfirmMessage()).then(function () {
    operationLogRetentionLoading.value = true;
    return retainPluginOperationLog({
      retentionDays: operationLogRetentionForm.retentionDays,
      dryRun: false
    });
  }).then(response => {
    operationLogRetentionResult.value = response.data || {};
    proxy.$modal.msgSuccess("插件操作审计清理完成");
    getOperationLogList();
  }).catch(error => {
    if (!isUserCancel(error)) {
      proxy.$modal.msgError(getErrorMessage(error));
    }
  }).finally(() => {
    operationLogRetentionLoading.value = false;
  });
}

function buildOperationLogRetentionConfirmMessage() {
  if (Number(operationLogRetentionForm.retentionDays) === 0) {
    return "确认清理当前时间之前的全部插件操作审计日志吗?";
  }

  return '确认清理超过"' + operationLogRetentionForm.retentionDays + '"天的插件操作审计日志吗?';
}

/** 安装插件预演 */
function handleInstallDryRun(row) {
  actionLoading.value = true;
  installPlugin(row.pluginId, true).then(response => {
    showActionResult("插件安装预演", response.data, {
      type: "install",
      label: "安装",
      pluginId: row.pluginId,
      pluginName: row.pluginName
    });
  }).catch(error => {
    showActionResult("插件安装预演失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: "install"
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 升级插件预演 */
function handleUpgradeDryRun(row) {
  actionLoading.value = true;
  upgradePlugin(row.pluginId, true).then(response => {
    showActionResult("插件升级预演", response.data, {
      type: "upgrade",
      label: "升级",
      pluginId: row.pluginId,
      pluginName: row.pluginName
    });
  }).catch(error => {
    showActionResult("插件升级预演失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: "upgrade"
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 安全卸载插件预演 */
function handleUninstallDryRun(row) {
  actionLoading.value = true;
  uninstallPlugin(row.pluginId, true).then(response => {
    showActionResult("插件卸载预演", response.data, {
      type: "uninstall",
      label: "卸载",
      pluginId: row.pluginId,
      pluginName: row.pluginName
    });
  }).catch(error => {
    showActionResult("插件卸载预演失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: "uninstall"
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 物理清理孤儿插件元数据预演 */
function handlePurgeDryRun(row) {
  actionLoading.value = true;
  purgePlugin(row.pluginId, true).then(response => {
    showActionResult("孤儿插件清理预演", response.data, {
      type: "purge",
      label: "清理孤儿元数据",
      pluginId: row.pluginId,
      pluginName: row.pluginName
    });
  }).catch(error => {
    showActionResult("孤儿插件清理预演失败", buildErrorActionResult(error, {
      pluginId: row.pluginId,
      operation: "purge"
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 执行预演后的插件操作 */
function handleExecutePendingAction() {
  if (!pendingAction.value.type) {
    return;
  }
  const action = pendingAction.value;
  proxy.$modal.confirm('确认要执行"' + action.pluginName + '"插件' + action.label + '吗?').then(function () {
    actionLoading.value = true;
    const requestMap = {
      install: installPlugin,
      upgrade: upgradePlugin,
      uninstall: uninstallPlugin,
      purge: purgePlugin
    };
    const request = requestMap[action.type];
    return request(action.pluginId, false);
  }).then(response => {
    showActionResult("插件" + action.label + "结果", response.data, {});
    proxy.$modal.msgSuccess("插件" + action.label + "完成");
    getList();
  }).catch(error => {
    if (isUserCancel(error)) {
      return;
    }
    showActionResult("插件" + action.label + "失败", buildErrorActionResult(error, {
      pluginId: action.pluginId,
      operation: action.type
    }), {});
  }).finally(() => {
    actionLoading.value = false;
  });
}

/** 展示插件操作结果 */
function showActionResult(title, result, nextAction) {
  actionTitle.value = title;
  actionResult.value = normalizeActionResult(result);
  pendingAction.value = canExecuteActionResult(actionResult.value) ? nextAction : {};
  actionOpen.value = true;
}

/** 从详情进入异常插件的重新安装修复流程 */
function handleRepairFromDetail() {
  const plugin = { ...detail.value };
  detailOpen.value = false;
  handleInstallDryRun(plugin);
}

function getStatusLabel(status) {
  const option = pluginStatusOptions.find(item => item.value === status);
  return option ? option.label : status || "-";
}

function getStatusTagType(status) {
  const option = pluginStatusOptions.find(item => item.value === status);
  return option ? option.tagType : "info";
}

function canInstall(row) {
  return !isOrphanPlugin(row) && (!row.installedVersion || row.status === "discovered" || row.status === "error");
}

function canUpgrade(row) {
  return !isOrphanPlugin(row) && row.status === "pending_upgrade";
}

function canUninstall(row) {
  return !isOrphanPlugin(row) && row.installedVersion && row.enabled === "0";
}

function isOrphanPlugin(row) {
  return row?.source === "orphan";
}

function canExecuteActionResult(result) {
  return !result.error && !isCapabilityOperationBlocked(result.capability, result.operation) && result.dryRun && result.structureOk !== false && result.menuConflictOk !== false;
}

function isOperationBlocked(row, operation) {
  return isCapabilityOperationBlocked(row?.capability, operation);
}

function isCapabilityOperationBlocked(capability, operation) {
  return Array.isArray(capability?.blockedOperations) && capability.blockedOperations.includes(operation);
}

function getCapabilityReason(capability) {
  return capability?.primaryReason || capability?.warnings?.[0] || "当前环境不允许执行该插件操作";
}

function getDependencyPolicyReason(policy) {
  const messages = [
    ...(Array.isArray(policy?.reasons) ? policy.reasons : []),
    ...(Array.isArray(policy?.requirements) ? policy.requirements : [])
  ];
  return messages[0] || "当前依赖安装策略不允许执行真实安装";
}

function getOperationTooltip(row, operation, label) {
  return isOperationBlocked(row, operation) ? getCapabilityReason(row.capability) : label;
}

function getDependencyTagType(row) {
  if (row.status === "skipped") {
    return "info";
  }
  return row.ok ? "success" : "danger";
}

function formatDependencyInstalled(row) {
  if (row.status === "skipped") {
    return "不适用";
  }
  return row.installed ? "是" : "否";
}

function formatDependencyVersionSatisfied(row) {
  if (row.status === "skipped") {
    return "不适用";
  }
  return row.versionSatisfied ? "是" : "否";
}

function normalizeActionResult(result) {
  return normalizePluginActionResult(result);
}

function buildErrorActionResult(error, context = {}) {
  const message = getErrorMessage(error);
  const payload = error?.response?.data?.data || {};
  const migrationRecovery = payload.migrationRecovery;
  return {
    ok: false,
    pluginId: payload.pluginId || context.pluginId,
    operation: payload.operation || context.operation,
    dependencyOk: false,
    structureOk: undefined,
    menuConflictOk: undefined,
    failedStep: payload.failedStep,
    migrationRecovery,
    error: {
      message: payload.error || message,
      suggestion: migrationRecovery?.suggestion || "请先执行插件检查，确认目录结构、依赖和菜单权限冲突后再重试。",
      raw: serializeError(error)
    },
    message
  };
}

function buildErrorBatchResult(error, operation) {
  const message = getErrorMessage(error);
  const executablePluginIds = planResult.value.executablePluginIds;
  return {
    ok: false,
    operation,
    message,
    summary: {
      total: executablePluginIds.length,
      succeeded: 0,
      failed: 1,
      skipped: Math.max(executablePluginIds.length - 1, 0)
    },
    executed: [
      {
        pluginId: executablePluginIds[0] || "-",
        operation,
        ok: false,
        status: "failed",
        message,
        suggestion: "请查看审计详情或后端日志后重试。"
      }
    ]
  };
}

function getErrorMessage(error) {
  if (!error) {
    return "插件操作失败";
  }
  if (typeof error === "string") {
    return error;
  }
  return error.message || error.msg || error.response?.data?.msg || "插件操作失败";
}

function serializeError(error) {
  if (!error) {
    return {};
  }
  if (typeof error === "string") {
    return { message: error };
  }
  return {
    message: error.message,
    name: error.name,
    status: error.response?.status,
    data: error.response?.data
  };
}

function isUserCancel(error) {
  return error === "cancel" || error === "close" || error?.message === "cancel";
}

function formatBoolean(value) {
  if (value === undefined || value === null) {
    return "-";
  }
  return value ? "通过" : "异常";
}

function formatPlanDependencies(dependencies) {
  return Array.isArray(dependencies) && dependencies.length ? dependencies.join(", ") : "-";
}

function formatPluginIdsForDisplay(pluginIds) {
  const ids = Array.isArray(pluginIds) ? pluginIds.filter(Boolean) : [];
  if (!ids.length) {
    return "-";
  }
  const visibleIds = ids.slice(0, 8).join(", ");
  return ids.length > 8 ? visibleIds + " 等 " + ids.length + " 个插件" : visibleIds;
}

function formatConfigDefaultValue(item) {
  const value = item.default;
  if (item.secret && value !== undefined && value !== null && value !== "") {
    return "******";
  }
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function formatConfigConstraint(item) {
  const constraints = [];
  if (item.min !== undefined && item.min !== null) {
    constraints.push("最小值 " + item.min);
  }
  if (item.max !== undefined && item.max !== null) {
    constraints.push("最大值 " + item.max);
  }
  if (item.pattern) {
    constraints.push("正则 " + item.pattern);
  }
  if (Array.isArray(item.options) && item.options.length) {
    constraints.push("选项 " + item.options.map(formatConfigOption).join(", "));
  }
  return constraints.length ? constraints.join("; ") : "-";
}

function formatConfigOption(option) {
  if (!option || typeof option !== "object") {
    return String(option);
  }
  const value = option.value === undefined || option.value === null ? "" : String(option.value);
  return option.label ? option.label + "(" + value + ")" : value;
}

function formatPluginOperation(operation) {
  return getPlanOperationLabel(operation, plugin_operation_type.value);
}

function getOperationLogStatusLabel(status) {
  const option = operationLogStatusOptions.find(item => item.value === status);

  return option ? option.label : status || "-";
}

function getOperationLogStatusTagType(status) {
  const option = operationLogStatusOptions.find(item => item.value === status);

  return option ? option.tagType : "info";
}

function formatRetentionMessage(result) {
  const actionText = result.dryRun ? "预览" : "清理";
  const cutoffTime = formatPluginTime(result.cutoffTime);
  return actionText + "完成：保留 " + result.retentionDays + " 天，截止 " + cutoffTime + "，匹配 " + result.matchedCount + " 条，已删除 " + result.deletedCount + " 条";
}

function formatActionPlanState(action) {
  if (action.ok === true) {
    return "通过";
  }
  if (action.ok === false) {
    return "异常";
  }
  if (action.hook) {
    return action.hook;
  }
  if (action.targetEnabled !== undefined) {
    return action.targetEnabled ? "目标启用" : "目标停用";
  }
  if (action.targetStatus !== undefined) {
    return action.targetStatus === "0" ? "目标正常" : "目标停用";
  }
  return "-";
}

function formatJson(value) {
  return JSON.stringify(value || {}, null, 2);
}

getList();
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.mr12 {
  margin-right: 12px;
}

.plugin-selection-tag {
  height: 32px;
  line-height: 30px;
}

.plugin-switch-tooltip-target {
  display: inline-flex;
  align-items: center;
}

.plugin-action-buttons {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.plugin-action-buttons :deep(.el-button) {
  margin-left: 0;
}

.plugin-query-form :deep(.el-input),
.plugin-query-form :deep(.el-select) {
  width: 220px;
}

.plugin-audit-drawer {
  display: flex;
  min-height: 100%;
  flex-direction: column;
}

.plugin-audit-search {
  padding: 12px 12px 4px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.plugin-audit-search {
  background: #fff;
}

.plugin-audit-maintenance {
  margin-bottom: 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.plugin-audit-maintenance :deep(.el-collapse-item__header) {
  height: 40px;
  padding: 0 12px;
  background: transparent;
  border-bottom-color: transparent;
}

.plugin-audit-maintenance :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-bottom: 0;
}

.plugin-audit-maintenance :deep(.el-collapse-item__content) {
  padding: 0 12px 12px;
}

.plugin-audit-maintenance-title {
  margin-right: 8px;
  color: #606266;
  font-weight: 600;
}

.plugin-log-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.plugin-log-toolbar :deep(.el-form-item) {
  margin-bottom: 10px;
}

.plugin-audit-date-range :deep(.el-date-editor) {
  width: 220px;
}

.plugin-audit-table {
  flex: 1;
  min-height: 0;
}

.plugin-audit-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.plugin-audit-table-actions {
  flex: 1;
}

.drawer-footer {
  margin-top: 16px;
  text-align: right;
}

@media (max-width: 768px) {
  .plugin-audit-table-toolbar {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
}
</style>
