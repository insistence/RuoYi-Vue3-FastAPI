const seedTitles = [
  '确认本周交付范围',
  '整理需求评审记录',
  '补充接口使用示例',
  '核对页面文案',
  '准备演示环境',
  '验证异常处理流程',
  '完善操作说明',
  '检查移动端布局',
  '同步项目里程碑',
  '回顾已完成事项',
  '确认验收清单',
  '整理下一阶段待办',
]

function seedTasks() {
  return seedTitles.map((title, index) => ({
    id: (index + 1).toString(16).padStart(32, '0'),
    title,
    description: index % 3 === 0 ? '与团队核对完成标准，并记录需要继续跟进的事项。' : '',
    status: index % 4 === 0 ? 'done' : 'todo',
    priority: index % 3 === 2 ? 'high' : 'normal',
    createdAt: new Date(Date.UTC(2026, 9, 1, 2, index * 10)).toISOString(),
    updatedAt: new Date(Date.UTC(2026, 9, 2, 2, index * 10)).toISOString(),
  }))
}

function validateTask(data) {
  const title = typeof data?.title === 'string' ? data.title.trim() : ''
  if (!title || title.length > 120) throw new Error('任务标题需为 1–120 个字符')
  if (typeof data?.description !== 'string' || data.description.length > 500)
    throw new Error('任务说明不能超过 500 个字符')
  if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(title + data.description))
    throw new Error('文本不能包含不可显示的控制字符')
  if (!['todo', 'done'].includes(data.status)) throw new Error('任务状态无效')
  if (!['normal', 'high'].includes(data.priority)) throw new Error('任务优先级无效')
  return {
    title,
    description: data.description,
    status: data.status,
    priority: data.priority,
  }
}

/**
 * 本地内存 API：使用与生产接口一致的分页、筛选、详情和写入契约。
 * 只供 dev.html 使用；重载整个页面会重置数据，不请求真实服务、不保存凭据。
 */
export function createMockTaskApi({
  getDelay = () => 300,
  shouldFail = () => false,
  getCanWrite = () => true,
} = {}) {
  let tasks = seedTasks()
  let nextId = tasks.length + 1
  const pause = (signal) =>
    new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(new Error('请求已取消'))
      const cancel = () => {
        clearTimeout(timer)
        reject(new Error('请求已取消'))
      }
      const timer = setTimeout(
        () => {
          signal?.removeEventListener('abort', cancel)
          resolve()
        },
        Math.max(0, Math.min(5000, Number(getDelay()) || 0))
      )
      signal?.addEventListener('abort', cancel, { once: true })
    })

  async function request(config) {
    const prefix = '/apps/task_demo/api/'
    if (!config.url?.startsWith(prefix)) throw new Error('模拟宿主只处理当前插件 API')
    const path = config.url.slice(prefix.length)
    const method = String(config.method || 'get').toUpperCase()
    await pause(config.signal)
    if (config.signal?.aborted) throw new Error('请求已取消')
    if (shouldFail()) throw new Error('模拟请求失败，请关闭“模拟请求失败”后重试。')
    const canWrite = getCanWrite() === true
    if (method === 'GET' && path === 'info')
      return { pluginId: 'task_demo', version: '1.1.0', canWrite }
    if (method === 'GET' && path === 'tasks') {
      const page = Number(config.params?.page ?? 1)
      const pageSize = Number(config.params?.pageSize ?? 10)
      const status = config.params?.status || ''
      if (
        !Number.isInteger(page) ||
        page < 1 ||
        page > 1000000 ||
        !Number.isInteger(pageSize) ||
        pageSize < 1 ||
        pageSize > 20
      )
        throw new Error('分页参数无效')
      if (status && !['todo', 'done'].includes(status)) throw new Error('筛选状态无效')
      const filtered = tasks
        .filter((task) => !status || task.status === status)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id))
      return {
        items: structuredClone(filtered.slice((page - 1) * pageSize, page * pageSize)),
        total: filtered.length,
        page,
        pageSize,
        canWrite,
      }
    }
    const match = /^tasks\/([0-9a-f]{32})$/.exec(path)
    const index = match ? tasks.findIndex((task) => task.id === match[1]) : -1
    if (method === 'GET' && match) {
      if (index === -1) throw new Error('任务不存在或已被删除')
      return structuredClone(tasks[index])
    }
    if (!['POST', 'PUT', 'DELETE'].includes(method)) throw new Error('模拟接口未实现')
    // UI 隐藏按钮之外，再次在请求处理层检查写权限。
    if (!canWrite) throw new Error('当前会话没有写入权限')
    if (method === 'POST' && path === 'tasks') {
      const data = validateTask(config.data)
      const now = new Date().toISOString()
      const task = {
        id: (nextId++).toString(16).padStart(32, '0'),
        ...data,
        createdAt: now,
        updatedAt: now,
      }
      tasks.push(task)
      return structuredClone(task)
    }
    if (match && (method === 'PUT' || method === 'DELETE')) {
      if (index === -1) throw new Error('任务不存在或已被删除')
      if (method === 'DELETE') {
        tasks.splice(index, 1)
        return { deleted: true }
      }
      tasks[index] = {
        ...tasks[index],
        ...validateTask(config.data),
        updatedAt: new Date().toISOString(),
      }
      return structuredClone(tasks[index])
    }
    throw new Error('模拟接口未实现')
  }
  return {
    request,
    reset() {
      tasks = seedTasks()
      nextId = tasks.length + 1
    },
    clear() {
      tasks = []
    },
  }
}
