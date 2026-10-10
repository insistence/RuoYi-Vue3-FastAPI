<template>
  <div id="app">
    <router-view />
    <theme-picker />
  </div>
</template>

<script>
import { refreshDeviceTimezone } from '@/utils/time'
import ThemePicker from '@/components/ThemePicker'

export default {
  name: 'App',
  components: { ThemePicker },
  mounted() {
    window.addEventListener('focus', refreshDeviceTimezone)
    document.addEventListener('visibilitychange', this.refreshTimezoneOnVisible)
  },
  beforeDestroy() {
    window.removeEventListener('focus', refreshDeviceTimezone)
    document.removeEventListener('visibilitychange', this.refreshTimezoneOnVisible)
  },
  methods: {
    refreshTimezoneOnVisible() {
      if (document.visibilityState === 'visible') refreshDeviceTimezone()
    },
  },
}
</script>
<style scoped>
#app .theme-picker {
  display: none;
}
</style>
