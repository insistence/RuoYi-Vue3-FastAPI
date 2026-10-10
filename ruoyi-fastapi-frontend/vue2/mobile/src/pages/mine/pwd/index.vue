<template>
  <view class="min-h-screen bg-white p-4">
    <view class="space-y-5">
      <!-- Old Password -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700">旧密码</text>
        <input
          v-model="user.oldPassword"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="password"
          placeholder="请输入旧密码"
        />
      </view>
      <!-- New Password -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700">新密码</text>
        <input
          v-model="user.newPassword"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="password"
          placeholder="请输入新密码"
        />
      </view>
      <!-- Confirm Password -->
      <view class="group relative">
        <text class="mb-2 block text-sm font-medium text-gray-700"
          >确认密码</text
        >
        <input
          v-model="user.confirmPassword"
          class="h-11 w-full rounded-xl bg-gray-50 px-4 text-sm text-gray-800 outline-none ring-1 ring-gray-200 transition-all focus:bg-white focus:ring-2 focus:ring-blue-500"
          type="password"
          placeholder="请确认新密码"
        />
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

<script>
import { updateUserPwd } from "@/api/system/user";

export default {
  data() {
    return {
      user: {
        oldPassword: "",
        newPassword: "",
        confirmPassword: "",
      },
    };
  },
  methods: {
    submit() {
      if (!this.user.oldPassword) {
        this.$modal.msgError("旧密码不能为空");
        return;
      }
      if (!this.user.newPassword) {
        this.$modal.msgError("新密码不能为空");
        return;
      }
      if (
        this.user.newPassword.length < 6 ||
        this.user.newPassword.length > 20
      ) {
        this.$modal.msgError("长度在 6 到 20 个字符");
        return;
      }
      if (!this.user.confirmPassword) {
        this.$modal.msgError("确认密码不能为空");
        return;
      }
      if (this.user.newPassword !== this.user.confirmPassword) {
        this.$modal.msgError("两次输入的密码不一致");
        return;
      }

      updateUserPwd(this.user.oldPassword, this.user.newPassword).then(
        (response) => {
          this.$modal.msgSuccess("修改成功");
          setTimeout(() => {
            this.$tab.navigateBack();
          }, 1500);
        },
      );
    },
  },
};
</script>
