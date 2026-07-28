<template>
   <el-dialog :title="title" :model-value="modelValue" width="920px" append-to-body @update:model-value="emit('update:modelValue', $event)">
      <el-alert
         v-if="result.message"
         :title="result.message"
         :type="result.ok ? 'success' : 'warning'"
         show-icon
         :closable="false"
         class="mb16"
      />

      <el-skeleton v-if="loading" :rows="6" animated />
      <template v-else>
         <div class="diagnostic-summary">
            <div class="diagnostic-summary-item">
               <span class="diagnostic-summary-label">插件ID</span>
               <span class="diagnostic-summary-value">{{ result.pluginId || "-" }}</span>
            </div>
            <div class="diagnostic-summary-item">
               <span class="diagnostic-summary-label">结果</span>
               <el-tag :type="result.ok ? 'success' : 'danger'">{{ result.ok ? "正常" : "异常" }}</el-tag>
            </div>
            <div v-if="health" class="diagnostic-summary-item">
               <span class="diagnostic-summary-label">状态</span>
               <span class="diagnostic-summary-value">{{ health.status || "-" }}</span>
            </div>
            <div v-if="health" class="diagnostic-summary-item">
               <span class="diagnostic-summary-label">耗时</span>
               <span class="diagnostic-summary-value">{{ health.durationMs ?? "-" }}ms</span>
            </div>
         </div>

         <el-tabs>
            <el-tab-pane v-if="health" label="健康状态">
               <el-descriptions :column="2" border class="mb16">
                  <el-descriptions-item label="检查器">{{ health.checker || "-" }}</el-descriptions-item>
                  <el-descriptions-item label="状态">{{ health.status || "-" }}</el-descriptions-item>
                  <el-descriptions-item label="说明" :span="2">{{ health.message || "-" }}</el-descriptions-item>
                  <el-descriptions-item label="错误" :span="2">{{ health.error || "-" }}</el-descriptions-item>
               </el-descriptions>
               <el-input :model-value="formatJson(health.details)" type="textarea" :rows="8" readonly />
            </el-tab-pane>

            <el-tab-pane v-if="diagnose" label="检查摘要">
               <el-descriptions :column="3" border class="mb16">
                  <el-descriptions-item label="依赖">{{ formatBoolean(diagnose.check?.dependencyOk) }}</el-descriptions-item>
                  <el-descriptions-item label="Manifest">{{ formatBoolean(diagnose.check?.manifestOk) }}</el-descriptions-item>
                  <el-descriptions-item label="结构">{{ formatBoolean(diagnose.check?.structureOk) }}</el-descriptions-item>
                  <el-descriptions-item label="插件依赖">{{ formatBoolean(diagnose.check?.pluginDependencyOk) }}</el-descriptions-item>
                  <el-descriptions-item label="菜单冲突">{{ formatBoolean(diagnose.check?.menuConflictOk) }}</el-descriptions-item>
                  <el-descriptions-item label="配置项">{{ diagnose.config?.summary?.total ?? "-" }}</el-descriptions-item>
               </el-descriptions>
               <el-table :data="validationItems" size="small" border empty-text="暂无诊断问题">
                  <el-table-column label="分类" prop="category" width="120" align="center" />
                  <el-table-column label="等级" width="90" align="center">
                     <template #default="scope">
                        <el-tag :type="getValidationLevelTagType(scope.row.level)">{{ getValidationLevelLabel(scope.row.level) }}</el-tag>
                     </template>
                  </el-table-column>
                  <el-table-column label="类型" prop="kind" width="170" :show-overflow-tooltip="true" />
                  <el-table-column label="对象" prop="value" min-width="180" :show-overflow-tooltip="true" />
                  <el-table-column label="说明" prop="message" min-width="260" :show-overflow-tooltip="true" />
               </el-table>
            </el-tab-pane>

            <el-tab-pane v-if="diagnose" label="菜单计划">
               <el-input :model-value="formatJson(diagnose.menuPlan)" type="textarea" :rows="12" readonly />
            </el-tab-pane>

            <el-tab-pane label="原始数据">
               <el-input :model-value="formatJson(result)" type="textarea" :rows="14" readonly />
            </el-tab-pane>
         </el-tabs>
      </template>

      <template #footer>
         <div class="dialog-footer">
            <el-button @click="emit('update:modelValue', false)">关 闭</el-button>
         </div>
      </template>
   </el-dialog>
</template>

<script setup name="PluginDiagnosticDialog">
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: "插件诊断"
  },
  result: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  },
  formatJson: {
    type: Function,
    required: true
  },
  formatBoolean: {
    type: Function,
    required: true
  },
  getValidationLevelLabel: {
    type: Function,
    required: true
  },
  getValidationLevelTagType: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["update:modelValue"]);

const health = computed(() => props.result.health || null);
const diagnose = computed(() => props.result.info || props.result.check ? props.result : null);

const validationItems = computed(() => {
  const check = diagnose.value?.check || {};
  const groups = [
    ["依赖", check.dependencies],
    ["Manifest 错误", check.manifestIssues],
    ["Manifest 警告", check.manifestWarnings],
    ["插件依赖", check.pluginDependencyErrors],
    ["结构", check.structureErrors],
    ["菜单冲突", check.menuConflicts]
  ];

  return groups.flatMap(([category, items]) =>
    Array.isArray(items)
      ? items.map(item => ({
          category,
          level: item.level || (category.includes("警告") ? "warning" : "error"),
          kind: item.kind || item.name || item.status || "-",
          value: item.value || item.requirement || item.path || item.pluginId || item.perms || "-",
          message: item.message || item.suggestion || item.reason || ""
        }))
      : []
  );
});
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.diagnostic-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.diagnostic-summary-item {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f8f9fb;
}

.diagnostic-summary-label {
  display: block;
  margin-bottom: 6px;
  color: #909399;
  font-size: 12px;
}

.diagnostic-summary-value {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}
</style>
