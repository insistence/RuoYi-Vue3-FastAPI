<template>
  <el-drawer
    :title="drawerTitle"
    :visible.sync="visible"
    size="70%"
    append-to-body
    :wrapper-closable="!saving"
  >
    <div class="drawer-content">
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
      <div
        v-if="!batchMode"
        class="permission-section"
      >
        <div class="permission-section__title">内置权限</div>
        <el-table
          v-loading="loading"
          :data="builtinPermissions"
          border
        >
          <el-table-column
            label="权限来源"
            align="center"
            width="110"
          >
            <template slot-scope="scope">
              <el-tag
                :type="builtinSourceType(scope.row.source)"
                effect="plain"
                >{{ builtinSourceLabel(scope.row.source) }}</el-tag
              >
            </template>
          </el-table-column>
          <el-table-column
            label="权限主体"
            align="center"
            min-width="180"
          >
            <template slot-scope="scope">
              {{ scope.row.subjectName || scope.row.subjectId || '-' }}
            </template>
          </el-table-column>
          <el-table-column
            label="规则"
            align="center"
            width="110"
          >
            <template slot-scope="scope">
              <el-tag
                :type="scope.row.enabled ? 'success' : 'info'"
                effect="plain"
                >{{ scope.row.enabled ? '允许下载' : '已移除' }}</el-tag
              >
            </template>
          </el-table-column>
          <el-table-column
            label="拒绝覆盖"
            align="center"
            width="135"
          >
            <template slot-scope="scope">
              <el-tag
                v-if="scope.row.enabled"
                :type="scope.row.denyOverridable ? 'warning' : 'info'"
                effect="plain"
                >{{ scope.row.denyOverridable ? '可以覆盖' : '不可覆盖' }}</el-tag
              >
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
        <el-button
          type="primary"
          plain
          size="mini"
          icon="el-icon-plus"
          @click="addEntry"
          >添加授权</el-button
        >
      </div>
      <el-table
        v-loading="loading"
        :data="entries"
      >
        <el-table-column
          label="主体类型"
          align="center"
          width="125"
        >
          <template slot-scope="scope">
            <el-select
              v-model="scope.row.subjectType"
              @change="handleSubjectTypeChange(scope.row)"
            >
              <el-option
                label="用户"
                value="user"
              />
              <el-option
                label="角色"
                value="role"
              />
              <el-option
                label="部门"
                value="dept"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column
          label="授权主体"
          align="center"
          min-width="230"
        >
          <template slot-scope="scope">
            <treeselect
              v-if="scope.row.subjectType === 'dept'"
              v-model="scope.row.subjectId"
              :options="deptOptions"
              :normalizer="normalizer"
              :append-to-body="true"
              :z-index="3000"
              placeholder="请选择部门"
              :clearable="true"
              :searchable="true"
              style="width: 100%"
            />
            <el-select
              v-else
              v-model="scope.row.subjectId"
              filterable
              remote
              clearable
              :loading="scope.row.subjectLoading"
              :remote-method="getSubjectRemoteMethod(scope.row)"
              placeholder="输入名称搜索"
              style="width: 100%"
              @visible-change="handleSubjectVisible(scope.row, $event)"
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
        <el-table-column
          label="规则"
          align="center"
          width="120"
        >
          <template slot-scope="scope">
            <el-select v-model="scope.row.effect">
              <el-option
                label="允许下载"
                value="allow"
              />
              <el-option
                label="拒绝下载"
                value="deny"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column
          label="包含下级部门"
          align="center"
          width="125"
        >
          <template slot-scope="scope">
            <el-switch
              v-if="scope.row.subjectType === 'dept'"
              v-model="scope.row.includeChildren"
            />
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          label="有效期至"
          align="center"
          width="310"
        >
          <template slot-scope="scope">
            <BusinessDateTimePicker
              v-model="scope.row.expireTime"
              label="有效期至，留空为永久有效"
            />
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          align="center"
          width="70"
        >
          <template slot-scope="scope">
            <el-tooltip
              content="删除"
              placement="top"
            >
              <el-button
                type="text"
                class="file-action-danger"
                icon="el-icon-delete"
                @click="removeEntry(scope.$index)"
              />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
      <div class="drawer-footer">
        <el-button
          type="primary"
          :loading="saving"
          @click="submit"
        >
          保 存
        </el-button>
        <el-button @click="visible = false">取 消</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script>
import { prepareTimeFields, serializeTimeFieldsForSubmit } from '@/utils/time'
import BusinessDateTimePicker from '@/components/BusinessDateTimePicker'
import Treeselect from '@riophae/vue-treeselect'
import '@riophae/vue-treeselect/dist/vue-treeselect.css'
import {
  batchSaveFileAcl,
  getFileAclDeptTree,
  listFileAcl,
  saveFileAcl,
  searchFileAclSubjects,
} from '@/api/system/file'

