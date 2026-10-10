<template>
  <el-drawer
    v-model="visible"
    title="应用访问策略"
    size="min(960px, 96vw)"
    @open="handleQuery"
  >
    <el-alert
      title="可在用户首次授权前禁止访问应用。未配置策略时默认允许；解除禁止后，已撤销的授权不会恢复。"
      type="info"
      :closable="false"
      show-icon
      class="policy-note"
    />
    <el-form
      ref="queryRef"
      :model="queryParams"
      :inline="true"
      @submit.prevent="handleQuery"
    >
      <el-form-item
        label="用户"
        prop="userId"
      >
        <el-input
          v-model="queryParams.userId"
          clearable
          placeholder="用户编号"
          class="filter-input"
        />
      </el-form-item>
      <el-form-item
        label="应用"
        prop="clientId"
      >
        <el-input
          v-model="queryParams.clientId"
          clearable
          placeholder="Client ID"
          class="filter-input"
        />
      </el-form-item>
      <el-form-item
        label="策略"
        prop="accessStatus"
      >
        <el-select
          v-model="queryParams.accessStatus"
          clearable
          placeholder="全部策略"
          class="filter-input"
        >
          <el-option
            label="禁止访问"
            value="blocked"
          />
          <el-option
            label="允许访问"
            value="allowed"
          />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          icon="Search"
          native-type="submit"
          >查找</el-button
        >
        <el-button
          icon="Refresh"
          @click="resetQuery"
          >清空</el-button
        >
      </el-form-item>
    </el-form>
    <div class="policy-toolbar">
      <span>已配置 {{ total }} 条策略</span>
      <el-button
        type="primary"
        icon="Plus"
        v-hasPermi="['system:oauthGrant:revoke']"
        @click="openAccess()"
      >
        新增禁止策略
      </el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="rows"
    >
      <el-table-column
        label="用户"
        min-width="140"
      >
        <template #default="scope">
          <div class="policy-target">
            <strong>{{ scope.row.userName }}</strong
            ><small>{{ scope.row.userId }}</small>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        label="应用"
        min-width="160"
      >
        <template #default="scope">
          <div class="policy-target">
            <strong>{{ scope.row.clientName }}</strong
            ><small>{{ scope.row.clientId }}</small>
          </div>
        </template>
      </el-table-column>
      <el-table-column
        label="策略"
        width="110"
      >
        <template #default="scope">
          <el-tag :type="scope.row.accessStatus === 'blocked' ? 'danger' : 'success'">
            {{ scope.row.accessStatus === 'blocked' ? '禁止访问' : '允许访问' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="reason"
        label="操作原因"
        min-width="180"
        show-overflow-tooltip
      />
      <el-table-column
        prop="updateBy"
        label="操作人"
        width="110"
      />
      <el-table-column
        label="最近操作"
        width="170"
      >
        <template #default="scope">{{ parseTime(scope.row.updateTime) || '—' }}</template>
      </el-table-column>
      <el-table-column
        label="操作"
        width="110"
        fixed="right"
        align="center"
      >
        <template #default="scope">
          <el-button
            link
            :type="scope.row.accessStatus === 'blocked' ? 'primary' : 'danger'"
            v-hasPermi="['system:oauthGrant:revoke']"
            @click="openAccess(scope.row)"
            >{{ scope.row.accessStatus === 'blocked' ? '解除禁止' : '禁止访问' }}</el-button
          >
        </template>
      </el-table-column>
      <template #empty><el-empty description="没有符合条件的访问策略" /></template>
    </el-table>
    <pagination
      v-show="total > 0"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      :total="total"
      @pagination="getList"
    />
    <el-dialog
      v-model="accessOpen"
      :title="accessBlocked ? '禁止用户访问应用' : '解除应用访问禁止'"
      width="min(540px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-alert
        :title="
          accessBlocked
            ? '将撤销该用户对应用的全部现有授权，并阻止后续授权。'
            : '解除后允许重新授权，已有授权和令牌不会恢复。'
        "
        :type="accessBlocked ? 'warning' : 'info'"
        :closable="false"
        show-icon
        class="policy-note"
      />
      <el-form
        ref="accessRef"
        :model="accessForm"
        :rules="accessRules"
        label-position="top"
      >
        <el-form-item
          label="用户编号"
          prop="userId"
        >
          <el-input
            v-model="accessForm.userId"
            :disabled="!creating || saving"
            maxlength="19"
            inputmode="numeric"
            placeholder="输入用户管理中的用户编号"
          />
        </el-form-item>
        <el-form-item
          label="Client ID"
          prop="clientId"
        >
          <el-input
            v-model="accessForm.clientId"
            :disabled="!creating || saving"
            maxlength="128"
            placeholder="输入客户端管理中的 Client ID"
          />
        </el-form-item>
        <el-form-item
          label="操作原因"
          prop="reason"
        >
          <el-input
            v-model="accessForm.reason"
            :disabled="saving"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="填写原因，便于后续审计"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          :disabled="saving"
          @click="accessOpen = false"
          >取消</el-button
        >
        <el-button
          :type="accessBlocked ? 'danger' : 'primary'"
          :loading="saving"
          @click="saveAccess"
        >
          {{ accessBlocked ? '确认禁止' : '确认解除' }}
        </el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup name="OAuthAccessPolicyDrawer">
import { listOAuthAccessPolicies, setOAuthClientAccess } from '@/api/system/oauthSession'

const visible = defineModel({ type: Boolean, default: false })
const emit = defineEmits(['changed'])
const { proxy } = getCurrentInstance()
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const accessOpen = ref(false)
const accessBlocked = ref(true)
const creating = ref(false)
const saving = ref(false)
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: undefined,
  clientId: undefined,
  accessStatus: undefined,
})
const accessForm = reactive({ userId: '', clientId: '', reason: '' })
const accessRules = {
  userId: [
    {
      required: true,
      pattern: /^[1-9]\d{0,18}$/,
      message: '请输入有效的用户编号',
      trigger: 'blur',
    },
  ],
  clientId: [{ required: true, whitespace: true, message: '请输入 Client ID', trigger: 'blur' }],
  reason: [{ required: true, whitespace: true, message: '请填写操作原因', trigger: 'blur' }],
}

