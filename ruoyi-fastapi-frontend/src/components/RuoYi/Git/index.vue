<template>
  <div>
    <svg-icon icon-class="github" @click="goto" />
  </div>
</template>

<script setup>
const url = ref('https://gitee.com/insistence2022/RuoYi-Vue3-FastAPI');

function goto() {
  window.open(url.value)
}
</script>