export default {
  name: 'FileAclDrawer',
  components: { Treeselect, BusinessDateTimePicker },
  data() {
    return {
      visible: false,
      loading: false,
      saving: false,
      fileId: '',
      fileName: '',
      fileIds: '',
      batchMode: false,
      batchCount: 0,
      aclVersion: 0,
      builtinPermissions: [],
      entries: [],
      deptOptions: [],
    }
  },
  computed: {
    drawerTitle() {
      return this.batchMode ? `批量授权 - ${this.batchCount}个文件` : `访问权限 - ${this.fileName}`
    },
  },
  methods: {
    normalizer(node) {
      return {
        id: node.id,
        label: node.label,
        children: node.children,
      }
    },
    open(row, selectedIds, selectedPrivateIds) {
      this.batchMode = !(row && row.fileId)
      if (this.batchMode && !selectedPrivateIds.length) {
        this.$modal.msgWarning('请选择正常状态的受保护文件')
        return
      }
      this.fileId = row && row.fileId ? row.fileId : ''
      this.fileIds = this.batchMode ? selectedPrivateIds.join(',') : row.fileId
      this.batchCount = this.batchMode ? selectedPrivateIds.length : 0
      this.fileName = row && row.originalName ? row.originalName : ''
      if (this.batchMode && selectedPrivateIds.length < selectedIds.length) {
        this.$modal.msgWarning(
          `已忽略${selectedIds.length - selectedPrivateIds.length}个公开或非正常状态的文件`
        )
      }
      this.visible = true
      this.loading = true
      this.builtinPermissions = []
      if (this.batchMode) {
        this.aclVersion = 0
        this.entries = []
        getFileAclDeptTree()
          .then((response) => {
            this.deptOptions = response.data
          })
          .finally(() => {
            this.loading = false
          })
        return
      }
      Promise.all([listFileAcl(row.fileId), getFileAclDeptTree()])
        .then(([aclResponse, deptResponse]) => {
          this.deptOptions = deptResponse.data
          this.aclVersion = aclResponse.data.aclVersion
          this.builtinPermissions = aclResponse.data.builtinPermissions || []
          this.entries = aclResponse.data.entries.map((item) =>
            prepareTimeFields(
              {
                subjectType: item.subjectType,
                subjectId: item.subjectId,
                effect: item.effect,
                includeChildren: item.includeChildren,
                expireTime: item.expireTime,
                subjectLoading: false,
                subjectOptions: [
                  {
                    subjectId: item.subjectId,
                    subjectName: item.subjectName,
                  },
                ],
              },
              ['expireTime']
            )
          )
        })
        .finally(() => {
          this.loading = false
        })
    },
    builtinSourceLabel(source) {
      return (
        {
          admin: '平台管理员',
          owner: '文件所有者',
          uploader: '文件上传人',
        }[source] || source
      )
    },
    builtinSourceType(source) {
      return (
        {
          admin: 'danger',
          owner: 'primary',
          uploader: 'warning',
        }[source] || 'info'
      )
    },
    addEntry() {
      this.entries.push({
        subjectType: 'user',
        subjectId: undefined,
        effect: 'allow',
        includeChildren: false,
        expireTime: undefined,
        subjectLoading: false,
        subjectOptions: [],
      })
    },
    removeEntry(index) {
      this.entries.splice(index, 1)
    },
    handleSubjectTypeChange(row) {
      row.subjectId = undefined
      row.includeChildren = false
      row.subjectOptions = []
    },
    handleSubjectVisible(row, visible) {
      if (visible && !row.subjectOptions.length) {
        this.searchSubjectOptions(row, '')
      }
    },
    getSubjectRemoteMethod(row) {
      return (keyword) => this.searchSubjectOptions(row, keyword)
    },
    searchSubjectOptions(row, keyword) {
      const subjectType = row.subjectType
      row.subjectLoading = true
      searchFileAclSubjects({ subjectType, keyword })
        .then((response) => {
          if (row.subjectType === subjectType) {
            row.subjectOptions = response.data
          }
          row.subjectLoading = false
        })
        .catch(() => {
          row.subjectLoading = false
        })
    },
    async submit() {
      if (this.entries.some((item) => !item.subjectId)) {
        this.$modal.msgError('请选择完整的授权主体')
        return
      }
      const convertedEntries = []
      for (const item of this.entries) {
        const converted = await serializeTimeFieldsForSubmit(item, ['expireTime'])
        if (!converted) return
        convertedEntries.push(converted)
      }
      const aclEntries = convertedEntries.map((item) => ({
        subjectType: item.subjectType,
        subjectId: item.subjectId,
        effect: item.effect,
        includeChildren: item.subjectType === 'dept' && item.includeChildren,
        expireTime: item.expireTime,
      }))
      const saveAcl = () => {
        this.saving = true
        const saveRequest = this.batchMode
          ? batchSaveFileAcl({
              fileIds: this.fileIds,
              entries: aclEntries,
            })
          : saveFileAcl(this.fileId, {
              aclVersion: this.aclVersion,
              entries: aclEntries,
            })
        saveRequest
          .then(() => {
            this.$modal.msgSuccess(this.batchMode ? '文件权限批量保存成功' : '文件权限保存成功')
            this.visible = false
            this.$emit('refresh')
          })
          .finally(() => {
            this.saving = false
          })
      }
      if (this.batchMode) {
        this.$modal
          .confirm(`将覆盖所选${this.batchCount}个文件的全部授权，是否继续?`)
          .then(saveAcl)
          .catch(() => {})
      } else {
        saveAcl()
      }
    },
  },
}
</script>

<style scoped>
.drawer-content {
  padding: 0 20px 20px;
}

.drawer-footer {
  padding-top: 20px;
  text-align: right;
}

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
  color: #303133;
  font-size: 15px;
  font-weight: 600;
}

.file-action-danger {
  color: #f56c6c;
}
</style>
