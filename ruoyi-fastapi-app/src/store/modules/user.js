import { defineStore } from "pinia";
import { ref } from "vue";
import config from "@/config";
import storage from "@/utils/storage";
import constant from "@/utils/constant";
import { isHttp, isEmpty } from "@/utils/validate";
import { getInfo, login, logout } from "@/api/login";
import { getToken, removeToken, setToken } from "@/utils/auth";
import defAva from "@/static/images/profile.jpg";

const baseUrl = config.baseUrl;

export const useUserStore = defineStore("user", () => {
  const token = ref(getToken());
  const id = ref(storage.get(constant.id));
  const name = ref(storage.get(constant.name));
  const avatar = ref(storage.get(constant.avatar));
  const roles = ref(storage.get(constant.roles));
  const permissions = ref(storage.get(constant.permissions));

  const SET_TOKEN = (val) => {
    token.value = val;
  };
  const SET_ID = (val) => {
    id.value = val;
    storage.set(constant.id, val);
  };
  const SET_NAME = (val) => {
    name.value = val;
    storage.set(constant.name, val);
  };
  const SET_AVATAR = (val) => {
    avatar.value = val;
    storage.set(constant.avatar, val);
  };
  const SET_ROLES = (val) => {
    roles.value = val;
    storage.set(constant.roles, val);
  };
  const SET_PERMISSIONS = (val) => {
    permissions.value = val;
    storage.set(constant.permissions, val);
  };

  // 登录
  const loginAction = (userInfo) => {
    const username = userInfo.username.trim();
    const password = userInfo.password;
    const code = userInfo.code;
    const uuid = userInfo.uuid;
    return new Promise((resolve, reject) => {
      login(username, password, code, uuid)
        .then((res) => {
          setToken(res.token);
          SET_TOKEN(res.token);
          resolve();
        })
        .catch((error) => {
          reject(error);
        });
    });
  };

  // 获取用户信息
  const getInfoAction = () => {
    return new Promise((resolve, reject) => {
      getInfo()
        .then((res) => {
          const user = res.user;
          let avatar = user.avatar || "";
          if (!isHttp(avatar)) {
            avatar = isEmpty(avatar) ? defAva : baseUrl + avatar;
          }
          const userid =
            isEmpty(user) || isEmpty(user.userId) ? "" : user.userId;
          const username =
            isEmpty(user) || isEmpty(user.userName) ? "" : user.userName;
          if (res.roles && res.roles.length > 0) {
            SET_ROLES(res.roles);
            SET_PERMISSIONS(res.permissions);
          } else {
            SET_ROLES(["ROLE_DEFAULT"]);
          }
          SET_ID(userid);
          SET_NAME(username);
          SET_AVATAR(avatar);
          resolve(res);
        })
        .catch((error) => {
          reject(error);
        });
    });
  };

  // 退出系统
  const logOutAction = () => {
    return new Promise((resolve, reject) => {
      logout(token.value)
        .then(() => {
          SET_TOKEN("");
          SET_ROLES([]);
          SET_PERMISSIONS([]);
          removeToken();
          storage.clean();
          resolve();
        })
        .catch((error) => {
          reject(error);
        });
    });
  };

  return {
    token,
    id,
    name,
    avatar,
    roles,
    permissions,
    SET_AVATAR,
    login: loginAction,
    getInfo: getInfoAction,
    logOut: logOutAction,
  };
});
