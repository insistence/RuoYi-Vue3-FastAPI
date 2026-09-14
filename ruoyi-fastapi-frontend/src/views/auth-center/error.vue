<template>
  <AuthCenterShell :show-progress="false">
    <div class="error-flow">
      <span
        class="error-symbol"
        aria-hidden="true"
        ><el-icon><CloseBold /></el-icon
      ></span>
      <p class="panel-kicker">认证未完成</p>
      <h2>这次访问无法继续</h2>
      <p class="panel-lead">{{ safeMessage }}</p>

      <div class="next-steps">
        <strong>你可以这样处理</strong>
        <ol>
          <li>返回刚才的应用，重新发起登录。</li>
          <li>如果仍然失败，把出现问题的时间和应用名称告诉管理员。</li>
        </ol>
      </div>

      <el-button
        v-if="canGoBack"
        type="primary"
        size="large"
        class="return-action"
        @click="returnBack"
      >
        返回上一页
      </el-button>
      <p
        v-else
        class="close-help"
      >
        可以安全关闭此页面，再回到应用重新登录。
      </p>
    </div>
  </AuthCenterShell>
</template>

<script setup name="AuthCenterError">
import AuthCenterShell from './AuthCenterShell.vue'

const route = useRoute()
const router = useRouter()
const canGoBack = typeof window !== 'undefined' && window.history.length > 1
const safeMessage = computed(() => {
  const message = typeof route.query.message === 'string' ? route.query.message : ''
  return message.slice(0, 240) || '认证请求可能已经过期、内容不完整，或应用的接入配置已经变更。'
})

/** 返回浏览器历史中的上一页 */
function returnBack() {
  router.back()
}
</script>

<style scoped>
.error-flow {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  min-height: 370px;
}

.error-symbol {
  display: grid;
  width: 48px;
  height: 48px;
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-7);
  border-radius: 13px;
  font-size: 20px;
  place-items: center;
}

.panel-kicker {
  margin: 22px 0 8px;
  color: var(--el-color-danger);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
}

h2 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 25px;
  font-weight: 650;
  line-height: 1.4;
}

.panel-lead {
  margin: 13px 0 20px;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.75;
}

.next-steps {
  width: 100%;
  padding: 15px 17px;
  background: var(--el-fill-color-lighter);
  border-radius: 9px;
}

.next-steps strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.next-steps ol {
  margin: 9px 0 0;
  padding-left: 20px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.8;
}

.return-action {
  width: 100%;
  height: 44px;
  margin-top: 22px;
}

.close-help {
  width: 100%;
  margin: 20px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: center;
}
</style>
