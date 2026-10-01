<template>
  <div class="oauth-route-page">
    <PageFrame
      section="安全运维"
      title="安全日志"
      description="按时间查看登录、授权、凭据签发和策略变更，快速判断一次操作是否正常、影响了谁。"
      filter-hint="日志内容已经脱敏，不包含密码、密钥或完整凭据"
    >
      <template #actions>
        <el-button
          type="primary"
          plain
          icon="Download"
          v-hasPermi="['monitor:oauthAudit:export']"
          @click="exportRows"
        >
          导出当前结果
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
            label="发生的操作"
            prop="eventType"
          >
            <el-select
              v-model="queryParams.eventType"
              clearable
              filterable
              placeholder="全部操作"
              style="width: 200px"
            >
              <el-option-group
                v-for="group in eventGroups"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="item in group.options"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item
            label="应用"
            prop="clientId"
          >
            <el-input
              v-model="queryParams.clientId"
              clearable
              placeholder="应用编号"
              style="width: 200px"
            />
          </el-form-item>
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
            label="处理结果"
            prop="result"
          >
            <el-select
              v-model="queryParams.result"
              clearable
              placeholder="全部结果"
              style="width: 200px"
            >
              <el-option
                label="已完成"
                value="success"
              />
              <el-option
                label="未完成"
                value="failure"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            label="风险程度"
            prop="riskLevel"
          >
            <el-select
              v-model="queryParams.riskLevel"
              clearable
              placeholder="全部风险"
              style="width: 200px"
            >
              <el-option
                label="常规"
                value="normal"
              />
              <el-option
                label="需要关注"
                value="medium"
              />
              <el-option
                label="高风险"
                value="high"
              />
              <el-option
                label="严重"
                value="critical"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="发生时间">
            <el-date-picker
              v-model="dateRange"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm:ss"
              range-separator="至"
              start-placeholder="开始"
              end-placeholder="结束"
              style="width: 200px"
            />
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
          >找到 <strong>{{ total }}</strong> 条记录</span
        >
        <right-toolbar
          v-model:showSearch="showSearch"
          @queryTable="getList"
        />
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        row-key="auditId"
      >
        <el-table-column
          label="发生时间"
          width="170"
        >
          <template #default="scope">{{
            parseTime(scope.row.occurredAt || scope.row.createTime)
          }}</template>
        </el-table-column>
        <el-table-column
          label="发生的操作"
          min-width="230"
        >
          <template #default="scope">
            <div class="event-cell">
              <span
                class="event-mark"
                :class="`is-${eventTone(scope.row)}`"
                ><el-icon><Key /></el-icon
              ></span>
              <span
                ><strong>{{ eventLabel(scope.row.eventType) }}</strong
                ><small>{{ eventSummary(scope.row) }}</small></span
              >
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="相关对象"
          min-width="200"
        >
          <template #default="scope">
            <div class="subject-cell">
              <span>{{ scope.row.userName || scope.row.userId || '系统或机器身份' }}</span>
              <small>{{ scope.row.clientName || scope.row.clientId || '未关联具体应用' }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="来源"
          min-width="150"
        >
          <template #default="scope"
            ><div class="subject-cell">
              <span>{{ scope.row.ipAddress || '系统内部' }}</span
              ><small>{{ sourceText(scope.row) }}</small>
            </div></template
          >
        </el-table-column>
        <el-table-column
          label="处理结果"
          width="105"
          align="center"
        >
          <template #default="scope"
            ><el-tag :type="scope.row.result === 'success' ? 'success' : 'danger'">{{
              scope.row.result === 'success' ? '已完成' : '未完成'
            }}</el-tag></template
          >
        </el-table-column>
        <el-table-column
          label="风险"
          width="110"
          align="center"
        >
          <template #default="scope"
            ><el-tag :type="riskType(scope.row.riskLevel)">{{
              riskText(scope.row.riskLevel)
            }}</el-tag></template
          >
        </el-table-column>
        <el-table-column
          label="需要关注"
          min-width="210"
          show-overflow-tooltip
        >
          <template #default="scope">{{
            failureText(scope.row.failureCode, scope.row.result)
          }}</template>
        </el-table-column>
        <el-table-column
          label="操作"
          width="100"
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
            </div>
          </template>
        </el-table-column>
        <template #empty><el-empty description="当前条件下没有安全日志" /></template>
      </el-table>
      <pagination
        v-show="total > 0"
        v-model:page="queryParams.pageNum"
        v-model:limit="queryParams.pageSize"
        :total="total"
        @pagination="getList"
      />
    </PageFrame>

    <el-drawer
      v-model="detailOpen"
      title="安全事件详情"
      size="min(660px, 92vw)"
    >
      <div class="detail-hero">
        <span
          class="event-mark large"
          :class="`is-${eventTone(detail)}`"
          ><el-icon><Key /></el-icon
        ></span>
        <div>
          <strong>{{ eventLabel(detail.eventType) }}</strong>
          <p>{{ parseTime(detail.occurredAt || detail.createTime) || '时间未知' }}</p>
        </div>
        <div class="detail-tags">
          <el-tag :type="detail.result === 'success' ? 'success' : 'danger'">{{
            detail.result === 'success' ? '已完成' : '未完成'
          }}</el-tag>
          <el-tag :type="riskType(detail.riskLevel)">{{ riskText(detail.riskLevel) }}</el-tag>
        </div>
      </div>
      <section class="detail-section">
        <h4>发生了什么</h4>
        <p>
          {{ eventSummary(detail)
          }}{{
            failureText(detail.failureCode, detail.result) !== '无需处理'
              ? `。${failureText(detail.failureCode, detail.result)}`
              : ''
          }}
        </p>
      </section>
      <el-descriptions
        :column="1"
        border
        class="detail-descriptions"
      >
        <el-descriptions-item label="相关用户">{{
          detail.userName || detail.userId || '系统或机器身份'
        }}</el-descriptions-item>
        <el-descriptions-item label="相关应用">{{
          detail.clientName || detail.clientId || '未关联具体应用'
        }}</el-descriptions-item>
        <el-descriptions-item label="相关服务">{{
          detail.resourceId || '未关联具体服务'
        }}</el-descriptions-item>
        <el-descriptions-item label="来源地址">{{
          detail.ipAddress || '系统内部'
        }}</el-descriptions-item>
        <el-descriptions-item label="失败原因">{{
          failureText(detail.failureCode, detail.result)
        }}</el-descriptions-item>
      </el-descriptions>
      <el-collapse class="technical-details">
        <el-collapse-item
          title="查看排障信息"
          name="technical"
        >
          <dl>
            <dt>事件代码</dt>
            <dd>{{ detail.eventType || '—' }}</dd>
            <dt>事件 ID</dt>
            <dd>{{ detail.auditId || detail.eventId || '—' }}</dd>
            <dt>链路 ID</dt>
            <dd>{{ detail.traceId || '—' }}</dd>
            <dt>用户主体</dt>
            <dd>{{ detail.subjectId || '—' }}</dd>
            <dt>会话 ID</dt>
            <dd>{{ detail.sid || '—' }}</dd>
            <dt>授权 ID</dt>
            <dd>{{ detail.grantId || '—' }}</dd>
            <dt>凭据 ID</dt>
            <dd>{{ detail.tokenId || '—' }}</dd>
            <dt>错误代码</dt>
            <dd>{{ detail.failureCode || '—' }}</dd>
            <dt>浏览器信息</dt>
            <dd>{{ detail.userAgent || '—' }}</dd>
          </dl>
        </el-collapse-item>
      </el-collapse>
    </el-drawer>
  </div>
