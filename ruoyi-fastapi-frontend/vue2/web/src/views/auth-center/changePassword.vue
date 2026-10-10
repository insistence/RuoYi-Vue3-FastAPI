<template>
  <AuthCenterShell
    :current-step="0"
    :steps="['保护账户', '确认权限']"
    :expires-in="interaction.expiresIn"
    :application-name="interaction.client?.clientName"
    :application-id="interaction.client?.clientId"
  >
    <div
      v-loading="initializing"
      class="auth-flow"
    >
      <p class="panel-kicker">账户保护</p>
      <h2>先设置新的登录密码</h2>
      <p class="panel-lead">
        检测到当前密码已过期或仍是初始密码。更新后才能继续访问 <strong>{{ applicationName }}</strong
        >。
      </p>

      <div class="security-impact">
        <i
          class="el-icon el-icon-warning-outline"
          aria-hidden="true"
        ></i>
        <span
          ><strong>更新后会保护整个账户</strong
          ><small>其他外部应用中的旧登录会话会退出，需要使用新密码重新登录。</small></span
        >
      </div>
      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="false"
      />

      <el-form
        ref="passwordRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.native.prevent="submit"
      >
        <el-form-item
          label="当前密码"
          prop="oldPassword"
        >
          <el-input
            v-model="form.oldPassword"
            type="password"
            show-password
            size="medium"
            autocomplete="current-password"
            placeholder="用于确认是你本人"
          >
            <template #prefix
              ><i
                class="el-icon el-icon-lock"
                aria-hidden="true"
              ></i
            ></template>
          </el-input>
        </el-form-item>
        <el-form-item
          label="新密码"
          prop="newPassword"
        >
          <el-input
            v-model="form.newPassword"
            type="password"
            show-password
            size="medium"
            autocomplete="new-password"
            placeholder="输入新的登录密码"
          >
            <template #prefix
              ><i
                class="el-icon el-icon-key"
                aria-hidden="true"
              ></i
            ></template>
          </el-input>
          <div
            class="password-meter"
            aria-live="polite"
          >
            <div class="meter-heading">
              <span>安全强度</span
              ><strong :class="`is-${strengthLevel}`">{{ strengthLabel }}</strong>
            </div>
            <div
              class="meter-bars"
              aria-hidden="true"
            >
              <i
                v-for="index in 3"
                :key="index"
                :class="{ active: index <= strengthLevel }"
              />
            </div>
            <small>{{ policyDescription }}</small>
          </div>
        </el-form-item>
        <el-form-item
          label="再次输入新密码"
          prop="confirmPassword"
        >
          <el-input
            v-model="form.confirmPassword"
            type="password"
            show-password
            size="medium"
            autocomplete="new-password"
            placeholder="再次输入，避免输错"
          >
            <template #prefix
              ><i
                class="el-icon el-icon-circle-check"
                aria-hidden="true"
              ></i
            ></template>
          </el-input>
        </el-form-item>
        <el-button
          class="primary-action"
          type="primary"
          size="medium"
          native-type="submit"
          :loading="submitting"
        >
          更新密码并继续
        </el-button>
      </el-form>
    </div>
  </AuthCenterShell>
</template>

<script>
export default { name: 'AuthCenterChangePassword' }
</script>

<script setup>
import { computed, getCurrentInstance, reactive, ref } from 'vue'
import { getInteraction, submitInteractionPasswordChange } from '@/api/authCenter'
import { usePasswordRule } from '@/utils/passwordRule'
import AuthCenterShell from './AuthCenterShell.vue'
import { useInteractionContext } from './useInteraction'

const { interactionId, csrfToken, goToAction, followServerRedirect } = useInteractionContext()
const { pwdChrType, infoPwdValidator } = usePasswordRule()
const router = getCurrentInstance().proxy.$router
const passwordRef = ref()
const interaction = ref({})
const initializing = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const form = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const applicationName = computed(() => interaction.value.client?.clientName || '发起登录的应用')
const policyDescription = computed(
  () =>
    ({
      0: "需要 6–20 个字符，不能包含 < > “ ” ' \\ |",
      1: '需要 6–20 位数字',
      2: '需要 6–20 个英文字母',
      3: '需要 6–20 个字符，并同时包含字母和数字',
      4: '需要 6–20 个字符，并同时包含字母、数字和特殊字符',
    })[pwdChrType.value] || '需要 6–20 个字符'
)

const strengthLevel = computed(() => {
  const value = form.newPassword || ''
  if (value.length < 6) {
    return 0
  }
  let level = 1
  if (value.length >= 10) {
    level += 1
  }
  const types = [/[A-Za-z]/.test(value), /\d/.test(value), /[^A-Za-z\d]/.test(value)].filter(
    Boolean
  ).length
  if (types >= 2) {
    level += 1
  }
  return Math.min(3, level)
})
const strengthLabel = computed(() => ['尚未达到要求', '基础', '良好', '较强'][strengthLevel.value])

