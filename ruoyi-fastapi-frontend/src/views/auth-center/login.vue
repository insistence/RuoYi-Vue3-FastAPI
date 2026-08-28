<template>
  <AuthCenterShell
    :current-step="0"
    :expires-in="interaction.expiresIn"
    :application-name="interaction.client?.clientName"
    :application-id="interaction.client?.clientId"
  >
    <div v-loading="initializing" class="auth-flow">
      <p class="panel-kicker">验证身份</p>
      <h2>使用你的账户继续</h2>
      <p class="panel-lead">登录成功后，你将返回 <strong>{{ applicationName }}</strong> 完成访问。本次登录不会改变管理后台的登录状态。</p>

      <el-alert v-if="errorMessage" :title="errorMessage" type="error" show-icon :closable="false" />
      <el-form ref="loginRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submitLogin">
        <el-form-item label="账号" prop="userName">
          <el-input v-model="form.userName" size="large" autocomplete="username" placeholder="请输入你的账号" autofocus>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" size="large" type="password" show-password autocomplete="current-password" placeholder="请输入登录密码" @keyup.enter="submitLogin">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item v-if="captcha.captchaEnabled" label="安全验证码" prop="code">
          <div class="captcha-row">
            <el-input v-model="form.code" size="large" autocomplete="off" placeholder="输入图中字符" @keyup.enter="submitLogin" />
            <el-button class="captcha-image" text aria-label="看不清，换一张验证码" title="看不清，换一张" @click="loadCaptcha">
              <img v-if="captcha.img" :src="`data:image/gif;base64,${captcha.img}`" alt="安全验证码" />
              <span v-else>换一张</span>
            </el-button>
          </div>
        </el-form-item>

        <div class="preference-row">
          <el-checkbox v-model="form.rememberMe">在这台设备上保持登录</el-checkbox>
          <small>仅在你信任的个人设备上勾选</small>
        </div>
        <el-button class="primary-action" type="primary" size="large" native-type="submit" :loading="submitting">
          登录并继续
        </el-button>
      </el-form>
      <el-button class="cancel-action" link :disabled="submitting" @click="cancel">取消并返回应用</el-button>
    </div>
  </AuthCenterShell>
</template>

<script setup name="AuthCenterLogin">
import { cancelInteraction, getInteraction, getInteractionCaptcha, submitInteractionLogin } from '@/api/authCenter'
import AuthCenterShell from './AuthCenterShell.vue'
import { useInteractionContext } from './useInteraction'

const { interactionId, csrfToken, goToAction, followServerRedirect } = useInteractionContext()
const router = useRouter()
const loginRef = ref()
const initializing = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const interaction = ref({})
const captcha = ref({ captchaEnabled: false, uuid: '', img: '' })
const form = reactive({ userName: '', password: '', code: '', uuid: '', rememberMe: false })
const applicationName = computed(() => interaction.value.client?.clientName || '发起登录的应用')
const rules = {
  userName: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  code: [{ validator: (_rule, value, callback) => captcha.value.captchaEnabled && !value ? callback(new Error('请输入安全验证码')) : callback(), trigger: 'blur' }]
}

async function initialize() {
  if (!interactionId.value || !csrfToken()) return showFatal('认证请求不完整，请返回应用重新登录')
  try {
    const response = await getInteraction(interactionId.value, csrfToken())
    interaction.value = response.data || {}
    if (interaction.value.nextAction && interaction.value.nextAction !== 'login') return goToAction(interaction.value.nextAction)
    if (interaction.value.captchaEnabled) await loadCaptcha()
  } catch (error) {
    showFatal(error?.message || '认证请求已失效，请返回应用重新登录')
  } finally { initializing.value = false }
}

async function loadCaptcha() {
  const response = await getInteractionCaptcha(interactionId.value)
  captcha.value = response.data || { captchaEnabled: false }
  form.uuid = captcha.value.uuid || ''
  form.code = ''
}

async function submitLogin() {
  if (!await loginRef.value?.validate().catch(() => false)) return
  submitting.value = true
  errorMessage.value = ''
  try {
    const response = await submitInteractionLogin(interactionId.value, csrfToken(), { ...form })
    form.password = ''
    const result = response.data || {}
    if (result.nextAction === 'redirect') return followServerRedirect(result.redirectUrl)
    await goToAction(result.nextAction)
  } catch (error) {
    form.password = ''
    errorMessage.value = error?.message || '身份验证失败，请检查账号和密码后重试'
    if (captcha.value.captchaEnabled) await loadCaptcha().catch(() => {})
  } finally { submitting.value = false }
}

async function cancel() {
  try {
    const response = await cancelInteraction(interactionId.value, csrfToken())
    if (response.data?.redirectUrl) return followServerRedirect(response.data.redirectUrl)
  } catch (error) { errorMessage.value = error?.message || '暂时无法取消认证请求' }
}

function showFatal(message) { router.replace({ path: '/auth-center/error', query: { message } }) }
initialize()
</script>

<style scoped>
.auth-flow {
  min-height: 390px;
}

.panel-kicker {
  margin: 0 0 8px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .1em;
}

h2 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 25px;
  font-weight: 650;
  line-height: 1.4;
}

.panel-lead {
  margin: 12px 0 24px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.panel-lead strong {
  color: var(--el-text-color-primary);
}

.el-alert {
  margin-bottom: 18px;
}

.captcha-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 10px;
  width: 100%;
}

.captcha-image {
  height: 40px;
  padding: 0;
  overflow: hidden;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.captcha-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.preference-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 2px;
}

.preference-row small {
  color: var(--el-text-color-secondary);
  font-size: 11px;
}

.primary-action {
  width: 100%;
  height: 44px;
  margin-top: 22px;
}

.cancel-action {
  display: block;
  margin: 14px auto 0;
  color: var(--el-text-color-regular);
}

@media (max-width: 440px) {
  .captcha-row {
    grid-template-columns: minmax(0, 1fr) 112px;
  }

  .preference-row {
    display: block;
  }

  .preference-row small {
    display: block;
    margin: 2px 0 0 24px;
  }
}
</style>
