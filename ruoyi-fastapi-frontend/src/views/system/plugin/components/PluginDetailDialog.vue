<template>
   <el-dialog title="插件详情" :model-value="modelValue" width="920px" append-to-body @update:model-value="emit('update:modelValue', $event)">
      <el-tabs>
         <el-tab-pane label="概览">
            <div class="detail-section-title detail-section-title-first">基础信息</div>
            <el-descriptions :column="2" border class="mb16">
               <el-descriptions-item label="插件ID">{{ detail.pluginId }}</el-descriptions-item>
               <el-descriptions-item label="插件名称">{{ detail.pluginName }}</el-descriptions-item>
               <el-descriptions-item label="源码版本">{{ detail.version }}</el-descriptions-item>
               <el-descriptions-item label="已安装版本">{{ detail.installedVersion || "-" }}</el-descriptions-item>
               <el-descriptions-item label="启用设置">{{ detail.enabled === "0" ? "启用" : "停用" }}</el-descriptions-item>
               <el-descriptions-item label="插件状态">{{ getStatusLabel(detail.status) }}</el-descriptions-item>
               <el-descriptions-item label="来源">{{ detail.source || "-" }}</el-descriptions-item>
               <el-descriptions-item label="更新时间">{{ formatPluginTime(detail.updateTime) }}</el-descriptions-item>
               <el-descriptions-item label="分类">{{ detail.metadata?.category || "-" }}</el-descriptions-item>
               <el-descriptions-item label="标签">{{ formatDetailTags(detail.metadata?.tags) }}</el-descriptions-item>
               <el-descriptions-item label="作者">{{ detail.metadata?.author || "-" }}</el-descriptions-item>
               <el-descriptions-item label="许可证">{{ detail.metadata?.license || "-" }}</el-descriptions-item>
               <el-descriptions-item label="最近错误" :span="2">{{ detail.lastError || "-" }}</el-descriptions-item>
               <el-descriptions-item label="插件说明" :span="2">{{ detail.description || "-" }}</el-descriptions-item>
            </el-descriptions>

            <div class="detail-section-title">后端声明</div>
            <el-descriptions :column="2" border class="mb16">
               <el-descriptions-item label="后端路径" :span="2">{{ detail.backendPath || "-" }}</el-descriptions-item>
               <el-descriptions-item label="后端模块" :span="2">{{ detail.backend?.module || "-" }}</el-descriptions-item>
               <el-descriptions-item label="自动扫描路由">{{ formatYesNo(detail.backend?.autoScanRouters) }}</el-descriptions-item>
               <el-descriptions-item label="定时任务">{{ detail.backend?.jobs?.length || 0 }}</el-descriptions-item>
            </el-descriptions>

            <div class="detail-section-title">前端声明</div>
            <el-descriptions :column="2" border>
               <el-descriptions-item label="前端路径" :span="2">{{ detail.frontendPath || "-" }}</el-descriptions-item>
               <el-descriptions-item label="前端插件ID">{{ detail.frontend?.pluginId || "-" }}</el-descriptions-item>
               <el-descriptions-item label="前端基础路径">{{ detail.frontend?.basePath || "-" }}</el-descriptions-item>
               <el-descriptions-item label="视图目录">{{ detail.frontend?.viewsPath || "-" }}</el-descriptions-item>
               <el-descriptions-item label="API 目录">{{ detail.frontend?.apiPath || "-" }}</el-descriptions-item>
               <el-descriptions-item label="前端交付">{{ getFrontendDeliveryLabel(detail.frontend?.delivery) }}</el-descriptions-item>
               <el-descriptions-item label="菜单声明">{{ detail.frontend?.menus?.length || 0 }}</el-descriptions-item>
            </el-descriptions>
         </el-tab-pane>
         <el-tab-pane label="菜单">
            <el-table :data="detail.frontend?.menus || []" size="small" border empty-text="暂无菜单声明">
               <el-table-column label="名称" prop="name" min-width="140" :show-overflow-tooltip="true" />
               <el-table-column label="路径" prop="path" min-width="140" :show-overflow-tooltip="true" />
               <el-table-column label="组件" prop="component" min-width="180" :show-overflow-tooltip="true" />
               <el-table-column label="权限" prop="perms" min-width="160" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.perms || "-" }}</template>
               </el-table-column>
               <el-table-column label="类型" prop="type" width="70" align="center" />
               <el-table-column label="排序" prop="orderNum" width="70" align="center" />
            </el-table>
         </el-tab-pane>
         <el-tab-pane label="权限">
            <el-table :data="detail.permissions || []" size="small" border empty-text="暂无权限声明">
               <el-table-column label="权限标识" prop="code" min-width="180" :show-overflow-tooltip="true" />
               <el-table-column label="展示名称" prop="name" min-width="140" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.name || "-" }}</template>
               </el-table-column>
               <el-table-column label="说明" prop="description" min-width="220" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.description || "-" }}</template>
               </el-table-column>
            </el-table>
         </el-tab-pane>
         <el-tab-pane label="配置">
            <el-table :data="detail.config || []" size="small" border empty-text="暂无配置声明">
               <el-table-column label="配置键" prop="key" min-width="160" :show-overflow-tooltip="true" />
               <el-table-column label="名称" prop="label" min-width="140" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.label || "-" }}</template>
               </el-table-column>
               <el-table-column label="类型" prop="type" width="100" align="center" />
               <el-table-column label="必填" width="70" align="center">
                  <template #default="scope">
                     <el-tag :type="scope.row.required ? 'warning' : 'info'">{{ scope.row.required ? "是" : "否" }}</el-tag>
                  </template>
               </el-table-column>
               <el-table-column label="敏感" width="70" align="center">
                  <template #default="scope">
                     <el-tag :type="scope.row.secret ? 'warning' : 'info'">{{ scope.row.secret ? "是" : "否" }}</el-tag>
                  </template>
               </el-table-column>
               <el-table-column label="默认值" min-width="160" :show-overflow-tooltip="true">
                  <template #default="scope">{{ formatConfigDefaultValue(scope.row) }}</template>
               </el-table-column>
               <el-table-column label="约束" min-width="200" :show-overflow-tooltip="true">
                  <template #default="scope">{{ formatConfigConstraint(scope.row) }}</template>
               </el-table-column>
               <el-table-column label="说明" prop="description" min-width="220" :show-overflow-tooltip="true" />
            </el-table>
         </el-tab-pane>
         <el-tab-pane label="依赖">
            <div class="detail-section-title detail-section-title-first">运行依赖</div>
            <el-table :data="detailDependencyRows" size="small" border empty-text="暂无运行依赖声明">
               <el-table-column label="类型" prop="label" width="120" align="center" />
               <el-table-column label="数量" width="80" align="center">
                  <template #default="scope">{{ scope.row.items.length }}</template>
               </el-table-column>
               <el-table-column label="依赖项" min-width="520">
                  <template #default="scope">
                     <div class="detail-tag-list">
                        <el-tag
                           v-for="item in scope.row.items"
                           :key="scope.row.kind + item"
                           :type="scope.row.tagType"
                           effect="plain"
                        >{{ item }}</el-tag>
                        <span v-if="!scope.row.items.length" class="detail-empty-text">-</span>
                     </div>
                  </template>
               </el-table-column>
            </el-table>

            <div class="detail-section-title">数据库脚本</div>
            <el-table :data="detailScriptRows" size="small" border empty-text="暂无数据库脚本声明">
               <el-table-column label="类型" prop="label" width="120" align="center" />
               <el-table-column label="数量" width="80" align="center">
                  <template #default="scope">{{ scope.row.items.length }}</template>
               </el-table-column>
               <el-table-column label="脚本" min-width="520">
                  <template #default="scope">
                     <div class="detail-tag-list">
                        <el-tag
                           v-for="item in scope.row.items"
                           :key="scope.row.kind + item"
                           type="info"
                           effect="plain"
                        >{{ item }}</el-tag>
                        <span v-if="!scope.row.items.length" class="detail-empty-text">-</span>
                     </div>
                  </template>
               </el-table-column>
            </el-table>

            <div class="detail-section-title">执行历史</div>
            <el-table v-loading="migrationLoading" :data="migrationHistory" size="small" border empty-text="暂无 migration 执行历史">
               <el-table-column label="脚本" prop="migrationPath" min-width="220" :show-overflow-tooltip="true" />
               <el-table-column label="版本" prop="version" width="100" align="center">
                  <template #default="scope">{{ scope.row.version || "-" }}</template>
               </el-table-column>
               <el-table-column label="状态" width="120" align="center">
                  <template #default="scope">
                     <el-tag :type="getMigrationStatusTagType(scope.row.status)">
                        {{ getMigrationStatusLabel(scope.row.status) }}
                     </el-tag>
                  </template>
               </el-table-column>
               <el-table-column label="次数" prop="attemptCount" width="70" align="center">
                  <template #default="scope">{{ scope.row.attemptCount ?? 0 }}</template>
               </el-table-column>
               <el-table-column label="语句" prop="statementCount" width="70" align="center">
                  <template #default="scope">{{ scope.row.statementCount ?? 0 }}</template>
               </el-table-column>
               <el-table-column label="开始时间" width="160" align="center">
                  <template #default="scope">{{ formatPluginTime(scope.row.startedTime || scope.row.createTime) }}</template>
               </el-table-column>
               <el-table-column label="结束时间" width="160" align="center">
                  <template #default="scope">{{ formatPluginTime(scope.row.finishedTime) }}</template>
               </el-table-column>
               <el-table-column label="错误信息" min-width="220" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.errorMessage || "-" }}</template>
               </el-table-column>
               <el-table-column label="操作" width="110" align="center" fixed="right">
                  <template #default="scope">
                     <div class="detail-row-actions">
                        <el-tooltip v-if="canMarkMigrationSuccess(scope.row)" content="标记成功" placement="top">
                           <el-button
                              link
                              type="success"
                              icon="CircleCheck"
                              @click="emit('mark-migration-success', scope.row)"
                              v-hasPermi="['system:plugin:edit']"
                           />
                        </el-tooltip>
                        <el-tooltip v-if="canMarkMigrationFailed(scope.row)" content="标记失败" placement="top">
                           <el-button
                              link
                              type="danger"
                              icon="CircleClose"
                              @click="emit('mark-migration-failed', scope.row)"
                              v-hasPermi="['system:plugin:edit']"
                           />
                        </el-tooltip>
                        <span v-if="!canMarkMigrationSuccess(scope.row) && !canMarkMigrationFailed(scope.row)">-</span>
                     </div>
                  </template>
               </el-table-column>
            </el-table>

            <div class="detail-section-title">插件依赖</div>
            <el-table :data="detail.pluginDependencies || []" size="small" border empty-text="暂无插件依赖">
               <el-table-column label="插件ID" prop="id" width="160" :show-overflow-tooltip="true" />
               <el-table-column label="版本约束" prop="version" width="140" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.version || "-" }}</template>
               </el-table-column>
               <el-table-column label="说明" prop="description" min-width="220" :show-overflow-tooltip="true" />
            </el-table>
            <div class="detail-section-title">定时任务</div>
            <el-table :data="detail.backend?.jobs || []" size="small" border empty-text="暂无定时任务声明">
               <el-table-column label="任务ID" prop="id" width="140" :show-overflow-tooltip="true" />
               <el-table-column label="名称" prop="name" min-width="140" :show-overflow-tooltip="true">
                  <template #default="scope">{{ scope.row.name || "-" }}</template>
               </el-table-column>
               <el-table-column label="调用目标" prop="callable" min-width="220" :show-overflow-tooltip="true" />
               <el-table-column label="Cron" prop="cronExpression" width="150" :show-overflow-tooltip="true" />
               <el-table-column label="默认启用" width="90" align="center">
                  <template #default="scope">
                     <el-tag :type="scope.row.enabled ? 'success' : 'info'">{{ scope.row.enabled ? "是" : "否" }}</el-tag>
                  </template>
               </el-table-column>
               <el-table-column label="说明" prop="description" min-width="220" :show-overflow-tooltip="true" />
            </el-table>
         </el-tab-pane>
      </el-tabs>
      <template #footer>
         <div class="dialog-footer">
            <el-button
               v-if="detail.status === 'error'"
               type="primary"
               @click="emit('repair')"
               v-hasPermi="['system:plugin:edit']"
            >重新安装修复</el-button>
            <el-button @click="emit('update:modelValue', false)">关 闭</el-button>
         </div>
      </template>
   </el-dialog>
