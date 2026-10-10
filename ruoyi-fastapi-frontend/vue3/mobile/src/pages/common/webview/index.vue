<template>
  <view v-if="params.url">
    <web-view :webview-styles="webviewStyles" :src="`${params.url}`"></web-view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";

const params = ref({});
const webviewStyles = ref({
  progress: {
    color: "#FF3333",
  },
});

const props = defineProps({
  src: {
    type: String,
    default: null,
  },
});

onLoad((event) => {
  params.value = event;
  if (event.title) {
    uni.setNavigationBarTitle({
      title: event.title,
    });
  }
});
</script>
