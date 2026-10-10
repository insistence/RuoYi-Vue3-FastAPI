<template>
  <div class="app-container chat-container">
    <el-container style="height: 100%">
      <!-- 侧边栏：会话历史 -->
      <el-aside
        width="260px"
        class="session-sidebar"
      >
        <div class="sidebar-header">
          <el-button
            type="primary"
            class="new-chat-btn"
            icon="el-icon-plus"
            @click="clearChat"
            >新建对话</el-button
          >
        </div>
        <div
          class="session-list"
          v-loading="sessionLoading"
        >
          <div
            v-for="session in sessionList"
            :key="session.sessionId"
            :class="['session-item', currentSessionId === session.sessionId ? 'active' : '']"
            @click="loadSession(session.sessionId)"
          >
            <div class="session-icon">
              <i class="el-icon-chat-dot-round"></i>
            </div>
            <div class="session-info">
              <div class="session-title">
                {{ session.sessionTitle || '新对话' }}
              </div>
              <div class="session-time">
                {{ formatTime(session.createdAt) }}
              </div>
            </div>
            <el-button
              class="delete-btn"
              type="text"
              icon="el-icon-delete"
              style="color: #f56c6c"
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
            <el-tooltip
              content="全局参数配置"
              placement="bottom"
            >
              <el-button
                icon="el-icon-setting"
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

        <div
          class="chat-history"
          ref="chatHistoryRef"
          @scroll="handleScroll"
        >
          <div
            class="chat-content"
            ref="chatContentRef"
            :class="{ 'is-empty': messageList.length === 0 }"
          >
            <div
              v-if="messageList.length === 0"
              class="welcome-screen"
            >
              <div class="welcome-icon">
                <i
                  class="el-icon-service"
                  style="font-size: 60px"
                ></i>
              </div>
              <h2>你好！我是你的 AI 助手</h2>
              <p>请在下方输入问题开始对话...</p>
            </div>

            <div
              v-for="(msg, index) in messageList"
              :key="index"
              :class="['message-row', msg.role === 'user' ? 'message-user' : 'message-ai']"
            >
              <div class="message-avatar">
                <el-avatar
                  :icon="msg.role === 'user' ? 'el-icon-user-solid' : 'el-icon-service'"
                  :size="40"
                  :class="msg.role === 'user' ? 'avatar-user' : 'avatar-ai'"
                ></el-avatar>
              </div>
              <div class="message-content-wrapper">
                <div class="message-sender">
                  {{ msg.role === 'user' ? '我' : 'AI 助手' }}
                  <span
                    class="message-time"
                    v-if="msg.createdAt"
                    >{{ formatTime(msg.createdAt) }}</span
                  >
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
                    :is-dark="isDark"
                  />
                </div>
                <div class="message-footer">
                  <div class="footer-actions">
                    <el-tooltip
                      content="复制"
                      placement="top"
                    >
                      <el-button
                        type="text"
                        icon="el-icon-document-copy"
                        size="small"
                        style="color: #606266"
                        @click="copyText(msg.content)"
                      ></el-button>
                    </el-tooltip>
                    <div
                      v-if="userConfig.metricsDefaultVisible == '0' && hasMetrics(msg)"
                      class="message-metrics"
                    >
                      <span
                        v-if="
                          msg.metrics &&
                          msg.metrics.duration !== null &&
                          msg.metrics.duration !== undefined
                        "
                        >耗时 {{ msg.metrics.duration.toFixed(3) }} s</span
                      >
                      <span
                        v-if="
                          msg.metrics &&
                          msg.metrics.inputTokens !== null &&
                          msg.metrics.inputTokens !== undefined
                        "
                        >输入 {{ msg.metrics.inputTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics &&
                          msg.metrics.outputTokens !== null &&
                          msg.metrics.outputTokens !== undefined
                        "
                        >输出 {{ msg.metrics.outputTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics &&
                          msg.metrics.totalTokens !== null &&
                          msg.metrics.totalTokens !== undefined
                        "
                        >总 {{ msg.metrics.totalTokens }} tokens</span
                      >
                      <span
                        v-if="
                          msg.metrics &&
                          msg.metrics.reasoningTokens !== null &&
                          msg.metrics.reasoningTokens !== undefined
                        "
                        >推理 {{ msg.metrics.reasoningTokens }} tokens</span
                      >
                    </div>
                  </div>
                  <div
                    v-if="msg.role === 'assistant'"
                    class="model-info"
                  >
                    <el-tag
                      size="small"
                      type="info"
                      effect="plain"
                      v-if="currentSessionAgentData && currentSessionAgentData.model"
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
              @keydown.enter.native.exact.prevent="handleSend"
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
                    type="text"
                    icon="el-icon-picture-outline"
                    style="color: #606266"
                    @click="triggerImageUpload"
                  />
                </el-tooltip>
                <el-button
                  v-if="currentModelInfo && currentModelInfo.supportReasoning === 'Y'"
                  class="toggle-chip"
                  size="mini"
                  icon="deepthink"
                  :type="chatConfig.isReasoning ? 'primary' : ''"
                  :plain="!chatConfig.isReasoning"
                  @click="chatConfig.isReasoning = !chatConfig.isReasoning"
                >
                  <svg-icon icon-class="deepthink" />
                  深度思考
                </el-button>
              </div>
              <el-button
                :type="loading ? 'danger' : 'primary'"
                :icon="loading ? 'el-icon-video-pause' : 'el-icon-s-promotion'"
                @click="handleMainAction"
                :disabled="!loading && !inputMessage.trim() && !inputImages.length"
              >
                {{ loading ? '停止' : '发送' }}
              </el-button>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>

    <!-- 全局配置弹窗 -->
    <el-dialog
      :visible.sync="showConfigDialog"
      title="用户全局配置"
      width="700px"
      append-to-body
      class="chat-config-dialog"
    >
      <el-form
        :model="editingUserConfig"
        label-width="150px"
      >
        <el-row>
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
        </el-row>
        <el-row>
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
        </el-row>
        <el-row>
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
        </el-row>
        <el-row>
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
          <el-button
            type="primary"
            @click="handleSaveConfig"
            >保存</el-button
          >
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

<script>
import { listModelAll } from '../../api/model'
import {
  listChatSession,
  delChatSession,
  getChatSession,
  getUserChatConfig,
  saveUserChatConfig,
  cancelChatRun,
} from '../../api/chat'
import { getToken } from '@/utils/auth'
import AiMessage from './components/AiMessage'
import { v4 as uuidv4 } from 'uuid'

export default {
  name: 'AiChat',
  components: { AiMessage },
  data() {
    return {
      modelOptions: [],
      currentModelId: undefined,
      messageList: [],
      inputMessage: '',
      inputImages: [],
      loading: false,
      currentSessionId: null,
      showConfigDialog: false,
      sessionList: [],
      sessionLoading: false,
      abortController: null,
      currentRunId: null,
      isAutoScroll: true,
      currentSessionAgentData: null,
      isProgrammaticScroll: false,
      scrollTimeout: null,
      chatConfig: {
        temperature: undefined,
        isReasoning: true,
      },
      userConfig: {
        chatConfigId: undefined,
        userId: undefined,
        temperature: undefined,
        addHistoryToContext: '0',
        numHistoryRuns: 3,
        systemPrompt: '',
        metricsDefaultVisible: '1',
        visionEnabled: '0',
        imageMaxSizeMb: 5,
        createTime: undefined,
        updateTime: undefined,
      },
      editingUserConfig: {
        chatConfigId: undefined,
        userId: undefined,
        temperature: undefined,
        addHistoryToContext: '0',
        numHistoryRuns: 3,
        systemPrompt: '',
        metricsDefaultVisible: '1',
        visionEnabled: '0',
        imageMaxSizeMb: 5,
        createTime: undefined,
        updateTime: undefined,
      },
      isDark: false, // Default to light
    }
  },
  computed: {
    currentModelInfo() {
      if (!this.currentModelId) return null
      return this.modelOptions.find((m) => m.modelId === this.currentModelId)
    },
  },
  watch: {
    currentModelId(newVal) {
      const model = this.modelOptions.find((m) => m.modelId === newVal)
      if (model) {
        this.chatConfig.temperature = model.temperature
      }
    },
  },
  mounted() {
    this.getModels()
    this.getSessions()
    this.loadUserConfig()
    // Initialize ResizeObserver for auto-scroll if supported
    if (window.ResizeObserver && this.$refs.chatContentRef) {
      this.resizeObserver = new ResizeObserver(() => {
        if (this.isAutoScroll) {
          this.scrollToBottom()
        }
      })
      this.resizeObserver.observe(this.$refs.chatContentRef)
    }
  },
  beforeDestroy() {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect()
    }
    if (this.abortController) {
      this.abortController.abort()
    }
  },
  methods: {
    generateSessionId() {
      return uuidv4()
    },
    loadUserConfig() {
      getUserChatConfig().then((res) => {
        if (res.data) {
          if (res.data.temperature === null) {
            res.data.temperature = undefined
          }
          if (res.data.numHistoryRuns === null) {
            res.data.numHistoryRuns = undefined
          }
          if (res.data.imageMaxSizeMb === null) {
            res.data.imageMaxSizeMb = undefined
          }
          Object.assign(this.userConfig, res.data)
          Object.assign(this.editingUserConfig, res.data)
        }
      })
    },
    openConfigDialog() {
      Object.assign(this.editingUserConfig, this.userConfig)
      this.showConfigDialog = true
    },
    handleSaveConfig() {
      const payload = { ...this.editingUserConfig }
      saveUserChatConfig(payload).then(() => {
        this.$modal.msgSuccess('配置保存成功')
        this.showConfigDialog = false
        this.loadUserConfig()
      })
    },
    hasMetrics(msg) {
      const m = msg && msg.metrics
      if (!m) return false
      return (
        (m.inputTokens !== null && m.inputTokens !== undefined) ||
        (m.outputTokens !== null && m.outputTokens !== undefined) ||
        (m.totalTokens !== null && m.totalTokens !== undefined) ||
        (m.reasoningTokens !== null && m.reasoningTokens !== undefined) ||
        (m.duration !== null && m.duration !== undefined)
      )
    },
    getImageUrl(url) {
      if (!url) return ''
      if (url.startsWith('http') || url.startsWith('https') || url.startsWith('blob:')) {
        return url
      }
      return process.env.VUE_APP_BASE_API + url
    },
    formatTime(timeStr) {
      if (!timeStr) return ''
      try {
        const date = new Date(timeStr)
        return date.toLocaleString()
      } catch (e) {
        return timeStr
      }
    },
    getModels() {
      listModelAll().then((res) => {
        this.modelOptions = res.data
        if (this.modelOptions.length > 0) {
          this.currentModelId = this.modelOptions[0].modelId
          const model = this.modelOptions[0]
          this.chatConfig.temperature = model.temperature
        }
      })
    },
    getSessions() {
      this.sessionLoading = true
      listChatSession().then((res) => {
        this.sessionList = res.data
        if (this.sessionList && this.sessionList.length > 0) {
          this.sessionList.sort((a, b) => {
            const dateA = new Date(a.createdAt).getTime()
            const dateB = new Date(b.createdAt).getTime()
            return dateB - dateA
          })
        }
        this.sessionLoading = false
      })
    },
    loadSession(sessionId) {
      if (this.currentSessionId === sessionId) return
      this.currentSessionId = sessionId
      this.messageList = []
      this.loading = true
      getChatSession(sessionId).then((res) => {
        this.messageList = res.data.messages
        this.currentSessionAgentData = res.data.agentData
        this.loading = false
        this.isAutoScroll = true
        this.scrollToBottom()
      })
    },
    handleDeleteSession(sessionId) {
      this.$modal
        .confirm('是否确认删除该会话？')
        .then(() => {
          return delChatSession(sessionId)
        })
        .then(() => {
          this.getSessions()
          if (this.currentSessionId === sessionId) {
            this.clearChat()
          }
          this.$modal.msgSuccess('删除成功')
        })
        .catch(() => {})
    },
    async sendRequest(text, images) {
      if (!this.currentModelId) {
        this.$modal.msgError('请先选择模型')
        return
      }

      this.loading = true
      const imageList = images ? images.slice() : []

      this.messageList.push({
        role: 'assistant',
        content: '',
        reasoningContent: '',
      })
      const aiMsgIndex = this.messageList.length - 1

      this.scrollToBottom()
      this.isAutoScroll = true

      this.abortController = new AbortController()

      try {
        const response = await fetch(process.env.VUE_APP_BASE_API + '/ai/chat/send', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + getToken(),
          },
          signal: this.abortController.signal,
          body: JSON.stringify({
            modelId: this.currentModelId,
            message: text,
            images: imageList,
            sessionId: this.currentSessionId,
            stream: true,
            temperature: this.chatConfig.temperature,
            isReasoning: this.chatConfig.isReasoning,
          }),
        })

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let aiContent = ''
        let aiReasoning = ''
        let buffer = ''
        let needRefreshSessions = false

        while (true) {
          if (!this.abortController) break
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()

          for (const line of lines) {
            if (!line.trim()) continue
            try {
              const data = JSON.parse(line)
              if (data.type === 'content') {
                aiContent += data.content
                this.$set(this.messageList[aiMsgIndex], 'content', aiContent)
              } else if (data.type === 'reasoning') {
                aiReasoning += data.content
                this.$set(this.messageList[aiMsgIndex], 'reasoningContent', aiReasoning)
              } else if (data.type === 'meta') {
                this.currentSessionId = data.session_id
                if (!this.sessionList.find((s) => s.sessionId === data.session_id)) {
                  needRefreshSessions = true
                }
              } else if (data.type === 'run_info') {
                this.currentRunId = data.run_id
              } else if (data.type === 'metrics') {
                this.$set(this.messageList[aiMsgIndex], 'metrics', data.metrics)
              } else if (data.type === 'error') {
                this.$modal.msgError(data.error)
              }
            } catch (e) {
              console.error('Parse error', e)
            }
          }
        }

        if (needRefreshSessions) {
          this.getSessions()
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          // User aborted
        } else {
          this.$modal.msgError('请求失败: ' + err.message)
        }
      } finally {
        this.loading = false
        this.abortController = null
      }
    },
    clearChat() {
      this.messageList = []
      this.currentSessionId = this.generateSessionId()
      this.currentSessionAgentData = null
    },
    copyText(text) {
      if (!text) {
        this.$modal.msgWarning('内容为空，无法复制')
        return
      }
      navigator.clipboard
        .writeText(text)
        .then(() => {
          this.$modal.msgSuccess('复制成功')
        })
        .catch(() => {
          this.$modal.msgError('复制失败')
        })
    },
    triggerImageUpload() {
      if (!this.userConfig.visionEnabled || this.loading) return
      const input = this.$refs.imageInputRef
      if (input) {
        input.value = ''
        input.click()
      }
    },
    async handleImageInputChange(event) {
      const files = Array.from(event.target.files || [])
      if (!files.length) return
      if (files.length + this.inputImages.length > 10) {
        this.$modal.msgError('最多只能上传 10 张图片')
        return
      }
      const maxSize = (this.userConfig.imageMaxSizeMb || 5) * 1024 * 1024
      for (const file of files) {
        if (file.size > maxSize) {
          this.$modal.msgError(`单张图片大小不能超过 ${this.userConfig.imageMaxSizeMb} MB`)
          return
        }
      }
      try {
        this.$modal.loading('正在上传图片，请稍候...')
        for (const file of files) {
          const form = new FormData()
          form.append('file', file)
          const resp = await fetch(process.env.VUE_APP_BASE_API + '/common/upload', {
            method: 'POST',
            headers: {
              Authorization: 'Bearer ' + getToken(),
            },
            body: form,
          })
          const data = await resp.json()
          if (data.code === 200 && data.fileName) {
            this.inputImages.push(data.fileName)
          } else {
            this.$modal.msgError(data.msg || '上传图片失败')
          }
        }
      } catch (e) {
        this.$modal.msgError('上传图片失败')
      } finally {
        this.$modal.closeLoading()
      }
    },
    async handleSend() {
      const text = this.inputMessage.trim()
      const images = this.inputImages
      if (!text && !images.length) return
      if (!this.currentModelId) {
        this.$modal.msgError('请先选择模型')
        return
      }

      const imageList = images.slice()
      this.messageList.push({
        role: 'user',
        content: text,
        images: imageList,
      })
      this.inputMessage = ''
      this.inputImages = []
      this.currentRunId = null

      await this.sendRequest(text, imageList)
    },
    stopGeneration() {
      if (this.abortController) {
        const controller = this.abortController
        this.abortController = null
        this.loading = false

        if (this.currentRunId) {
          cancelChatRun(this.currentRunId)
            .then(() => {})
            .catch((err) => {
              console.error('Failed to cancel run:', err)
            })
            .finally(() => {
              controller.abort()
            })
        } else {
          controller.abort()
        }
      }
    },
    handleScroll(e) {
      if (this.isProgrammaticScroll) return

      const { scrollTop, scrollHeight, clientHeight } = e.target
      const distanceToBottom = scrollHeight - scrollTop - clientHeight

      if (distanceToBottom > 100) {
        this.isAutoScroll = false
      } else if (distanceToBottom < 20) {
        this.isAutoScroll = true
      }
    },
    scrollToBottom() {
      if (this.isAutoScroll && this.$refs.chatHistoryRef) {
        this.isProgrammaticScroll = true

        this.$refs.chatHistoryRef.scrollTop = this.$refs.chatHistoryRef.scrollHeight

        this.$nextTick(() => {
          if (this.$refs.chatHistoryRef && this.isAutoScroll) {
            this.$refs.chatHistoryRef.scrollTop = this.$refs.chatHistoryRef.scrollHeight
          }
        })

        if (this.scrollTimeout) clearTimeout(this.scrollTimeout)

        this.scrollTimeout = setTimeout(() => {
          this.isProgrammaticScroll = false
          this.scrollTimeout = null
        }, 100)
      }
    },
    handleMainAction() {
      if (this.loading) {
        this.stopGeneration()
      } else {
        this.handleSend()
      }
    },
  },
}
</script>

<style scoped lang="scss">
.chat-container {
  height: calc(100vh - 84px);
  padding: 0;
  background-color: #f0f2f5;
  overflow: hidden;
}

.session-sidebar {
  border-right: 1px solid #dcdfe6;
  background-color: #ffffff;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 5px rgba(0, 0, 0, 0.02);
  z-index: 10;
  margin-bottom: 0;
  overflow: hidden;

  .sidebar-header {
    padding: 20px;
    border-bottom: 1px solid #dcdfe6;

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
      background: #dcdfe6;
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
        background-color: #f5f7fa;
      }

      &.active {
        background-color: #ecf5ff;
        border-color: #c6e2ff;

        .session-icon {
          color: #409eff;
        }

        .session-title {
          color: #409eff;
        }
      }

      .session-icon {
        margin-right: 10px;
        color: #909399;
        display: flex;
        align-items: center;
      }

      .session-info {
        flex: 1;
        overflow: hidden;

        .session-title {
          font-size: 14px;
          color: #303133;
          margin-bottom: 4px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .session-time {
          font-size: 12px;
          color: #909399;
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
      color: #909399;
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
  background-color: #f0f2f5;
  position: relative;
  overflow: hidden;

  .chat-header {
    height: 60px;
    background-color: #ffffff;
    border-bottom: 1px solid #dcdfe6;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.02);

    .header-title {
      font-size: 16px;
      font-weight: 600;
      color: #303133;
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
      color: #909399;
      opacity: 0.8;

      .welcome-icon {
        border-radius: 50%;
        padding: 20px;
        margin-bottom: 5px;
        color: #409eff;
      }

      h2 {
        margin-bottom: 10px;
        font-weight: 500;
      }

      p {
        margin-top: 0;
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
          background-color: #409eff;
        }

        .avatar-ai {
          background-color: #67c23a;
        }
      }

      .message-content-wrapper {
        flex: 1;
        display: flex;
        flex-direction: column;
        max-width: calc(100% - 52px);

        .message-sender {
          font-size: 12px;
          color: #909399;
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
          background-color: #fff;
        }

        .message-footer {
          margin-top: 6px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          width: 100%;

          .message-metrics {
            font-size: 12px;
            color: #909399;
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

          .message-footer {
            flex-direction: row-reverse;
          }

          .message-bubble {
            background-color: #409eff;
            color: #fff;
            border-top-right-radius: 2px;
          }
        }
      }

      &.message-ai {
        padding-right: 52px;

        .message-bubble {
          background-color: #ffffff;
          color: #303133;
          border-top-left-radius: 2px;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        }
      }
    }
  }
}

.chat-input-area {
  background-color: #ffffff;
  border-top: 1px solid #dcdfe6;
  padding: 20px;

  .input-wrapper {
    max-width: 900px;
    margin: 0 auto;
    position: relative;
    border: 1px solid #dcdfe6;
    border-radius: 12px;
    padding: 10px;
    transition: border-color 0.2s;

    &:focus-within {
      border-color: #409eff;
      box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
    }

    ::v-deep .el-textarea__inner {
      border: none;
      box-shadow: none;
      padding: 0;
      resize: none;
      background: transparent;

      &:focus {
        box-shadow: none;
      }
    }

    .selected-images {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px dashed #dcdfe6;

      .selected-image-item {
        width: 60px;
        height: 60px;
        border-radius: 4px;
        border: 1px solid #dcdfe6;
      }
    }

    .input-actions {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid #dcdfe6;

      .left-actions {
        display: flex;
        gap: 6px;
        align-items: center;

        .toggle-chip {
          border-radius: 999px;
          margin-left: 0;
        }
      }
    }
  }
}

.chat-config-dialog {
  ::v-deep .el-dialog__body {
    padding-top: 10px;
    padding-bottom: 10px;
  }
}

.chat-image-input {
  display: none;
}

.user-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;

  .user-image-item {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    cursor: pointer;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }
}

.user-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
