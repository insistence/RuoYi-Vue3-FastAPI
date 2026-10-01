<template>
  <div class="oauth-route-page">
    <PageFrame
      section="接入管理"
      title="服务"
      description="登记接收访问凭据的接口服务，并限制每个服务能够获得的用户信息。"
      filter-hint="按服务名称或当前状态查找"
    >
      <template #actions>
        <el-button
          type="primary"
          icon="Plus"
          v-hasPermi="['system:oauthResource:add']"
          @click="handleAdd"
          >新增服务</el-button
        >
      </template>

      <template #filters>
        <el-form
          v-show="showSearch"
          ref="queryRef"
          :model="queryParams"
          :inline="true"
        >
          <el-form-item
            label="服务名称"
            prop="resourceName"
          >
            <el-input
              v-model="queryParams.resourceName"
              clearable
              placeholder="输入服务名称"
              style="width: 200px"
              @keyup.enter="handleQuery"
            />
          </el-form-item>
          <el-form-item
            label="状态"
            prop="status"
          >
            <el-select
              v-model="queryParams.status"
              clearable
              placeholder="全部状态"
              style="width: 200px"
            >
              <el-option
                label="使用中"
                value="0"
              />
              <el-option
                label="已停用"
                value="1"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              icon="Search"
              @click="handleQuery"
              >查找</el-button
            >
            <el-button
              icon="Refresh"
              @click="resetQuery"
              >清空</el-button
            >
          </el-form-item>
        </el-form>
      </template>

      <template #toolbar>
        <span class="result-count"
          >已登记 <strong>{{ total }}</strong> 个服务</span
        >
        <right-toolbar
          v-model:showSearch="showSearch"
          @queryTable="getList"
        />
      </template>

      <el-table
        v-loading="loading"
        :data="resourceList"
        row-key="resourceId"
      >
        <el-table-column
          label="服务"
          min-width="230"
        >
          <template #default="scope">
            <div class="entity-cell">
              <span class="service-mark"
                ><el-icon><Connection /></el-icon
              ></span>
              <span class="entity-copy">
                <strong>{{ scope.row.resourceName }}</strong>
                <code>{{ scope.row.resourceId }}</code>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="令牌目标"
          prop="audience"
          min-width="250"
          show-overflow-tooltip
        >
          <template #default="scope"
            ><code class="audience-value">{{ scope.row.audience }}</code></template
          >
        </el-table-column>
        <el-table-column
          label="返回的用户信息"
          min-width="240"
        >
          <template #default="scope">
            <div class="tag-summary">
              <el-tag
                v-for="claim in (scope.row.allowedClaims || []).slice(0, 3)"
                :key="claim"
                size="small"
                effect="plain"
                >{{ claimLabel(claim) }}</el-tag
              >
              <span
                v-if="(scope.row.allowedClaims || []).length > 3"
                class="muted-value"
                >+{{ scope.row.allowedClaims.length - 3 }}</span
              >
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="有效时长"
          width="120"
          align="center"
        >
          <template #default="scope">{{
            scope.row.accessTokenTtlSeconds
              ? formatDuration(scope.row.accessTokenTtlSeconds)
              : '平台默认'
          }}</template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="105"
          align="center"
        >
          <template #default="scope">
            <el-tag :type="scope.row.status === '0' ? 'success' : 'info'">{{
              scope.row.status === '0' ? '使用中' : '已停用'
            }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="180"
          fixed="right"
          align="center"
        >
          <template #default="scope">
            <div class="table-actions">
              <el-button
                link
                type="primary"
                icon="Edit"
                v-hasPermi="['system:oauthResource:edit']"
                @click="handleUpdate(scope.row)"
                >编辑</el-button
              >
              <el-dropdown
                trigger="click"
                @command="(command) => handleRowCommand(command, scope.row)"
              >
                <el-button
                  link
                  type="primary"
                  icon="ArrowDown"
                  >更多</el-button
                >
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-if="scope.row.status !== '0'"
                      command="enable"
                      icon="CircleCheck"
                      v-hasPermi="['system:oauthResource:edit']"
                      >重新启用</el-dropdown-item
                    >
                    <el-dropdown-item
                      v-else
                      command="disable"
                      icon="CircleClose"
                      v-hasPermi="['system:oauthResource:remove']"
                      >停用服务</el-dropdown-item
                    >
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有符合条件的服务">
            <el-button
              type="primary"
              v-hasPermi="['system:oauthResource:add']"
              @click="handleAdd"
              >新增第一个服务</el-button
            >
          </el-empty>
        </template>
      </el-table>
      <pagination
        v-show="total > 0"
        v-model:page="queryParams.pageNum"
        v-model:limit="queryParams.pageSize"
        :total="total"
        @pagination="getList"
      />
    </PageFrame>

    <el-dialog
      v-model="open"
      :title="form.persisted ? '编辑服务' : '新增服务'"
      width="min(820px, calc(100vw - 48px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="160px"
        class="resource-form"
      >
        <section class="form-section">
          <div class="section-heading">
            <h3>服务身份</h3>
            <p>应用通过服务标识申请访问，服务通过令牌目标判断凭据是否发给自己。</p>
          </div>
          <el-row :gutter="18">
            <el-col
              :xs="24"
              :sm="12"
            >
              <el-form-item prop="resourceName">
                <template #label
                  ><FieldLabel
                    label="服务名称"
                    help="管理端展示名称，便于管理员识别这个服务。"
                /></template>
                <el-input
                  v-model="form.resourceName"
                  placeholder="例如：订单服务"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
            <el-col
              :xs="24"
              :sm="12"
            >
              <el-form-item prop="resourceId">
                <template #label
                  ><FieldLabel
                    label="服务标识"
                    help="应用通过这个唯一标识关联服务，保存后不能修改。"
                /></template>
                <el-input
                  v-model="form.resourceId"
                  :disabled="form.persisted"
                  placeholder="例如：orders-api"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item prop="audience">
            <template #label
              ><FieldLabel
                label="令牌目标"
                help="服务校验访问凭据时使用的唯一值，必须与服务端配置完全一致。"
            /></template>
            <el-input
              v-model="form.audience"
              :disabled="form.persisted"
              placeholder="例如：https://api.example.com"
              style="width: 100%"
            />
          </el-form-item>
        </section>

        <section class="form-section">
          <div class="section-heading">
            <h3>凭据和用户信息</h3>
            <p>控制访问凭据的寿命，以及这个服务最多可以获得哪些用户信息。</p>
          </div>
          <el-row :gutter="18">
            <el-col
              :xs="24"
              :sm="12"
            >
              <el-form-item>
                <template #label
                  ><FieldLabel
                    label="有效时长"
                    help="服务收到的访问凭据最多可以使用多久，留空使用平台默认值。"
                /></template>
                <el-input-number
                  v-model="form.accessTokenTtlSeconds"
                  :min="1"
                  placeholder="平台默认"
                  controls-position="right"
                  style="width: 100%"
                />
                <span class="input-unit">秒</span>
              </el-form-item>
            </el-col>
            <el-col
              :xs="24"
              :sm="12"
            >
              <el-form-item>
                <template #label
                  ><FieldLabel
                    label="令牌检查应用"
                    help="可选。填写一个后端应用编号，用于检查凭据是否仍然有效。"
                /></template>
                <el-input
                  v-model="form.introspectionClientId"
                  placeholder="可选：后端应用编号"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item prop="allowedClaims">
            <template #label
              ><FieldLabel
                label="可返回用户信息"
                help="限制这个服务最多能收到哪些用户信息，最终结果仍会受权限项限制。"
            /></template>
            <el-select
              v-model="form.allowedClaims"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入用户字段"
              style="width: 100%"
            >
              <el-option
                v-for="item in claimOptions"
                :key="item.value"
                :label="item.label"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <template #label
              ><FieldLabel
                label="备注"
                help="仅供管理员记录，不会发送给外部应用或服务。"
            /></template>
            <el-input
              v-model="form.remark"
              type="textarea"
              :rows="3"
              maxlength="500"
              show-word-limit
              style="width: 100%"
            />
          </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="submitForm"
          >保存服务</el-button
        >
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="OAuthResource">
import {
  addOAuthResource,
  changeOAuthResourceStatus,
  deleteOAuthResources,
  getOAuthResource,
  listOAuthResources,
  updateOAuthResource,
} from '@/api/system/oauthResource'
import FieldLabel from '@/components/OAuthWorkspace/FieldLabel.vue'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'

const { proxy } = getCurrentInstance()
const resourceList = ref([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const showSearch = ref(true)
const open = ref(false)
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  resourceName: undefined,
  status: undefined,
})
const form = reactive(emptyForm())
const claimOptions = [
  { value: 'sub', label: '用户唯一标识（sub）' },
  { value: 'name', label: '姓名（name）' },
  { value: 'email', label: '邮箱（email）' },
  { value: 'roles', label: '角色（roles）' },
  { value: 'client_id', label: '应用编号（client_id）' },
  { value: 'scope', label: '已获权限（scope）' },
  { value: 'sid', label: '会话标识（sid）' },
]
const rules = {
  resourceId: [{ required: true, message: '请输入服务标识', trigger: 'blur' }],
  resourceName: [{ required: true, message: '请输入服务名称', trigger: 'blur' }],
  audience: [
    {
      required: true,
      message: '请输入令牌目标（通常填写服务地址）',
      trigger: 'blur',
    },
  ],
  allowedClaims: [
    {
      required: true,
      type: 'array',
      min: 1,
      message: '至少选择一项可返回的用户信息',
      trigger: 'change',
    },
  ],
}

/** 创建资源服务表单默认值 */
function emptyForm() {
  return {
    persisted: false,
    resourceId: '',
    resourceName: '',
    audience: '',
    tokenFormat: 'jwt',
    signingAlg: 'RS256',
    accessTokenTtlSeconds: null,
    introspectionClientId: null,
    allowedClaims: ['sub', 'client_id', 'scope', 'sid'],
    status: '0',
    remark: '',
  }
}

/** 重置资源服务表单 */
function resetForm() {
  Object.assign(form, emptyForm())
  proxy.resetForm('formRef')
}

/** 查询资源服务列表 */
async function getList() {
  loading.value = true
  try {
    const response = await listOAuthResources(queryParams)
    resourceList.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

/** 新增按钮操作 */
function handleAdd() {
  resetForm()
  open.value = true
}

/** 修改按钮操作 */
async function handleUpdate(row) {
  resetForm()
  const response = await getOAuthResource(row.resourceId)
  Object.assign(form, response.data, {
    persisted: true,
    allowedClaims: [...(response.data.allowedClaims || [])],
  })
  open.value = true
}

/** 校验并保存资源服务配置 */
async function submitForm() {
  await proxy.$refs.formRef.validate()
  saving.value = true
  try {
    const { persisted, ...data } = form
    data.allowedClaims = [...form.allowedClaims]
    if (!persisted) {
      delete data.status
    }
    await (persisted ? updateOAuthResource(data) : addOAuthResource(data))
    proxy.$modal.msgSuccess('资源配置已保存')
    open.value = false
    await getList()
  } finally {
    saving.value = false
  }
}

/** 修改资源服务状态 */
async function changeStatus(row, status) {
  try {
    await proxy.$modal.confirm(`${status === '0' ? '启用' : '停用'}资源“${row.resourceName}”？`)
    await changeOAuthResourceStatus({ resourceId: row.resourceId, status })
    getList()
  } catch {
    getList()
  }
}

/** 删除按钮操作 */
async function handleDelete(row) {
  await proxy.$modal.confirm(
    `停用“${row.resourceName}”后将停止为该服务签发和刷新访问令牌，是否继续？`
  )
  await deleteOAuthResources(row.resourceId)
  proxy.$modal.msgSuccess('资源已停用')
  await getList()
}

/** 处理资源服务行操作 */
function handleRowCommand(command, row) {
  if (command === 'enable') {
    return changeStatus(row, '0')
  }
  if (command === 'disable') {
    return handleDelete(row)
  }
}

/** 获取声明字段的展示名称 */
function claimLabel(value) {
  return claimOptions.find((item) => item.value === value)?.label?.replace(/（.*）$/, '') || value
}

/** 显示访问令牌有效期 */
function formatDuration(value) {
  const seconds = Number(value) || 0
  if (seconds >= 3600 && seconds % 3600 === 0) {
    return `${seconds / 3600} 小时`
  }
  if (seconds >= 60 && seconds % 60 === 0) {
    return `${seconds / 60} 分钟`
  }
  return `${seconds} 秒`
}

getList()
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

.entity-cell {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.service-mark {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 8px;
  place-items: center;
}

.entity-copy {
  min-width: 0;
}

.entity-copy strong,
.entity-copy code {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entity-copy strong {
  color: var(--el-text-color-primary);
}

.entity-copy code,
.audience-value {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.entity-copy code {
  margin-top: 4px;
}

.tag-summary {
  display: flex;
  align-items: center;
  gap: 5px;
}

.muted-value {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.form-section + .form-section {
  margin-top: 6px;
  padding-top: 22px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.section-heading {
  margin-bottom: 22px;
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

.resource-form :deep(.el-input-number) {
  flex: 1;
  width: auto !important;
}

.input-unit {
  flex: 0 0 auto;
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 768px) {
  .resource-form :deep(.el-form-item) {
    display: block;
  }

  .resource-form :deep(.el-form-item__label) {
    width: auto !important;
    margin-bottom: 6px;
  }

  .resource-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }
}
</style>