</template>

<script setup name="OAuthAudit">
import { listOAuthAudit } from '@/api/monitor/oauthAudit'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'

const { proxy } = getCurrentInstance()
const rows = ref([])
const detail = ref({})
const dateRange = ref([])
const total = ref(0)
const loading = ref(false)
const showSearch = ref(true)
const detailOpen = ref(false)

const eventGroups = [
  {
    label: '登录与授权',
    options: [
      { label: '收到登录授权请求', value: 'authorize_requested' },
      { label: '登录授权已完成', value: 'authorize_succeeded' },
      { label: '登录授权被拒绝', value: 'authorize_denied' },
      { label: '用户登录成功', value: 'login_succeeded' },
      { label: '用户登录失败', value: 'login_failed' },
      { label: '用户同意授权', value: 'consent_granted' },
      { label: '用户撤销授权', value: 'consent_revoked' },
    ],
  },
  {
    label: '凭据与会话',
    options: [
      { label: '访问凭据已签发', value: 'token_issued' },
      { label: '访问凭据处理失败', value: 'token_failed' },
      { label: '刷新凭据已更新', value: 'refresh_rotated' },
      { label: '发现刷新凭据被重复使用', value: 'refresh_reuse_detected' },
      { label: '访问凭据已撤销', value: 'token_revoked' },
      { label: '登录会话已下线', value: 'session_revoked' },
      { label: '用户授权已撤销', value: 'grant_revoked' },
      { label: '用户应用访问已禁止', value: 'client_access_blocked' },
      { label: '用户应用访问已允许', value: 'client_access_allowed' },
      { label: '应用退出通知成功', value: 'backchannel_logout_succeeded' },
      { label: '应用退出通知失败', value: 'backchannel_logout_failed' },
    ],
  },
  {
    label: '配置与安全',
    options: [
      { label: '应用已注册', value: 'client_created' },
      { label: '应用已停用', value: 'client_disabled' },
      { label: '应用密钥已更新', value: 'client_secret_rotated' },
      { label: '签名密钥已轮换', value: 'signing_key_rotated' },
      { label: '服务访问策略已变更', value: 'resource_policy_changed' },
      { label: '权限策略已变更', value: 'scope_policy_changed' },
      { label: '发现授权码被重复使用', value: 'authorization_code_reused' },
      { label: '应用身份验证失败', value: 'invalid_client' },
      { label: '用户身份标识缺失', value: 'identity_subject_missing' },
      { label: '账户安全版本已变更', value: 'security_version_changed' },
    ],
  },
]

