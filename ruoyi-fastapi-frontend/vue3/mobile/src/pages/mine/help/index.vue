<template>
  <view class="flex h-full flex-col overflow-y-auto bg-gray-50 p-4 pb-24">
    <view v-for="(item, findex) in list" :key="findex" class="mb-6">
      <view
        class="mb-3 ml-2 flex items-center text-base font-bold text-gray-800"
      >
        <view :class="['mr-2 text-lg text-blue-500', item.icon]"></view
        >{{ item.title }}
      </view>
      <view
        class="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-gray-100"
      >
        <view
          v-for="(child, zindex) in item.childList"
          :key="zindex"
          class="relative"
          hover-class="bg-gray-50"
          @click="handleText(child)"
        >
          <view class="p-4 text-sm text-gray-600">{{ child.title }}</view>
          <view
            class="h-px w-full bg-gray-100"
            v-if="zindex !== item.childList.length - 1"
          ></view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, getCurrentInstance } from "vue";

const { proxy } = getCurrentInstance();

const list = ref([
  {
    icon: "i-mdi-github",
    title: "RuoYi-FastAPI问题",
    childList: [
      {
        title: "RuoYi-FastAPI开源吗？",
        content: "开源",
      },
      {
        title: "RuoYi-FastAPI可以商用吗？",
        content: "可以",
      },
      {
        title: "RuoYi-FastAPI官网地址多少？",
        content: "https://vfadmin.insistence.tech",
      },
      {
        title: "RuoYi-FastAPI文档地址多少？",
        content: "https://vfadmin.insistence.tech",
      },
    ],
  },
  {
    icon: "i-mdi-help-circle-outline",
    title: "其他问题",
    childList: [
      {
        title: "如何退出登录？",
        content: "请点击[我的] - [应用设置] - [退出登录]即可退出登录",
      },
      {
        title: "如何修改用户头像？",
        content: "请点击[我的] - [选择头像] - [点击提交]即可更换用户头像",
      },
      {
        title: "如何修改登录密码？",
        content: "请点击[我的] - [应用设置] - [修改密码]即可修改登录密码",
      },
    ],
  },
]);

function handleText(item) {
  proxy.$tab.navigateTo(
    `/pages/common/textview/index?title=${item.title}&content=${item.content}`,
  );
}
</script>

<style>
page {
  height: 100%;
  background-color: #f9fafb;
}
</style>
