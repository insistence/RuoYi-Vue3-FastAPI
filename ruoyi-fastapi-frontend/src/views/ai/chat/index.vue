<template>
  <div class="app-container chat-container">
    <el-container style="height: 100%">
      <!-- 侧边栏：会话历史 -->
      <el-aside width="260px" class="session-sidebar">
        <div class="sidebar-header">
          <el-button
            type="primary"
            class="new-chat-btn"
            icon="Plus"
            @click="clearChat"
            >新建对话</el-button
          >
        </div>
        <div class="session-list" v-loading="sessionLoading">
          <div
            v-for="session in sessionList"
            :key="session.sessionId"
            :class="[
              'session-item',
              currentSessionId === session.sessionId ? 'active' : '',
            ]"
            @click="loadSession(session.sessionId)"
          >
            <div class="session-icon">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <div class="session-info">
              <div class="session-title">
                {{ session.sessionTitle || "新对话" }}
              </div>
              <div class="session-time">
                {{ formatTime(session.createdAt) }}
              </div>
            </div>
            <el-button
              class="delete-btn"
              type="danger"
              link
              icon="Delete"
              @click.stop="handleDeleteSession(session.sessionId)"
            ></el-button>
          </div>
          <div
            v-if="sessionList.length === 0 && !sessionLoading"
            class="empty-session"
          >
            暂无历史对话
          </div>
        </div>
      </el-aside>

      <!-- 主区域：对话框 -->
      <el-main class="chat-main">
        <div class="chat-header">
          <div class="header-left">
            <span class="header-title">AI 智能助手</span>
          </div>
          <div class="header-right">
            <el-tooltip content="全局参数配置" placement="bottom">
              <el-button
                icon="Setting"
                circle
                style="margin-right: 10px"
                @click="openConfigDialog"
              ></el-button>
            </el-tooltip>
            <el-select
              v-model="currentModelId"
              placeholder="选择模型"
              size="large"
              style="width: 210px"
            >
              <el-option
                v-for="item in modelOptions"
                :key="item.modelId"
                :label="`${item.provider}/${item.modelCode}`"
                :value="item.modelId"
              />
            </el-select>
          </div>
        </div>

        <div class="chat-history" ref="chatHistoryRef" @scroll="handleScroll">
          <div
            class="chat-content"
            ref="chatContentRef"
            :class="{ 'is-empty': messageList.length === 0 }"
          >
            <div v-if="messageList.length === 0" class="welcome-screen">
              <div class="welcome-icon">
                <el-icon size="60"><Service /></el-icon>
              </div>
              <h2>你好！我是你的 AI 助手</h2>
              <p>请在下方输入问题开始对话...</p>
            </div>

            <div
              v-for="(msg, index) in messageList"
              :key="index"
              :class="[
                'message-row',
                msg.role === 'user' ? 'message-user' : 'message-ai',
              ]"
            >
              <div class="message-avatar">
                <el-avatar
                  :icon="msg.role === 'user' ? 'UserFilled' : 'Service'"
                  :size="40"
                  :class="msg.role === 'user' ? 'avatar-user' : 'avatar-ai'"
                ></el-avatar>
              </div>
              <div class="message-content-wrapper">
                <div class="message-sender">
                  {{ msg.role === "user" ? "我" : "AI 助手" }}
                  <span class="message-time" v-if="msg.createdAt">{{
                    formatTime(msg.createdAt)
                  }}</span>
                </div>
                <div class="message-bubble">
                  <div v-if="msg.role === 'user'">
                    <div
                      v-if="msg.images && msg.images.length > 0"
                      class="user-images"
                    >
                      <el-image
                        v-for="(img, idx) in msg.images"
                        :key="idx"
                        :src="getImageUrl(img)"
                        :preview-src-list="msg.images.map(getImageUrl)"
                        fit="cover"
                        class="user-image-item"
                      />
                    </div>
                    <div class="user-text">{{ msg.content }}</div>
                  </div>
                  <AiMessage
                    v-else
                    :content="msg.content"
                    :reasoning-content="msg.reasoningContent"
                    :loading="loading && index === messageList.length - 1"
                  />
                </div>
                <div class="message-footer">
                  <div class="footer-actions">
                    <el-tooltip content="复制" placement="top">
                      <el-button
                        link
                        type="info"
                        :icon="DocumentCopy"
                        size="small"
                        @click="copyText(msg.content)"
                      ></el-button>
                    </el-tooltip>
                    <div
                      v-if="
                        userConfig.metricsDefaultVisible == '0' &&
                        hasMetrics(msg)
                      "
                      class="message-metrics"
                    >
                      <span
                        v-if="
                          msg.metrics?.duration !== null &&
                          msg.metrics?.duration !== undefined
                        "
                        >耗时 {{ msg.metrics.duration.toFixed(3) }} s</span
                      >
                      <span
                        v-if="
                          msg.metrics?.inputTokens !== null &&
                          msg.metrics?.inputTokens !== undefined
                        "
                        >输入 {{ msg.metrics.inputTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics?.outputTokens !== null &&
                          msg.metrics?.outputTokens !== undefined
                        "
                        >输出 {{ msg.metrics.outputTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics?.totalTokens !== null &&
                          msg.metrics?.totalTokens !== undefined
                        "
                        >总 {{ msg.metrics.totalTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics?.reasoningTokens !== null &&
                          msg.metrics?.reasoningTokens !== undefined
                        "
                        >推理 {{ msg.metrics.reasoningTokens }} tokens</span
                      >
                    </div>
                  </div>
                  <div v-if="msg.role === 'assistant'" class="model-info">
                    <el-tag
                      size="small"
                      type="info"
                      effect="plain"
                      v-if="currentSessionAgentData?.model"
                    >
                      {{ currentSessionAgentData.model.provider }} /
                      {{ currentSessionAgentData.model.id }}
                    </el-tag>
                    <el-tag
                      size="small"
                      type="info"
                      effect="plain"
                      v-else-if="currentModelInfo"
                    >
                      {{ currentModelInfo.provider }} /
                      {{ currentModelInfo.modelCode }}
                    </el-tag>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <div class="input-wrapper">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="3"
              resize="none"
              placeholder="请输入您的问题... (Enter 发送，Shift + Enter 换行)"
              @keydown.enter.exact.prevent="handleSend"
              :disabled="loading"
            />
            <div
              class="selected-images"
              v-if="userConfig.visionEnabled == '0' && inputImages.length"
            >
              <el-image
                v-for="(img, idx) in inputImages"
                :key="idx"
                :src="getImageUrl(img)"
                :preview-src-list="inputImages.map(getImageUrl)"
                fit="cover"
                class="selected-image-item"
              />
            </div>
            <div class="input-actions">
              <div class="left-actions">
                <el-tooltip
                  v-if="
                    currentModelInfo &&
                    currentModelInfo.supportImages === 'Y' &&
                    userConfig.visionEnabled == '0'
                  "
                  content="上传图片"
                  placement="top"
                >
                  <el-button
                    circle
                    text
                    :icon="Picture"
                    @click="triggerImageUpload"
                  />
                </el-tooltip>
                <el-button
                  v-if="
                    currentModelInfo &&
                    currentModelInfo.supportReasoning === 'Y'
                  "
                  class="toggle-chip"
                  size="small"
                  :type="chatConfig.isReasoning ? 'primary' : ''"
                  :plain="!chatConfig.isReasoning"
                  @click="chatConfig.isReasoning = !chatConfig.isReasoning"
                >
                  <template #icon>
                    <svg-icon icon-class="deepthink" />
                  </template>
                  深度思考
                </el-button>
              </div>
              <el-button
                :type="loading ? 'danger' : 'primary'"
                :icon="loading ? 'VideoPause' : 'Promotion'"
                @click="handleMainAction"
                :disabled="
                  !loading && !inputMessage.trim() && !inputImages.length
                "
              >
                {{ loading ? "停止" : "发送" }}
              </el-button>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>

    <!-- 全局配置弹窗 -->
    <el-dialog
      v-model="showConfigDialog"
      title="用户全局配置"
      width="700px"
      append-to-body
      class="chat-config-dialog"
    >
      <el-form :model="editingUserConfig" label-width="150px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="默认温度">
              <el-input-number
                v-model="editingUserConfig.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                :precision="1"
                placeholder="默认温度"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="附带历史消息">
              <el-switch
                active-value="0"
                inactive-value="1"
                v-model="editingUserConfig.addHistoryToContext"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              label="历史消息轮数"
              v-if="editingUserConfig.addHistoryToContext == '0'"
            >
              <el-input-number
                v-model="editingUserConfig.numHistoryRuns"
                :min="1"
                :max="20"
                placeholder="历史消息轮数"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="默认显示指标">
              <el-switch
                active-value="0"
                inactive-value="1"
                v-model="editingUserConfig.metricsDefaultVisible"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="开启视觉功能">
              <el-switch
                active-value="0"
                inactive-value="1"
                v-model="editingUserConfig.visionEnabled"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              label="图片最大大小"
              v-if="editingUserConfig.visionEnabled"
            >
              <el-input-number
                v-model="editingUserConfig.imageMaxSizeMb"
                :min="1"
                :max="50"
                placeholder="图片大小"
                style="width: 100%"
              >
                <template #suffix>
                  <span>MB</span>
                </template>
              </el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="系统提示词">
              <el-input
                v-model="editingUserConfig.systemPrompt"
                type="textarea"
                :rows="4"
                placeholder="设置全局系统提示词"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="showConfigDialog = false">取消</el-button>
          <el-button type="primary" @click="handleSaveConfig">保存</el-button>
        </span>
      </template>
    </el-dialog>
    <input
      v-if="userConfig.visionEnabled"
      ref="imageInputRef"
      type="file"
      accept="image/*"
      multiple
      class="chat-image-input"
      @change="handleImageInputChange"
    />
  </div>
</template>

<script setup name="AiChat">
import { listModelAll } from "@/api/ai/model";
import {
  listChatSession,
  delChatSession,
  getChatSession,
  getUserChatConfig,
  saveUserChatConfig,
  cancelChatRun,
} from "@/api/ai/chat";
import { getToken } from "@/utils/auth";
import AiMessage from "./components/AiMessage.vue";
import { Picture, DocumentCopy } from "@element-plus/icons-vue";
import { v4 as uuidv4 } from "uuid";
import { useResizeObserver } from "@vueuse/core";
import { getUseMonaco } from 'markstream-vue'

getUseMonaco()

const { proxy } = getCurrentInstance();

const modelOptions = ref([]);
const currentModelId = ref(undefined);
const messageList = ref([]);
const inputMessage = ref("");
const inputImages = ref([]);
const loading = ref(false);
const chatHistoryRef = ref(null);
const chatContentRef = ref(null);
const currentSessionId = ref(null);
const showConfigDialog = ref(false);
const imageInputRef = ref(null);
const sessionList = ref([]);
const sessionLoading = ref(false);
const abortController = ref(null);
const currentRunId = ref(null);
const isAutoScroll = ref(true);
const currentSessionAgentData = ref(null);
const isProgrammaticScroll = ref(false);
let scrollTimeout = null;

function generateSessionId() {
  return uuidv4();
}

const chatConfig = reactive({
  temperature: undefined,
  isReasoning: true,
});

const userConfig = reactive({
  chatConfigId: undefined,
  userId: undefined,
  temperature: undefined,
  addHistoryToContext: "0",
  numHistoryRuns: 3,
  systemPrompt: "",
  metricsDefaultVisible: "1",
  visionEnabled: "0",
  imageMaxSizeMb: 5,
  createTime: undefined,
  updateTime: undefined,
});

const editingUserConfig = reactive({
  chatConfigId: undefined,
  userId: undefined,
  temperature: undefined,
  addHistoryToContext: "0",
  numHistoryRuns: 3,
  systemPrompt: "",
  metricsDefaultVisible: "1",
  visionEnabled: "0",
  imageMaxSizeMb: 5,
  createTime: undefined,
  updateTime: undefined,
});

const currentModelInfo = computed(() => {
  if (!currentModelId.value) return null;
  return modelOptions.value.find((m) => m.modelId === currentModelId.value);
});

function loadUserConfig() {
  getUserChatConfig().then((res) => {
    if (res.data) {
      Object.assign(userConfig, res.data);
      Object.assign(editingUserConfig, res.data);
    }
  });
}

function openConfigDialog() {
  Object.assign(editingUserConfig, userConfig);
  showConfigDialog.value = true;
}

function handleSaveConfig() {
  const payload = { ...editingUserConfig };
  saveUserChatConfig(payload).then(() => {
    proxy.$modal.msgSuccess("配置保存成功");
    showConfigDialog.value = false;
    loadUserConfig();
  });
}

function hasMetrics(msg) {
  const m = msg?.metrics;
  if (!m) return false;
  return (
    (m.inputTokens !== null && m.inputTokens !== undefined) ||
    (m.outputTokens !== null && m.outputTokens !== undefined) ||
    (m.totalTokens !== null && m.totalTokens !== undefined) ||
    (m.reasoningTokens !== null && m.reasoningTokens !== undefined) ||
    (m.duration !== null && m.duration !== undefined)
  );
}

function getImageUrl(url) {
  if (!url) return "";
  if (
    url.startsWith("http") ||
    url.startsWith("https") ||
    url.startsWith("blob:")
  ) {
    return url;
  }
  return import.meta.env.VITE_APP_BASE_API + url;
}

function formatTime(timeStr) {
  if (!timeStr) return "";
  try {
    const date = new Date(timeStr);
    return date.toLocaleString();
  } catch (e) {
    return timeStr;
  }
}

function getModels() {
  listModelAll().then((res) => {
    modelOptions.value = res.data;
    if (modelOptions.value.length > 0) {
      currentModelId.value = modelOptions.value[0].modelId;
      // 初始化配置
      const model = modelOptions.value[0];
      chatConfig.temperature = model.temperature;
    }
  });
}

// 监听模型切换，更新默认配置
watch(currentModelId, (newVal) => {
  const model = modelOptions.value.find((m) => m.modelId === newVal);
  if (model) {
    chatConfig.temperature = model.temperature;
  }
});

function getSessions() {
  sessionLoading.value = true;
  listChatSession().then((res) => {
    sessionList.value = res.data;
    // 按创建时间倒序排序
    if (sessionList.value && sessionList.value.length > 0) {
      sessionList.value.sort((a, b) => {
        const dateA = new Date(a.createdAt).getTime();
        const dateB = new Date(b.createdAt).getTime();
        return dateB - dateA;
      });
    }
    sessionLoading.value = false;
  });
}

function loadSession(sessionId) {
  if (currentSessionId.value === sessionId) return;
  currentSessionId.value = sessionId;
  messageList.value = [];
  loading.value = true;
  getChatSession(sessionId).then((res) => {
    messageList.value = res.data.messages;
    currentSessionAgentData.value = res.data.agentData;
    loading.value = false;
    isAutoScroll.value = true;
    scrollToBottom();
  });
}

function handleDeleteSession(sessionId) {
  proxy.$modal
    .confirm("是否确认删除该会话？")
    .then(function () {
      return delChatSession(sessionId);
    })
    .then(() => {
      getSessions();
      if (currentSessionId.value === sessionId) {
        clearChat();
      }
      proxy.$modal.msgSuccess("删除成功");
    })
    .catch(() => {});
}

async function sendRequest(text, images) {
  if (!currentModelId.value) {
    proxy.$modal.msgError("请先选择模型");
    return;
  }

  loading.value = true;
  const imageList = images ? images.slice() : [];

  const aiMsgIndex =
    messageList.value.push({
      role: "assistant",
      content: "",
      reasoningContent: "",
    }) - 1;
  scrollToBottom();
  isAutoScroll.value = true;

  abortController.value = new AbortController();

  try {
    const response = await fetch(
      import.meta.env.VITE_APP_BASE_API + "/ai/chat/send",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + getToken(),
        },
        signal: abortController.value.signal,
        body: JSON.stringify({
          modelId: currentModelId.value,
          message: text,
          images: imageList,
          sessionId: currentSessionId.value,
          stream: true,
          temperature: chatConfig.temperature,
          isReasoning: chatConfig.isReasoning,
        }),
      },
    );

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let aiContent = "";
    let aiReasoning = "";
    let buffer = "";
    let needRefreshSessions = false;

    while (true) {
      if (!abortController.value) break;
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // 保留最后一个可能不完整的行

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          if (data.type === "content") {
            aiContent += data.content;
            messageList.value[aiMsgIndex].content = aiContent;
          } else if (data.type === "reasoning") {
            aiReasoning += data.content;
            messageList.value[aiMsgIndex].reasoningContent = aiReasoning;
          } else if (data.type === "meta") {
            currentSessionId.value = data.session_id;
            // 如果是新会话，标记需要刷新列表
            if (
              !sessionList.value.find((s) => s.sessionId === data.session_id)
            ) {
              needRefreshSessions = true;
            }
          } else if (data.type === "run_info") {
            currentRunId.value = data.run_id;
          } else if (data.type === "metrics") {
            messageList.value[aiMsgIndex].metrics = data.metrics;
          } else if (data.type === "error") {
            proxy.$modal.msgError(data.error);
          }
        } catch (e) {
          console.error("Parse error", e);
        }
      }
    }

    // 整个响应结束后，如果需要则刷新会话列表
    if (needRefreshSessions) {
      getSessions();
    }
  } catch (err) {
    if (err.name === "AbortError") {
      // 用户终止
    } else {
      proxy.$modal.msgError("请求失败: " + err.message);
    }
  } finally {
    loading.value = false;
    abortController.value = null;
  }
}

function clearChat() {
  messageList.value = [];
  currentSessionId.value = generateSessionId();
  currentSessionAgentData.value = null;
}

function copyText(text) {
  if (!text) {
    proxy.$modal.msgWarning("内容为空，无法复制");
    return;
  }
  navigator.clipboard
    .writeText(text)
    .then(() => {
      proxy.$modal.msgSuccess("复制成功");
    })
    .catch(() => {
      proxy.$modal.msgError("复制失败");
    });
}

function triggerImageUpload() {
  if (!userConfig.visionEnabled || loading.value) return;
  const input = imageInputRef.value;
  if (input) {
    input.value = "";
    input.click();
  }
}

async function handleImageInputChange(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  if (files.length + inputImages.value.length > 10) {
    proxy.$modal.msgError("最多只能上传 10 张图片");
    return;
  }
  const maxSize = (userConfig.imageMaxSizeMb || 5) * 1024 * 1024;
  for (const file of files) {
    if (file.size > maxSize) {
      proxy.$modal.msgError(
        `单张图片大小不能超过 ${userConfig.imageMaxSizeMb} MB`,
      );
      return;
    }
  }
  try {
    proxy.$modal.loading("正在上传图片，请稍候...");
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(
        import.meta.env.VITE_APP_BASE_API + "/common/upload",
        {
          method: "POST",
          headers: {
            Authorization: "Bearer " + getToken(),
          },
          body: form,
        },
      );
      const data = await resp.json();
      if (data.code === 200 && data.fileName) {
        inputImages.value.push(data.fileName);
      } else {
        proxy.$modal.msgError(data.msg || "上传图片失败");
      }
    }
  } catch (e) {
    proxy.$modal.msgError("上传图片失败");
  } finally {
    proxy.$modal.closeLoading();
  }
}

async function handleSend() {
  const text = inputMessage.value.trim();
  const images = inputImages.value;
  if (!text && !images.length) return;
  if (!currentModelId.value) {
    proxy.$modal.msgError("请先选择模型");
    return;
  }

  const imageList = images.slice();
  messageList.value.push({ role: "user", content: text, images: imageList });
  inputMessage.value = "";
  inputImages.value = [];
  currentRunId.value = null;

  await sendRequest(text, imageList);
}

function stopGeneration() {
  if (abortController.value) {
    const controller = abortController.value;
    abortController.value = null;
    loading.value = false;

    // Send cancellation signal to backend first
    if (currentRunId.value) {
      cancelChatRun(currentRunId.value)
        .then(() => {})
        .catch((err) => {
          console.error("Failed to cancel run:", err);
        })
        .finally(() => {
          // Abort the connection after attempting to cancel on server
          // This ensures the server has time to handle the cancellation and save data
          controller.abort();
        });
    } else {
      controller.abort();
    }
  }
}

function handleScroll(e) {
  if (isProgrammaticScroll.value) return;

  const { scrollTop, scrollHeight, clientHeight } = e.target;
  const distanceToBottom = scrollHeight - scrollTop - clientHeight;

  // If user scrolls up (distance from bottom > 100px), disable auto-scroll
  if (distanceToBottom > 100) {
    isAutoScroll.value = false;
  } else if (distanceToBottom < 20) {
    // If user scrolls back to bottom, re-enable auto-scroll
    isAutoScroll.value = true;
  }
}

function scrollToBottom() {
  if (isAutoScroll.value && chatHistoryRef.value) {
    isProgrammaticScroll.value = true;

    // Force scroll to bottom immediately
    chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight;

    // Double check in next frames to catch layout shifts (like Mermaid rendering)
    requestAnimationFrame(() => {
      if (chatHistoryRef.value && isAutoScroll.value) {
        chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight;
      }
    });

    // Reset flag after a short delay, clearing any previous timer
    if (scrollTimeout) clearTimeout(scrollTimeout);

    scrollTimeout = setTimeout(() => {
      isProgrammaticScroll.value = false;
      scrollTimeout = null;
    }, 100);
  }
}

function handleMainAction() {
  if (loading.value) {
    stopGeneration();
  } else {
    handleSend();
  }
}

// 监听内容变化，自动滚动
useResizeObserver(chatContentRef, () => {
  if (isAutoScroll.value) {
    scrollToBottom();
  }
});

onMounted(() => {
  getModels();
  getSessions();
  loadUserConfig();
});
</script>

<style scoped lang="scss">
.chat-container {
  height: calc(100vh - 84px);
  padding: 0;
  background-color: var(--el-bg-color-page);
  overflow: hidden;
}

.session-sidebar {
  border-right: 1px solid var(--el-border-color);
  background-color: var(--el-bg-color);
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 5px rgba(0, 0, 0, 0.02);
  z-index: 10;
  margin-bottom: 0;
  overflow: hidden;

  .sidebar-header {
    padding: 20px;
    border-bottom: 1px solid var(--el-border-color);

    .new-chat-btn {
      width: 100%;
      border-radius: 8px;
      height: 40px;
      font-size: 14px;
    }
  }

  .session-list {
    flex: 1;
    overflow-y: auto;
    padding: 10px;

    &::-webkit-scrollbar {
      width: 4px;
    }
    &::-webkit-scrollbar-thumb {
      background: var(--el-border-color);
      border-radius: 2px;
    }

    .session-item {
      display: flex;
      align-items: center;
      padding: 12px;
      margin-bottom: 8px;
      background-color: transparent;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s;
      position: relative;
      border: 1px solid transparent;

      &:hover {
        background-color: var(--el-fill-color);
      }

      &.active {
        background-color: var(--el-color-primary-light-9);
        border-color: var(--el-color-primary-light-7);

        .session-icon {
          color: var(--el-color-primary);
        }

        .session-title {
          color: var(--el-color-primary);
        }
      }

      html.dark & {
        &.active {
          // 使用更深一点的背景色，避免文字看不清
          background-color: var(--el-color-primary-light-8);
          border-color: var(--el-color-primary-light-6);

          .session-icon {
            color: var(--el-color-primary);
          }

          .session-title {
            color: var(--el-color-primary);
          }
        }
      }

      .session-icon {
        margin-right: 10px;
        color: var(--el-text-color-secondary);
        display: flex;
        align-items: center;
      }

      .session-info {
        flex: 1;
        overflow: hidden;

        .session-title {
          font-size: 14px;
          color: var(--el-text-color-primary);
          margin-bottom: 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .session-time {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
      }

      .delete-btn {
        opacity: 0;
        transition: opacity 0.2s;
        padding: 4px;
      }

      &:hover .delete-btn {
        opacity: 1;
      }
    }

    .empty-session {
      text-align: center;
      color: var(--el-text-color-secondary);
      font-size: 13px;
      margin-top: 40px;
    }
  }
}

.chat-main {
  padding: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--el-bg-color-page);
  position: relative;
  overflow: hidden;

  .chat-header {
    height: 60px;
    background-color: var(--el-bg-color);
    border-bottom: 1px solid var(--el-border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);

    .header-title {
      font-size: 16px;
      font-weight: 600;
      color: var(--el-text-color-primary);
    }
  }

  .chat-history {
    flex: 1;
    overflow-y: auto;
    padding: 20px;

    .chat-content {
      min-height: 100%;
      padding-bottom: 20px;

      &.is-empty {
        display: flex;
        flex-direction: column;
        height: 100%;
      }
    }

    .welcome-screen {
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      color: var(--el-text-color-secondary);
      opacity: 0.8;

      .welcome-icon {
        background: var(--el-fill-color);
        border-radius: 50%;
        padding: 20px;
        margin-bottom: 20px;
        color: var(--el-color-primary);
      }

      h2 {
        margin-bottom: 10px;
        font-weight: 500;
      }
    }

    .message-row {
      display: flex;
      max-width: 900px;
      margin-bottom: 24px;
      margin-left: auto;
      margin-right: auto;

      .message-avatar {
        flex-shrink: 0;
        margin-right: 12px;
        margin-top: 2px;

        .avatar-user {
          background-color: var(--el-color-primary);
        }

        .avatar-ai {
          background-color: var(--el-color-success);
        }
      }

      .message-content-wrapper {
        flex: 1;
        display: flex;
        flex-direction: column;
        max-width: calc(100% - 52px);

        .message-sender {
          font-size: 12px;
          color: var(--el-text-color-secondary);
          margin-bottom: 4px;
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .message-time {
          font-size: 11px;
          opacity: 0.8;
        }

        .message-bubble {
          padding: 12px 16px;
          border-radius: 12px;
          font-size: 15px;
          line-height: 1.6;
          max-width: 100%;
          min-width: 60px;
        }

        .message-footer {
          margin-top: 6px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          width: 100%;

          .message-metrics {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
          }

          .footer-actions {
            display: flex;
            align-items: center;
            gap: 10px;
          }

          .model-info {
            margin-left: auto;
          }
        }
      }

      &.message-user {
        flex-direction: row-reverse;
        padding-left: 52px;

        .message-avatar {
          margin-left: 12px;
          margin-right: 0;
        }

        .message-content-wrapper {
          align-items: flex-end;

          .message-sender {
            flex-direction: row-reverse;
          }

          .message-bubble {
            background-color: var(--el-color-primary);
            color: #fff;
            border-top-right-radius: 2px;

            .user-text {
              white-space: pre-wrap;
              word-break: break-word;
            }

            .user-images {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              margin-bottom: 8px;
              justify-content: flex-end;

              .user-image-item {
                width: 100px;
                height: 100px;
                border-radius: 4px;
                cursor: pointer;
                background-color: rgba(255, 255, 255, 0.1);
              }
            }
          }

          .message-footer {
            justify-content: flex-end;

            .footer-actions {
              flex-direction: row-reverse;
            }
          }
        }
      }

      &.message-ai {
        padding-right: 52px;

        .message-content-wrapper {
          align-items: stretch;

          .message-bubble {
            background-color: var(--el-bg-color);
            border: 1px solid var(--el-border-color);
            border-top-left-radius: 2px;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
          }
        }
      }
    }
  }

  .chat-input-area {
    background-color: var(--el-bg-color);
    padding: 20px;
    border-top: 1px solid var(--el-border-color);

    .input-wrapper {
      max-width: 900px;
      margin: 0 auto;
      border: 1px solid var(--el-border-color);
      border-radius: 8px;
      padding: 10px;
      background-color: var(--el-bg-color);
      box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
      transition: all 0.3s;

      &:focus-within {
        border-color: var(--el-color-primary);
        box-shadow: 0 2px 12px 0 var(--el-color-primary-light-9);
      }

      .selected-images {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;

        .selected-image-item {
          width: 60px;
          height: 60px;
          border-radius: 4px;
          cursor: pointer;
          border: 1px solid var(--el-border-color);
          background-color: var(--el-fill-color-light);
        }
      }

      :deep(.el-textarea__inner) {
        border: none;
        box-shadow: none;
        padding: 0;
        resize: none;
        max-height: 200px;
        background-color: transparent;
        color: var(--el-text-color-primary);

        &:focus {
          box-shadow: none;
        }
      }

      .input-actions {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid var(--el-border-color);

        .left-actions {
          display: flex;
          align-items: center;

          .toggle-chip {
            border-radius: 999px;
            margin-left: 0;
          }
        }
      }
    }
  }
}

.chat-config-dialog {
  :deep(.el-dialog__body) {
    padding-top: 10px;
    padding-bottom: 10px;
  }

  :deep(.el-form-item) {
    margin-bottom: 16px;
  }

  :deep(.el-form-item__label) {
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }
}
</style>
