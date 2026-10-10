import { setBusinessTimezone, setUserTimezone } from "@/utils/time";
import config from "@/config";
import storage from "@/utils/storage";
import constant from "@/utils/constant";
import { isHttp, isEmpty } from "@/utils/validate";
import { login, logout, getInfo } from "@/api/login";
import { getToken, setToken, removeToken } from "@/utils/auth";
import defAva from "@/static/images/profile.jpg";

const baseUrl = config.baseUrl;

const user = {
  state: {
    token: getToken(),
    appTimezone: "Asia/Shanghai",
    timeZone: "auto",
    id: storage.get(constant.id),
    name: storage.get(constant.name),
    avatar: storage.get(constant.avatar),
    roles: storage.get(constant.roles),
    permissions: storage.get(constant.permissions),
  },

  mutations: {
    SET_APP_TIMEZONE: (state, timezone) => {
      setBusinessTimezone(timezone);
      state.appTimezone = timezone;
    },
    SET_TIMEZONE: (state, preference = "auto") => {
      setUserTimezone(preference);
      state.timeZone = preference;
      storage.set(constant.timezone, { appTimezone: state.appTimezone, timeZone: preference });
    },
    SET_TOKEN: (state, token) => {
      state.token = token;
    },
    SET_ID: (state, id) => {
      state.id = id;
      storage.set(constant.id, id);
    },
    SET_NAME: (state, name) => {
      state.name = name;
      storage.set(constant.name, name);
    },
    SET_AVATAR: (state, avatar) => {
      state.avatar = avatar;
      storage.set(constant.avatar, avatar);
    },
    SET_ROLES: (state, roles) => {
      state.roles = roles;
      storage.set(constant.roles, roles);
    },
    SET_PERMISSIONS: (state, permissions) => {
      state.permissions = permissions;
      storage.set(constant.permissions, permissions);
    },
  },

  actions: {
    ApplyTimezone({ commit }, preference = "auto") {
      commit("SET_TIMEZONE", preference);
    },
    // 登录
    Login({ commit }, userInfo) {
      const username = userInfo.username.trim();
      const password = userInfo.password;
      const code = userInfo.code;
      const uuid = userInfo.uuid;
      return new Promise((resolve, reject) => {
        login(username, password, code, uuid)
          .then((res) => {
            setToken(res.token);
            commit("SET_TOKEN", res.token);
            resolve();
          })
          .catch((error) => {
            reject(error);
          });
      });
    },

    // 获取用户信息
    GetInfo({ commit, state }) {
      return new Promise((resolve, reject) => {
        getInfo()
          .then((res) => {
            const user = res.user;
            commit("SET_APP_TIMEZONE", res.appTimezone);
            commit("SET_TIMEZONE", user.timeZone);
            let avatar = user.avatar || "";
            if (!isHttp(avatar)) {
              avatar = isEmpty(avatar) ? defAva : baseUrl + avatar;
            }
            const userid =
              isEmpty(user) || isEmpty(user.userId) ? "" : user.userId;
            const username =
              isEmpty(user) || isEmpty(user.userName) ? "" : user.userName;
            if (res.roles && res.roles.length > 0) {
              commit("SET_ROLES", res.roles);
              commit("SET_PERMISSIONS", res.permissions);
            } else {
              commit("SET_ROLES", ["ROLE_DEFAULT"]);
            }
            commit("SET_ID", userid);
            commit("SET_NAME", username);
            commit("SET_AVATAR", avatar);
            resolve(res);
          })
          .catch((error) => {
            reject(error);
          });
      });
    },

    // 退出系统
    LogOut({ commit, state }) {
      return new Promise((resolve, reject) => {
        logout(state.token)
          .then(() => {
            commit("SET_TOKEN", "");
            commit("SET_TIMEZONE", "auto");
            commit("SET_ROLES", []);
            commit("SET_PERMISSIONS", []);
            removeToken();
            storage.clean();
            resolve();
          })
          .catch((error) => {
            reject(error);
          });
      });
    },
  },
};

// 恢复已登录账号的偏好，避免冷启动首屏使用错误时区。
const savedTimezone = storage.get(constant.timezone);
if (user.state.token && savedTimezone) {
  try {
    user.mutations.SET_APP_TIMEZONE(user.state, savedTimezone.appTimezone);
    user.mutations.SET_TIMEZONE(user.state, savedTimezone.timeZone);
  } catch {
    storage.remove(constant.timezone);
  }
}

export default user;
