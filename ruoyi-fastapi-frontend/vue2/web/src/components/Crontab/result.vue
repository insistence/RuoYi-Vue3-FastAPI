<template>
  <div
    class="popup-result"
    :aria-busy="loading"
  >
    <p class="title">最近5次运行时间（{{ resultTimeZone }}）</p>
    <ul
      class="popup-result-scroll"
      aria-live="polite"
    >
      <li
        v-if="errorMessage"
        class="preview-error"
        role="alert"
      >
        {{ errorMessage }}
      </li>
      <li v-else-if="loading">计算结果中...</li>
      <template v-else>
        <li
          v-for="item in resultList"
          :key="item"
        >
          {{ formatBusinessTime(item, 'YYYY-MM-DD HH:mm:ss Z', resultTimeZone) }}
        </li>
        <li v-if="!resultList.length">没有未来执行时间</li>
      </template>
    </ul>
  </div>
</template>

<script>
import { previewJob } from '@/api/monitor/job'
import { formatBusinessTime } from '@/utils/time'

export default {
  name: 'crontab-result',
  props: {
    ex: { type: String, default: '' },
    timeZone: { type: String, required: true },
  },
  data() {
    return {
      resultList: [],
      resultTimeZone: this.timeZone,
      loading: false,
      errorMessage: '',
    }
  },
  computed: {
    previewInput() {
      return [this.ex, this.timeZone]
    },
  },
  watch: {
    previewInput: {
      handler: 'loadPreview',
      immediate: true,
    },
  },
  beforeCreate() {
    this._previewTimer = null
    this._previewController = null
    this._previewRequestSequence = 0
  },
  beforeDestroy() {
    this.cancelPreview()
  },
  methods: {
    formatBusinessTime,
    /** 取消防抖计时和请求，让过期响应不再更新组件。 */
    cancelPreview() {
      clearTimeout(this._previewTimer)
      if (this._previewController) this._previewController.abort()
      this._previewRequestSequence++
    },
    /** 表达式或时区变化后重新预览，销毁时释放请求。 */
    loadPreview([expression, timeZone]) {
      this.cancelPreview()
      const requestId = this._previewRequestSequence
      const controller = new AbortController()
      this._previewController = controller
      this.loading = true
      this.errorMessage = ''
      this.resultList = []
      this.resultTimeZone = timeZone
      this._previewTimer = setTimeout(async () => {
        try {
          const response = await previewJob(
            { cronExpression: expression, timeZone, count: 5 },
            controller.signal
          )
          if (requestId !== this._previewRequestSequence) return
          this.resultList = response.data.nextRunTimes
          this.resultTimeZone = response.data.timeZone
        } catch (error) {
          if (requestId !== this._previewRequestSequence || controller.signal.aborted) return
          this.errorMessage = error.message || '无法获取运行时间，请稍后重试'
        } finally {
          if (requestId === this._previewRequestSequence) this.loading = false
        }
      }, 300)
    },
  },
}
</script>

<style scoped>
.preview-error {
  color: #f56c6c;
}
</style>
