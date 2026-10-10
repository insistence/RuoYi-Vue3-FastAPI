<template>
  <main class="auth-center">
    <section
      class="auth-shell"
      :class="{ 'is-compact': !showProgress }"
      aria-label="统一认证中心"
    >
      <aside class="trust-panel">
        <div>
          <div class="brand-row">
            <span class="brand-mark"
              ><i
                class="el-icon el-icon-lock"
                aria-hidden="true"
              ></i
            ></span>
            <div>
              <strong>{{ productTitle }}</strong
              ><small>统一认证中心</small>
            </div>
          </div>

          <div class="trust-copy">
            <p class="trust-kicker">安全连接</p>
            <h1>确认身份后，安全返回应用</h1>
            <p>认证过程在这里完成。你的密码、验证码和登录会话不会交给接入应用。</p>
          </div>

          <div
            v-if="applicationName || applicationId"
            class="application-card"
          >
            <small>正在请求访问的应用</small>
            <div class="application-identity">
              <span>{{ applicationInitial }}</span>
              <div>
                <strong>{{ applicationName || '外部应用' }}</strong
                ><code v-if="applicationId">{{ applicationId }}</code>
              </div>
            </div>
          </div>

          <ul class="trust-points">
            <li>
              <i
                class="el-icon el-icon-circle-check"
                aria-hidden="true"
              ></i
              ><span>只会分享你明确确认的信息</span>
            </li>
            <li>
              <i
                class="el-icon el-icon-circle-check"
                aria-hidden="true"
              ></i
              ><span>你可以取消，并返回发起登录的应用</span>
            </li>
          </ul>
        </div>

        <div class="request-status">
          <span
            class="status-dot"
            aria-hidden="true"
          />
          <span v-if="hasExpiry">本次请求将在 {{ formatTime(remainingSeconds) }} 后失效</span>
          <span v-else>受保护的认证连接</span>
        </div>
      </aside>

      <div class="auth-main">
        <div
          v-if="showProgress"
          class="progress-wrap"
          aria-label="认证进度"
        >
          <span>认证进度</span>
          <el-steps
            :active="currentStep"
            finish-status="success"
            align-center
          >
            <el-step
              v-for="step in steps"
              :key="step"
              :title="step"
            />
          </el-steps>
        </div>
        <div class="auth-content"><slot /></div>
        <footer class="mobile-security-note">
          <i
            class="el-icon el-icon-lock"
            aria-hidden="true"
          ></i>
          <span>{{ productTitle }} 不会向应用提供密码或验证码</span>
        </footer>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = defineProps({
  currentStep: { type: Number, default: 0 },
  steps: { type: Array, default: () => ['验证身份', '确认权限'] },
  expiresIn: { type: Number, default: 0 },
  applicationName: { type: String, default: '' },
  applicationId: { type: String, default: '' },
  showProgress: { type: Boolean, default: true },
})

const productTitle = process.env.VUE_APP_TITLE
const remainingSeconds = ref(0)
const hasExpiry = ref(false)
let countdownTimer

const applicationInitial = computed(() => {
  const name = String(props.applicationName || props.applicationId || '应用').trim()
  return name.slice(0, 1).toUpperCase()
})

/** 将剩余秒数显示为分秒倒计时 */
function formatTime(seconds) {
  const value = Math.max(0, Number(seconds) || 0)
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
}

/** 同步当前认证请求的剩余有效时间 */
function resetCountdown(value) {
  remainingSeconds.value = Math.max(0, Math.floor(Number(value) || 0))
  hasExpiry.value = remainingSeconds.value > 0
}

watch(() => props.expiresIn, resetCountdown, { immediate: true })

onMounted(() => {
  countdownTimer = window.setInterval(() => {
    if (remainingSeconds.value > 0) {
      remainingSeconds.value -= 1
    }
  }, 1000)
})

onBeforeUnmount(() => window.clearInterval(countdownTimer))
</script>

<style scoped>
.auth-center {
  --trust-bg: #16324f;
  --trust-text: #f5f8fb;
  display: grid;
  min-height: 100vh;
  padding: 32px;
  background: var(--oauth-bg-color-page);
  place-items: center;
}

.auth-shell {
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  width: min(960px, 100%);
  min-height: 620px;
  overflow: hidden;
  background: var(--oauth-bg-color-overlay);
  border: 1px solid var(--oauth-border-color-lighter);
  border-radius: 16px;
  box-shadow: 0 18px 50px rgb(15 35 55 / 10%);
}

