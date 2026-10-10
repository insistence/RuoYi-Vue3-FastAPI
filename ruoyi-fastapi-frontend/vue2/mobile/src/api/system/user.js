import upload from "@/utils/upload";
import request from "@/utils/request";

// 用户密码重置
export function updateUserPwd(oldPassword, newPassword) {
  const data = {
    oldPassword,
    newPassword,
  };
  return request({
    url: "/system/user/profile/updatePwd",
    method: "put",
    data: data,
  });
}

// 查询用户个人信息
export function getUserProfile() {
  return request({
    url: "/system/user/profile",
    method: "get",
  });
}

// 查询服务端支持的显示时区
export function getTimezoneOptions() {
  return request({ url: "/system/user/profile/timezones", method: "get" });
}

// 修改当前账号的显示时区
export function updateUserTimezone(timeZone) {
  return request({
    url: "/system/user/profile/timezone",
    method: "put",
    data: { timeZone },
  });
}

// 修改用户个人信息
export function updateUserProfile(data) {
  return request({
    url: "/system/user/profile",
    method: "put",
    data: data,
  });
}

// 用户头像上传
export function uploadAvatar(data) {
  return upload({
    url: "/system/user/profile/avatar",
    name: data.name,
    filePath: data.filePath,
  });
}