</template>

<script setup name="PluginDetailDialog">
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  detail: {
    type: Object,
    default: () => ({})
  },
  getStatusLabel: {
    type: Function,
    required: true
  },
  formatPluginTime: {
    type: Function,
    required: true
  },
  formatConfigDefaultValue: {
    type: Function,
    required: true
  },
  formatConfigConstraint: {
    type: Function,
    required: true
  },
  migrationHistory: {
    type: Array,
    default: () => []
  },
  migrationLoading: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(["update:modelValue", "repair", "mark-migration-success", "mark-migration-failed"]);

const detailDependencyRows = computed(() => {
  const dependencies = props.detail.dependencies || {};
  return [
    {
      kind: "python",
      label: "Python",
      tagType: "success",
      items: normalizeDetailItems(dependencies.python)
    },
    {
      kind: "npm",
      label: "npm",
      tagType: "primary",
      items: normalizeDetailItems(dependencies.npm)
    },
    {
      kind: "npmDev",
      label: "npmDev",
      tagType: "warning",
      items: normalizeDetailItems(dependencies.npmDev)
    }
  ];
});

const detailScriptRows = computed(() => {
  const backend = props.detail.backend || {};
  return [
    {
      kind: "migration",
      label: "Migration",
      items: normalizeDetailItems(backend.migrations)
    },
    {
      kind: "seed",
      label: "Seed",
      items: normalizeDetailItems(backend.seeds)
    }
  ];
});