const validateNewPassword = (_rule, value, callback) => {
  if (value && value === form.oldPassword) {
    return callback(new Error('新密码不能与当前密码相同'))
  }
  callback()
}
const validateConfirmation = (_rule, value, callback) => {
  if (!value) {
    return callback(new Error('请再次输入新密码'))
  }
  if (value !== form.newPassword) {
    return callback(new Error('两次输入的新密码不一致'))
  }
  callback()
}
const rules = computed(() => ({
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [...infoPwdValidator.value, { validator: validateNewPassword, trigger: 'blur' }],
  confirmPassword: [{ validator: validateConfirmation, trigger: 'blur' }],
}))

/** 读取认证交互状态并检查是否需要修改密码 */
async function initialize() {
  if (!interactionId.value || !csrfToken()) {
    return fatal('认证请求不完整，请返回应用重新登录')
  }
  try {
    const response = await getInteraction(interactionId.value, csrfToken())
    interaction.value = response.data || {}
    if (interaction.value.nextAction !== 'changePassword') {
      await goToAction(interaction.value.nextAction)
    }
  } catch (error) {
    fatal(error?.message || '认证请求已失效，请返回应用重新登录')
  } finally {
    initializing.value = false
  }
}

/** 校验并提交密码修改 */
async function submit() {
  if (!interactionId.value || !csrfToken()) {
    return fatal('认证请求不完整，请返回应用重新登录')
  }
  if (!(await passwordRef.value?.validate().catch(() => false))) {
    return
  }
  submitting.value = true
  errorMessage.value = ''
  try {
    const response = await submitInteractionPasswordChange(interactionId.value, csrfToken(), {
      ...form,
    })
    Object.assign(form, {
      oldPassword: '',
      newPassword: '',
      confirmPassword: '',
    })
    if (response.data?.nextAction === 'redirect') {
      return followServerRedirect(response.data.redirectUrl)
    }
    await goToAction(response.data?.nextAction)
  } catch (error) {
    form.oldPassword = ''
    errorMessage.value = error?.message || '密码更新失败，请根据页面提示检查后重试'
  } finally {
    submitting.value = false
  }
}

/** 跳转到认证错误页面 */
function fatal(message) {
  router.replace({ path: '/auth-center/error', query: { message } })
}
initialize()
</script>

<style scoped>
.auth-flow {
  min-height: 410px;
}

.panel-kicker {
  margin: 0 0 8px;
  color: var(--oauth-color-warning-dark-2);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

h2 {
  margin: 0;
  color: var(--oauth-text-color-primary);
  font-size: 25px;
  font-weight: 650;
  line-height: 1.4;
}

.panel-lead {
  margin: 12px 0 18px;
  color: var(--oauth-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}

.panel-lead strong {
  color: var(--oauth-text-color-primary);
}

.security-impact {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 18px;
  padding: 12px 14px;
  color: var(--oauth-color-warning-dark-2);
  background: var(--oauth-color-warning-light-9);
  border: 1px solid var(--oauth-color-warning-light-7);
  border-radius: 8px;
}

.security-impact > .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
}

.security-impact strong,
.security-impact small {
  display: block;
}

.security-impact strong {
  color: var(--oauth-text-color-primary);
  font-size: 12px;
}

.security-impact small {
  margin-top: 3px;
  color: var(--oauth-text-color-regular);
  font-size: 11px;
  line-height: 1.5;
}

.el-alert {
  margin-bottom: 18px;
}

.password-meter {
  width: 100%;
  margin-top: 8px;
}

.meter-heading {
  display: flex;
  justify-content: space-between;
  color: var(--oauth-text-color-secondary);
  font-size: 11px;
}

.meter-heading strong.is-0 {
  color: var(--oauth-text-color-secondary);
}

.meter-heading strong.is-1 {
  color: var(--oauth-color-danger);
}

.meter-heading strong.is-2 {
  color: var(--oauth-color-warning-dark-2);
}

.meter-heading strong.is-3 {
  color: var(--oauth-color-success);
}

.meter-bars {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 5px;
  margin: 6px 0;
}

.meter-bars i {
  height: 3px;
  background: var(--oauth-fill-color-dark);
  border-radius: 3px;
}

.meter-bars i.active {
  background: var(--oauth-color-warning);
}

.meter-bars i:nth-child(3).active {
  background: var(--oauth-color-success);
}

.password-meter > small {
  color: var(--oauth-text-color-secondary);
  font-size: 11px;
  line-height: 1.5;
}

.primary-action {
  width: 100%;
  height: 44px;
  margin-top: 10px;
}
</style>
