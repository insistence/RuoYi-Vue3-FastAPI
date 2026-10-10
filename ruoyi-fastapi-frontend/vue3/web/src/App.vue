<template>
  <router-view />
</template>

<script setup>
import useSettingsStore from '@/store/modules/settings'
import { handleThemeStyle } from '@/utils/theme'
import { refreshDeviceTimezone } from '@/utils/time'

/** 页面重新可见时同步设备时区。 */
function refreshTimezoneOnVisible() {
  if (document.visibilityState === 'visible') {
    refreshDeviceTimezone()
  }
}

onMounted(() => {
  window.addEventListener('focus', refreshDeviceTimezone)
  document.addEventListener('visibilitychange', refreshTimezoneOnVisible)
  nextTick(() => {
    // 初始化主题样式
    handleThemeStyle(useSettingsStore().theme)
  })
})
onUnmounted(() => {
  window.removeEventListener('focus', refreshDeviceTimezone)
  document.removeEventListener('visibilitychange', refreshTimezoneOnVisible)
})
</script>
