<template>
  <el-dialog
    :title="`转移文件 - ${fileName}`"
    v-model="visible"
    width="620px"
    append-to-body
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
      <el-form-item label="新所有者" prop="ownerUserId">
        <el-select
          v-model="form.ownerUserId"
          filterable
          remote
          clearable
          :loading="userLoading"
          :remote-method="searchUsers"
          @visible-change="visible => visible && searchUsers('')"
          @change="handleUserChange"
          placeholder="输入用户名称搜索"
          style="width: 100%"
        >
          <el-option
            v-for="item in userOptions"
            :key="item.subjectId"
            :label="item.subjectName"
            :value="item.subjectId"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="所属部门" prop="deptId">
        <el-tree-select
          v-model="form.deptId"
          :data="deptOptions"
          :props="{ value: 'id', label: 'label', children: 'children' }"
          value-key="id"
          placeholder="请选择所属部门"
          filterable
          clearable
          check-strictly
          :render-after-expand="false"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item label="上传人权限">
        <el-switch
          v-model="form.retainUploaderAccess"
          active-text="保留"
          inactive-text="移除"
        />
        <div class="form-tip">
          {{
            form.retainUploaderAccess
              ? "原上传人继续拥有内置下载权限，匹配的显式拒绝仍可覆盖。"
              : "原上传人不再因上传身份获得下载权限，上传记录仍会保留。"
          }}
        </div>
      </el-form-item>
      <el-form-item label="转移原因" prop="reason">
        <el-input
          v-model="form.reason"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="请输入转移原因"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button type="primary" :loading="saving" @click="submit">
          确 定
        </el-button>
        <el-button @click="visible = false">取 消</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import {
  getFileAclDeptTree,
  searchFileAclSubjects,
  transferFile
} from "@/api/system/file";

const emit = defineEmits(["refresh"]);
const { proxy } = getCurrentInstance();
const visible = ref(false);
const saving = ref(false);
const userLoading = ref(false);
const fileIds = ref("");
const fileName = ref("");
const userOptions = ref([]);
const deptOptions = ref([]);
const formRef = ref();
const form = reactive({
  ownerUserId: undefined,
  deptId: undefined,
  retainUploaderAccess: true,
  reason: undefined
});
const rules = {
  ownerUserId: [
    { required: true, message: "请选择新所有者", trigger: "change" }
  ],
  deptId: [{ required: true, message: "请选择所属部门", trigger: "change" }],
  reason: [{ required: true, message: "请输入转移原因", trigger: "blur" }]
};

function open(row, selectedIds) {
  const isSingle = row?.fileId;
  fileIds.value = isSingle ? row.fileId : selectedIds.join(",");
  fileName.value = isSingle ? row.originalName : `${selectedIds.length}个文件`;
  Object.assign(form, {
    ownerUserId: undefined,
    deptId: undefined,
    retainUploaderAccess: true,
    reason: undefined
  });
  userOptions.value = [];
  visible.value = true;
  nextTick(() => formRef.value?.clearValidate());
  getFileAclDeptTree().then(response => {
    deptOptions.value = response.data;
  });
  searchUsers("");
}

function searchUsers(keyword) {
  userLoading.value = true;
  searchFileAclSubjects({ subjectType: "user", keyword })
    .then(response => {
      userOptions.value = response.data;
    })
    .finally(() => {
      userLoading.value = false;
    });
}

function handleUserChange(userId) {
  const targetUser = userOptions.value.find(item => item.subjectId === userId);
  if (targetUser?.deptId) {
    form.deptId = targetUser.deptId;
  }
}

function submit() {
  formRef.value.validate(valid => {
    if (!valid) return;
    saving.value = true;
    transferFile(fileIds.value, form)
      .then(() => {
        visible.value = false;
        emit("refresh");
        proxy.$modal.msgSuccess("文件转移成功");
      })
      .finally(() => {
        saving.value = false;
      });
  });
}

defineExpose({ open });
</script>

<style scoped>
.form-tip {
  width: 100%;
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 20px;
}
</style>
