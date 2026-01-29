<template>
  <view class="h-full overflow-y-auto p-4">
    <view class="bg-white rounded-xl shadow-sm p-4">
      <view
        class="text-lg font-bold text-gray-900 mb-3 border-b border-gray-100 pb-2"
      >
        {{ title }}
      </view>
      <text class="block text-sm text-gray-600 leading-relaxed">
        {{ content }}
      </text>
    </view>
  </view>
</template>

<script setup>
import { ref } from "vue";
import { onLoad } from "@dcloudio/uni-app";

const title = ref("");
const content = ref("");

onLoad((options) => {
  title.value = options.title;
  content.value = options.content;
  uni.setNavigationBarTitle({
    title: options.title,
  });
});
</script>

<style>
page {
  height: 100%;
  background-color: #f9fafb;
}
</style>