.auth-shell.is-compact {
  min-height: 530px;
}

.trust-panel {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 34px 30px 28px;
  color: var(--trust-text);
  background: var(--trust-bg);
}

.brand-row,
.application-identity,
.trust-points li,
.request-status,
.mobile-security-note {
  display: flex;
  align-items: center;
}

.brand-row {
  gap: 11px;
}

.brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  color: #16324f;
  background: #fff;
  border-radius: 10px;
  font-size: 19px;
  place-items: center;
}

.brand-row strong,
.brand-row small {
  display: block;
}

.brand-row strong {
  color: #fff;
  font-size: 15px;
}

.brand-row small {
  margin-top: 3px;
  color: rgb(255 255 255 / 66%);
  font-size: 11px;
  letter-spacing: 0.08em;
}

.trust-copy {
  margin-top: 70px;
}

.trust-kicker {
  margin: 0 0 10px;
  color: #99c4ee;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.trust-copy h1 {
  margin: 0;
  color: #fff;
  font-size: 27px;
  font-weight: 650;
  line-height: 1.35;
}

.trust-copy > p:last-child {
  margin: 16px 0 0;
  color: rgb(255 255 255 / 70%);
  font-size: 13px;
  line-height: 1.75;
}

.application-card {
  margin-top: 30px;
  padding: 16px;
  background: rgb(255 255 255 / 8%);
  border: 1px solid rgb(255 255 255 / 13%);
  border-radius: 11px;
}

.application-card > small {
  color: rgb(255 255 255 / 58%);
  font-size: 11px;
}

.application-identity {
  gap: 10px;
  margin-top: 10px;
}

.application-identity > span {
  display: grid;
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  color: #16324f;
  background: #fff;
  border-radius: 9px;
  font-weight: 700;
  place-items: center;
}

.application-identity > div {
  min-width: 0;
}

.application-identity strong,
.application-identity code {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.application-identity strong {
  color: #fff;
  font-size: 14px;
}

.application-identity code {
  margin-top: 3px;
  color: rgb(255 255 255 / 56%);
  font-size: 11px;
}

.trust-points {
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}

.trust-points li {
  gap: 8px;
  color: rgb(255 255 255 / 72%);
  font-size: 12px;
  line-height: 1.5;
}

.trust-points li + li {
  margin-top: 10px;
}

.trust-points .el-icon {
  flex: 0 0 auto;
  color: #76d5a8;
}

.request-status {
  gap: 8px;
  color: rgb(255 255 255 / 62%);
  font-size: 11px;
}

.status-dot {
  width: 7px;
  height: 7px;
  background: #76d5a8;
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgb(118 213 168 / 12%);
}

.auth-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 32px 44px 24px;
}

.progress-wrap {
  padding-bottom: 24px;
  border-bottom: 1px solid var(--oauth-border-color-lighter);
}

.progress-wrap > span {
  display: block;
  margin-bottom: 17px;
  color: var(--oauth-text-color-secondary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.progress-wrap :deep(.el-step__title) {
  font-size: 12px;
}

.progress-wrap :deep(.el-step__icon) {
  width: 26px;
  height: 26px;
  font-size: 12px;
}

.auth-content {
  flex: 1;
  padding: 28px 8px 16px;
}

.mobile-security-note {
  display: none;
  gap: 7px;
  padding-top: 16px;
  color: var(--oauth-text-color-secondary);
  font-size: 11px;
  border-top: 1px solid var(--oauth-border-color-lighter);
}

@media (max-width: 800px) {
  .auth-center {
    padding: 16px;
    place-items: start center;
  }

  .auth-shell {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .trust-panel {
    display: block;
    padding: 20px 22px;
  }

  .trust-copy,
  .trust-points {
    display: none;
  }

  .application-card {
    margin-top: 18px;
    padding: 12px;
  }

  .request-status {
    margin-top: 14px;
  }

  .auth-main {
    padding: 24px 24px 18px;
  }

  .auth-content {
    padding: 24px 0 12px;
  }

  .mobile-security-note {
    display: flex;
  }
}

@media (max-width: 460px) {
  .auth-center {
    padding: 0;
    background: var(--oauth-bg-color-overlay);
  }

  .auth-shell {
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .auth-main {
    padding: 22px 18px 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .auth-center *,
  .auth-center *::before,
  .auth-center *::after {
    transition-duration: 0.01ms !important;
  }
}
</style>
