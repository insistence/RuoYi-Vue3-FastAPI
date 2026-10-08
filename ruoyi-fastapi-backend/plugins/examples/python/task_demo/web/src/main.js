import { createPluginClient } from '@ruoyi/plugin-bridge'
import './style.css'

const element = (id) => document.getElementById(id)
const filters = [...element('status-filters').querySelectorAll('button')]
const state = {
  items: [],
  total: 0,
  page: 1,
  pageSize: 10,
  status: '',
  connected: false,
  ended: false,
  canWrite: false,
  loading: true,
  loaded: false,
  listError: false,
  mutating: false,
  editorLoading: false,
  editorFailed: false,
  editorTask: null,
  deleteTask: null,
}
let client
let context = {}
let listController
let detailController
let listGeneration = 0
let detailGeneration = 0

function showNotice(message, error = false) {
  element('notice').textContent = message
  element('notice').classList.toggle('is-error', error)
}

function formatTime(value) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return '—'
  try {
    return new Intl.DateTimeFormat(context.language || 'zh-CN', {
      timeZone: context.timeZone || 'UTC',
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(date)
  } catch {
    return date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
  }
}

function setEditorControls() {
  const writable = state.connected && !state.ended && state.canWrite
  const blocked = state.editorLoading || state.editorFailed || state.mutating
  element('task-fields').disabled = blocked
  element('task-title').readOnly = !writable
  element('task-description').readOnly = !writable
  element('task-status').disabled = !writable
  element('task-priority').disabled = !writable
  element('form-read-only').hidden = writable || state.editorLoading
  element('save-task').hidden = !writable
  element('save-task').disabled = !writable || blocked
  element('close-dialog').disabled = state.mutating
  element('cancel-dialog').disabled = state.mutating
  element('cancel-dialog').textContent = writable ? '取消' : '关闭'
  element('dialog-heading').textContent = writable
    ? state.editorTask
      ? '编辑任务'
      : '新增任务'
    : '查看任务'
  element('save-task').textContent = state.mutating
    ? '正在保存…'
    : state.editorTask
      ? '保存修改'
      : '新增任务'
}

function updateControls() {
  const available = state.connected && !state.ended
  const idle = available && !state.loading && !state.mutating
  element('access-mode').textContent = state.ended
    ? '会话已结束'
    : !state.connected
      ? '未连接'
      : state.canWrite
        ? '可编辑 · 共享任务'
        : '只读 · 共享任务'
  element('read-only-notice').hidden = !available || state.canWrite
  element('create-task').disabled = !idle || !state.canWrite
  element('empty-create').disabled = !idle || !state.canWrite
  element('empty-create').hidden = !state.canWrite || Boolean(state.status)
  element('refresh').disabled = !idle
  element('retry').disabled = !idle
  element('page-size').disabled = !idle
  element('previous-page').disabled = !idle || state.page <= 1
  element('next-page').disabled = !idle || state.page * state.pageSize >= state.total
  for (const button of filters) {
    button.disabled = !idle
    button.setAttribute('aria-pressed', String(button.dataset.status === state.status))
  }
  element('list-region').setAttribute('aria-busy', String(state.loading))
  element('loading-state').hidden = !state.loading
  element('loading-message').textContent = state.connected ? '正在加载任务…' : '正在连接工作区…'
  element('task-table').hidden = !state.items.length
  element('empty-state').hidden =
    state.loading || state.listError || !state.loaded || Boolean(state.items.length)
  element('empty-heading').textContent = state.status ? '没有符合条件的任务' : '还没有任务'
  element('empty-description').textContent = state.status
    ? '试试其他状态，或查看全部任务。'
    : state.canWrite
      ? '新增第一条任务，开始记录团队待办。'
      : '当前还没有共享任务，请稍后刷新查看。'
  element('clear-filter').hidden = !state.status
  element('list-heading').textContent =
    state.status === 'todo' ? '待完成任务' : state.status === 'done' ? '已完成任务' : '全部任务'
  element('task-count').textContent = state.loaded ? `${state.total} 条` : '等待加载'
  const start = state.total ? (state.page - 1) * state.pageSize + 1 : 0
  const end = Math.min(state.page * state.pageSize, state.total)
  element('page-summary').textContent = state.loaded
    ? `显示 ${start}–${end} 条，共 ${state.total} 条任务`
    : '尚未加载任务'
  element('page-number').textContent = state.loaded
    ? `${state.page} / ${Math.max(1, Math.ceil(state.total / state.pageSize))}`
    : '—'
  for (const button of element('task-rows').querySelectorAll('button')) button.disabled = !idle
  element('cancel-delete').disabled = state.mutating
  element('confirm-delete').disabled = !available || !state.canWrite || state.mutating
  element('confirm-delete').textContent = state.mutating ? '正在删除…' : '确认删除'
  setEditorControls()
}

function node(tag, className, text) {
  const result = document.createElement(tag)
  if (className) result.className = className
  if (text !== undefined) result.textContent = text
  return result
}

// 用户内容始终写入文本节点，任务标题和说明不会作为 HTML 执行。
function renderRows() {
  const rows = state.items.map((task) => {
    const row = node('tr', task.priority === 'high' ? 'is-priority' : '')
    const titleCell = node('td')
    const title = node('button', 'task-title-button', task.title)
    title.type = 'button'
    title.addEventListener('click', () => openEditor(task.id))
    titleCell.append(title)
    if (task.description) titleCell.append(node('p', 'task-description', task.description))
    titleCell.append(node('span', 'task-id', `#${task.id}`))
    const status = node('td')
    status.dataset.label = '状态'
    status.append(
      node(
        'span',
        `status-badge status-${task.status}`,
        task.status === 'done' ? '已完成' : '待完成'
      )
    )
    const priority = node('td')
    priority.dataset.label = '优先级'
    priority.append(
      node(
        'span',
        task.priority === 'high' ? 'priority-label priority-high' : 'priority-label',
        task.priority === 'high' ? '优先处理' : '普通'
      )
    )
    const updated = node('td')
    updated.dataset.label = '更新时间'
    updated.append(node('span', 'updated-time', formatTime(task.updatedAt)))
    const actions = node('td')
    const group = node('div', 'row-actions')
    if (state.canWrite) {
      const edit = node('button', 'row-button', '编辑')
      edit.type = 'button'
      edit.setAttribute('aria-label', `编辑任务：${task.title}`)
      edit.addEventListener('click', () => openEditor(task.id))
      const remove = node('button', 'row-button row-delete', '删除')
      remove.type = 'button'
      remove.setAttribute('aria-label', `删除任务：${task.title}`)
      remove.addEventListener('click', () => openDelete(task))
      group.append(edit, remove)
    } else group.append(node('span', 'read-only-label', '仅查看'))
    actions.append(group)
    row.append(titleCell, status, priority, updated, actions)
    return row
  })
  element('task-rows').replaceChildren(...rows)
}

async function loadTasks({ reloadInfo = false } = {}) {
  if (!state.connected || state.ended) return
  listController?.abort()
  const controller = new AbortController()
  listController = controller
  const generation = ++listGeneration
  state.loading = true
  state.listError = false
  element('list-error').hidden = true
  updateControls()
  try {
    if (reloadInfo) {
      const info = await client.request(
        { method: 'GET', path: 'info' },
        { signal: controller.signal }
      )
      if (generation !== listGeneration || state.ended) return
      state.canWrite = info.canWrite === true
      renderRows()
      updateControls()
    }
    const params = { page: state.page, pageSize: state.pageSize }
    if (state.status) params.status = state.status
    const result = await client.request(
      { method: 'GET', path: 'tasks', params },
      { signal: controller.signal }
    )
    if (generation !== listGeneration || state.ended) return
    state.canWrite = result.canWrite === true
    state.total = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / state.pageSize))
    if (state.page > lastPage) {
      state.page = lastPage
      return await loadTasks()
    }
    state.items = result.items
    state.loaded = true
    renderRows()
  } catch (error) {
    if (controller.signal.aborted || generation !== listGeneration || state.ended) return
    state.listError = true
    element('list-error-message').textContent = `任务加载失败。${error.message || '请稍后重试。'}`
    element('list-error').hidden = false
  } finally {
    if (generation === listGeneration) {
      state.loading = false
      listController = null
      updateControls()
    }
  }
}

