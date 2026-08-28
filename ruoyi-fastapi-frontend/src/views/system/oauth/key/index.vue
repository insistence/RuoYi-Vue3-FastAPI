<template>
  <div class="oauth-route-page">
    <PageFrame
      section="安全运维"
      title="签名密钥"
      description="管理系统用来证明身份凭据真实可信的签名密钥，并通过重叠验证窗口安全完成轮换。"
    >
      <template #actions>
        <el-button type="primary" icon="RefreshRight" v-hasPermi="['system:oauthKey:rotate']" @click="openRotation">
          安排密钥轮换
        </el-button>
      </template>

      <template #context>
        <div class="key-overview">
          <div class="overview-state" :class="{ 'is-disabled': !ready }">
            <span class="overview-icon"><el-icon><Lock /></el-icon></span>
            <div>
              <small>认证服务</small>
              <strong>{{ serviceStatus.title }}</strong>
              <p>{{ serviceStatus.description }}</p>
            </div>
          </div>
          <div class="overview-divider" aria-hidden="true"><el-icon><Right /></el-icon></div>
          <div class="overview-state">
            <span class="overview-icon is-success"><el-icon><Key /></el-icon></span>
            <div>
              <small>当前签名密钥</small>
              <strong>{{ activeKey?.kid || '尚未激活' }}</strong>
              <p>{{ activeKey ? `自 ${parseTime(activeKey.signingStartAt) || '计划时间'} 起签发新凭据` : '需要先激活一把已公开的密钥。' }}</p>
            </div>
          </div>
          <div class="overview-divider" aria-hidden="true"><el-icon><Right /></el-icon></div>
          <div class="overview-state">
            <span class="overview-icon is-next"><el-icon><Clock /></el-icon></span>
            <div>
              <small>下一次轮换</small>
              <strong>{{ nextKey?.kid || '尚未安排' }}</strong>
              <p>{{ nextKey ? `计划在 ${parseTime(nextKey.signingStartAt) || '待确认时间'} 接管签名` : '建议在现有密钥到期前安排轮换。' }}</p>
            </div>
          </div>
        </div>
      </template>

      <template #toolbar>
        <span class="result-count">共 <strong>{{ total }}</strong> 把密钥</span>
        <right-toolbar :show-search="false" @queryTable="getList" />
      </template>

      <el-table v-loading="loading" :data="rows" row-key="kid">
        <el-table-column label="密钥" min-width="250">
          <template #default="scope">
            <div class="key-cell">
              <span class="key-mark" :class="`is-${scope.row.status}`"><el-icon><Key /></el-icon></span>
              <span>
                <strong>{{ scope.row.kid }}</strong>
                <small>{{ scope.row.fingerprint || publicFingerprint(scope.row.publicJwk) }}</small>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="当前作用" min-width="190">
          <template #default="scope">
            <div class="role-cell"><el-tag :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag><small>{{ roleText(scope.row.status) }}</small></div>
          </template>
        </el-table-column>
        <el-table-column label="签名方式" width="110" align="center">
          <template #default="scope"><el-tag type="info" effect="plain">{{ scope.row.alg }}</el-tag></template>
        </el-table-column>
        <el-table-column label="生命周期" min-width="280">
          <template #default="scope">
            <div class="timeline-cell">
              <span><small>公开给应用</small>{{ parseTime(scope.row.publishAt) || '—' }}</span>
              <span><small>{{ scope.row.status === 'pending' ? '计划开始签名' : '开始签名' }}</small>{{ parseTime(scope.row.signingStartAt) || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="下一步" min-width="220">
          <template #default="scope">
            <div class="next-action"><strong>{{ nextActionText(scope.row) }}</strong><small>{{ nextActionTime(scope.row) }}</small></div>
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="150" align="center">
          <template #default="scope">
            <div class="table-actions">
              <el-tooltip
                v-if="scope.row.status === 'pending' && activationDisabledReason(scope.row)"
                :content="activationDisabledReason(scope.row)"
                placement="top"
              >
                <span>
                  <el-button link type="primary" icon="Clock" disabled v-hasPermi="['system:oauthKey:activate']">
                    等待公开
                  </el-button>
                </span>
              </el-tooltip>
              <el-button v-else-if="scope.row.status === 'pending'" link type="primary" icon="CircleCheck" v-hasPermi="['system:oauthKey:activate']" @click="activate(scope.row)">开始使用</el-button>
              <el-button v-if="scope.row.status === 'active'" link type="warning" icon="VideoPause" v-hasPermi="['system:oauthKey:retire']" @click="retire(scope.row)">停止签名</el-button>
              <el-button v-if="scope.row.status === 'retired'" link type="danger" icon="Delete" v-hasPermi="['system:oauthKey:retire']" @click="handleDelete(scope.row)">删除记录</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="尚未准备签名密钥">
            <el-button type="primary" v-hasPermi="['system:oauthKey:rotate']" @click="openRotation">创建第一把密钥</el-button>
          </el-empty>
        </template>
      </el-table>
      <pagination v-show="total > 0" v-model:page="query.pageNum" v-model:limit="query.pageSize" :total="total" @pagination="getList" />
    </PageFrame>

    <el-dialog
      v-model="open"
      title="安排签名密钥轮换"
      width="min(780px, calc(100vw - 48px))"
      append-to-body
      :close-on-click-modal="false"
    >
      <div class="rotation-preview" aria-label="密钥轮换过程">
        <div><span>1</span><strong>先公开</strong><small>应用提前拿到公钥</small></div>
        <i aria-hidden="true" />
        <div><span>2</span><strong>再接管签名</strong><small>新凭据改用新密钥</small></div>
        <i aria-hidden="true" />
        <div><span>3</span><strong>保留旧公钥</strong><small>旧凭据仍可验证到期</small></div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="160px" class="rotation-form">
        <section class="form-section">
          <h3>轮换标识</h3>
          <p>给这次轮换一个易识别的编号，便于在日志和故障排查中定位。</p>
          <el-form-item prop="kid">
            <template #label><FieldLabel label="密钥编号" help="公开密钥列表中的唯一编号。建议包含年份、月份或用途，例如 2026-09-primary。" /></template>
            <el-input v-model="form.kid" maxlength="128" placeholder="例如：2026-09-primary" />
          </el-form-item>
          <el-form-item>
            <template #label><FieldLabel label="签名方式" help="RS256 是应用兼容性较好的非对称签名方式。应用只会获取公钥，无法据此伪造凭据。" /></template>
            <div class="algorithm-value"><strong>RS256</strong><span>私钥不会在此页面展示或导出</span></div>
          </el-form-item>
        </section>

        <section class="form-section">
          <h3>生效安排</h3>
          <p>先公开公钥，再开始使用它签名，给接入应用留出同步时间。</p>
          <el-form-item prop="publishAt">
            <template #label><FieldLabel label="公开公钥时间" help="从这个时间起，接入应用可以在公开密钥列表中获取新公钥，但系统还不会使用它签发新凭据。" /></template>
            <el-date-picker v-model="form.publishAt" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="选择公开时间" style="width: 100%" />
          </el-form-item>
          <el-form-item prop="activateAt">
            <template #label><FieldLabel label="开始签名时间" help="从这个时间起，新签发的身份和访问凭据会改用新密钥。该时间不能早于公开公钥时间。" /></template>
            <el-date-picker v-model="form.activateAt" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" placeholder="选择接管签名时间" style="width: 100%" />
          </el-form-item>
          <el-form-item>
            <template #label><FieldLabel label="变更说明" help="记录轮换原因或关联工单，便于后续审计；不会公开给接入应用。" /></template>
            <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="例如：季度例行轮换，关联工单 SEC-1024" />
          </el-form-item>
        </section>
      </el-form>
      <template #footer>
        <el-button @click="open = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="rotate">创建轮换计划</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup name="OAuthKey">
import { activateOidcKey, deleteOidcKey, listOidcKeys, retireOidcKey, rotateOidcKey } from '@/api/system/oauthSession'
import FieldLabel from '@/components/OAuthWorkspace/FieldLabel.vue'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const rows = ref([])
const total = ref(0)
const enabled = ref(true)
const ready = ref(false)
const loading = ref(false)
const saving = ref(false)
const open = ref(false)
const query = reactive({ pageNum: 1, pageSize: 10 })
const form = reactive({ alg: 'RS256', kid: '', publishAt: '', activateAt: '', remark: '' })

const activeKey = computed(() => rows.value.find(item => item.status === 'active'))
const serviceStatus = computed(() => {
  if (!enabled.value) {
    return {
      title: '尚未启用',
      description: '可以先准备密钥，启用服务后再对外签发凭据。'
    }
  }
  if (!ready.value) {
    return {
      title: '等待初始化签名密钥',
      description: '管理后台可以正常使用，认证接口会暂时拒绝请求。'
    }
  }
  return {
    title: '已启用并可以提供认证',
    description: '身份凭据会使用当前签名密钥签署。'
  }
})
const nextKey = computed(() => rows.value
  .filter(item => item.status === 'pending')
  .sort((left, right) => String(left.signingStartAt || '').localeCompare(String(right.signingStartAt || '')))[0])

const validateActivationTime = (_rule, value, callback) => {
  if (!value) return callback(new Error('请选择开始签名时间'))
  if (form.publishAt && new Date(value).getTime() < new Date(form.publishAt).getTime()) return callback(new Error('开始签名时间不能早于公开公钥时间'))
  callback()
}

const rules = {
  kid: [
    { required: true, message: '请输入便于识别的密钥编号', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9._-]+$/, message: '只能使用字母、数字、点、横线和下划线', trigger: 'blur' }
  ],
  publishAt: [{ required: true, message: '请选择公开公钥时间', trigger: 'change' }],
  activateAt: [{ validator: validateActivationTime, trigger: 'change' }]
}

function statusText(value) {
  return { pending: '等待接管', active: '正在签名', retiring: '验证旧凭据', retired: '已退出', compromised: '疑似泄露' }[value] || value
}

function statusType(value) {
  return ({ pending: 'primary', active: 'success', retiring: 'warning', retired: 'info', compromised: 'danger' })[value] || 'info'
}

function roleText(value) {
  return {
    pending: '公钥已发布，尚未签发新凭据', active: '正在用于签发新的身份和访问凭据',
    retiring: '不再签发新凭据，只验证尚未到期的旧凭据', retired: '已从公开密钥列表移出', compromised: '已标记为不可信，请尽快完成应急轮换'
  }[value] || '状态信息未知'
}

function publicFingerprint(jwk) {
  if (!jwk?.n) return '公开指纹尚未提供'
  return `公开指纹 RSA · ${jwk.n.slice(0, 18)}…`
}

function nextActionText(row) {
  return {
    pending: '等待开始使用', active: '在下一把密钥接管后停止签名', retiring: '等待旧凭据全部到期', retired: '可以清理元数据', compromised: '立即安排应急轮换'
  }[row.status] || '暂无计划'
}

function nextActionTime(row) {
  if (row.status === 'pending') return parseTime(row.signingStartAt) || '需要手动开始使用'
  if (['retiring', 'retired'].includes(row.status)) return row.removeFromJwksAt ? `最早清理：${parseTime(row.removeFromJwksAt)}` : '等待安全验证窗口结束'
  if (row.status === 'active') return '当前没有自动停止时间'
  return '请查看安全日志'
}

function activationDisabledReason(row) {
  const publishAt = new Date(row.publishAt).getTime()
  if (!Number.isFinite(publishAt)) return '公钥公开时间无效，请刷新列表后重试'
  if (publishAt > Date.now()) return `公钥将在 ${parseTime(row.publishAt)} 公开，之后才能开始使用`
  return ''
}

async function getList() {
  loading.value = true
  try {
    const response = await listOidcKeys(query)
    rows.value = response.rows || []
    total.value = response.total || 0
    enabled.value = response.enabled !== false
    ready.value = response.ready === true
  } finally { loading.value = false }
}

function openRotation() {
  Object.assign(form, { alg: 'RS256', kid: '', publishAt: '', activateAt: '', remark: '' })
  open.value = true
  nextTick(() => proxy.$refs.formRef?.clearValidate())
}

async function rotate() {
  await proxy.$refs.formRef.validate()
  saving.value = true
  try {
    await rotateOidcKey({ ...form })
    proxy.$modal.msgSuccess('轮换计划已创建，新公钥会按计划先行公开')
    open.value = false
    await getList()
  } finally { saving.value = false }
}

async function activate(row) {
  const disabledReason = activationDisabledReason(row)
  if (disabledReason) {
    proxy.$modal.msgWarning(disabledReason)
    return
  }
  const signingStartAt = new Date(row.signingStartAt).getTime()
  const scheduleNotice = Number.isFinite(signingStartAt) && signingStartAt > Date.now()
    ? `该密钥原计划在 ${parseTime(row.signingStartAt)} 开始签名，本次操作将提前生效。`
    : '它将立即接管新凭据的签发。'
  await proxy.$modal.confirm(`开始使用密钥 ${row.kid}？${scheduleNotice}当前签名密钥会进入旧凭据验证期。`)
  await activateOidcKey(row.kid)
  proxy.$modal.msgSuccess('新的签名密钥已开始使用')
  await getList()
}

async function retire(row) {
  await proxy.$modal.confirm(`停止使用密钥 ${row.kid} 签发新凭据？它的公钥仍会保留一段时间，用于验证尚未到期的旧凭据。`)
  await retireOidcKey(row.kid)
  proxy.$modal.msgSuccess('密钥已停止签名，当前仅用于验证旧凭据')
  await getList()
}

async function handleDelete(row) {
  await proxy.$modal.confirm(`删除密钥 ${row.kid} 的记录？请确认所有由它签署的凭据都已到期。`)
  await deleteOidcKey(row.kid)
  proxy.$modal.msgSuccess('密钥记录已删除')
  await getList()
}

getList()
</script>

<style scoped>
.key-overview {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr) 32px minmax(0, 1fr);
  align-items: center;
}

