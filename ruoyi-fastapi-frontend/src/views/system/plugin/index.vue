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
         <el-form-item label="启用状态" prop="enabled">
            <el-select v-model="queryParams.enabled" placeholder="启用状态" clearable>
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
            <el-button type="primary" plain icon="Share" @click="handlePlan('install')" v-hasPermi="['system:plugin:query']">安装计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button type="success" plain icon="Connection" @click="handlePlan('enable')" v-hasPermi="['system:plugin:query']">启用计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button type="warning" plain icon="Upload" @click="handlePlan('upgrade')" v-hasPermi="['system:plugin:query']">升级计划</el-button>
         </el-col>
         <el-col :span="1.5">
            <el-button plain icon="Tickets" @click="handleOperationLog" v-hasPermi="['system:plugin:query']">审计记录</el-button>
         </el-col>
         <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
      </el-row>

      <el-table v-loading="loading" :data="pluginList" @selection-change="handleSelectionChange">
         <el-table-column type="selection" width="55" align="center" />
         <el-table-column label="插件ID" align="center" prop="pluginId" width="120" :show-overflow-tooltip="true" />
         <el-table-column label="插件名称" align="center" prop="pluginName" min-width="140" :show-overflow-tooltip="true" />
         <el-table-column label="源码版本" align="center" prop="version" width="100" />
         <el-table-column label="已安装版本" align="center" prop="installedVersion" width="110">
            <template #default="scope">
               <span>{{ scope.row.installedVersion || "-" }}</span>
            </template>
         </el-table-column>
         <el-table-column label="启用状态" align="center" width="90">
            <template #default="scope">
               <el-switch
                  v-model="scope.row.enabled"
                  active-value="0"
                  inactive-value="1"
                  :disabled="scope.row.status === 'error' || isOperationBlocked(scope.row, scope.row.enabled === '0' ? 'disable' : 'enable')"
                  @change="handleEnabledChange(scope.row)"
                  v-hasPermi="['system:plugin:edit']"
               />
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
         <el-table-column label="操作" align="center" width="180" class-name="small-padding fixed-width">
            <template #default="scope">
               <div class="plugin-action-buttons">
                  <el-tooltip content="详情" placement="top">
                     <el-button link type="primary" icon="View" @click="handleDetail(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="配置" placement="top">
                     <el-button link type="primary" icon="Setting" @click="handleConfig(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="依赖" placement="top">
                     <el-button link type="primary" icon="Connection" @click="handleDependencies(scope.row)" v-hasPermi="['system:plugin:query']" />
                  </el-tooltip>
                  <el-tooltip content="检查" placement="top">
                     <el-button link type="primary" icon="CircleCheck" @click="handleCheck(scope.row)" v-hasPermi="['system:plugin:query']" />
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

      <el-dialog title="插件详情" v-model="detailOpen" width="720px" append-to-body>
         <el-descriptions :column="2" border>
            <el-descriptions-item label="插件ID">{{ detail.pluginId }}</el-descriptions-item>
            <el-descriptions-item label="插件名称">{{ detail.pluginName }}</el-descriptions-item>
            <el-descriptions-item label="源码版本">{{ detail.version }}</el-descriptions-item>
            <el-descriptions-item label="已安装版本">{{ detail.installedVersion || "-" }}</el-descriptions-item>
            <el-descriptions-item label="启用状态">{{ detail.enabled === "0" ? "启用" : "停用" }}</el-descriptions-item>
            <el-descriptions-item label="插件状态">{{ getStatusLabel(detail.status) }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ detail.source || "-" }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatPluginTime(detail.updateTime) }}</el-descriptions-item>
            <el-descriptions-item label="后端路径" :span="2">{{ detail.backendPath || "-" }}</el-descriptions-item>
            <el-descriptions-item label="前端路径" :span="2">{{ detail.frontendPath || "-" }}</el-descriptions-item>
            <el-descriptions-item label="最近错误" :span="2">{{ detail.lastError || "-" }}</el-descriptions-item>
            <el-descriptions-item label="插件说明" :span="2">{{ detail.description || "-" }}</el-descriptions-item>
         </el-descriptions>
         <template #footer>
            <div class="dialog-footer">
               <el-button
                  v-if="detail.status === 'error'"
                  type="primary"
                  @click="handleEnableFromDetail"
                  v-hasPermi="['system:plugin:edit']"
               >重新启用</el-button>
               <el-button @click="detailOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>

      <el-dialog title="插件依赖" v-model="dependencyOpen" width="860px" append-to-body>
         <el-alert
            v-if="dependencyResult.message"
            :title="dependencyResult.message"
            :type="dependencyResult.ok ? 'success' : 'warning'"
            show-icon
            :closable="false"
            class="mb16"
         />
         <el-descriptions :column="3" border class="mb16">
            <el-descriptions-item label="插件ID">{{ dependencyResult.pluginId || "-" }}</el-descriptions-item>
            <el-descriptions-item label="依赖检查">{{ formatBoolean(dependencyResult.dependencyOk) }}</el-descriptions-item>
            <el-descriptions-item label="安装计划">{{ dependencyResult.planCount ?? "-" }}</el-descriptions-item>
         </el-descriptions>
         <el-tabs>
            <el-tab-pane label="依赖状态">
               <el-table :data="dependencyResult.dependencies || []" size="small" border empty-text="暂无依赖声明">
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
                  <el-table-column label="说明" prop="message" min-width="240" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="安装计划">
               <el-table :data="dependencyResult.plan || []" size="small" border empty-text="暂无安装计划">
                  <el-table-column label="类型" prop="kind" width="90" align="center" />
                  <el-table-column label="依赖" prop="requirement" min-width="150" :show-overflow-tooltip="true" />
                  <el-table-column label="工作目录" prop="workdir" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="命令" prop="commandText" min-width="260" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
         </el-tabs>
         <template #footer>
            <div class="dialog-footer">
               <el-button type="primary" :disabled="isCapabilityOperationBlocked(dependencyResult.capability, 'dependency_install')" :loading="dependencyLoading" @click="handleDependencyDryRun">生成安装计划</el-button>
               <el-button @click="dependencyOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>

      <el-dialog :title="planTitle" v-model="planOpen" width="920px" append-to-body>
         <el-alert
            v-if="planResult.message"
            :title="planResult.message"
            :type="planResult.ok ? 'success' : 'warning'"
            show-icon
            :closable="false"
            class="mb16"
         />
         <el-descriptions :column="3" border class="mb16">
            <el-descriptions-item label="计划操作">{{ formatPluginOperation(planResult.operation) }}</el-descriptions-item>
            <el-descriptions-item label="执行插件">{{ planResult.requestedPluginIds.length }}</el-descriptions-item>
            <el-descriptions-item label="阻塞项">{{ planResult.blockerCount }}</el-descriptions-item>
            <el-descriptions-item label="执行顺序" :span="3">
               <el-tag
                  v-for="pluginId in planResult.executablePluginIds"
                  :key="pluginId"
                  class="plan-order-tag"
                  type="info"
               >{{ pluginId }}</el-tag>
               <span v-if="!planResult.executablePluginIds.length">-</span>
            </el-descriptions-item>
         </el-descriptions>

         <el-tabs>
            <el-tab-pane label="计划项">
               <el-table :data="planResult.items" size="small" border empty-text="暂无计划项">
                  <el-table-column label="顺序" prop="order" width="70" align="center" />
                  <el-table-column label="插件ID" prop="pluginId" width="140" :show-overflow-tooltip="true" />
                  <el-table-column label="插件名称" prop="name" min-width="150" :show-overflow-tooltip="true" />
                  <el-table-column label="版本" prop="version" width="100" align="center" />
                  <el-table-column label="显式选择" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.requested ? 'success' : 'info'">{{ scope.row.requested ? "是" : "依赖" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="可执行" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getPlanReadyTagType(scope.row.ready)">{{ scope.row.ready ? "是" : "否" }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="依赖" min-width="180" :show-overflow-tooltip="true">
                     <template #default="scope">
                        <span>{{ formatPlanDependencies(scope.row.dependencies) }}</span>
                     </template>
                  </el-table-column>
                  <el-table-column label="阻塞项" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="scope.row.blockers?.length ? 'danger' : 'success'">{{ scope.row.blockers?.length || 0 }}</el-tag>
                     </template>
                  </el-table-column>
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="阻塞原因">
               <el-table :data="planResult.blockers" size="small" border empty-text="暂无阻塞项">
                  <el-table-column label="插件ID" prop="pluginId" width="140" :show-overflow-tooltip="true" />
                  <el-table-column label="依赖插件" prop="dependencyId" width="140" :show-overflow-tooltip="true" />
                  <el-table-column label="状态" width="150" align="center">
                     <template #default="scope">
                        <el-tag type="danger">{{ getPlanBlockerStatusLabel(scope.row.status) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="说明" prop="message" min-width="320" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
            <el-tab-pane label="执行结果">
               <el-descriptions :column="4" border class="mb16">
                  <el-descriptions-item label="总数">{{ batchResult.summary.total }}</el-descriptions-item>
                  <el-descriptions-item label="成功">{{ batchResult.summary.succeeded }}</el-descriptions-item>
                  <el-descriptions-item label="失败">{{ batchResult.summary.failed }}</el-descriptions-item>
                  <el-descriptions-item label="跳过">{{ batchResult.summary.skipped }}</el-descriptions-item>
               </el-descriptions>
               <el-table :data="batchResult.executed" size="small" border empty-text="暂无执行记录">
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
                  <el-table-column label="说明" prop="message" min-width="220" :show-overflow-tooltip="true" />
                  <el-table-column label="建议" prop="suggestion" min-width="260" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>
         </el-tabs>

         <template #footer>
            <div class="dialog-footer">
               <el-switch
                  v-model="batchContinueOnError"
                  active-text="失败后继续"
                  inactive-text="失败即中止"
                  class="mr12"
               />
               <el-button
                  type="primary"
                  :disabled="!canExecuteBatchPlan"
                  :loading="planLoading"
                  @click="handleExecuteBatch(false)"
                  v-hasPermi="['system:plugin:edit']"
               >执行{{ formatPluginOperation(planResult.operation) }}</el-button>
               <el-button @click="planOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>

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

            <div class="plugin-audit-maintenance">
               <el-form :model="operationLogRetentionForm" :inline="true" label-width="84px" class="plugin-log-toolbar">
                  <el-form-item label="保留天数">
                     <el-input-number v-model="operationLogRetentionForm.retentionDays" :min="0" :max="3650" controls-position="right" style="width: 150px" />
                  </el-form-item>
                  <el-form-item>
                     <el-tag type="info">默认 {{ operationLogRetentionDefaultDays }} 天</el-tag>
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
            </div>

            <div class="plugin-audit-table">
               <div class="plugin-audit-table-toolbar">
                  <el-row :gutter="10" class="plugin-audit-table-actions">
                     <el-col :span="1.5">
                        <el-button type="warning" plain icon="Download" @click="handleOperationLogExport" v-hasPermi="['system:plugin:export']">导出</el-button>
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

      <el-dialog :title="configTitle" v-model="configOpen" width="720px" append-to-body>
         <el-form ref="configRef" :model="configForm" label-width="120px">
            <el-empty v-if="!configItems.length" description="暂无插件配置" />
            <el-form-item
               v-for="item in configItems"
               :key="item.key"
               :label="item.label || item.key"
               :prop="'values.' + item.key"
               :rules="item.required ? [{ required: true, message: '不能为空', trigger: 'blur' }] : []"
            >
               <el-switch v-if="item.type === 'boolean'" v-model="configForm.values[item.key]" />
               <el-input-number v-else-if="item.type === 'number'" v-model="configForm.values[item.key]" style="width: 220px" />
               <el-select v-else-if="item.type === 'select'" v-model="configForm.values[item.key]" style="width: 260px">
                  <el-option
                     v-for="option in item.options || []"
                     :key="String(option.value)"
                     :label="option.label"
                     :value="option.value"
                  />
               </el-select>
               <el-input
                  v-else-if="item.type === 'textarea' || item.type === 'json'"
                  v-model="configForm.values[item.key]"
                  type="textarea"
                  :rows="4"
               />
               <el-input
                  v-else
                  v-model="configForm.values[item.key]"
                  :type="item.type === 'password' || item.secret ? 'password' : 'text'"
                  show-password
               />
               <div v-if="item.description" class="config-help">{{ item.description }}</div>
            </el-form-item>
         </el-form>
         <template #footer>
            <div class="dialog-footer">
               <el-button
                  type="primary"
                  :loading="configLoading"
                  @click="submitConfig"
                  v-hasPermi="['system:plugin:edit']"
               >保 存</el-button>
               <el-button @click="configOpen = false">关 闭</el-button>
            </div>
         </template>
      </el-dialog>

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
                  v-if="pendingAction.type"
                  type="primary"
                  :loading="actionLoading"
                  @click="handleExecutePendingAction"
                  v-hasPermi="['system:plugin:edit']"
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
  disablePlugin,
  enablePlugin,
  getPlugin,
  getPluginConfig,
  getPluginOperationLog,
  installPluginDependencies,
  installPlugin,
  listPlugin,
  listPluginOperationLog,
  planPlugins,
  retainPluginOperationLog,
  uninstallPlugin,
  updatePluginConfig,
  upgradePlugin
} from "@/api/system/plugin";
import { getConfigKey } from "@/api/system/config";
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

const pluginList = ref([]);
const selectedPluginIds = ref([]);
const loading = ref(true);
const showSearch = ref(true);
const total = ref(0);
const detailOpen = ref(false);
const detail = ref({});
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
const planOpen = ref(false);
const planLoading = ref(false);
const planTitle = ref("插件依赖计划");
const planResult = ref(normalizePluginPlanResponse({}));
const batchContinueOnError = ref(false);
const batchResult = ref(normalizePluginBatchResponse({}));
const operationLogOpen = ref(false);
const operationLogShowSearch = ref(true);
const operationLogLoading = ref(false);
const operationLogList = ref([]);
const operationLogTotal = ref(0);
const operationLogDateRange = ref([]);
const operationLogDetailOpen = ref(false);
const operationLogDetail = ref({});
const operationLogRetentionLoading = ref(false);
const operationLogRetentionResult = ref({});
const operationLogRetentionDefaultDays = ref(180);
const configForm = reactive({
  values: {}
});
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

const canExecuteBatchPlan = computed(() => {
  return planResult.value.ok && planResult.value.executablePluginIds.length > 0;
});

/** 查询插件列表 */
function getList() {
  loading.value = true;
  listPlugin(queryParams.value).then(response => {
    pluginList.value = response.rows;
    total.value = response.total;
    loading.value = false;
  });
}

/** 多选框选中数据 */
function handleSelectionChange(selection) {
  selectedPluginIds.value = selection.map(item => item.pluginId).filter(Boolean);
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1;
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
  const operation = enabled ? "enable" : "disable";
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

/** 打开详情 */
function handleDetail(row) {
  getPlugin(row.pluginId).then(response => {
    detail.value = response.data;
    detailOpen.value = true;
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
    configForm.values = {};
    configs.forEach(item => {
      configForm.values[item.key] = item.value;
    });
    configOpen.value = true;
  }).finally(() => {
    configLoading.value = false;
  });
}

/** 保存插件配置 */
function submitConfig() {
  proxy.$refs["configRef"].validate(valid => {
    if (!valid) {
      return;
    }
    configLoading.value = true;
    updatePluginConfig(configPluginId.value, { values: configForm.values }).then(() => {
      proxy.$modal.msgSuccess("插件配置已保存");
      configOpen.value = false;
    }).finally(() => {
      configLoading.value = false;
    });
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
  }).finally(() => {
    dependencyLoading.value = false;
  });
}

/** 生成插件批量操作拓扑计划 */
function handlePlan(operation) {
  planLoading.value = true;
  planTitle.value = "插件" + formatPluginOperation(operation) + "计划";
  const pluginIds = getBatchTargetPluginIds();
  batchResult.value = normalizePluginBatchResponse({});
  planPlugins(operation, pluginIds).then(response => {
    planResult.value = normalizePluginPlanResponse(response.data);
    planOpen.value = true;
  }).finally(() => {
    planLoading.value = false;
  });
}

/** 获取批量目标插件ID */
function getBatchTargetPluginIds() {
  return selectedPluginIds.value.length ? selectedPluginIds.value : pluginList.value.map(item => item.pluginId).filter(Boolean);
}

/** 执行插件批量操作 */
function handleExecuteBatch(dryRun) {
  if (!canExecuteBatchPlan.value) {
    return;
  }
  const operation = planResult.value.operation;
  const pluginIds = planResult.value.executablePluginIds;
  proxy.$modal.confirm('确认要批量执行插件' + formatPluginOperation(operation) + '吗?').then(function () {
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
  }).finally(() => {
    operationLogLoading.value = false;
  });
}

/** 打开插件操作审计详情 */
function handleOperationLogDetail(row) {
  getPluginOperationLog(row.operationId).then(response => {
    operationLogDetail.value = normalizePluginOperationLogDetail(response.data || {});
    operationLogDetailOpen.value = true;
  });
}

/** 导出插件操作审计 */
function handleOperationLogExport() {
  proxy.download("system/plugin/operation-log/export", {
    ...buildOperationLogQueryParams(),
    exportLimit: 5000
  }, `plugin_operation_log_${new Date().getTime()}.xlsx`);
}

/** 预览插件操作审计保留策略 */
function handleOperationLogRetentionPreview() {
  operationLogRetentionLoading.value = true;
  retainPluginOperationLog({
    retentionDays: operationLogRetentionForm.retentionDays,
    dryRun: true
  }).then(response => {
    operationLogRetentionResult.value = response.data || {};
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
      uninstall: uninstallPlugin
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

/** 从详情重新启用异常插件 */
function handleEnableFromDetail() {
  const pluginId = detail.value.pluginId;
  proxy.$modal.confirm('确认要重新启用"' + detail.value.pluginName + '"插件吗? 最近错误将被清除。').then(function () {
    return enablePlugin(pluginId);
  }).then(() => {
    proxy.$modal.msgSuccess("重新启用成功");
    detailOpen.value = false;
    getList();
  });
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
  return !row.installedVersion || row.status === "discovered";
}

function canUpgrade(row) {
  return row.status === "pending_upgrade";
}

function canUninstall(row) {
  return row.installedVersion && row.enabled === "0";
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
  return {
    ok: false,
    pluginId: context.pluginId,
    operation: context.operation,
    dependencyOk: false,
    structureOk: undefined,
    menuConflictOk: undefined,
    error: {
      message,
      suggestion: "请先执行插件检查，确认目录结构、依赖和菜单权限冲突后再重试。",
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

.config-help {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 18px;
}

.plan-order-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

.mr12 {
  margin-right: 12px;
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

.plugin-audit-search,
.plugin-audit-maintenance {
  padding: 12px 12px 4px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.plugin-audit-search {
  background: #fff;
}

.plugin-audit-maintenance {
  background: #f8f9fb;
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
</style>
