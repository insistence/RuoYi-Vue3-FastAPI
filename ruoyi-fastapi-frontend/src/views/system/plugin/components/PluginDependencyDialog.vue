<template>
   <el-dialog title="插件依赖" :model-value="modelValue" width="860px" append-to-body @update:model-value="emit('update:modelValue', $event)">
      <el-alert
         v-if="result.message"
         :title="result.message"
         :type="result.ok ? 'success' : 'warning'"
         show-icon
         :closable="false"
         class="mb16"
      />
      <div class="dependency-summary">
         <div class="dependency-summary-item">
            <span class="dependency-summary-label">插件ID</span>
            <span class="dependency-summary-value">{{ result.pluginId || "-" }}</span>
         </div>
         <div class="dependency-summary-item">
            <span class="dependency-summary-label">依赖检查</span>
            <el-tag :type="result.dependencyOk ? 'success' : 'danger'">{{ formatBoolean(result.dependencyOk) }}</el-tag>
         </div>
         <div class="dependency-summary-item">
            <span class="dependency-summary-label">缺失依赖</span>
            <span class="dependency-summary-value is-danger">{{ dependencyProblemCount }}</span>
         </div>
         <div class="dependency-summary-item">
            <span class="dependency-summary-label">安装计划</span>
            <span class="dependency-summary-value">{{ result.planCount ?? (result.plan || []).length }}</span>
         </div>
      </div>
      <el-tabs>
         <el-tab-pane label="依赖状态">
            <el-table :data="result.dependencies || []" size="small" border empty-text="暂无依赖声明">
               <el-table-column label="类型" prop="kind" width="90" align="center" />
               <el-table-column label="依赖" prop="requirement" min-width="200" :show-overflow-tooltip="true" />
               <el-table-column label="已安装版本" min-width="130" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.installedVersion || "-" }}</template>
               </el-table-column>
               <el-table-column label="安装状态" width="100" align="center">
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
            <el-table :data="result.plan || []" size="small" border empty-text="暂无安装计划">
               <el-table-column label="类型" prop="kind" width="90" align="center" />
               <el-table-column label="依赖" prop="requirement" min-width="150" :show-overflow-tooltip="true" />
               <el-table-column label="工作目录" prop="workdir" min-width="220" :show-overflow-tooltip="true" />
               <el-table-column label="命令" min-width="300">
                  <template #default="scope">
                     <div class="dependency-command-cell">
                        <span class="dependency-command-text">{{ scope.row.commandText || "-" }}</span>
                        <el-tooltip content="复制命令" placement="top">
                           <el-button
                              link
                              type="primary"
                              icon="CopyDocument"
                              :disabled="!scope.row.commandText"
                              @click="copyDependencyCommand(scope.row.commandText)"
                           />
                        </el-tooltip>
                     </div>
                  </template>
               </el-table-column>
            </el-table>
         </el-tab-pane>
      </el-tabs>
      <template #footer>
         <div class="dialog-footer">
            <el-button type="primary" :disabled="isCapabilityOperationBlocked(result.capability, 'dependency_install')" :loading="loading" @click="emit('dry-run')">生成安装计划</el-button>
            <el-button
               type="success"
               :disabled="isCapabilityOperationBlocked(result.capability, 'dependency_install') || !(result.plan || []).length"
               :loading="loading"
               @click="emit('install')"
               v-hasPermi="['system:plugin:edit']"
            >执行依赖安装</el-button>
            <el-button @click="emit('update:modelValue', false)">关 闭</el-button>
         </div>
      </template>
   </el-dialog>
</template>

<script setup name="PluginDependencyDialog">
import { computed } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  result: {
    type: Object,
    default: () => ({})
  },
  loading: {
    type: Boolean,
    default: false
  },
  isCapabilityOperationBlocked: {
    type: Function,
    required: true
  },
  formatBoolean: {
    type: Function,
    required: true
  },
  getDependencyTagType: {
    type: Function,
    required: true
  },
  formatDependencyInstalled: {
    type: Function,
    required: true
  },
  formatDependencyVersionSatisfied: {
    type: Function,
    required: true
  }
});

const emit = defineEmits(["update:modelValue", "dry-run", "install"]);

const dependencyProblemCount = computed(() => {
  const dependencies = Array.isArray(props.result.dependencies) ? props.result.dependencies : [];
  return dependencies.filter(item => item.status !== "skipped" && !item.ok).length;
});

function copyDependencyCommand(commandText) {
  if (!commandText) {
    return;
  }
  copyText(commandText).then(() => {
    ElMessage.success("命令已复制");
  }).catch(() => {
    ElMessage.error("复制失败，请手动复制命令");
  });
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!ok) {
    throw new Error("copy failed");
  }
}
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.dependency-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.dependency-summary-item {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f8f9fb;
}

.dependency-summary-label {
  display: block;
  margin-bottom: 6px;
  color: #909399;
  font-size: 12px;
}

.dependency-summary-value {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}

.dependency-summary-value.is-danger {
  color: #f56c6c;
}

.dependency-command-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dependency-command-text {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #303133;
  font-family: monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1200px) {
  .dependency-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .dependency-summary {
    grid-template-columns: 1fr;
  }
}
</style>