function formatYesNo(value) {
  if (value === undefined || value === null) {
    return "-";
  }
  return value ? "是" : "否";
}

function formatDetailTags(tags) {
  return Array.isArray(tags) && tags.length ? tags.join(", ") : "-";
}

function getFrontendDeliveryLabel(delivery) {
  if (!delivery) {
    return "-";
  }
  const typeMap = {
    none: "无前端资源",
    source: "源码交付"
  };
  return typeMap[delivery.type] || delivery.type || "-";
}

function normalizeDetailItems(items) {
  return Array.isArray(items) ? items.filter(Boolean) : [];
}

function getMigrationStatusLabel(status) {
  const statusMap = {
    running: "执行中/中断",
    success: "成功",
    failed: "失败",
    unknown: "未知"
  };
  return statusMap[status] || status || "-";
}

function getMigrationStatusTagType(status) {
  const statusMap = {
    running: "warning",
    success: "success",
    failed: "danger",
    unknown: "info"
  };
  return statusMap[status] || "info";
}

function canMarkMigrationSuccess(row) {
  return ["running", "failed"].includes(row?.status);
}

function canMarkMigrationFailed(row) {
  return row?.status === "running";
}
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.detail-section-title {
  margin: 14px 0 8px;
  color: #606266;
  font-size: 13px;
  font-weight: 600;
}

.detail-section-title-first {
  margin-top: 0;
}

.detail-tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 24px;
  align-items: center;
}

.detail-empty-text {
  color: #909399;
}

.detail-row-actions {
  display: flex;
  justify-content: center;
  gap: 4px;
}
</style>