const eventLabels = Object.fromEntries(
  eventGroups.flatMap((group) => group.options).map((item) => [item.value, item.label])
)
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  eventType: undefined,
  clientId: undefined,
  userId: undefined,
  result: undefined,
  riskLevel: undefined,
})

/** 获取安全事件名称 */
function eventLabel(value) {
  return eventLabels[value] || value || '未知安全操作'
}

/** 获取安全事件的业务说明 */
function eventSummary(row = {}) {
  const labels = {
    authorize_requested: '应用发起了用户登录或权限授权请求',
    authorize_succeeded: '用户身份确认和应用授权流程已经完成',
    authorize_denied: '登录或权限授权请求没有继续执行',
    login_succeeded: '用户已经通过身份验证',
    login_failed: '用户身份验证没有通过',
    consent_granted: '用户允许应用访问所请求的信息',
    consent_revoked: '用户取消了应用的持续访问权限',
    token_issued: '系统为应用签发了新的短期访问凭据',
    token_failed: '系统没有为应用签发访问凭据',
    refresh_rotated: '应用用于续期的凭据已经安全更新',
    refresh_reuse_detected: '同一份旧续期凭据被再次使用，可能存在泄露',
    token_revoked: '一份访问凭据已经作废',
    session_revoked: '一个外部登录会话已经被强制结束',
    grant_revoked: '一项用户对应用的访问授权已经撤销',
    client_access_blocked: '管理员已禁止用户访问指定应用，并撤销现有授权',
    client_access_allowed: '管理员已解除用户对指定应用的访问禁止，仍需重新授权',
    backchannel_logout_succeeded: '系统已经通知关联应用结束本地登录会话',
    backchannel_logout_failed: '关联应用没有成功接收退出通知',
    client_created: '一个新应用已接入统一认证',
    client_disabled: '一个应用已被禁止继续使用统一认证',
    client_secret_rotated: '应用用于证明身份的密钥已经更新',
    signing_key_rotated: '系统用于签署身份凭据的密钥已经更新',
    resource_policy_changed: '一个服务允许访问的凭据或用户信息配置已变更',
    scope_policy_changed: '一个权限的适用范围或用户确认要求已变更',
    authorization_code_reused: '一次性登录授权码被再次使用，可能存在攻击',
    invalid_client: '应用无法证明自己的身份',
    identity_subject_missing: '用户缺少统一认证所需的稳定身份标识',
    security_version_changed: '账户安全信息变更，旧登录状态将逐步失效',
  }
  return labels[row.eventType] || '系统记录了一次认证安全操作'
}

