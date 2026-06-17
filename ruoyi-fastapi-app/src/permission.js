import { getToken, removeToken } from "@/utils/auth";
import storage from "@/utils/storage";

// 登录页面
const loginPage = "/pages/login";

// 页面白名单
const whiteList = [
  "/pages/login",
  "/pages/register",
  "/pages/common/webview/index",
  "/pages/common/agreement/index",
  "/pages/common/privacy/index",
];

// 检查地址白名单
function checkWhite(url) {
  const path = url.split("?")[0];
  return whiteList.indexOf(path) !== -1;
}

// 清除认证信息
function clearAuth() {
  removeToken();
  storage.clean();
}

// 页面跳转验证拦截器
let list = ["navigateTo", "redirectTo", "reLaunch", "switchTab"];
list.forEach((item) => {
  uni.addInterceptor(item, {
    invoke(to) {
      if (getToken()) {
        if (to.url === loginPage) {
          uni.switchTab({ url: "/pages/index" });
          return false;
        }
        return true;
      } else {
        if (checkWhite(to.url)) {
          return true;
        }
        uni.reLaunch({ url: loginPage });
        return false;
      }
    },
    fail(err) {
      console.log(err);
    },
  });
});
