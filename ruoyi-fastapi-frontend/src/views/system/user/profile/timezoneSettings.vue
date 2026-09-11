<template>
  <el-form class="timezone-settings" label-position="top" @submit.prevent="save">
    <el-form-item label="时间显示方式">
      <el-radio-group v-model="mode" :disabled="saving">
        <el-radio value="auto">自动跟随设备</el-radio>
        <el-radio value="custom">手动选择</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item v-if="mode === 'custom'" label="显示时区" :error="fieldError">
      <el-select
        v-model="selectedZone"
        filterable
        :disabled="saving"
        :loading="loading"
        placeholder="搜索时区，例如 Asia/Shanghai"
        aria-label="显示时区"
        class="timezone-settings__select"
        @change="fieldError = ''"
      >
        <el-option v-for="zone in timezones" :key="zone" :label="zone" :value="zone" />
      </el-select>
    </el-form-item>
    <el-alert v-if="loadError" type="warning" :closable="false" class="timezone-settings__notice">
      <template #title>
        时区列表加载失败，仍可使用当前时区。
        <el-button link type="primary" :loading="loading" @click="loadOptions">重试</el-button>
      </template>
    </el-alert>
    <div class="timezone-settings__preview" aria-live="polite">
      <div>
        预览时区：<strong>{{ previewZone }}</strong>
      </div>
      <div>时间预览：{{ previewTime }}</div>
      <div v-if="mode === 'auto' && !deviceZone" class="timezone-settings__fallback">
        当前设备无法识别时区，已使用系统时区；你也可以手动选择。
      </div>
    </div>
    <p class="timezone-settings__hint">用于时间显示、日期筛选和导出。定时任务和业务统计使用各自配置的时区。</p>
    <p v-if="saveError" role="alert" class="timezone-settings__error">{{ saveError }}</p>
    <el-button type="primary" native-type="submit" :loading="saving">保存时区</el-button>
  </el-form>
</template>

<script setup>
import { getTimezoneOptions, updateUserTimezone } from '@/api/system/user'
import useUserStore from '@/store/modules/user'
import {
  formatBusinessTime,
  getBusinessTimezone,
  getDeviceTimezone,
  getDisplayTimezone,
  getSupportedTimezones
} from '@/utils/time'

const props = defineProps({ user: Object })
const emit = defineEmits(['saved'])
const { proxy } = getCurrentInstance()
const userStore = useUserStore()
const mode = ref(userStore.timeZone === 'auto' ? 'auto' : 'custom')
const selectedZone = ref(getDisplayTimezone())
const timezones = ref(getSupportedTimezones())
const loading = ref(false)
const loadError = ref(false)
const saving = ref(false)
const saveError = ref('')
const fieldError = ref('')
const now = ref(new Date())
const deviceZone = computed(getDeviceTimezone)
const previewZone = computed(() =>
  mode.value === 'auto' ? deviceZone.value || getBusinessTimezone() : selectedZone.value
)
const previewTime = computed(() => formatBusinessTime(now.value, 'YYYY-MM-DD HH:mm:ss', previewZone.value))

watch(
  () => props.user?.timeZone,
  value => {
    if (!value) {
      return
    }
    mode.value = value === 'auto' ? 'auto' : 'custom'
    selectedZone.value = value === 'auto' ? getDisplayTimezone() : value
  }
)

/** 加载当前浏览器支持的时区选项。 */
async function loadOptions() {
  loading.value = true
  loadError.value = false
  try {
    const response = await getTimezoneOptions()
    timezones.value = getSupportedTimezones(response.data)
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

/** 保存账号时区，并同步当前页面展示。 */
async function save() {
  if (saving.value) {
    return
  }
  if (mode.value === 'custom' && !selectedZone.value) {
    fieldError.value = '请选择显示时区'
    return
  }
  saving.value = true
  saveError.value = ''
  const preference = mode.value === 'auto' ? 'auto' : selectedZone.value
  try {
    await updateUserTimezone(preference)
    userStore.applyTimezone(preference)
    emit('saved', preference)
    now.value = new Date()
    proxy.$modal.msgSuccess('时区设置已保存')
  } catch (error) {
    saveError.value = error.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.timezone-settings {
  max-width: 560px;
}
.timezone-settings__select {
  width: 100%;
}
.timezone-settings__preview {
  padding: 12px 16px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  line-height: 1.8;
  overflow-wrap: anywhere;
}
.timezone-settings__hint,
.timezone-settings__fallback {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.7;
}
.timezone-settings__notice {
  margin-bottom: 16px;
}
.timezone-settings__error {
  color: var(--el-color-danger);
}
</style>