/** 查询已配置的独立访问策略 */
async function getList() {
  loading.value = true
  try {
    const response = await listOAuthAccessPolicies(queryParams)
    rows.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
}

/** 从第一页查询访问策略 */
function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

/** 清空查询条件 */
function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

/** 打开新增或变更访问策略的确认表单 */
function openAccess(row) {
  creating.value = !row
  accessBlocked.value = !row || row.accessStatus !== 'blocked'
  Object.assign(accessForm, {
    userId: row ? String(row.userId) : '',
    clientId: row?.clientId || '',
    reason: '',
  })
  accessOpen.value = true
  nextTick(() => proxy.$refs.accessRef?.clearValidate())
}

/** 提交独立访问策略并同步授权列表 */
async function saveAccess() {
  if (saving.value || !(await proxy.$refs.accessRef.validate().catch(() => false))) {
    return
  }
  saving.value = true
  try {
    await setOAuthClientAccess(accessForm.userId.trim(), accessForm.clientId.trim(), {
      blocked: accessBlocked.value,
      reason: accessForm.reason.trim(),
    })
    proxy.$modal.msgSuccess(accessBlocked.value ? '已禁止用户访问应用' : '已解除访问禁止')
    accessOpen.value = false
    emit('changed')
    await getList()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.policy-note {
  margin-bottom: 20px;
}

.filter-input {
  width: 180px;
}

.policy-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  color: var(--el-text-color-regular);
}

.policy-target strong,
.policy-target small {
  display: block;
  overflow-wrap: anywhere;
}

.policy-target strong {
  color: var(--el-text-color-primary);
}

.policy-target small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
}
</style>