function updateCounts() {
  element('title-count').textContent = `${element('task-title').value.length} / 120`
  element('description-count').textContent = `${element('task-description').value.length} / 500`
  element('task-title').setCustomValidity('')
}

function fillEditor(task = {}) {
  element('task-title').value = task.title || ''
  element('task-description').value = task.description || ''
  element('task-status').value = task.status || 'todo'
  element('task-priority').value = task.priority || 'normal'
  element('task-timestamps').hidden = !task.id
  element('task-timestamps').textContent = task.id
    ? `创建于 ${formatTime(task.createdAt)} · 更新于 ${formatTime(task.updatedAt)}`
    : ''
  updateCounts()
}

async function openEditor(id) {
  if (!state.connected || state.ended || state.mutating || (!id && !state.canWrite)) return
  detailController?.abort()
  const generation = ++detailGeneration
  state.editorTask = id ? { id } : null
  state.editorLoading = Boolean(id)
  state.editorFailed = false
  element('dialog-kicker').textContent = id ? `共享任务 #${id}` : '新任务'
  element('form-error').hidden = true
  element('save-state').textContent = ''
  element('detail-loading').hidden = !id
  fillEditor()
  setEditorControls()
  element('task-dialog').showModal()
  if (!id) {
    element('task-title').focus()
    return
  }
  const controller = new AbortController()
  detailController = controller
  try {
    const task = await client.request(
      { method: 'GET', path: `tasks/${id}` },
      { signal: controller.signal }
    )
    if (controller.signal.aborted || generation !== detailGeneration || state.ended) return
    state.editorTask = task
    fillEditor(task)
  } catch (error) {
    if (controller.signal.aborted || generation !== detailGeneration || state.ended) return
    state.editorFailed = true
    element('form-error').textContent = `任务详情加载失败。${error.message || '请关闭后重试。'}`
    element('form-error').hidden = false
    element('form-error').focus()
  } finally {
    if (generation === detailGeneration) {
      state.editorLoading = false
      element('detail-loading').hidden = true
      setEditorControls()
    }
  }
}

