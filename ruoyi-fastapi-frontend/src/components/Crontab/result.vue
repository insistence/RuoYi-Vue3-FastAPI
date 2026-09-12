<template>
  <div class="popup-result" :aria-busy="loading">
    <p class="title">最近 5 次运行时间（{{ resultTimeZone }}）</p>
    <p v-if="errorMessage" role="alert" class="preview-error">{{ errorMessage }}</p>
    <ul v-else class="popup-result-scroll" aria-live="polite">
      <li v-if="loading">正在获取运行时间…</li>
      <li v-else-if="!resultList.length">没有未来执行时间</li>
      <li v-for="item in resultList" v-else :key="item">
        {{ formatBusinessTime(item, 'YYYY-MM-DD HH:mm:ss Z', resultTimeZone) }}
      </li>
    </ul>
  </div>
</template>

<script setup>
import { previewJob } from '@/api/monitor/job'
import { formatBusinessTime } from '@/utils/time'

const props = defineProps({
  ex: {
    type: String,
    default: ''
  },
  timeZone: {
    type: String,
    required: true
  }
})
const resultList = ref([])
const resultTimeZone = ref(props.timeZone)
const loading = ref(false)
const errorMessage = ref('')
let previewRequestSequence = 0

watch(
  () => [props.ex, props.timeZone],
  ([expression, timeZone], _, onCleanup) => {
    const requestId = ++previewRequestSequence
    const controller = new AbortController()
    loading.value = true
    errorMessage.value = ''
    resultList.value = []
    resultTimeZone.value = timeZone
    const timer = setTimeout(async () => {
      try {
        const response = await previewJob({ cronExpression: expression, timeZone, count: 5 }, controller.signal)
        if (requestId !== previewRequestSequence) {
          return
        }
        resultList.value = response.data.nextRunTimes
        resultTimeZone.value = response.data.timeZone
      } catch (error) {
        if (requestId !== previewRequestSequence || controller.signal.aborted) {
          return
        }
        errorMessage.value = error.message || '无法获取运行时间，请稍后重试'
      } finally {
        if (requestId === previewRequestSequence) {
          loading.value = false
        }
      }
    }, 300)
    onCleanup(() => {
      clearTimeout(timer)
      controller.abort()
    })
  },
  { immediate: true }
)
</script>

<style scoped>
.preview-error {
  color: var(--el-color-danger);
}
</style>
