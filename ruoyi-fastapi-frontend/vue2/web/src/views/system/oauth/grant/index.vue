<template>
  <div class="oauth-route-page">
    <PageFrame
      section="访问控制"
      title="用户授权"
      description="管理用户对应用的访问授权，撤销当前访问或禁止后续授权。"
      filter-hint="授权状态与应用访问策略分别管理；解除禁止后仍需重新授权"
    >
      <template #actions>
        <el-button
          type="primary"
          plain
          icon="el-icon-lock"
          @click="policyOpen = true"
          >访问策略</el-button
        >
        <el-button
          type="danger"
          plain
          icon="el-icon-circle-close"
          :disabled="!selected.length"
          v-hasPermi="['system:oauthGrant:revoke']"
          @click="openRevoke()"
        >
          撤销选中{{ selected.length ? `（${selected.length}）` : '' }}
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
                label="仍然有效"
                value="active"
              />
              <el-option
                label="已撤销"
                value="revoked"
              />
              <el-option
                label="已过期"
                value="expired"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            label="应用访问"
            prop="accessStatus"
          >
            <el-select
              v-model="queryParams.accessStatus"
              clearable
              placeholder="全部策略"
              style="width: 200px"
            >
              <el-option
                label="允许授权"
                value="allowed"
              />
              <el-option
                label="禁止访问"
                value="blocked"
              />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              icon="el-icon-search"
              @click="handleQuery"
              >查找</el-button
            >
            <el-button
              icon="el-icon-refresh"
              @click="resetQuery"
              >清空</el-button
            >
          </el-form-item>
        </el-form>
      </template>
      <template #toolbar>
        <span class="result-count"
          >找到 <strong>{{ total }}</strong> 条授权</span
        >
        <right-toolbar
          :showSearch.sync="showSearch"
          @queryTable="getList"
        />
      </template>

      <el-table
        v-loading="loading"
        :data="rows"
        row-key="grantId"
        @selection-change="selected = $event"
      >
        <el-table-column
          type="selection"
          width="48"
          :selectable="(row) => row.status === 'active'"
        />
        <el-table-column
          label="用户"
          min-width="180"
        >
          <template #default="scope">
            <div class="person-cell">
              <span class="person-mark"
                ><i
                  class="el-icon el-icon-user"
                  aria-hidden="true"
                ></i
              ></span>
              <span
                ><strong>{{ scope.row.userName || `用户 ${scope.row.userId}` }}</strong
                ><small>{{ scope.row.userId || short(scope.row.subjectId) }}</small></span
              >
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="授权给应用"
          min-width="210"
        >
          <template #default="scope"
            ><div class="stacked-cell">
              <strong>{{ scope.row.clientName || scope.row.clientId }}</strong
              ><code>{{ scope.row.clientId }}</code>
            </div></template
          >
        </el-table-column>
        <el-table-column
          label="允许的权限"
          min-width="260"
        >
          <template #default="scope">
            <div class="tag-summary">
              <el-tag
                v-for="item in (scope.row.grantedScopes || []).slice(0, 3)"
                :key="item"
                size="small"
                effect="plain"
                >{{ item }}</el-tag
              >
              <span
                v-if="(scope.row.grantedScopes || []).length > 3"
                class="muted-value"
                >+{{ scope.row.grantedScopes.length - 3 }}</span
              >
            </div>
          </template>
        </el-table-column>
        <el-table-column
          label="可访问服务"
          min-width="170"
          show-overflow-tooltip
        >
          <template #default="scope">{{
            (scope.row.grantedResources || []).join('、') || '仅身份信息'
          }}</template>
        </el-table-column>
        <el-table-column
          label="最后使用"
          width="170"
        >
          <template #default="scope">{{ parseTime(scope.row.lastUsedAt) || '尚未使用' }}</template>
        </el-table-column>
        <el-table-column
          label="状态"
          width="105"
          align="center"
        >
          <template #default="scope"
            ><el-tag :type="statusType(scope.row.status)">{{
              statusText(scope.row.status)
            }}</el-tag></template
          >
        </el-table-column>
        <el-table-column
          label="应用访问"
          width="110"
          align="center"
        >
          <template #default="scope">
            <el-tag
              :type="scope.row.accessStatus === 'blocked' ? 'danger' : 'info'"
              effect="plain"
            >
              {{ scope.row.accessStatus === 'blocked' ? '禁止访问' : '允许授权' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          label="操作"
          fixed="right"
          width="260"
          align="center"
        >
          <template #default="scope">
            <div class="table-actions">
              <el-button
                type="text"
                icon="el-icon-view"
                @click="showDetail(scope.row)"
                >查看</el-button
              >
              <el-button
                class="oauth-button-danger"
                type="text"
                v-if="scope.row.status === 'active'"
                icon="el-icon-circle-close"
                v-hasPermi="['system:oauthGrant:revoke']"
                @click="openRevoke(scope.row)"
                >撤销</el-button
              >
              <el-button
                type="text"
                :class="{ 'oauth-button-danger': scope.row.accessStatus !== 'blocked' }"
                :icon="scope.row.accessStatus === 'blocked' ? 'el-icon-unlock' : 'el-icon-lock'"
                v-hasPermi="['system:oauthGrant:revoke']"
                @click="openAccess(scope.row)"
                >{{ scope.row.accessStatus === 'blocked' ? '解除禁止' : '禁止访问' }}</el-button
              >
            </div>
          </template>
        </el-table-column>
        <template #empty><el-empty description="没有符合条件的用户授权" /></template>
      </el-table>
      <pagination
        v-show="total > 0"
        :page.sync="queryParams.pageNum"
        :limit.sync="queryParams.pageSize"
        :total="total"
        @pagination="getList"
      />
    </PageFrame>

    <AccessPolicyDrawer
      v-model="policyOpen"
      @changed="getList"
    />

    <el-dialog
      custom-class="oauth-overlay"
      :visible.sync="revokeOpen"
      title="撤销用户授权"
      width="min(540px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="impact-summary">
        <i
          class="el-icon el-icon-warning"
          aria-hidden="true"
        ></i>
        <div>
          <strong>将撤销 {{ revokeTargetCount }} 组用户与应用的现有授权</strong>
          <p>
            包括一次性授权、已记住的授权和持续访问权限。在线校验的资源将在下次检查时拒绝旧凭据；仅本地验签或缓存校验结果的资源可能延迟生效。用户重新同意后可以再次访问。
          </p>
        </div>
      </div>
      <label
        class="reason-label"
        for="grant-revoke-reason"
        >撤销原因</label
      >
      <el-input
        id="grant-revoke-reason"
        v-model="reason"
        type="textarea"
        :rows="3"
        maxlength="200"
        show-word-limit
        placeholder="说明为什么要撤销，便于后续审计"
      />
      <template #footer>
        <el-button @click="revokeOpen = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="!reason.trim()"
          :loading="revoking"
          @click="revoke"
          >确认撤销</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      custom-class="oauth-overlay"
      :visible.sync="accessOpen"
      :title="accessBlocked ? '禁止用户访问应用' : '解除应用访问禁止'"
      width="min(540px, calc(100vw - 32px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="impact-summary">
        <i
          class="el-icon el-icon-warning"
          aria-hidden="true"
        ></i>
        <div>
          <strong
            >{{ accessTarget.userName || `用户 ${accessTarget.userId}` }} ·
            {{ accessTarget.clientName || accessTarget.clientId }}</strong
          >
          <p v-if="accessBlocked">
            将撤销该用户对应用的全部现有授权，并禁止再次授权。只有管理员解除禁止后，用户才能重新授权；其他应用不受影响。
          </p>
          <p v-else>解除后用户可以重新授权。已撤销的授权和旧凭据保持失效。</p>
        </div>
      </div>
      <label
        class="reason-label"
        for="grant-access-reason"
        >操作原因</label
      >
      <el-input
        id="grant-access-reason"
        v-model="accessReason"
        type="textarea"
        :rows="3"
        maxlength="200"
        show-word-limit
        placeholder="说明操作原因，便于后续审计"
      />
      <template #footer>
        <el-button @click="accessOpen = false">取消</el-button>
        <el-button
          :type="accessBlocked ? 'danger' : 'primary'"
          :disabled="!accessReason.trim()"
          :loading="savingAccess"
          @click="saveAccess"
          >{{ accessBlocked ? '确认禁止' : '确认解除' }}</el-button
        >
      </template>
    </el-dialog>

    <el-drawer
      custom-class="oauth-overlay"
      :visible.sync="detailOpen"
      title="用户授权详情"
      size="min(640px, 92vw)"
    >
      <div class="detail-hero">
        <span class="person-mark large"
          ><i
            class="el-icon el-icon-user"
            aria-hidden="true"
          ></i
        ></span>
        <div>
          <strong>{{ detail.userName || detail.userId || '用户' }}</strong>
          <p>已授权给 {{ detail.clientName || detail.clientId }}</p>
        </div>
        <el-tag :type="statusType(detail.status)">{{ statusText(detail.status) }}</el-tag>
      </div>
      <section class="detail-section">
        <h4>允许的权限</h4>
        <div class="tag-summary">
          <el-tag
            v-for="item in detail.grantedScopes || []"
            :key="item"
            effect="plain"
            >{{ item }}</el-tag
          >
        </div>
      </section>
      <section class="detail-section">
        <h4>可访问服务</h4>
        <p>{{ (detail.grantedResources || []).join('、') || '仅用于获取登录身份信息' }}</p>
      </section>
      <el-descriptions
        :column="1"
        border
        class="detail-descriptions"
      >
        <el-descriptions-item label="授权时间">{{
          parseTime(detail.consentedAt) || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="最后使用">{{
          parseTime(detail.lastUsedAt) || '尚未使用'
        }}</el-descriptions-item>
        <el-descriptions-item label="后续免确认">{{
          (detail.rememberedScopes || []).join('、') || '未记住，下次仍需按策略确认'
        }}</el-descriptions-item>
        <el-descriptions-item label="应用访问">{{
          detail.accessStatus === 'blocked' ? '禁止访问，需管理员解除' : '允许重新授权'
        }}</el-descriptions-item>
        <el-descriptions-item label="访问策略原因">{{
          detail.accessReason || '—'
        }}</el-descriptions-item>
        <el-descriptions-item label="撤销原因">{{
          detail.revokeReason || '—'
        }}</el-descriptions-item>
      </el-descriptions>
      <el-collapse class="technical-details">
        <el-collapse-item
          title="查看技术标识"
          name="technical"
        >
          <dl>
            <dt>授权 ID</dt>
            <dd>{{ detail.grantId }}</dd>
            <dt>用户主体</dt>
            <dd>{{ detail.subjectId }}</dd>
            <dt>策略版本</dt>
            <dd>{{ detail.clientPolicyVersion || '—' }}</dd>
          </dl>
        </el-collapse-item>
      </el-collapse>
    </el-drawer>
  </div>
</template>

<script>
export default { name: 'OAuthGrant' }
</script>

<script setup>
import { getCurrentInstance, reactive, ref } from 'vue'
import {
  getOAuthGrant,
  listOAuthGrants,
  revokeOAuthGrants,
  setOAuthClientAccess,
} from '@/api/system/oauthSession'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'
import AccessPolicyDrawer from './AccessPolicyDrawer.vue'

const { proxy } = getCurrentInstance()
const rows = ref([])
const selected = ref([])
const detail = ref({})
const total = ref(0)
const loading = ref(false)
const revoking = ref(false)
const showSearch = ref(true)
const revokeOpen = ref(false)
const detailOpen = ref(false)
const revokeIds = ref([])
const reason = ref('')
const revokeTargetCount = ref(0)
const policyOpen = ref(false)
const accessOpen = ref(false)
const accessTarget = ref({})
const accessBlocked = ref(true)
const accessReason = ref('')
const savingAccess = ref(false)
const queryParams = reactive({
  pageNum: 1,
  pageSize: 10,
  userId: undefined,
  clientId: undefined,
  status: undefined,
  accessStatus: undefined,
})

/** 缩略显示授权标识 */
function short(value) {
  if (!value) {
    return '—'
  }
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
}

/** 获取授权状态名称 */
function statusText(value) {
  return { active: '仍然有效', revoked: '已撤销', expired: '已过期' }[value] || '未知状态'
}

/** 获取授权状态标签类型 */
function statusType(value) {
  return { active: 'success', revoked: 'danger', expired: 'info' }[value] || 'info'
}

/** 查询用户授权列表 */
async function getList() {
  loading.value = true
  try {
    const response = await listOAuthGrants(queryParams)
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

/** 打开授权撤销对话框 */
function openRevoke(row) {
  const targets = row ? [row] : selected.value
  revokeIds.value = targets.map((item) => item.grantId)
  revokeTargetCount.value = new Set(targets.map((item) => `${item.userId}:${item.clientId}`)).size
  reason.value = ''
  revokeOpen.value = true
}

/** 提交选中授权的撤销原因 */
async function revoke() {
  revoking.value = true
  try {
    await revokeOAuthGrants(revokeIds.value.join(','), {
      reason: reason.value.trim(),
    })
    proxy.$modal.msgSuccess('授权已撤销')
    revokeOpen.value = false
    await getList()
  } finally {
    revoking.value = false
  }
}

/** 打开用户应用访问控制对话框 */
function openAccess(row) {
  accessTarget.value = row
  accessBlocked.value = row.accessStatus !== 'blocked'
  accessReason.value = ''
  accessOpen.value = true
}

/** 保存访问策略并刷新授权状态 */
async function saveAccess() {
  savingAccess.value = true
  try {
    await setOAuthClientAccess(accessTarget.value.userId, accessTarget.value.clientId, {
      blocked: accessBlocked.value,
      reason: accessReason.value.trim(),
    })
    proxy.$modal.msgSuccess(accessBlocked.value ? '已禁止访问该应用' : '已解除禁止，请重新授权')
    accessOpen.value = false
    await getList()
  } finally {
    savingAccess.value = false
  }
}

/** 查询并展示授权详情 */
async function showDetail(row) {
  const response = await getOAuthGrant(row.grantId)
  detail.value = response.data
  detailOpen.value = true
}
getList()
</script>

<style scoped>
.result-count {
  color: var(--oauth-text-color-regular);
  font-size: 13px;
}

.result-count strong {
  color: var(--oauth-text-color-primary);
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
  color: var(--oauth-color-primary);
  background: var(--oauth-color-primary-light-9);
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
.stacked-cell code {
  display: block;
}

.person-cell strong,
.stacked-cell strong {
  color: var(--oauth-text-color-primary);
}

.person-cell small,
.stacked-cell code {
  margin-top: 3px;
  color: var(--oauth-text-color-secondary);
  font-size: 12px;
}

.tag-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.muted-value {
  color: var(--oauth-text-color-secondary);
  font-size: 12px;
}

.impact-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 16px;
  color: var(--oauth-color-warning-dark-2);
  background: var(--oauth-color-warning-light-9);
  border: 1px solid var(--oauth-color-warning-light-7);
  border-radius: 8px;
}

.impact-summary > .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  font-size: 18px;
}

.impact-summary strong {
  color: var(--oauth-text-color-primary);
}

.impact-summary p {
  margin: 5px 0 0;
  color: var(--oauth-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
}

.reason-label {
  display: block;
  margin-bottom: 8px;
  color: var(--oauth-text-color-primary);
  font-weight: 600;
}

.detail-hero {
  padding: 0 0 20px;
  border-bottom: 1px solid var(--oauth-border-color-lighter);
}

.detail-hero > div {
  flex: 1;
}

.detail-hero strong {
  color: var(--oauth-text-color-primary);
  font-size: 17px;
}

.detail-hero p {
  margin: 5px 0 0;
  color: var(--oauth-text-color-secondary);
}

.detail-section {
  padding: 18px 0;
  border-bottom: 1px solid var(--oauth-border-color-lighter);
}

.detail-section h4 {
  margin: 0 0 10px;
  color: var(--oauth-text-color-primary);
}

.detail-section p {
  margin: 0;
  color: var(--oauth-text-color-regular);
  line-height: 1.6;
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
  color: var(--oauth-text-color-secondary);
}

.technical-details dd {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--oauth-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
