<template>
  <el-dialog
    :title="`转移文件 - ${fileName}`"
    :visible.sync="visible"
    width="620px"
    append-to-body
  >
    <el-form
      ref="form"
      :model="form"
      :rules="rules"
      label-width="100px"
    >
      <el-form-item
        label="新所有者"
        prop="ownerUserId"
      >
        <el-select
          v-model="form.ownerUserId"
          filterable
          remote
          clearable
          :loading="userLoading"
          :remote-method="searchUsers"
          placeholder="输入用户名称搜索"
          style="width: 100%"
          @visible-change="handleUserVisible"
          @change="handleUserChange"
        >
          <el-option
            v-for="item in userOptions"
            :key="item.subjectId"
            :label="item.subjectName"
            :value="item.subjectId"
          />
        </el-select>
      </el-form-item>
      <el-form-item
        label="所属部门"
        prop="deptId"
      >
        <treeselect
          v-model="form.deptId"
          :options="deptOptions"
          :normalizer="normalizer"
          placeholder="请选择所属部门"
          :clearable="true"
          :searchable="true"
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
              ? '原上传人继续拥有内置下载权限，匹配的显式拒绝仍可覆盖。'
              : '原上传人不再因上传身份获得下载权限，上传记录仍会保留。'
          }}
        </div>
      </el-form-item>
      <el-form-item
        label="转移原因"
        prop="reason"
      >
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
    <div
      slot="footer"
      class="dialog-footer"
    >
      <el-button
        type="primary"
        :loading="saving"
        @click="submit"
      >
        确 定
      </el-button>
      <el-button @click="visible = false">取 消</el-button>
    </div>
  </el-dialog>
</template>

<script>
import Treeselect from '@riophae/vue-treeselect'
import '@riophae/vue-treeselect/dist/vue-treeselect.css'
import { getFileAclDeptTree, searchFileAclSubjects, transferFile } from '@/api/system/file'

export default {
  name: 'FileTransferDialog',
  components: { Treeselect },
  data() {
    return {
      visible: false,
      saving: false,
      userLoading: false,
      fileIds: '',
      fileName: '',
      userOptions: [],
      deptOptions: [],
      form: {
        ownerUserId: undefined,
        deptId: undefined,
        retainUploaderAccess: true,
        reason: undefined,
      },
      rules: {
        ownerUserId: [{ required: true, message: '请选择新所有者', trigger: 'change' }],
        deptId: [{ required: true, message: '请选择所属部门', trigger: 'change' }],
        reason: [{ required: true, message: '请输入转移原因', trigger: 'blur' }],
      },
    }
  },
  methods: {
    normalizer(node) {
      return {
        id: node.id,
        label: node.label,
        children: node.children,
      }
    },
    open(row, selectedIds) {
      const isSingle = row && row.fileId
      this.fileIds = isSingle ? row.fileId : selectedIds.join(',')
      this.fileName = isSingle ? row.originalName : `${selectedIds.length}个文件`
      Object.assign(this.form, {
        ownerUserId: undefined,
        deptId: undefined,
        retainUploaderAccess: true,
        reason: undefined,
      })
      this.userOptions = []
      this.visible = true
      this.$nextTick(() => this.$refs.form.clearValidate())
      getFileAclDeptTree().then((response) => {
        this.deptOptions = response.data
      })
      this.searchUsers('')
    },
    searchUsers(keyword) {
      this.userLoading = true
      searchFileAclSubjects({ subjectType: 'user', keyword })
        .then((response) => {
          this.userOptions = response.data
        })
        .finally(() => {
          this.userLoading = false
        })
    },
    handleUserVisible(visible) {
      if (visible) {
        this.searchUsers('')
      }
    },
    handleUserChange(userId) {
      const targetUser = this.userOptions.find((item) => item.subjectId === userId)
      if (targetUser && targetUser.deptId) {
        this.form.deptId = targetUser.deptId
      }
    },
    submit() {
      this.$refs.form.validate((valid) => {
        if (!valid) {
          return
        }
        this.saving = true
        transferFile(this.fileIds, this.form)
          .then(() => {
            this.visible = false
            this.$emit('refresh')
            this.$modal.msgSuccess('文件转移成功')
          })
          .finally(() => {
            this.saving = false
          })
      })
    },
  },
}
</script>

<style scoped>
.form-tip {
  width: 100%;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 20px;
}
</style>
