import config from "@/config";
import { getToken } from "@/utils/auth";
import errorCode from "@/utils/errorCode";
import { useUserStore } from "@/store/modules/user";
import { toast, showConfirm, tansParams } from "@/utils/common";
import {
  decryptTransportErrorResponse,
  decryptTransportResponse,
  encryptTransportRequest,
  invalidateTransportKeyMeta,
  resetTransportRequestConfig,
  shouldRetryTransportWithFreshKey,
} from "@/utils/transportCrypto";

let timeout = 10000;
const baseUrl = config.baseUrl;

const request = async (config) => {
  // 是否需要设置 token
  const isToken = (config.headers || {}).isToken === false;
  config.header = config.header || {};
  config.headers = config.headers || {};
  if (getToken() && !isToken) {
    config.header["Authorization"] = "Bearer " + getToken();
  }

  try {
    config = await encryptTransportRequest(config);

    // get请求映射params参数
    if (config.params) {
      let url = config.url + "?" + tansParams(config.params);
      url = url.slice(0, -1);
      config.url = url;
    }

    return await new Promise((resolve, reject) => {
      uni.request({
        method: config.method || "get",
        timeout: config.timeout || timeout,
        url: config.baseUrl || baseUrl + config.url,
        data: config.data,
        header: config.header,
        dataType: "json",
        success: async (response) => {
          try {
            const res = await decryptTransportResponse(response, config);

            if (shouldRetryTransportWithFreshKey(res) && !config.__transportRetried) {
              invalidateTransportKeyMeta();
              config.__transportRetried = true;
              config.headers.repeatSubmit = false;
              resetTransportRequestConfig(config);
              resolve(await request(config));
              return;
            }

            const code = res.data.code || 200;
            const msg = errorCode[code] || res.data.msg || errorCode["default"];
            if (code === 401) {
              showConfirm(
                "登录状态已过期，您可以继续留在该页面，或者重新登录?",
              ).then((res) => {
                if (res.confirm) {
                  useUserStore()
                    .logOut()
                    .then(() => {
                      uni.reLaunch({ url: "/pages/login" });
                    });
                }
              });
              const error = new Error("无效的会话，或者会话已过期，请重新登录。");
              error.response = res;
              reject(error);
            } else if (code === 500) {
              const error = new Error(msg);
              error.response = res;
              reject(error);
            } else if (code !== 200) {
              const error = new Error(msg);
              error.response = res;
              reject(error);
            } else {
              resolve(res.data);
            }
          } catch (error) {
            reject(error);
          }
        },
        fail: reject,
      });
    });
  } catch (error) {
    error = await decryptTransportErrorResponse(error, config);
    if (shouldRetryTransportWithFreshKey(error) && !config.__transportRetried) {
      invalidateTransportKeyMeta();
      config.__transportRetried = true;
      config.headers.repeatSubmit = false;
      resetTransportRequestConfig(config);
      return request(config);
    }

    const response = error.response;
    const responseStatus = response?.status ?? response?.statusCode;
    const responseCode = response?.data?.code;
    const responseMsg = response?.data?.msg;
    if (responseMsg) {
      uni.showToast({
        title: responseMsg,
        icon: "none",
        duration: responseStatus === 429 || responseCode === 429 ? 5000 : 3000,
      });
      throw error;
    }

    let { message } = error;
    if (message === "Network Error") {
      message = "后端接口连接异常";
    } else if (message && message.includes("timeout")) {
      message = "系统接口请求超时";
    } else if (message && message.includes("Request failed with status code")) {
      message = "系统接口" + message.substr(message.length - 3) + "异常";
    }
    if (message) {
      toast(message);
    }
    throw error;
  }
};

export default request;
