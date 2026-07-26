<template>
  <el-drawer
    :title="drawerTitle"
    v-model="visible"
    size="70%"
    append-to-body
    :close-on-click-modal="!saving"
  >
    <el-alert
      :title="
        batchMode
          ? '批量操作仅覆盖所选文件的显式授权；内置权限仍按各文件规则生效。'
          : '内置权限只读展示；管理员和所有者不可被拒绝，启用的上传人权限可被匹配的显式拒绝覆盖。'
      "
      type="info"
      :closable="false"
      show-icon
      class="mb8"
    />
    <div v-if="!batchMode" class="permission-section">
      <div class="permission-section__title">内置权限</div>
      <el-table v-loading="loading" :data="builtinPermissions" border>
        <el-table-column label="权限来源" align="center" width="110">
          <template #default="scope">
            <el-tag :type="builtinSourceType(scope.row.source)" effect="plain">
              {{ builtinSourceLabel(scope.row.source) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="权限主体" align="center" min-width="180">
          <template #default="scope">
            {{ scope.row.subjectName || scope.row.subjectId || "-" }}
          </template>
        </el-table-column>
        <el-table-column label="规则" align="center" width="110">
          <template #default="scope">
            <el-tag
              :type="scope.row.enabled ? 'success' : 'info'"
              effect="plain"
            >
              {{ scope.row.enabled ? "允许下载" : "已移除" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="拒绝覆盖" align="center" width="135">
          <template #default="scope">
            <el-tag
              v-if="scope.row.enabled"
              :type="scope.row.denyOverridable ? 'warning' : 'info'"
              effect="plain"
            >
              {{ scope.row.denyOverridable ? "可以覆盖" : "不可覆盖" }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="description"
          label="权限说明"
          align="left"
          min-width="320"
          show-overflow-tooltip
        />
      </el-table>
    </div>
    <div class="permission-section__header">
      <span class="permission-section__title">显式授权</span>
      <el-button type="primary" plain icon="Plus" @click="addEntry">
        添加授权
      </el-button>
    </div>
    <el-table v-loading="loading" :data="entries">
      <el-table-column label="主体类型" align="center" width="125">
        <template #default="scope">
          <el-select
            v-model="scope.row.subjectType"
            @change="handleSubjectTypeChange(scope.row)"
          >
            <el-option label="用户" value="user" />
            <el-option label="角色" value="role" />
            <el-option label="部门" value="dept" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="授权主体" align="center" min-width="230">
        <template #default="scope">
          <el-tree-select
            v-if="scope.row.subjectType === 'dept'"
            v-model="scope.row.subjectId"
            :data="deptOptions"
            :props="{ value: 'id', label: 'label', children: 'children' }"
            value-key="id"
            placeholder="请选择部门"
            filterable
            clearable
            check-strictly
            :render-after-expand="false"
            style="width: 100%"
          />
          <el-select
            v-else
            v-model="scope.row.subjectId"
            filterable
            remote
            clearable
            :loading="scope.row.subjectLoading"
            :remote-method="keyword => searchSubjectOptions(scope.row, keyword)"
            @visible-change="
              visible => handleSubjectVisible(scope.row, visible)
            "
            placeholder="输入名称搜索"
            style="width: 100%"
          >
            <el-option
              v-for="item in scope.row.subjectOptions"
              :key="item.subjectId"
              :label="item.subjectName"
              :value="item.subjectId"
            />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="规则" align="center" width="120">
        <template #default="scope">
          <el-select v-model="scope.row.effect">
            <el-option label="允许下载" value="allow" />
            <el-option label="拒绝下载" value="deny" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="包含下级部门" align="center" width="125">
        <template #default="scope">
          <el-switch
            v-if="scope.row.subjectType === 'dept'"
            v-model="scope.row.includeChildren"
          />
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="有效期至" align="center" width="205">
        <template #default="scope">
          <el-date-picker
            v-model="scope.row.expireTime"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
            placeholder="永久有效"
            style="width: 185px"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" width="70">
        <template #default="scope">
          <el-tooltip content="删除" placement="top">
            <el-button
              link
              type="danger"
              icon="Delete"
              @click="removeEntry(scope.$index)"
            />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="saving" @click="submit">
          保 存
        </el-button>
        <el-button @click="visible = false">取 消</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import {
  batchSaveFileAcl,
  getFileAclDeptTree,
  listFileAcl,
  saveFileAcl,
  searchFileAclSubjects
} from "@/api/system/file";

const emit = defineEmits(["refresh"]);
const { proxy } = getCurrentInstance();
const visible = ref(false);
const loading = ref(false);
const saving = ref(false);
const fileId = ref("");
const fileName = ref("");
const fileIds = ref("");
const batchMode = ref(false);
const batchCount = ref(0);
const aclVersion = ref(0);
const builtinPermissions = ref([]);
const entries = ref([]);
const deptOptions = ref([]);
const drawerTitle = computed(() =>
  batchMode.value
    ? `批量授权 - ${batchCount.value}个文件`
    : `访问权限 - ${fileName.value}`
);

function open(row, selectedIds, selectedPrivateIds) {
  batchMode.value = !row?.fileId;
  if (batchMode.value && !selectedPrivateIds.length) {
    proxy.$modal.msgWarning("请选择正常状态的受保护文件");
    return;
  }
  fileId.value = row?.fileId || "";
  fileIds.value = batchMode.value
    ? selectedPrivateIds.join(",")
    : row.fileId;
  batchCount.value = batchMode.value ? selectedPrivateIds.length : 0;
  fileName.value = row?.originalName || "";
  if (batchMode.value && selectedPrivateIds.length < selectedIds.length) {
    proxy.$modal.msgWarning(
      `已忽略${selectedIds.length - selectedPrivateIds.length}个公开或非正常状态的文件`
    );
  }
  visible.value = true;
  loading.value = true;
  builtinPermissions.value = [];
  if (batchMode.value) {
    aclVersion.value = 0;
    entries.value = [];
    getFileAclDeptTree()
      .then(response => {
        deptOptions.value = response.data;
      })
      .finally(() => {
        loading.value = false;
      });
    return;
  }
  Promise.all([listFileAcl(row.fileId), getFileAclDeptTree()])
    .then(([aclResponse, deptResponse]) => {
      deptOptions.value = deptResponse.data;
      aclVersion.value = aclResponse.data.aclVersion;
      builtinPermissions.value = aclResponse.data.builtinPermissions || [];
      entries.value = aclResponse.data.entries.map(item => ({
        subjectType: item.subjectType,
        subjectId: item.subjectId,
        effect: item.effect,
        includeChildren: item.includeChildren,
        expireTime: item.expireTime,
        subjectLoading: false,
        subjectOptions: [
          { subjectId: item.subjectId, subjectName: item.subjectName }
        ]
      }));
    })
    .finally(() => {
      loading.value = false;
    });
}

function builtinSourceLabel(source) {
  return (
    {
      admin: "平台管理员",
      owner: "文件所有者",
      uploader: "文件上传人"
    }[source] || source
  );
}

function builtinSourceType(source) {
  return (
    {
      admin: "danger",
      owner: "primary",
      uploader: "warning"
    }[source] || "info"
  );
}

function addEntry() {
  entries.value.push({
    subjectType: "user",
    subjectId: undefined,
    effect: "allow",
    includeChildren: false,
    expireTime: undefined,
    subjectLoading: false,
    subjectOptions: []
  });
}

function removeEntry(index) {
  entries.value.splice(index, 1);
}

function handleSubjectTypeChange(row) {
  row.subjectId = undefined;
  row.includeChildren = false;
  row.subjectOptions = [];
}

function handleSubjectVisible(row, visible) {
  if (visible && !row.subjectOptions.length) {
    searchSubjectOptions(row, "");
  }
}

function searchSubjectOptions(row, keyword) {
  const subjectType = row.subjectType;
  row.subjectLoading = true;
  searchFileAclSubjects({ subjectType, keyword })
    .then(response => {
      if (row.subjectType === subjectType) {
        row.subjectOptions = response.data;
      }
      row.subjectLoading = false;
    })
    .catch(() => {
      row.subjectLoading = false;
    });
}

function submit() {
  if (entries.value.some(item => !item.subjectId)) {
    proxy.$modal.msgError("请选择完整的授权主体");
    return;
  }
  const aclEntries = entries.value.map(item => ({
    subjectType: item.subjectType,
    subjectId: item.subjectId,
    effect: item.effect,
    includeChildren: item.subjectType === "dept" && item.includeChildren,
    expireTime: item.expireTime || undefined
  }));
  const saveAcl = () => {
    saving.value = true;
    const saveRequest = batchMode.value
      ? batchSaveFileAcl({ fileIds: fileIds.value, entries: aclEntries })
      : saveFileAcl(fileId.value, {
          aclVersion: aclVersion.value,
          entries: aclEntries
        });
    saveRequest
      .then(() => {
        proxy.$modal.msgSuccess(
          batchMode.value ? "文件权限批量保存成功" : "文件权限保存成功"
        );
        visible.value = false;
        emit("refresh");
      })
      .finally(() => {
        saving.value = false;
      });
  };
  if (batchMode.value) {
    proxy.$modal
      .confirm(`将覆盖所选${batchCount.value}个文件的全部授权，是否继续?`)
      .then(saveAcl)
      .catch(() => {});
  } else {
    saveAcl();
  }
}

defineExpose({ open });
</script>

<style scoped>
.permission-section {
  margin-bottom: 20px;
}

.permission-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 18px 0 8px;
}

.permission-section__title {
  color: var(--el-text-color-primary);
  font-size: 15px;
  font-weight: 600;
}
</style>
