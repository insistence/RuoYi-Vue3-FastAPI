<template>
  <div class="business-datetime-input">
    <div class="business-datetime-input__fields">
      <el-input
        v-model="dateInput"
        type="date"
        :aria-label="label + '日期'"
        :disabled="disabled"
        :clearable="clearable"
      />
      <el-input v-model="timeInput" type="time" step="1" :aria-label="label + '时间'" :disabled="disabled" />
    </div>
    <div class="business-datetime-input__zone">{{ timezoneName }}</div>
    <div v-if="validationMessage" class="business-datetime-input__error" role="alert">
      {{ validationMessage }}
    </div>
  </div>
</template>

<script>
import { formatBusinessTime, getDisplayTimezone, getWallTimeCandidates } from '@/utils/time'

// 日期和时间分别保存为字符串，避免 Date 控件先按宿主机时区修正不存在的时间。
export default {
  name: 'BusinessDateTimePicker',
  props: {
    modelValue: {
      type: String,
      default: undefined
    },
    // Vue 2 生成页面使用 value/input 绑定。
    value: {
      type: String,
      default: undefined
    },
    label: {
      type: String,
      default: '日期时间'
    },
    timezone: {
      type: String,
      default: ''
    },
    disabled: Boolean,
    clearable: {
      type: Boolean,
      default: true
    }
  },
  emits: ['update:modelValue', 'input'],
  computed: {
    wallValue() {
      return this.modelValue !== undefined ? this.modelValue : this.value
    },
    timezoneName() {
      return this.timezone || getDisplayTimezone()
    },
    dateInput: {
      get() {
        return this.wallValue?.slice(0, 10) || ''
      },
      set(value) {
        this.updateValue(value ? `${value} ${this.timeInput || '00:00:00'}` : null)
      }
    },
    timeInput: {
      get() {
        return this.wallValue?.slice(11, 19) || ''
      },
      set(value) {
        const date = this.dateInput || formatBusinessTime(new Date(), 'YYYY-MM-DD', this.timezoneName)
        const time = value.length === 5 ? value + ':00' : value
        this.updateValue(`${date} ${time}`)
      }
    },
    validationMessage() {
      if (!this.wallValue) {
        return ''
      }
      try {
        return getWallTimeCandidates(this.wallValue, this.timezoneName).length ? '' : '该时间在此时区不存在，请重新选择'
      } catch {
        return '请选择完整有效的日期和时间'
      }
    }
  },
  methods: {
    /**
     * 更新 Vue 2 和 Vue 3 表单绑定的业务时间。
     *
     * @param {string|null} value 业务时间，清空时为 null
     */
    updateValue(value) {
      this.$emit('update:modelValue', value)
      this.$emit('input', value)
    }
  }
}
</script>

<style scoped>
.business-datetime-input {
  width: 100%;
  line-height: 1.5;
}

.business-datetime-input__fields {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 6px;
}

.business-datetime-input__zone {
  margin-top: 3px;
  color: #606266;
  font-size: 12px;
}

.business-datetime-input__error {
  color: #c45656;
  font-size: 12px;
}
</style>
