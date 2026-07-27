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
         <div class="dependency-summary-item">
            <span class="dependency-summary-label">安装策略</span>
            <el-tag v-if="policy" :type="policyTagType">{{ policy.mode || "-" }}</el-tag>
            <span v-else class="dependency-summary-value">-</span>
         </div>
      </div>
      <el-alert
         v-if="policy"
         :title="policySummaryTitle"
         :type="policyAllowed ? 'success' : 'warning'"
         show-icon
         :closable="false"
         class="mb16"
      >
         <template #default>
            <div v-if="policyMessages.length" class="dependency-policy-messages">
               <div v-for="message in policyMessages" :key="message">{{ message }}</div>
            </div>
            <div v-if="policyNextStep" class="dependency-policy-next">{{ policyNextStep }}</div>
         </template>
      </el-alert>
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
         <el-tab-pane v-if="policy" label="策略判定">
            <el-descriptions :column="2" border size="small" class="mb16">
               <el-descriptions-item label="策略模式">{{ policy.mode || "-" }}</el-descriptions-item>
               <el-descriptions-item label="允许执行">
                  <el-tag :type="policyAllowed ? 'success' : 'danger'">{{ policyAllowed ? "允许" : "阻断" }}</el-tag>
               </el-descriptions-item>
               <el-descriptions-item label="阻断原因">{{ formatPolicyList(policy.reasons) }}</el-descriptions-item>
               <el-descriptions-item label="前置要求">{{ formatPolicyList(policy.requirements) }}</el-descriptions-item>
               <el-descriptions-item label="风险提示">{{ formatPolicyList(policy.warnings) }}</el-descriptions-item>
            </el-descriptions>
            <el-table :data="policy.items || []" size="small" border empty-text="暂无策略项">
               <el-table-column label="类型" prop="kind" width="90" align="center" />
               <el-table-column label="依赖" prop="requirement" min-width="180" :show-overflow-tooltip="true" />
               <el-table-column label="判定" width="90" align="center">
                  <template #default="scope">
                     <el-tag :type="scope.row.allowed ? 'success' : 'danger'">{{ scope.row.allowed ? "允许" : "阻断" }}</el-tag>
                  </template>
               </el-table-column>
               <el-table-column label="锁定版本" min-width="120" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.lockedVersion || "-" }}</template>
               </el-table-column>
               <el-table-column label="离线制品" min-width="220" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.artifactPath || "-" }}</template>
               </el-table-column>
               <el-table-column label="说明" min-width="260" :show-overflow-tooltip="true">
                  <template #default="scope">{{ formatPolicyItemMessage(scope.row) }}</template>
               </el-table-column>
            </el-table>
         </el-tab-pane>
      </el-tabs>
      <template #footer>
         <div class="dialog-footer">
            <el-button type="primary" :disabled="isCapabilityOperationBlocked(result.capability, 'dependency_install')" :loading="loading" @click="emit('dry-run')">生成安装计划</el-button>
            <el-button
               type="success"
               :disabled="!canInstall"
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

const policy = computed(() => {
  const policyPayload = props.result.policy;
  return policyPayload && typeof policyPayload === "object" ? policyPayload : null;
});

const policyAllowed = computed(() => policy.value?.allowed === true);

const policyTagType = computed(() => policyAllowed.value ? "success" : "warning");

const policySummaryTitle = computed(() => policyAllowed.value ? "策略允许执行真实安装" : "策略已阻断真实安装");

const policyMessages = computed(() => {
  if (!policy.value) {
    return [];
  }
  return [
    ...(Array.isArray(policy.value.reasons) ? policy.value.reasons : []),
    ...(Array.isArray(policy.value.requirements) ? policy.value.requirements : []),
    ...(Array.isArray(policy.value.warnings) ? policy.value.warnings : [])
  ];
});

const policyNextStep = computed(() => {
  if (!policy.value || policyAllowed.value) {
    return "";
  }
  if (policy.value.mode === "plan_only") {
    return "Web 管理端仅生成安装计划；真实安装请使用 CLI install-deps 受控执行。";
  }
  return "请按策略要求补齐确认参数、锁文件或离线制品后重试。";
});

const canInstall = computed(() => {
  return !props.isCapabilityOperationBlocked(props.result.capability, "dependency_install")
    && Array.isArray(props.result.plan)
    && props.result.plan.length > 0
    && policy.value?.allowed !== false;
});

function formatPolicyList(items) {
  return Array.isArray(items) && items.length ? items.join("；") : "-";
}

function formatPolicyItemMessage(item) {
  return formatPolicyList([
    ...(Array.isArray(item.reasons) ? item.reasons : []),
    ...(Array.isArray(item.requirements) ? item.requirements : []),
    ...(Array.isArray(item.warnings) ? item.warnings : [])
  ]);
}

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
  grid-template-columns: repeat(5, minmax(0, 1fr));
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

.dependency-policy-messages {
  display: grid;
  gap: 4px;
}

.dependency-policy-next {
  margin-top: 6px;
  color: #606266;
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
