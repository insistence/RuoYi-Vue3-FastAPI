<template>
  <ConfigProvider :theme="{ algorithm: settingsStore.isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }">
    <router-view />
  </ConfigProvider>
</template>

<script setup>
import useSettingsStore from '@/store/modules/settings'
import { handleThemeStyle } from '@/utils/theme'
import { ConfigProvider, theme } from 'ant-design-vue'

const settingsStore = useSettingsStore()

onMounted(() => {
  nextTick(() => {
    // 初始化主题样式
    handleThemeStyle(settingsStore.theme)
  })
})
</script>
