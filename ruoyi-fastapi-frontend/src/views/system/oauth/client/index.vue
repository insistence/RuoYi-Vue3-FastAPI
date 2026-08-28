<template>
  <div class="oauth-route-page">
    <PageFrame
      section="接入管理"
      title="应用"
      description="管理哪些网站、移动端和后端服务可以使用统一登录或访问受保护服务。"
      filter-hint="按应用名称、运行形态或当前状态查找"
    >
      <template #actions>
        <el-button type="primary" icon="Plus" v-hasPermi="['system:oauthClient:add']" @click="handleAdd">
          注册应用
        </el-button>
      </template>

      <template #filters>
        <el-form v-show="showSearch" ref="queryRef" :model="queryParams" :inline="true">
          <el-form-item label="应用名称" prop="clientName">
            <el-input v-model="queryParams.clientName" clearable placeholder="输入应用名称" style="width: 200px" @keyup.enter="handleQuery" />
          </el-form-item>
          <el-form-item label="运行形态" prop="clientType">
            <el-select v-model="queryParams.clientType" clearable placeholder="全部形态" style="width: 200px">
              <el-option label="后端服务" value="confidential" />
              <el-option label="网页或移动端" value="public" />
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
        <span class="result-count">已登记 <strong>{{ total }}</strong> 个应用</span>
        <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
      </template>

      <el-table v-loading="loading" :data="rows" row-key="clientId">
        <el-table-column label="应用" min-width="250">
          <template #default="scope">
            <div class="entity-cell">
              <span class="entity-avatar">{{ (scope.row.clientName || '应').slice(0, 1) }}</span>
              <span class="entity-copy">
                <strong>{{ scope.row.clientName }}</strong>
                <code>{{ scope.row.clientId }}</code>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="运行形态" width="130">
          <template #default="scope">
            <el-tag :type="scope.row.clientType === 'confidential' ? 'primary' : 'info'" effect="plain">
              {{ scope.row.clientType === 'confidential' ? '后端服务' : '网页/移动端' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="登录与调用方式" min-width="240">
          <template #default="scope">
            <span class="plain-summary">{{ grantTypeText(scope.row.grantTypes) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可访问服务" min-width="200">
          <template #default="scope">
            <div class="tag-summary">
              <el-tag v-for="item in (scope.row.resourceIds || []).slice(0, 2)" :key="item" size="small" effect="plain">{{ item }}</el-tag>
              <span v-if="!(scope.row.resourceIds || []).length" class="muted-value">仅身份信息</span>
              <span v-else-if="scope.row.resourceIds.length > 2" class="muted-value">+{{ scope.row.resourceIds.length - 2 }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="105" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.status === '0' ? 'success' : 'info'" effect="light">
              {{ scope.row.status === '0' ? '使用中' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近更新" width="170">
          <template #default="scope">{{ parseTime(scope.row.updateTime) || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="180" align="center">
          <template #default="scope">
            <div class="table-actions">
              <el-button link type="primary" icon="Edit" v-hasPermi="['system:oauthClient:edit']" @click="handleUpdate(scope.row)">编辑</el-button>
              <el-dropdown trigger="click" @command="command => handleRowCommand(command, scope.row)">
                <el-button link type="primary" icon="ArrowDown">更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-if="scope.row.clientType === 'confidential'"
                      command="rotate"
                      icon="Key"
                      v-hasPermi="['system:oauthClient:rotateSecret']"
                    >
                      轮换应用密钥
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-if="scope.row.status !== '0'"
                      command="enable"
                      icon="CircleCheck"
                      v-hasPermi="['system:oauthClient:edit']"
                    >
                      重新启用
                    </el-dropdown-item>
                    <el-dropdown-item
                      v-else
                      command="disable"
                      icon="CircleClose"
                      divided
                      v-hasPermi="['system:oauthClient:remove']"
                    >
                      停用应用
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有符合条件的应用">
            <el-button type="primary" v-hasPermi="['system:oauthClient:add']" @click="handleAdd">注册第一个应用</el-button>
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
      v-model="editorOpen"
      :title="form.clientId ? '编辑应用' : '注册应用'"
      width="min(960px, calc(100vw - 48px))"
      append-to-body
      destroy-on-close
      :close-on-click-modal="false"
      class="oauth-editor-dialog"
    >
      <div class="editor-map">
        <span class="editor-map-title">访问关系预览</span>
        <AccessMap
          :application="form.clientName"
          :type="form.clientType"
          :permissions="form.scopeCodes"
          :resources="form.resourceIds"
        />
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-width="160px" class="sectioned-form">
        <el-tabs v-model="activeEditorSection" tab-position="left" class="editor-tabs">
          <el-tab-pane label="基本信息" name="basic">
            <div class="section-heading">
              <h3>这个应用是谁</h3>
              <p>名称用于后台识别，运行形态决定它是否能够安全保存应用密钥。</p>
            </div>
            <el-form-item prop="clientName">
              <template #label><FieldLabel label="应用名称" help="便于管理员识别这个应用，不影响登录流程。" /></template>
              <el-input v-model="form.clientName" maxlength="100" show-word-limit style="width: 100%" />
            </el-form-item>
            <el-form-item prop="clientType">
              <template #label><FieldLabel label="运行形态" help="网页或移动端无法安全保存密钥；后端服务可以在服务器中安全保存密钥。" /></template>
              <el-radio-group v-model="form.clientType" class="choice-grid" :disabled="Boolean(form.clientId)" @change="syncClientType">
                <el-radio value="confidential" border>
                  <span class="choice-title">后端服务</span>
                  <small>可以安全保存应用密钥</small>
                </el-radio>
                <el-radio value="public" border>
                  <span class="choice-title">网页或移动端</span>
                  <small>不能在终端中保存密钥</small>
                </el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <template #label><FieldLabel label="备注" help="仅供管理员记录用途，不会发送给外部应用。" /></template>
              <el-input v-model="form.remark" type="textarea" :rows="3" maxlength="500" show-word-limit style="width: 100%" />
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane label="登录方式" name="login">
            <div class="section-heading">
              <h3>应用怎样完成登录或调用</h3>
              <p>只选择应用实际需要的方式，减少不必要的访问能力。</p>
            </div>
            <el-form-item prop="grantTypes">
              <template #label><FieldLabel label="允许的方式" help="网页或移动端通常使用用户登录；没有具体用户的后台任务使用服务间调用。" /></template>
              <el-checkbox-group v-model="form.grantTypes" class="option-stack">
                <el-checkbox value="authorization_code">用户登录</el-checkbox>
                <small>用户在统一认证中心输入账号后返回应用。</small>
                <el-checkbox value="refresh_token" :disabled="!form.grantTypes.includes('authorization_code')">保持登录</el-checkbox>
                <small>允许应用在用户离开后延长登录状态。</small>
                <el-checkbox value="client_credentials" :disabled="form.clientType === 'public'">服务间调用</el-checkbox>
                <small>后台服务以自身身份调用其他服务，不代表具体用户。</small>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item>
              <template #label><FieldLabel label="登录安全" help="系统自动启用登录安全保护；其余选项控制是否展示用户确认和是否信任该应用。" /></template>
              <div class="option-stack">
                <el-checkbox v-model="form.requirePkce" disabled>登录安全保护（系统自动开启）</el-checkbox>
                <el-checkbox v-model="form.requireConsent">登录时让用户确认权限</el-checkbox>
                <el-checkbox v-model="form.trustedClient">标记为受信任应用</el-checkbox>
              </div>
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane label="权限与服务" name="access">
            <div class="section-heading">
              <h3>应用能够申请什么</h3>
              <p>从已经启用的权限和服务中选择，避免保存后才发现标识不存在。</p>
            </div>
            <el-form-item prop="scopeCodes">
              <template #label><FieldLabel label="可申请权限" help="应用登录或访问服务时，只能申请这里列出的权限。" /></template>
              <el-select v-model="form.scopeCodes" multiple filterable placeholder="选择应用可申请的权限" style="width: 100%">
                <el-option v-for="item in scopeOptions" :key="item.scopeCode" :label="item.scopeName" :value="item.scopeCode">
                  <span>{{ item.scopeName }}</span><code class="option-code">{{ item.scopeCode }}</code>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item>
              <template #label><FieldLabel label="免重复确认" help="这些权限可以减少用户重复确认，必须属于上面的可申请权限。" /></template>
              <el-select v-model="form.preAuthorizedScopeCodes" multiple filterable placeholder="从已选权限中选择" style="width: 100%">
                <el-option v-for="item in selectedScopeOptions" :key="item.scopeCode" :label="item.scopeName" :value="item.scopeCode">
                  <span>{{ item.scopeName }}</span><code class="option-code">{{ item.scopeCode }}</code>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item>
              <template #label><FieldLabel label="可访问服务" help="填写服务与权限页面中已创建服务的标识，不是网址。" /></template>
              <el-select v-model="form.resourceIds" multiple filterable placeholder="选择应用可访问的服务" style="width: 100%">
                <el-option v-for="item in resourceOptions" :key="item.resourceId" :label="item.resourceName" :value="item.resourceId">
                  <span>{{ item.resourceName }}</span><code class="option-code">{{ item.resourceId }}</code>
                </el-option>
              </el-select>
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane label="回调地址" name="uri">
            <div class="section-heading">
              <h3>登录完成后可以去哪里</h3>
              <p>每个地址单独填写并校验。正式环境应使用 HTTPS 完整地址。</p>
            </div>
            <el-form-item prop="redirectUris">
              <template #label><FieldLabel label="登录返回地址" help="用户完成登录后，系统只会跳转到这里登记的地址。" /></template>
              <StringListInput v-model="form.redirectUris" placeholder="https://portal.example.com/callback" add-text="添加登录返回地址" />
            </el-form-item>
            <el-form-item prop="postLogoutRedirectUris">
              <template #label><FieldLabel label="退出返回地址" help="用户退出登录后可以返回的地址。" /></template>
              <StringListInput v-model="form.postLogoutRedirectUris" placeholder="https://portal.example.com/signed-out" add-text="添加退出返回地址" />
            </el-form-item>
            <el-form-item prop="backchannelLogoutUris">
              <template #label><FieldLabel label="后台退出通知" help="应用需要接收后台退出通知时填写，可以留空。" /></template>
              <StringListInput v-model="form.backchannelLogoutUris" placeholder="https://portal.example.com/backchannel-logout" add-text="添加后台通知地址" />
            </el-form-item>
            <el-form-item prop="corsOrigins">
              <template #label><FieldLabel label="允许的网页来源" help="允许哪些网页从浏览器直接发起调用，只填写协议、域名和端口。" /></template>
              <StringListInput v-model="form.corsOrigins" placeholder="https://portal.example.com" add-text="添加网页来源" />
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane label="有效时长" name="duration">
            <div class="section-heading">
              <h3>登录凭据可以使用多久</h3>
              <p>留空时使用平台默认值。只有确有业务需要时才延长有效时间。</p>
            </div>
            <el-row :gutter="18">
              <el-col :xs="24" :sm="12">
                <el-form-item>
                  <template #label><FieldLabel label="访问凭据" help="应用访问服务时使用的短期凭据有效多久。" /></template>
                  <el-input-number v-model="form.accessTokenTtlSeconds" :min="1" placeholder="平台默认" controls-position="right" style="width: 100%" />
                  <span class="input-unit">秒</span>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item>
                  <template #label><FieldLabel label="闲置后失效" help="保持登录凭据连续多久未使用后自动失效。" /></template>
                  <el-input-number v-model="form.refreshTokenIdleSeconds" :min="1" placeholder="平台默认" controls-position="right" style="width: 100%" />
                  <span class="input-unit">秒</span>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :sm="12">
                <el-form-item>
                  <template #label><FieldLabel label="最长有效时间" help="保持登录凭据从签发起最多可以存在多久。" /></template>
                  <el-input-number v-model="form.refreshTokenAbsoluteSeconds" :min="1" placeholder="平台默认" controls-position="right" style="width: 100%" />
                  <span class="input-unit">秒</span>
                </el-form-item>
              </el-col>
            </el-row>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      <template #footer>
        <el-button @click="editorOpen = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存应用</el-button>
      </template>
    </el-dialog>

    <secret-dialog v-model="secretOpen" :secret="secret" />
  </div>
</template>

<script setup name="OAuthClient">
import {
  addOAuthClient,
  changeOAuthClientStatus,
  deleteOAuthClients,
  getOAuthClient,
  listOAuthClients,
  rotateOAuthClientSecret,
  updateOAuthClient
} from '@/api/system/oauthClient'
import { listOAuthResources, listOAuthScopes } from '@/api/system/oauthResource'
import { splitRegisteredUris, validateRegisteredUriList } from '@/utils/oauthUri'
import AccessMap from '@/components/OAuthWorkspace/AccessMap.vue'
import FieldLabel from '@/components/OAuthWorkspace/FieldLabel.vue'
import PageFrame from '@/components/OAuthWorkspace/PageFrame.vue'
import StringListInput from '@/components/OAuthWorkspace/StringListInput.vue'
import SecretDialog from './secret.vue'

const { proxy } = getCurrentInstance()
const loading = ref(false)
const submitting = ref(false)
const showSearch = ref(true)
const editorOpen = ref(false)
const activeEditorSection = ref('basic')
const secretOpen = ref(false)
const rows = ref([])
const scopeOptions = ref([])
const resourceOptions = ref([])
const total = ref(0)
const secret = ref({})
const queryParams = reactive({ pageNum: 1, pageSize: 10, clientName: undefined, clientType: undefined, status: undefined })
const form = reactive(emptyForm())
const selectedScopeOptions = computed(() => {
  const known = new Map(scopeOptions.value.map(item => [item.scopeCode, item]))
  return form.scopeCodes.map(code => known.get(code) || { scopeCode: code, scopeName: code })
})
const rules = {
  clientName: [{ required: true, message: '请输入应用名称', trigger: 'blur' }],
  clientType: [{ required: true, message: '请选择应用类型', trigger: 'change' }],
  grantTypes: [{ required: true, type: 'array', min: 1, message: '至少选择一种登录或调用方式', trigger: 'change' }],
  scopeCodes: [{ required: true, type: 'array', min: 1, message: '至少添加一项可申请权限', trigger: 'change' }],
  redirectUris: [registeredUriRule('redirect', () => form.grantTypes.includes('authorization_code'))],
  postLogoutRedirectUris: [registeredUriRule('post_logout')],
  backchannelLogoutUris: [registeredUriRule('backchannel_logout')],
  corsOrigins: [registeredUriRule('cors_origin')]
}

function emptyForm() {
  return {
    clientId: undefined,
    clientName: '',
    clientType: 'confidential',
    tokenEndpointAuthMethod: 'client_secret_basic',
    grantTypes: ['authorization_code', 'refresh_token'],
    responseTypes: ['code'],
    requirePkce: true,
    requireConsent: true,
    trustedClient: false,
    scopeCodes: ['openid'],
    preAuthorizedScopeCodes: [],
    resourceIds: [],
    redirectUris: [],
    postLogoutRedirectUris: [],
    backchannelLogoutUris: [],
    corsOrigins: [],
    accessTokenTtlSeconds: null,
    refreshTokenIdleSeconds: null,
    refreshTokenAbsoluteSeconds: null,
    logoUri: null,
    policyUri: null,
    tosUri: null,
    remark: ''
  }
}

function registeredUriRule(uriType, required = false) {
  return {
    trigger: 'blur',
    validator: (_rule, value, callback) => {
      try {
        validateRegisteredUriList((value || []).join('\n'), uriType, typeof required === 'function' ? required() : required)
        callback()
      } catch (error) {
        callback(error)
      }
    }
  }
}

function resetForm() {
  Object.assign(form, emptyForm())
  activeEditorSection.value = 'basic'
  proxy.resetForm('formRef')
}

function syncClientType() {
  form.tokenEndpointAuthMethod = form.clientType === 'public' ? 'none' : 'client_secret_basic'
  if (form.clientType === 'public') form.grantTypes = form.grantTypes.filter(item => item !== 'client_credentials')
}

async function loadAccessOptions() {
  const [scopes, resources] = await Promise.all([
    listOAuthScopes({ pageNum: 1, pageSize: 200, status: '0' }),
    listOAuthResources({ pageNum: 1, pageSize: 200, status: '0' })
  ])
  scopeOptions.value = scopes.rows || []
  resourceOptions.value = resources.rows || []
}

function toEditor(data) {
  return {
    ...emptyForm(),
    ...data,
    scopeCodes: [...(data.scopeCodes || [])],
    preAuthorizedScopeCodes: [...(data.preAuthorizedScopeCodes || [])],
    resourceIds: [...(data.resourceIds || [])],
    redirectUris: [...(data.redirectUris || [])],
    postLogoutRedirectUris: [...(data.postLogoutRedirectUris || [])],
    backchannelLogoutUris: [...(data.backchannelLogoutUris || [])],
    corsOrigins: [...(data.corsOrigins || [])]
  }
}

function payload() {
  const values = {
    clientId: form.clientId,
    clientName: form.clientName,
    clientType: form.clientType,
    tokenEndpointAuthMethod: form.tokenEndpointAuthMethod,
    grantTypes: [...form.grantTypes],
    responseTypes: [...form.responseTypes],
    requirePkce: form.requirePkce,
    requireConsent: form.requireConsent,
    trustedClient: form.trustedClient,
    scopeCodes: [...form.scopeCodes],
    preAuthorizedScopeCodes: [...form.preAuthorizedScopeCodes],
    resourceIds: [...form.resourceIds],
    redirectUris: splitRegisteredUris(form.redirectUris.join('\n')),
    postLogoutRedirectUris: splitRegisteredUris(form.postLogoutRedirectUris.join('\n')),
    backchannelLogoutUris: splitRegisteredUris(form.backchannelLogoutUris.join('\n')),
    corsOrigins: splitRegisteredUris(form.corsOrigins.join('\n')),
    accessTokenTtlSeconds: form.accessTokenTtlSeconds,
    refreshTokenIdleSeconds: form.refreshTokenIdleSeconds,
    refreshTokenAbsoluteSeconds: form.refreshTokenAbsoluteSeconds,
    logoUri: form.logoUri,
    policyUri: form.policyUri,
    tosUri: form.tosUri,
    remark: form.remark
  }
  if (!values.clientId) delete values.clientId
  if (!values.grantTypes.includes('authorization_code')) values.responseTypes = []
  return values
}

async function getList() {
  loading.value = true
  try {
    const response = await listOAuthClients(queryParams)
    rows.value = response.rows || []
    total.value = response.total || 0
  } finally {
    loading.value = false
  }
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
  loadAccessOptions().catch(() => {})
  editorOpen.value = true
}

async function handleUpdate(row) {
  resetForm()
  const [response] = await Promise.all([
    getOAuthClient(row.clientId),
    loadAccessOptions().catch(() => {})
  ])
  Object.assign(form, toEditor(response.data))
  editorOpen.value = true
}

function grantTypeText(types = []) {
  const labels = {
    authorization_code: '用户登录',
    refresh_token: '保持登录',
    client_credentials: '服务间调用'
  }
  return types.map(item => labels[item] || item).join(' · ') || '尚未配置'
}

function handleRowCommand(command, row) {
  if (command === 'rotate') return rotateSecret(row)
  if (command === 'enable') return changeStatus(row, '0')
  if (command === 'disable') return handleDelete(row)
}

async function submit() {
  try {
    await proxy.$refs.formRef.validate()
  } catch (fields) {
    const firstField = Object.keys(fields || {})[0]
    const sectionByField = {
      clientName: 'basic',
      clientType: 'basic',
      grantTypes: 'login',
      scopeCodes: 'access',
      redirectUris: 'uri',
      postLogoutRedirectUris: 'uri',
      backchannelLogoutUris: 'uri',
      corsOrigins: 'uri'
    }
    activeEditorSection.value = sectionByField[firstField] || activeEditorSection.value
    return
  }
  submitting.value = true
  try {
    const action = form.clientId ? updateOAuthClient : addOAuthClient
    await action(payload())
    proxy.$modal.msgSuccess('应用配置已保存')
    editorOpen.value = false
    await getList()
  } finally {
    submitting.value = false
  }
}

async function changeStatus(row, status) {
  const verb = status === '0' ? '启用' : '停用'
  try {
    await proxy.$modal.confirm(`${verb}应用“${row.clientName}”？`)
    await changeOAuthClientStatus({ clientId: row.clientId, status })
    proxy.$modal.msgSuccess(`${verb}成功`)
    await getList()
  } catch {
    // 用户取消或请求失败时刷新事实状态，避免保留乐观 UI
    await getList()
  }
}

async function handleDelete(row) {
  await proxy.$modal.confirm(`停用“${row.clientName}”将同时撤销该应用的授权与刷新凭据，是否继续？`)
  await deleteOAuthClients(row.clientId)
  proxy.$modal.msgSuccess('应用已停用')
  await getList()
}

async function rotateSecret(row) {
  await proxy.$modal.confirm(`为“${row.clientName}”生成新密钥？旧密钥将进入有界退役窗口。`)
  const response = await rotateOAuthClientSecret(row.clientId)
  secret.value = response.data
  secretOpen.value = true
  await getList()
}

watch(secretOpen, visible => {
  if (!visible) secret.value = {}
})

watch(() => [...form.grantTypes], grantTypes => {
  if (!grantTypes.includes('authorization_code') && grantTypes.includes('refresh_token')) {
    form.grantTypes = grantTypes.filter(item => item !== 'refresh_token')
  }
})

watch(() => [...form.scopeCodes], scopeCodes => {
  const allowed = new Set(scopeCodes)
  form.preAuthorizedScopeCodes = form.preAuthorizedScopeCodes.filter(code => allowed.has(code))
})

Promise.all([getList(), loadAccessOptions().catch(() => {})])
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

.entity-avatar {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  color: var(--el-color-primary);
  font-weight: 700;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
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
  font-weight: 600;
}

.entity-copy code {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.plain-summary {
  color: var(--el-text-color-regular);
}

.tag-summary {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.muted-value {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.editor-map {
  margin-bottom: 20px;
  padding: 14px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 9px;
}

.editor-map-title {
  display: block;
  margin-bottom: 10px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  font-weight: 600;
}

.editor-tabs {
  min-height: 470px;
}

.editor-tabs :deep(.el-tabs__header.is-left) {
  width: 132px;
  margin-right: 24px;
}

.editor-tabs :deep(.el-tabs__item.is-left) {
  height: 46px;
  text-align: left;
}

.editor-tabs :deep(.el-tabs__content) {
  min-width: 0;
}

.section-heading {
  margin: 2px 0 24px;
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
  min-height: 70px;
  margin: 0;
  padding: 13px 14px;
  white-space: normal;
}

.choice-grid :deep(.el-radio__label) {
  display: block;
  min-width: 0;
}

.choice-title,
.choice-grid small {
  display: block;
}

.choice-title {
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.choice-grid small {
  margin-top: 5px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.option-stack {
  display: grid;
  grid-template-columns: 1fr;
  width: 100%;
}

.option-stack :deep(.el-checkbox) {
  margin-right: 0;
}

.option-stack>small {
  margin: -3px 0 10px 24px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.sectioned-form :deep(.el-input-number) {
  flex: 1;
  width: auto !important;
}

.input-unit {
  flex: 0 0 auto;
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}

.option-code {
  float: right;
  margin-left: 18px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 768px) {
  .editor-map {
    display: none;
  }

  .editor-tabs :deep(.el-tabs__header.is-left) {
    float: none;
    width: 100%;
    margin: 0 0 18px;
  }

  .editor-tabs :deep(.el-tabs__nav-wrap.is-left) {
    padding: 0;
  }

  .editor-tabs :deep(.el-tabs__nav.is-left) {
    display: flex;
    overflow-x: auto;
  }

  .editor-tabs :deep(.el-tabs__item.is-left) {
    flex: 0 0 auto;
    padding: 0 14px;
  }

  .editor-tabs :deep(.el-tabs__active-bar.is-left) {
    display: none;
  }

  .sectioned-form :deep(.el-form-item) {
    display: block;
  }

  .sectioned-form :deep(.el-form-item__label) {
    width: auto !important;
    margin-bottom: 6px;
  }

  .sectioned-form :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }

  .choice-grid {
    grid-template-columns: 1fr;
  }
}
</style>
