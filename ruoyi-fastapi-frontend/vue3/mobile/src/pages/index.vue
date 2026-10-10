<template>
  <view class="flex h-full flex-col bg-gray-50">
    <!-- Header Area -->
    <view class="bg-white pb-6 rounded-b-3xl shadow-sm z-50">
      <!-- Title -->
      <view class="pt-12 pb-4 px-4 flex justify-center items-center">
        <text class="text-lg font-bold text-gray-800">RuoYi-FastAPI移动端</text>
      </view>

      <!-- Search & Notification -->
      <view class="px-4 pb-2">
        <view class="flex items-center space-x-3">
          <!-- Search Input -->
          <view class="flex-1 relative">
            <view
              class="absolute left-3 top-0 bottom-0 flex items-center text-gray-400"
            >
              <view class="i-mdi-magnify text-lg"></view>
            </view>
            <input
              type="text"
              placeholder="搜索..."
              placeholder-class="text-gray-400"
              class="w-full h-10 rounded-full bg-gray-100 pl-10 pr-4 text-sm text-gray-800"
            />
          </view>
          <!-- Notification -->
          <view
            class="relative flex h-10 w-10 items-center justify-center rounded-full bg-gray-50 text-gray-600 active:scale-95 transition-transform border border-gray-100"
          >
            <view class="i-mdi-bell-outline text-xl"></view>
            <view
              class="absolute top-2.5 right-2.5 h-2 w-2 rounded-full bg-red-500 border border-white"
            ></view>
          </view>
        </view>
      </view>
    </view>

    <scroll-view
      scroll-y
      class="flex-1 overflow-hidden"
      :show-scrollbar="false"
    >
      <view class="p-4 space-y-5 pb-24">
        <!-- Hero Card -->
        <view
          class="relative overflow-hidden rounded-3xl bg-gradient-to-r from-indigo-500 to-purple-600 p-6 text-white shadow-xl shadow-indigo-200"
        >
          <view
            class="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-white/20 blur-2xl"
          ></view>
          <view
            class="absolute -bottom-10 -left-10 h-32 w-32 rounded-full bg-white/20 blur-2xl"
          ></view>

          <view class="relative z-10">
            <view class="mb-4 flex items-center justify-between">
              <view
                class="rounded-lg bg-white/20 px-3 py-1 text-xs font-medium backdrop-blur-sm"
                >系统运行正常</view
              >
              <view class="text-xs opacity-80">刚刚更新</view>
            </view>
            <view class="flex items-end justify-between">
              <view>
                <view class="text-3xl font-bold">85%</view>
                <view class="text-sm opacity-90">工作效率</view>
              </view>
              <view
                class="h-10 w-24 overflow-hidden rounded-lg bg-white/10 p-1"
              >
                <view class="h-full w-full flex items-end justify-between px-1">
                  <view class="w-1 bg-white/50 h-2 rounded-full"></view>
                  <view class="w-1 bg-white/70 h-4 rounded-full"></view>
                  <view class="w-1 bg-white/40 h-3 rounded-full"></view>
                  <view class="w-1 bg-white/90 h-6 rounded-full"></view>
                  <view class="w-1 bg-white/60 h-4 rounded-full"></view>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- Stats Grid -->
        <view class="grid grid-cols-2 gap-4">
          <view
            class="rounded-2xl bg-white p-4 shadow-sm border border-gray-100 flex items-center justify-between"
          >
            <view>
              <view class="text-xs text-gray-500 mb-1">新通知</view>
              <view class="text-2xl font-bold text-gray-800">12</view>
            </view>
            <view
              class="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-500"
            >
              <view class="i-mdi-bell text-xl"></view>
            </view>
          </view>
          <view
            class="rounded-2xl bg-white p-4 shadow-sm border border-gray-100 flex items-center justify-between"
          >
            <view>
              <view class="text-xs text-gray-500 mb-1">待办任务</view>
              <view class="text-2xl font-bold text-gray-800">5</view>
            </view>
            <view
              class="flex h-12 w-12 items-center justify-center rounded-full bg-purple-50 text-purple-500"
            >
              <view class="i-mdi-calendar text-xl"></view>
            </view>
          </view>
        </view>

        <!-- Quick Functions -->
        <view>
          <view class="mb-4 flex items-center justify-between">
            <view class="text-base font-bold text-gray-800">快捷入口</view>
          </view>
          <view
            class="grid grid-cols-4 gap-2 rounded-2xl bg-white p-4 shadow-sm"
          >
            <view class="flex flex-col items-center space-y-2">
              <view
                class="flex h-12 w-12 items-center justify-center rounded-2xl bg-orange-50 text-orange-500"
              >
                <view class="i-mdi-file-document-edit text-xl"></view>
              </view>
              <view class="text-xs font-medium text-gray-600">申请</view>
            </view>
            <view class="flex flex-col items-center space-y-2">
              <view
                class="flex h-12 w-12 items-center justify-center rounded-2xl bg-green-50 text-green-500"
              >
                <view class="i-mdi-newspaper text-xl"></view>
              </view>
              <view class="text-xs font-medium text-gray-600">新闻</view>
            </view>
            <view class="flex flex-col items-center space-y-2">
              <view
                class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-500"
              >
                <view class="i-mdi-chart-bar text-xl"></view>
              </view>
              <view class="text-xs font-medium text-gray-600">统计</view>
            </view>
            <view class="flex flex-col items-center space-y-2">
              <view
                class="flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-50 text-gray-400"
              >
                <view class="i-mdi-calendar text-xl"></view>
              </view>
              <view class="text-xs font-medium text-gray-600">计划</view>
            </view>
          </view>
        </view>

        <!-- Recent Apps -->
        <view>
          <view class="mb-4 flex items-center justify-between">
            <view class="text-base font-bold text-gray-800">最近更新</view>
            <view class="text-xs text-blue-500">查看全部</view>
          </view>
          <view class="space-y-3">
            <view
              class="flex items-center rounded-2xl bg-white p-4 shadow-sm border border-gray-50"
            >
              <view
                class="flex h-12 w-12 items-center justify-center rounded-xl bg-blue-50 text-blue-500"
              >
                <view class="i-mdi-clipboard-text-outline text-xl"></view>
              </view>
              <view class="ml-4 flex-1">
                <view class="font-bold text-gray-800">请假申请</view>
                <view class="text-xs text-gray-500">等待经理审批</view>
              </view>
              <view
                class="rounded-full bg-yellow-50 px-3 py-1 text-xs font-medium text-yellow-600"
                >待处理</view
              >
            </view>
            <view
              class="flex items-center rounded-2xl bg-white p-4 shadow-sm border border-gray-50"
            >
              <view
                class="flex h-12 w-12 items-center justify-center rounded-xl bg-green-50 text-green-500"
              >
                <view class="i-mdi-newspaper text-xl"></view>
              </view>
              <view class="ml-4 flex-1">
                <view class="font-bold text-gray-800">周报</view>
                <view class="text-xs text-gray-500">提交成功</view>
              </view>
              <view
                class="rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-600"
                >已完成</view
              >
            </view>
          </view>
        </view>
      </view>
    </scroll-view>
  </view>
</template>

<script setup>
const globalConfig = getApp().globalData.config;
</script>