.overview-state {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}

.overview-icon {
  display: grid;
  flex: 0 0 42px;
  width: 42px;
  height: 42px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 11px;
  font-size: 18px;
  place-items: center;
}

.overview-icon.is-success {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.overview-icon.is-next {
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
}

.overview-state.is-disabled .overview-icon {
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
}

.overview-state>div {
  min-width: 0;
}

.overview-state small,
.overview-state strong,
.overview-state p {
  display: block;
}

.overview-state small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.overview-state strong {
  margin-top: 3px;
  overflow: hidden;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-state p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.overview-divider {
  color: var(--el-border-color-dark);
  text-align: center;
}

.result-count {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.result-count strong {
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.key-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.key-mark {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 9px;
  place-items: center;
}

.key-mark.is-active {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.key-mark.is-retiring {
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-9);
}

.key-mark.is-retired {
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}

.key-mark.is-compromised {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.key-cell strong,
.key-cell small,
.role-cell small,
.next-action strong,
.next-action small {
  display: block;
}

.key-cell strong {
  color: var(--el-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.key-cell small,
.role-cell small,
.next-action small {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.timeline-cell {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.timeline-cell span {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.timeline-cell small {
  display: block;
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.next-action strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.rotation-preview {
  display: grid;
  grid-template-columns: 1fr 36px 1fr 36px 1fr;
  align-items: center;
  margin-bottom: 24px;
  padding: 16px;
  background: var(--el-fill-color-light);
  border-radius: 9px;
}

.rotation-preview>div {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  column-gap: 9px;
  align-items: center;
}

.rotation-preview span {
  display: grid;
  grid-row: 1 / span 2;
  width: 30px;
  height: 30px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  font-weight: 700;
  place-items: center;
}

.rotation-preview strong,
.rotation-preview small {
  display: block;
}

.rotation-preview strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.rotation-preview small {
  margin-top: 3px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.rotation-preview i {
  height: 1px;
  background: var(--el-border-color);
}

.form-section+.form-section {
  margin-top: 24px;
  padding-top: 22px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.form-section h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.form-section>p {
  margin: 6px 0 18px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.algorithm-value {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 32px;
}

.algorithm-value strong {
  padding: 3px 9px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.algorithm-value span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 900px) {
  .key-overview {
    grid-template-columns: 1fr;
    gap: 16px;
  }

  .overview-divider {
    display: none;
  }
}

@media (max-width: 640px) {
  .rotation-form :deep(.el-form-item) {
    display: block;
  }

  .rotation-form :deep(.el-form-item__label) {
    display: flex;
    width: auto !important;
    margin-bottom: 7px;
  }

  .rotation-preview {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .rotation-preview i {
    display: none;
  }
}
</style>
