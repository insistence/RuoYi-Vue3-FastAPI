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
          ? '将覆盖所选受保护文件的全部授权；管理员和文件所有者仍始终允许访问。'
          : '管理员和文件所有者始终允许访问；显式拒绝优先于上传人兼容权限及其他授权。'
      "
      type="info"
      :closable="false"
      show-icon
      class="mb8"
    />
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="addEntry">
          添加授权
        </el-button>
      </el-col>
    </el-row>
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
