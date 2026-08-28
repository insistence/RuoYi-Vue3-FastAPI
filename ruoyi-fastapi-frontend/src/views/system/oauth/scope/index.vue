<template>
  <div class="oauth-route-page">
    <PageFrame
      section="接入管理"
      title="权限"
      description="用业务语言定义应用可以申请的身份信息和服务操作。"
      filter-hint="协议代码作为次要信息展示，日常按名称查找即可"
    >
      <template #actions>
        <el-button type="primary" icon="Plus" v-hasPermi="['system:oauthScope:add']" @click="handleAdd">新增权限</el-button>
      </template>

      <template #filters>
        <el-form v-show="showSearch" ref="queryRef" :model="queryParams" :inline="true">
          <el-form-item label="权限名称" prop="scopeName">
            <el-input v-model="queryParams.scopeName" clearable placeholder="输入权限名称" style="width: 200px" @keyup.enter="handleQuery" />
          </el-form-item>
          <el-form-item label="用途" prop="scopeType">
            <el-select v-model="queryParams.scopeType" clearable placeholder="全部用途" style="width: 200px">
              <el-option label="登录身份信息" value="identity" />
              <el-option label="服务访问" value="resource" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态" prop="status">
            <el-select v-model="queryParams.status" clearable placeholder="全部状态" style="width: 200px">
              <el-option label="使用中" value="0" />
              <el-option label="已停用" value="1" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" icon="Search" @click="handleQuery">查找</el-button>
            <el-button icon="Refresh" @click="resetQuery">清空</el-button>
          </el-form-item>
        </el-form>
      </template>

      <template #toolbar>
        <span class="result-count">已定义 <strong>{{ total }}</strong> 项权限</span>
        <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
      </template>

      <el-table v-loading="loading" :data="rows" row-key="scopeCode">
        <el-table-column label="权限" min-width="230">
          <template #default="scope">
            <div class="permission-cell">
              <strong>{{ scope.row.scopeName }}</strong>
              <code>{{ scope.row.scopeCode }}</code>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="用途" width="135">
          <template #default="scope">
            <el-tag :type="scope.row.scopeType === 'identity' ? 'primary' : 'success'" effect="plain">
              {{ scope.row.scopeType === 'identity' ? '登录身份信息' : '服务访问' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="所属服务" min-width="180">
          <template #default="scope">{{ resourceName(scope.row.resourceId) }}</template>
        </el-table-column>
        <el-table-column label="返回的用户信息" min-width="230">
          <template #default="scope">
            <div class="claim-summary">
              <el-tag v-for="item in (scope.row.claims || []).slice(0, 3)" :key="item" size="small" effect="plain">{{ claimLabel(item) }}</el-tag>
              <span v-if="!(scope.row.claims || []).length" class="muted-value">不返回额外信息</span>
              <span v-else-if="scope.row.claims.length > 3" class="muted-value">+{{ scope.row.claims.length - 3 }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="用户确认" width="145">
          <template #default="scope">
            <div class="policy-cell">
              <el-tag v-if="scope.row.sensitive" type="warning" size="small">敏感权限</el-tag>
              <span>{{ scope.row.consentRequired ? '需要确认' : '无需重复确认' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="105" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.status === '0' ? 'success' : 'info'">{{ scope.row.status === '0' ? '使用中' : '已停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="scope">
            <div class="table-actions">
              <el-button link type="primary" icon="Edit" v-hasPermi="['system:oauthScope:edit']" @click="handleUpdate(scope.row)">编辑</el-button>
              <el-dropdown v-if="scope.row.scopeCode !== 'openid'" trigger="click" @command="command => handleRowCommand(command, scope.row)">
                <el-button link type="primary" icon="ArrowDown">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="scope.row.status !== '0'" command="enable" icon="CircleCheck" v-hasPermi="['system:oauthScope:edit']">重新启用</el-dropdown-item>
                    <el-dropdown-item v-else command="disable" icon="CircleClose" v-hasPermi="['system:oauthScope:remove']">停用权限</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有符合条件的权限">
            <el-button type="primary" v-hasPermi="['system:oauthScope:add']" @click="handleAdd">新增第一项权限</el-button>
          </el-empty>
        </template>
      </el-table>
      <pagination v-show="total > 0" v-model:page="queryParams.pageNum" v-model:limit="queryParams.pageSize" :total="total" @pagination="getList" />
    </PageFrame>

    <el-dialog
      v-model="open"
      :title="form.persisted ? '编辑权限' : '新增权限'"
      width="min(780px, calc(100vw - 48px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="160px" class="permission-form">
        <div class="section-heading">
          <h3>权限含义</h3>
          <p>先选择这项权限用于登录信息还是服务访问，再说明它可以返回什么。</p>
        </div>
        <el-form-item prop="scopeType">
          <template #label><FieldLabel label="权限用途" help="登录身份信息用于返回用户资料；服务访问用于允许应用调用某个服务。" /></template>
          <el-radio-group v-model="form.scopeType" class="choice-grid" :disabled="form.scopeCode === 'openid'">
            <el-radio value="identity" border>
              <strong>登录身份信息</strong>
              <small>例如姓名、邮箱和角色</small>
            </el-radio>
            <el-radio value="resource" border>
              <strong>服务访问</strong>
              <small>例如查看订单或修改库存</small>
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-row :gutter="18">
          <el-col :xs="24" :sm="12">
            <el-form-item prop="scopeName">
              <template #label><FieldLabel label="显示名称" help="用户授权和后台列表中看到的名称，应直接说明允许做什么。" /></template>
              <el-input v-model="form.scopeName" placeholder="例如：查看订单" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item prop="scopeCode">
              <template #label><FieldLabel label="权限代码" help="应用在登录请求中使用的协议代码，保存后不能修改。" /></template>
              <el-input v-model="form.scopeCode" :disabled="form.persisted" placeholder="例如：orders.read" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item v-if="form.scopeType === 'resource'" prop="resourceId">
          <template #label><FieldLabel label="所属服务" help="选择应用获得这项权限后可以访问的服务。" /></template>
          <el-select v-model="form.resourceId" filterable placeholder="选择服务" style="width: 100%">
            <el-option v-for="item in resourceOptions" :key="item.resourceId" :label="item.resourceName" :value="item.resourceId">
              <span>{{ item.resourceName }}</span>
              <code class="option-code">{{ item.resourceId }}</code>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label><FieldLabel label="返回用户信息" help="应用获得这项权限后可以收到的用户信息，可多选。" /></template>
          <el-select v-model="form.claims" multiple filterable allow-create default-first-option placeholder="选择或输入用户字段" style="width: 100%">
            <el-option v-for="item in claimOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <template #label><FieldLabel label="用户确认" help="敏感权限应要求用户明确确认，并在授权页突出展示。" /></template>
          <div class="policy-options">
            <el-checkbox v-model="form.consentRequired">使用前让用户确认</el-checkbox>
            <el-checkbox v-model="form.sensitive">标记为敏感权限</el-checkbox>
          </div>
        </el-form-item>
        <el-form-item>
          <template #label><FieldLabel label="备注" help="仅供管理员记录，不会显示给外部应用。" /></template>
          <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存权限</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="OAuthScope">
import {
  addOAuthScope,
  changeOAuthScopeStatus,
  deleteOAuthScopes,
  getOAuthScope,
  listOAuthResources,
  listOAuthScopes,
  updateOAuthScope
} from '@/api/system/oauthResource'
import FieldLabel from '@/components/OAuthWorkspace/FieldLabel.vue'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'

const { proxy } = getCurrentInstance()
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const showSearch = ref(true)
const open = ref(false)
const resourceOptions = ref([])
const queryParams = reactive({ pageNum: 1, pageSize: 10, scopeName: undefined, scopeType: undefined, status: undefined })
const form = reactive(emptyForm())
const claimOptions = [
  { value: 'sub', label: '用户唯一标识（sub）' },
  { value: 'name', label: '姓名（name）' },
  { value: 'email', label: '邮箱（email）' },
  { value: 'roles', label: '角色（roles）' },
  { value: 'preferred_username', label: '登录账号（preferred_username）' }
]
const rules = {
  scopeCode: [{ required: true, message: '请输入权限代码', trigger: 'blur' }],
  scopeName: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  scopeType: [{ required: true, message: '请选择权限用途', trigger: 'change' }],
  resourceId: [{ required: true, message: '请选择这项权限所属的服务', trigger: 'change' }]
}

function emptyForm() {
  return {
    persisted: false,
    scopeCode: '',
    scopeName: '',
    scopeType: 'identity',
    resourceId: null,
    claims: [],
    consentRequired: true,
    sensitive: false,
    status: '0',
    remark: ''
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  proxy.resetForm('formRef')
}

async function getList() {
  loading.value = true
  try {
    const response = await listOAuthScopes(queryParams)
    rows.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
}

async function loadResourceOptions() {
  const response = await listOAuthResources({ pageNum: 1, pageSize: 200, status: '0' })
  resourceOptions.value = response.rows || []
}

function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function handleAdd() {
  resetForm()
  loadResourceOptions().catch(() => {})
  open.value = true
}

async function handleUpdate(row) {
  resetForm()
  const [response] = await Promise.all([
    getOAuthScope(row.scopeCode),
    loadResourceOptions().catch(() => {})
  ])
  Object.assign(form, response.data, {
    persisted: true,
    claims: [...(response.data.claims || [])]
  })
  open.value = true
}

async function submitForm() {
  await proxy.$refs.formRef.validate()
  saving.value = true
  try {
    const { persisted, ...data } = form
    data.claims = [...form.claims]
    if (data.scopeType === 'identity') data.resourceId = null
    await (persisted ? updateOAuthScope(data) : addOAuthScope(data))
    proxy.$modal.msgSuccess('权限已保存')
    open.value = false
    await getList()
  } finally {
    saving.value = false
  }
}

async function changeStatus(row, status) {
  try {
    await proxy.$modal.confirm(`${status === '0' ? '启用' : '停用'} Scope “${row.scopeCode}”？`)
    await changeOAuthScopeStatus({ scopeCode: row.scopeCode, status })
    await getList()
  } catch {
    await getList()
  }
}

async function handleDelete(row) {
  await proxy.$modal.confirm(`停用权限“${row.scopeName}”后，应用不能再申请这项权限，是否继续？`)
  await deleteOAuthScopes(row.scopeCode)
  proxy.$modal.msgSuccess('权限已停用')
  await getList()
}

function handleRowCommand(command, row) {
  if (command === 'enable') return changeStatus(row, '0')
  if (command === 'disable') return handleDelete(row)
}

function resourceName(resourceId) {
  if (!resourceId) return '统一身份信息'
  return resourceOptions.value.find(item => item.resourceId === resourceId)?.resourceName || resourceId
}

function claimLabel(value) {
  return claimOptions.find(item => item.value === value)?.label?.replace(/（.*）$/, '') || value
}

Promise.all([getList(), loadResourceOptions().catch(() => {})])
</script>

<style scoped>
.result-count {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.result-count strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.permission-cell strong,
.permission-cell code {
  display: block;
}

.permission-cell strong {
  color: var(--el-text-color-primary);
}

.permission-cell code {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.claim-summary,
.policy-cell {
  display: flex;
  align-items: center;
  gap: 5px;
}

.policy-cell {
  flex-wrap: wrap;
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.muted-value {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.section-heading {
  margin-bottom: 22px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.section-heading h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 17px;
  font-weight: 650;
}

.section-heading p {
  margin: 7px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.choice-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  width: 100%;
}

.choice-grid :deep(.el-radio) {
  width: 100%;
  height: auto;
  min-height: 68px;
  margin: 0;
  padding: 12px 14px;
  white-space: normal;
}

.choice-grid :deep(.el-radio__label),
.choice-grid strong,
.choice-grid small {
  display: block;
}

.choice-grid strong {
  color: var(--el-text-color-primary);
}

.choice-grid small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.policy-options {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}

.policy-options :deep(.el-checkbox) {
  margin-right: 0;
}

.option-code {
  float: right;
  margin-left: 20px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 768px) {
  .permission-form :deep(.el-form-item) {
    display: block;
  }

  .permission-form :deep(.el-form-item__label) {
    width: auto !important;
    margin-bottom: 6px;
  }

  .permission-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }

  .choice-grid {
    grid-template-columns: 1fr;
  }
}
</style>
