<template>
   <el-dialog :title="title" :model-value="modelValue" width="920px" append-to-body @update:model-value="emit('update:modelValue', $event)">
      <el-alert
         v-if="planResult.message"
         :title="planResult.message"
         :type="planResult.ok ? 'success' : 'warning'"
         show-icon
         :closable="false"
         class="mb16"
      />
      <div class="plan-summary">
         <div class="plan-summary-item">
            <span class="plan-summary-label">计划操作</span>
            <span class="plan-summary-value">{{ formatPluginOperation(planResult.operation) }}</span>
         </div>
         <div class="plan-summary-item">
            <span class="plan-summary-label">目标插件</span>
            <span class="plan-summary-value">{{ planResult.requestedPluginIds.length }}</span>
         </div>
         <div class="plan-summary-item">
            <span class="plan-summary-label">可执行</span>
            <span class="plan-summary-value">{{ planResult.executablePluginIds.length }}</span>
         </div>
         <div class="plan-summary-item">
            <span class="plan-summary-label">阻塞项</span>
            <span class="plan-summary-value is-danger">{{ planResult.blockerCount }}</span>
         </div>
      </div>
      <el-descriptions :column="1" border class="mb16">
         <el-descriptions-item label="目标范围">{{ formatPluginIdsForDisplay(planResult.requestedPluginIds) }}</el-descriptions-item>
         <el-descriptions-item label="执行顺序">
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
               :model-value="continueOnError"
               active-text="失败后继续"
               inactive-text="失败即中止"
               class="mr12"
               @update:model-value="emit('update:continueOnError', $event)"
            />
            <el-button
               type="primary"
               :disabled="!canExecuteBatchPlan"
               :loading="loading"
               @click="emit('execute')"
               v-hasPermi="['system:plugin:edit']"
            >执行计划：{{ formatPluginOperation(planResult.operation) }}</el-button>
            <el-button @click="emit('update:modelValue', false)">关 闭</el-button>
         </div>
      </template>
   </el-dialog>
</template>

<script setup name="PluginPlanDialog">
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: "插件依赖计划"
  },
  planResult: {
    type: Object,
    required: true
  },
  batchResult: {
    type: Object,
    required: true
  },
  continueOnError: {
    type: Boolean,
    default: false
  },
  loading: {
    type: Boolean,
    default: false
  },
  formatPluginOperation: {
    type: Function,
    required: true
  },
  formatPluginIdsForDisplay: {
    type: Function,
    required: true
  },
  formatPlanDependencies: {
    type: Function,
    required: true
  },
  getPlanReadyTagType: {
    type: Function,
    required: true
  },
  getPlanBlockerStatusLabel: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["update:modelValue", "update:continueOnError", "execute"]);

const canExecuteBatchPlan = computed(() => {
  return props.planResult.ok && props.planResult.executablePluginIds.length > 0;
});
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.mr12 {
  margin-right: 12px;
}

.plan-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.plan-summary-item {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f8f9fb;
}

.plan-summary-label {
  display: block;
  margin-bottom: 6px;
  color: #909399;
  font-size: 12px;
}

.plan-summary-value {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}

.plan-summary-value.is-danger {
  color: #f56c6c;
}

.plan-order-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

@media (max-width: 1200px) {
  .plan-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .plan-summary {
    grid-template-columns: 1fr;
  }
}
</style>
