<template>
  <div class="oauth-route-page">
    <PageFrame
      section="访问控制"
      title="登录会话"
      description="查看正在使用统一登录的用户、来源位置和关联应用，并强制结束异常会话。"
      filter-hint="默认只显示仍然在线的会话"
    >
      <template #actions>
        <el-button
          type="danger"
          plain
          icon="SwitchButton"
          :disabled="!selected.length"
          v-hasPermi="['system:oauthSession:revoke']"
          @click="openRevoke()"
        >
          强制下线{{ selected.length ? `（${selected.length}）` : '' }}
        </el-button>
      </template>
      <template #filters>
        <el-form
          v-show="showSearch"
          ref="queryRef"
          :model="queryParams"
          :inline="true"
        >
          <el-form-item
            label="用户"
            prop="userId"
          >
            <el-input
              v-model="queryParams.userId"
              clearable
              placeholder="用户编号"
              style="width: 200px"
            />
          </el-form-item>
          <el-form-item
            label="来源地址"
            prop="ipAddress"
          >
            <el-input
              v-model="queryParams.ipAddress"
              clearable
              placeholder="IP 地址"
              style="width: 200px"
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
                label="在线"
                value="active"
              />
              <el-option
                label="已下线"
                value="revoked"
              />
              <el-option
                label="已过期"
                value="expired"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              icon="Search"
              @click="handleQuery"
              >查找
            </el-button>
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
          >找到 <strong>{{ total }}</strong> 个会话
        </span>
        <right-toolbar
          v-model:showSearch="showSearch"
          @queryTable="getList"
        />
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        row-key="sid"
        @selection-change="selected = $event"
      >
        <el-table-column
          type="selection"
          width="48"
          :selectable="(row) => row.status !== 'revoked'"
        />
        <el-table-column
          label="用户"
          min-width="190"
        >
          <template #default="scope">
            <div class="person-cell">
              <span class="person-mark">
                <el-icon><User /></el-icon>
              </span>
              <span>
                <strong>{{ scope.row.userName || `用户 ${scope.row.userId}` }}</strong>
                <small>{{ scope.row.userId || shortId(scope.row.subjectId) }}</small>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="来源"
          min-width="160"
        >
          <template #default="scope">
            <div class="stacked-cell">
              <strong>{{ scope.row.ipAddress || '未知地址' }}</strong>
              <small>{{ authMethodText(scope.row.amr) }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="关联应用"
          min-width="210"
        >
          <template #default="scope">
            <div class="tag-summary">
              <el-tag
                v-for="item in (scope.row.clientIds || []).slice(0, 2)"
                :key="item"
                size="small"
                effect="plain"
                >{{ item }}</el-tag
              >
              <span
                v-if="!(scope.row.clientIds || []).length"
                class="muted-value"
                >尚无关联应用</span
              >
              <span
                v-else-if="scope.row.clientIds.length > 2"
                class="muted-value"
                >+{{ scope.row.clientIds.length - 2 }}</span
              >
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="最近活动"
          width="170"
        >
          <template #default="scope">
            {{ parseTime(scope.row.lastSeenAt) || '—' }}
          </template>
        </el-table-column>
        <el-table-column
          label="最晚结束时间"
          width="170"
        >
          <template #default="scope">
            {{ parseTime(scope.row.absoluteExpiresAt) || '—' }}
          </template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="105"
          align="center"
        >
          <template #default="scope">
            <el-tag :type="statusType(scope.row.status)">
              {{ statusText(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="160"
          fixed="right"
          align="center"
        >
          <template #default="scope">
            <div class="table-actions">
              <el-button
                link
                type="primary"
                icon="View"
                @click="showDetail(scope.row)"
                >查看</el-button
              >
              <el-button
                v-if="scope.row.status !== 'revoked'"
                link
                type="danger"
                icon="SwitchButton"
                v-hasPermi="['system:oauthSession:revoke']"
                @click="openRevoke(scope.row)"
                >下线</el-button
              >
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="没有符合条件的登录会话" />
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
      v-model="revokeOpen"
      title="强制结束登录会话"
      width="min(540px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="impact-summary">
        <el-icon><WarningFilled /></el-icon>
        <div>
          <strong>将结束 {{ revokeIds.length }} 个外部登录会话</strong>
          <p>
            将终止这些会话的登录状态及离线访问凭据。资源服务通过在线校验感知失效；应用本地登录状态由应用负责清理。
          </p>
        </div>
      </div>
      <label
        class="reason-label"
        for="session-revoke-reason"
        >下线原因</label
      >
      <el-input
        id="session-revoke-reason"
        v-model="reason"
        type="textarea"
        :rows="3"
        maxlength="200"
        show-word-limit
        placeholder="说明为什么要强制下线，便于后续审计"
      />
      <template #footer>
        <el-button @click="revokeOpen = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="!reason.trim()"
          :loading="revoking"
          @click="revoke"
          >确认下线</el-button
        >
      </template>
    </el-dialog>

    <el-drawer
      v-model="detailOpen"
      title="登录会话详情"
      size="min(640px, 92vw)"
    >
      <div class="detail-hero">
        <span class="person-mark large">
          <el-icon><User /></el-icon>
        </span>
        <div>
          <strong>{{ detail.userName || detail.userId || '用户' }}</strong>
          <p>
            {{ detail.ipAddress || '未知来源地址' }} ·
            {{ authMethodText(detail.amr) }}
          </p>
        </div>
        <el-tag :type="statusType(detail.status)">{{ statusText(detail.status) }}</el-tag>
      </div>
      <section class="detail-section">
        <h4>关联应用</h4>
        <div class="tag-summary">
          <el-tag
            v-for="item in detail.clientIds || []"
            :key="item"
            effect="plain"
            >{{ item }}</el-tag
          ><span
            v-if="!(detail.clientIds || []).length"
            class="muted-value"
            >尚无关联应用</span
          >
        </div>
      </section>
      <el-descriptions
        :column="1"
        border
        class="detail-descriptions"
      >
        <el-descriptions-item label="登录时间">{{
          parseTime(detail.authTime) || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="最近活动">{{
          parseTime(detail.lastSeenAt) || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="闲置后过期">{{
          parseTime(detail.idleExpiresAt) || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="最晚结束时间">{{
          parseTime(detail.absoluteExpiresAt) || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="下线原因">{{
          detail.revokeReason || '—'
        }}</el-descriptions-item>
      </el-descriptions>
      <el-collapse class="technical-details"
        ><el-collapse-item
          title="查看技术标识"
          name="technical"
          ><dl>
            <dt>会话 ID</dt>
            <dd>{{ detail.sid }}</dd>
            <dt>用户主体</dt>
            <dd>{{ detail.subjectId }}</dd>
            <dt>身份版本</dt>
            <dd>{{ detail.authVersion || '—' }}</dd>
            <dt>认证级别</dt>
            <dd>{{ detail.acr || '—' }}</dd>
          </dl></el-collapse-item
        ></el-collapse
      >
    </el-drawer>
  </div>
</template>

<script setup name="OAuthSession">
import { getOAuthSession, listOAuthSessions, revokeOAuthSessions } from '@/api/system/oauthSession'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'

const { proxy } = getCurrentInstance()
const rows = ref([])
const selected = ref([])
const total = ref(0)
const loading = ref(false)
const revoking = ref(false)
const showSearch = ref(true)
const revokeOpen = ref(false)
const detailOpen = ref(false)
const revokeIds = ref([])
const reason = ref('')
const detail = ref({})
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: undefined,
  ipAddress: undefined,
  status: 'active',
})

/** 缩略显示会话标识 */
function shortId(value, size = 12) {
  if (!value) {
    return '—'
  }
  return value.length > size ? `${value.slice(0, size)}…` : value
}

/** 获取会话状态名称 */
function statusText(value) {
  return { active: '在线', revoked: '已下线', expired: '已过期' }[value] || '未知状态'
}

/** 获取会话状态标签类型 */
function statusType(value) {
  return { active: 'success', revoked: 'danger', expired: 'info' }[value] || 'info'
}

/** 获取认证方式的展示名称 */
function authMethodText(methods = []) {
  const labels = {
    pwd: '密码登录',
    password: '密码登录',
    otp: '动态验证码',
    mfa: '多重验证',
    sms: '短信验证',
  }
  return methods.length ? methods.map((item) => labels[item] || item).join(' + ') : '登录方式未知'
}

/** 查询认证会话列表 */
async function getList() {
  loading.value = true
  try {
    const response = await listOAuthSessions(queryParams)
    selected.value = []
    rows.value = response.rows || []
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

/** 打开会话下线对话框 */
function openRevoke(row) {
  revokeIds.value = row ? [row.sid] : selected.value.map((item) => item.sid)
  reason.value = ''
  revokeOpen.value = true
}

/** 提交选中会话的下线原因 */
async function revoke() {
  revoking.value = true
  try {
    await revokeOAuthSessions(revokeIds.value.join(','), {
      reason: reason.value.trim(),
    })
    proxy.$modal.msgSuccess('会话已撤销')
    revokeOpen.value = false
    await getList()
  } finally {
    revoking.value = false
  }
}

/** 查询并展示会话详情 */
async function showDetail(row) {
  const response = await getOAuthSession(row.sid)
  detail.value = response.data
  detailOpen.value = true
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

.person-cell,
.detail-hero {
  display: flex;
  align-items: center;
  gap: 10px;
}

.person-mark {
  display: grid;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  place-items: center;
}

.person-mark.large {
  flex-basis: 42px;
  width: 42px;
  height: 42px;
}

.person-cell strong,
.person-cell small,
.stacked-cell strong,
.stacked-cell small {
  display: block;
}

.person-cell strong,
.stacked-cell strong {
  color: var(--el-text-color-primary);
}

.person-cell small,
.stacked-cell small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.tag-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.muted-value {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.impact-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 16px;
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-7);
  border-radius: 8px;
}

.impact-summary > .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  font-size: 18px;
}

.impact-summary strong {
  color: var(--el-text-color-primary);
}

.impact-summary p {
  margin: 5px 0 0;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
}

.reason-label {
  display: block;
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.detail-hero {
  padding: 0 0 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-hero > div {
  flex: 1;
}

.detail-hero strong {
  color: var(--el-text-color-primary);
  font-size: 17px;
}

.detail-hero p {
  margin: 5px 0 0;
  color: var(--el-text-color-secondary);
}

.detail-section {
  padding: 18px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-section h4 {
  margin: 0 0 10px;
  color: var(--el-text-color-primary);
}

.detail-descriptions {
  margin-top: 18px;
}

.technical-details {
  margin-top: 16px;
}

.technical-details dl {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  margin: 0;
}

.technical-details dt,
.technical-details dd {
  padding: 6px 0;
}

.technical-details dt {
  color: var(--el-text-color-secondary);
}

.technical-details dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