function closeEditor() {
  if (state.mutating) return
  detailController?.abort()
  detailGeneration++
  element('task-dialog').close()
}

async function checkWriteAccess() {
  try {
    const info = await client.request({ method: 'GET', path: 'info' })
    if (!state.ended) {
      state.canWrite = info.canWrite === true
      renderRows()
    }
  } catch {
    /* 保存原始错误；后续刷新仍可重新读取权限。 */
  }
}

async function saveTask(event) {
  event.preventDefault()
  if (state.mutating || state.editorLoading || state.editorFailed || !state.canWrite || state.ended)
    return
  const title = element('task-title').value.trim()
  if (!title) element('task-title').setCustomValidity('请输入任务标题，不能只包含空格。')
  if (!element('task-form').reportValidity()) return
  const data = {
    title,
    description: element('task-description').value,
    status: element('task-status').value,
    priority: element('task-priority').value,
  }
  const id = state.editorTask?.id
  state.mutating = true
  element('form-error').hidden = true
  element('save-state').textContent = '正在保存，请稍候…'
  updateControls()
  let saved = false
  try {
    await client.request({
      method: id ? 'PUT' : 'POST',
      path: id ? `tasks/${id}` : 'tasks',
      data,
    })
    if (state.ended) return
    saved = true
    element('task-dialog').close()
    const filteredOut = state.status && state.status !== data.status
    showNotice(
      `${id ? '任务已更新。' : '任务已新增。'}${filteredOut ? '该任务不在当前状态筛选中，可切换到“全部”查看。' : ''}`
    )
    if (!id) state.page = 1
  } catch (error) {
    if (state.ended) return
    element('form-error').textContent =
      `保存失败，填写内容已保留。${error.message || '请稍后重试。'}`
    element('form-error').hidden = false
    element('form-error').focus()
    await checkWriteAccess()
  } finally {
    state.mutating = false
    element('save-state').textContent = ''
    updateControls()
  }
  if (saved) await loadTasks()
}