/** 根据处理结果和风险等级显示事件颜色 */
function eventTone(row = {}) {
  if (row.result === 'failure' || ['high', 'critical'].includes(row.riskLevel)) {
    return 'danger'
  }
  if (row.riskLevel === 'medium') {
    return 'warning'
  }
  return 'normal'
}

/** 显示请求来源摘要 */
function sourceText(row = {}) {
  if (row.userAgent) {
    return row.userAgent.length > 26 ? `${row.userAgent.slice(0, 26)}…` : row.userAgent
  }
  return row.ipAddress ? '外部请求' : '后台操作'
}

/** 将协议失败代码转换为处理说明 */
function failureText(code, result) {
  if (result !== 'failure' && !code) {
    return '无需处理'
  }
  const labels = {
    invalid_request: '请求信息不完整或格式不正确',
    invalid_client: '应用身份验证失败，请检查应用凭据',
    invalid_grant: '登录或授权凭据已经失效',
    unauthorized_client: '应用未获准使用当前登录方式',
    unsupported_grant_type: '系统不支持当前登录方式',
    invalid_scope: '应用请求了尚未开放的权限',
    access_denied: '用户或安全策略拒绝了本次操作',
    login_required: '用户需要重新登录',
    consent_required: '需要用户确认应用所需权限',
    server_error: '认证服务暂时无法完成请求',
    temporarily_unavailable: '认证服务暂时不可用',
  }
  return labels[code] || (code ? `操作未完成（${code}）` : '操作未完成，详情中暂无具体原因')
}

/** 获取风险等级名称 */
function riskText(value) {
  return { normal: '常规', medium: '需关注', high: '高风险', critical: '严重' }[value] || '常规'
}
/** 获取风险等级标签类型 */
function riskType(value) {
  return { normal: 'info', medium: 'warning', high: 'danger', critical: 'danger' }[value] || 'info'
}
/** 合并分页条件和时间筛选范围 */
function params() {
  return {
    ...queryParams,
    startTime: dateRange.value?.[0],
    endTime: dateRange.value?.[1],
  }
}

/** 查询认证安全日志列表 */
async function getList() {
  loading.value = true
  try {
    const response = await listOAuthAudit(params())
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
  dateRange.value = []
  proxy.resetForm('queryRef')
  handleQuery()
}
/** 查看安全日志详情 */
function showDetail(row) {
  detail.value = row
  detailOpen.value = true
}
/** 导出当前筛选条件下的安全日志 */
function exportRows() {
  proxy.download('monitor/oauth/audit/export', params(), `oauth_audit_${Date.now()}.xlsx`)
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

.event-cell,
.detail-hero {
  display: flex;
  align-items: center;
  gap: 11px;
}

.event-mark {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 9px;
  place-items: center;
}

.event-mark.is-warning {
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
}

.event-mark.is-danger {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.event-mark.large {
  flex-basis: 44px;
  width: 44px;
  height: 44px;
  font-size: 19px;
}

.event-cell strong,
.event-cell small,
.subject-cell span,
.subject-cell small {
  display: block;
}

.event-cell strong,
.subject-cell span {
  color: var(--el-text-color-primary);
}

.event-cell small,
.subject-cell small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.detail-hero {
  padding-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-hero > div:nth-child(2) {
  flex: 1;
  min-width: 0;
}

.detail-hero strong {
  color: var(--el-text-color-primary);
  font-size: 17px;
}

.detail-hero p {
  margin: 5px 0 0;
  color: var(--el-text-color-secondary);
}

.detail-tags {
  display: flex;
  gap: 6px;
}

.detail-section {
  padding: 18px 0 0;
}

.detail-section h4 {
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}

.detail-section p {
  margin: 0;
  color: var(--el-text-color-regular);
  line-height: 1.7;
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

@media (max-width: 560px) {
  .detail-hero {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .detail-tags {
    width: 100%;
    padding-left: 55px;
  }
}
</style>
