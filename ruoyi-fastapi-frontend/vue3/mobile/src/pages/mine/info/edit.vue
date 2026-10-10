<template>
  <view class="flex h-full flex-col overflow-y-auto bg-white p-4">
    <view class="space-y-5">
      <!-- Nickname -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700"
          >用户昵称</text
        >
        <input
          v-model="user.nickName"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="text"
          placeholder="请输入昵称"
        />
      </view>

      <!-- Phone -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700"
          >手机号码</text
        >
        <input
          v-model="user.phonenumber"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="number"
          placeholder="请输入手机号码"
          maxlength="11"
        />
      </view>

      <!-- Email -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700">邮箱</text>
        <input
          v-model="user.email"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="text"
          placeholder="请输入邮箱"
        />
      </view>

      <!-- Sex -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700">性别</text>
        <view class="flex space-x-4">
          <view
            v-for="item in sexs"
            :key="item.value"
            @click="user.sex = item.value"
            class="flex flex-1 items-center justify-center rounded-xl border py-2.5 transition-all active:scale-95"
            :class="
              user.sex === item.value
                ? 'bg-blue-50 border-blue-500 text-blue-600'
                : 'bg-gray-50 border-transparent text-gray-500'
            "
          >
            <text class="text-sm font-medium">{{ item.text }}</text>
          </view>
        </view>
      </view>

      <!-- Submit Button -->
      <view class="pt-6">
        <button
          @click="submit"
          class="flex h-12 w-full items-center justify-center rounded-xl bg-blue-500 text-base font-semibold text-white shadow-lg shadow-blue-500/30 transition-all active:scale-95 active:bg-blue-600"
        >
          提 交
        </button>
      </view>
    </view>
  </view>
</template>

<script setup>
import { getUserProfile, updateUserProfile } from "@/api/system/user";
import { ref, getCurrentInstance } from "vue";
import { onLoad } from "@dcloudio/uni-app";

const { proxy } = getCurrentInstance();
const user = ref({
  nickName: "",
  phonenumber: "",
  email: "",
  sex: "",
});
const sexs = [
  {
    text: "男",
    value: "0",
  },
  {
    text: "女",
    value: "1",
  },
];

function getUser() {
  getUserProfile().then((response) => {
    const { nickName, phonenumber, email, sex } = response.data;
    user.value = { nickName, phonenumber, email, sex };
  });
}

function submit() {
  if (!user.value.nickName) {
    proxy.$modal.msgError("用户昵称不能为空");
    return;
  }
  if (!user.value.phonenumber) {
    proxy.$modal.msgError("手机号码不能为空");
    return;
  }
  if (!/^1[3|4|5|6|7|8|9][0-9]\d{8}$/.test(user.value.phonenumber)) {
    proxy.$modal.msgError("请输入正确的手机号码");
    return;
  }
  if (!user.value.email) {
    proxy.$modal.msgError("邮箱地址不能为空");
    return;
  }
  if (!/^\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*$/.test(user.value.email)) {
    proxy.$modal.msgError("请输入正确的邮箱地址");
    return;
  }

  updateUserProfile(user.value).then((response) => {
    proxy.$modal.msgSuccess("修改成功");
    setTimeout(() => {
      proxy.$tab.navigateBack();
    }, 1500);
  });
}

onLoad(() => {
  getUser();
});
</script>

<style>
page {
  height: 100%;
  background-color: #ffffff;
}
</style>