function openDelete(task) {
  if (!state.canWrite || state.mutating || state.ended) return
  state.deleteTask = task
  element('delete-title').textContent = task.title
  element('delete-error').hidden = true
  element('delete-dialog').showModal()
  element('cancel-delete').focus()
}

async function deleteTask() {
  if (!state.deleteTask || !state.canWrite || state.mutating || state.ended) return
  state.mutating = true
  element('delete-error').hidden = true
  updateControls()
  let deleted = false
  try {
    await client.request({
      method: 'DELETE',
      path: `tasks/${state.deleteTask.id}`,
    })
    if (state.ended) return
    deleted = true
    element('delete-dialog').close()
    showNotice('任务已删除。')
  } catch (error) {
    if (state.ended) return
    element('delete-error').textContent = `删除失败。${error.message || '请稍后重试。'}`
    element('delete-error').hidden = false
    element('delete-error').focus()
    await checkWriteAccess()
  } finally {
    state.mutating = false
    updateControls()
  }
  if (deleted) await loadTasks()
}

function setStatus(status) {
  state.status = status
  state.page = 1
  reloadQuery()
}

function reloadQuery() {
  // 切换查询条件后清除旧结果，避免把上一种筛选误认为当前列表。
  state.items = []
  state.loaded = false
  renderRows()
  loadTasks()
}

function applyContext(next) {
  context = { ...context, ...next }
  document.documentElement.dataset.theme = context.theme?.mode === 'dark' ? 'dark' : 'light'
  document.documentElement.lang = context.language || 'zh-CN'
  renderRows()
  updateControls()
}

function endSession() {
  state.ended = true
  state.canWrite = false
  state.loading = false
  listController?.abort()
  detailController?.abort()
  listGeneration++
  detailGeneration++
  element('task-dialog').close()
  element('delete-dialog').close()
  showNotice('会话已结束，请重新登录管理平台后打开任务清单。', true)
  renderRows()
  updateControls()
}

for (const button of filters)
  button.addEventListener('click', () => setStatus(button.dataset.status))
element('clear-filter').addEventListener('click', () => setStatus(''))
for (const id of ['create-task', 'empty-create'])
  element(id).addEventListener('click', () => openEditor())
for (const id of ['refresh', 'retry'])
  element(id).addEventListener('click', () => loadTasks({ reloadInfo: true }))
element('previous-page').addEventListener('click', () => {
  state.page--
  reloadQuery()
})
element('next-page').addEventListener('click', () => {
  state.page++
  reloadQuery()
})
element('page-size').addEventListener('change', () => {
  state.pageSize = Number(element('page-size').value)
  state.page = 1
  reloadQuery()
})
for (const id of ['close-dialog', 'cancel-dialog'])
  element(id).addEventListener('click', closeEditor)
element('task-dialog').addEventListener('cancel', (event) => {
  event.preventDefault()
  closeEditor()
})
element('delete-dialog').addEventListener('cancel', (event) => {
  if (state.mutating) event.preventDefault()
})
element('cancel-delete').addEventListener('click', () => {
  if (!state.mutating) element('delete-dialog').close()
})
element('confirm-delete').addEventListener('click', deleteTask)
element('task-form').addEventListener('submit', saveTask)
for (const id of ['task-title', 'task-description'])
  element(id).addEventListener('input', updateCounts)

async function connect() {
  try {
    const config = JSON.parse(element('ruoyi-plugin-config')?.textContent || '{}')
    if (config.pluginId !== 'task_demo') throw new Error('请从管理平台或本地模拟宿主打开任务清单。')
    client = createPluginClient({ pluginId: config.pluginId })
    client.subscribe(({ type, payload }) => {
      if (type === 'preferences') applyContext(payload)
      if (type === 'refresh') loadTasks({ reloadInfo: true })
      if (type === 'logout') endSession()
    })
    applyContext(await client.ready)
    state.connected = true
    await loadTasks({ reloadInfo: true })
  } catch (error) {
    state.loading = false
    showNotice(error.message || '连接失败，请重新打开任务清单。', true)
    updateControls()
  }
}
connect()
window.addEventListener(
  'pagehide',
  () => {
    listController?.abort()
    detailController?.abort()
    client?.destroy()
  },
  { once: true }
)
