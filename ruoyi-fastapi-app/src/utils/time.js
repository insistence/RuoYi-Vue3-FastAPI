// 补齐小程序运行时可能缺失的 Intl 能力和 IANA 时区数据。
// 同步加载，保证业务时区初始化和首屏渲染时已具备完整能力。
import '@formatjs/intl-getcanonicallocales/polyfill.js'
import '@formatjs/intl-locale/polyfill.js'
import '@formatjs/intl-pluralrules/polyfill.js'
import '@formatjs/intl-pluralrules/locale-data/en.js'
import '@formatjs/intl-numberformat/polyfill.js'
import '@formatjs/intl-numberformat/locale-data/en.js'
import '@formatjs/intl-datetimeformat/polyfill.js'
import '@formatjs/intl-datetimeformat/locale-data/en.js'
import '@formatjs/intl-datetimeformat/add-all-tz.js'

import { ref } from 'vue'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc.js'

dayjs.extend(utc)

const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const WALL_TIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/
const RFC3339_PATTERN = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']
const MILLISECONDS_PER_SECOND = 1000
const MILLISECONDS_PER_MINUTE = 60 * MILLISECONDS_PER_SECOND
const MILLISECONDS_PER_HOUR = 60 * MILLISECONDS_PER_MINUTE
const ORIGINAL_TIME_FIELDS = Symbol('originalTimeFields')
const timezoneFormatters = new Map()

const businessTimezone = ref('Asia/Shanghai')
const userTimezone = ref('auto')
const deviceTimezone = ref(null)

/**
 * 日期时间输入校验异常，包含夏令时重复时间的候选值。
 */
export class TimeInputError extends Error {
  /**
   * @param {string} message 校验提示
   * @param {string} code 错误类型
   * @param {Array<{epoch: number, offset: string, value: string}>} candidates 可选的真实时刻
   */
  constructor(message, code, candidates = []) {
    super(message)
    this.code = code
    this.candidates = candidates
  }
}

/**
 * 获取并缓存指定时区的日期时间格式化器。
 *
 * @param {string} timezoneName IANA 时区名称
 * @returns {Intl.DateTimeFormat} 格式化器实例
 */
function getFormatter(timezoneName) {
  if (typeof timezoneName !== 'string' || !timezoneName.trim() || /^[+-]/.test(timezoneName)) {
    throw new Error(`无效的 IANA 时区: ${timezoneName}`)
  }

  const name = timezoneName.trim()
  if (!timezoneFormatters.has(name)) {
    try {
      const formatter = new Intl.DateTimeFormat('en', {
        timeZone: name,
        calendar: 'gregory',
        numberingSystem: 'latn',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23'
      })
      timezoneFormatters.set(name, formatter)
    } catch {
      throw new Error(`无效的 IANA 时区: ${timezoneName}`)
    }
  }
  return timezoneFormatters.get(name)
}

/**
 * 更新默认业务时区。
 *
 * @param {string} timezoneName 服务端返回的 IANA 时区名称
 * @returns {void}
 */
export function setBusinessTimezone(timezoneName) {
  getFormatter(timezoneName)
  businessTimezone.value = timezoneName.trim()
}

/**
 * 获取当前业务时区。
 *
 * @returns {string} IANA 时区名称
 */
export function getBusinessTimezone() {
  return businessTimezone.value
}

/**
 * 设置账号显示偏好。auto 跟随设备；IANA 名称表示手动选择。
 *
 * @param {string} preference 账号保存的时区偏好
 * @returns {void}
 */
export function setUserTimezone(preference = 'auto') {
  if (preference !== 'auto') {
    getFormatter(preference)
  }
  userTimezone.value = preference.trim()
  refreshDeviceTimezone()
}

/**
 * 获取账号时区偏好。
 *
 * @returns {string} auto 或 IANA 时区名称
 */
export function getUserTimezone() {
  return userTimezone.value
}

/**
 * 重新识别设备的 IANA 时区。不能从单个 UTC 偏移猜测地区或夏令时规则。
 *
 * @returns {string|null} 设备时区；当前运行时不支持识别时返回 null
 */
export function refreshDeviceTimezone() {
  try {
    // FormatJS 默认时区是 UTC，不能把它误报为设备时区。
    if (Intl.DateTimeFormat.polyfilled) {
      deviceTimezone.value = null
      return null
    }
    const name = new Intl.DateTimeFormat().resolvedOptions().timeZone
    getFormatter(name)
    deviceTimezone.value = name
  } catch {
    deviceTimezone.value = null
  }
  return deviceTimezone.value
}

/**
 * 获取最近一次识别的设备时区。
 *
 * @returns {string|null} IANA 时区；无法识别时返回 null
 */
export function getDeviceTimezone() {
  return deviceTimezone.value
}

/**
 * 获取页面展示、日期输入和普通日期筛选使用的有效时区。
 *
 * @returns {string} IANA 时区名称
 */
export function getDisplayTimezone() {
  return userTimezone.value === 'auto' ? deviceTimezone.value || businessTimezone.value : userTimezone.value
}

/**
 * 获取已打开表单的时区，确保控件提示与提交转换一致。
 *
 * @param {Object} record 经 prepareTimeFields 准备的表单或子表行
 * @returns {string} 表单绑定的时区
 */
export function getTimeFieldsTimezone(record) {
  return record?.[ORIGINAL_TIME_FIELDS]?.timezoneName || getDisplayTimezone()
}

/**
 * 过滤当前运行时不支持的时区，保留设备时区和已保存的有效选择。
 *
 * @param {string[]} names 服务端提供的 IANA 名称
 * @returns {string[]} 按名称排序的可选时区
 */
export function getSupportedTimezones(names = []) {
  return [...new Set([...names, getDisplayTimezone(), getBusinessTimezone(), 'UTC'])]
    .filter(name => {
      try {
        getFormatter(name)
        return true
      } catch {
        return false
      }
    })
    .sort()
}

/**
 * 校验当地日期时间，并将各时间分量放入 UTC 毫秒坐标以便计算。
 *
 * @param {string} value 不含时区的日期或日期时间字符串
 * @param {boolean} dateOnly 是否仅校验纯日期
 * @returns {number|null} 用于日历计算的毫秒值，非法输入返回 null
 */
function parseWallTimeMilliseconds(value, dateOnly = false) {
  const match = typeof value === 'string' && value.match(dateOnly ? DATE_ONLY_PATTERN : WALL_TIME_PATTERN)
  if (!match) {
    return null
  }

  const [year, month, day, hour = 0, minute = 0, second = 0] = match.slice(1, 7).map(Number)
  const millisecond = Number((match[7] || '').padEnd(3, '0'))
  const date = new Date(0)
  date.setUTCFullYear(year, month - 1, day)
  date.setUTCHours(hour, minute, second, millisecond)

  // Date 会自动进位非法日期，逐项回读以拒绝越界输入。
  if (
    year < 1 ||
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day ||
    date.getUTCHours() !== hour ||
    date.getUTCMinutes() !== minute ||
    date.getUTCSeconds() !== second
  ) {
    return null
  }
  return date.getTime()
}

/**
 * 解析带偏移的真实时刻，拒绝无时区的日期时间。
 *
 * @param {string|Date} value RFC 3339 字符串或 Date 对象
 * @returns {number|null} Unix 毫秒时间戳，非法输入返回 null
 */
function parseInstantMilliseconds(value) {
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? value.getTime() : null
  }

  const match = typeof value === 'string' && value.match(RFC3339_PATTERN)
  if (!match || parseWallTimeMilliseconds(match[1]) === null) {
    return null
  }

  const result = Date.parse(`${match[1]}${(match[2] || '.000').slice(0, 4)}${match[3]}`)
  return Number.isFinite(result) ? result : null
}

/**
 * 计算指定时刻在目标时区的 UTC 偏移。
 *
 * @param {number} epoch Unix 毫秒时间戳
 * @param {string} timezoneName IANA 时区名称
 * @returns {number} 相对 UTC 的偏移分钟数
 */
function getTimezoneOffsetMinutes(epoch, timezoneName) {
  const parts = Object.fromEntries(
    getFormatter(timezoneName)
      .formatToParts(epoch)
      .map(part => [part.type, part.value])
  )
  const wallTime = `${parts.year.padStart(4, '0')}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
  const instantMilliseconds = Math.floor(epoch / MILLISECONDS_PER_SECOND) * MILLISECONDS_PER_SECOND
  return (parseWallTimeMilliseconds(wallTime) - instantMilliseconds) / MILLISECONDS_PER_MINUTE
}

/**
 * 按显式偏移创建业务时间，避免经过宿主机本地时区转换。
 *
 * @param {number} epoch Unix 毫秒时间戳
 * @param {string} timezoneName IANA 时区名称
 * @returns {import('dayjs').Dayjs} 目标时区下的日期时间
 */
function createZonedDateTime(epoch, timezoneName) {
  return dayjs.utc(epoch).utcOffset(getTimezoneOffsetMinutes(epoch, timezoneName))
}

/**
 * 格式化毫秒时间戳，兼容项目原有的日期格式占位符。
 *
 * @param {number} epoch Unix 毫秒时间戳
 * @param {string} pattern Day.js 格式或项目日期格式占位符
 * @param {string} timezoneName IANA 时区名称
 * @returns {string} 业务时间展示文本
 */
function formatEpoch(epoch, pattern, timezoneName) {
  const value = createZonedDateTime(epoch, timezoneName)
  const format = pattern
    .replaceAll('{y}', 'YYYY')
    .replaceAll('{m}', 'MM')
    .replaceAll('{d}', 'DD')
    .replaceAll('{h}', 'HH')
    .replaceAll('{i}', 'mm')
    .replaceAll('{s}', 'ss')
    .replaceAll('{a}', `[${WEEKDAYS[value.day()]}]`)
  return value.format(format)
}

/**
 * 将真实时刻格式化为业务时间。
 *
 * @param {string|Date} value RFC 3339 字符串或 Date 对象
 * @param {string} pattern 展示格式
 * @param {string} timezoneName 目标时区，默认使用当前用户展示时区
 * @returns {string|null} 展示文本，非法输入返回 null
 */
export function formatBusinessTime(value, pattern = 'YYYY-MM-DD HH:mm:ss', timezoneName = getDisplayTimezone()) {
  const epoch = parseInstantMilliseconds(value)
  return epoch === null ? null : formatEpoch(epoch, pattern, timezoneName)
}

/**
 * 格式化明确以毫秒为单位的 Unix 时间戳。
 *
 * @param {number} value Unix 毫秒时间戳
 * @param {string} pattern 展示格式
 * @param {string} timezoneName 目标时区，默认使用当前用户展示时区
 * @returns {string|null} 展示文本，非法输入返回 null
 */
export function formatEpochMilliseconds(value, pattern = 'YYYY-MM-DD HH:mm:ss', timezoneName = getDisplayTimezone()) {
  if (typeof value !== 'number' || !Number.isFinite(value) || !Number.isFinite(new Date(value).getTime())) {
    return null
  }
  return formatEpoch(value, pattern, timezoneName)
}

/**
 * 格式化明确以秒为单位的 Unix 时间戳。
 *
 * @param {number} value Unix 秒时间戳
 * @param {string} pattern 展示格式
 * @param {string} timezoneName 目标时区，默认使用当前用户展示时区
 * @returns {string|null} 展示文本，非法输入返回 null
 */
export function formatEpochSeconds(value, pattern, timezoneName) {
  return typeof value === 'number'
    ? formatEpochMilliseconds(value * MILLISECONDS_PER_SECOND, pattern, timezoneName)
    : null
}

/**
 * 查找业务当地时间对应的真实时刻候选值。
 *
 * @param {string} value 不含偏移的业务日期时间
 * @param {string} timezoneName IANA 时区名称
 * @returns {Array<{epoch: number, offset: string, value: string}>} 按时刻排序的候选值
 */
export function getWallTimeCandidates(value, timezoneName = getDisplayTimezone()) {
  const wallMilliseconds = parseWallTimeMilliseconds(value)
  if (wallMilliseconds === null) {
    throw new TimeInputError(`无效的日期时间: ${value}`, 'INVALID_TIME')
  }

  const offsets = new Set()
  // 采样跳转前后的偏移，覆盖半小时夏令时和跨日期变更。
  for (let hours = -48; hours <= 48; hours += 6) {
    offsets.add(getTimezoneOffsetMinutes(wallMilliseconds + hours * MILLISECONDS_PER_HOUR, timezoneName))
  }

  return [...offsets]
    .map(offset => ({ offset, epoch: wallMilliseconds - offset * MILLISECONDS_PER_MINUTE }))
    .filter(candidate => getTimezoneOffsetMinutes(candidate.epoch, timezoneName) === candidate.offset)
    .sort((first, second) => first.epoch - second.epoch)
    .map(candidate => ({
      epoch: candidate.epoch,
      offset: createZonedDateTime(candidate.epoch, timezoneName).format('Z'),
      value: createZonedDateTime(candidate.epoch, timezoneName).format('YYYY-MM-DDTHH:mm:ss.SSSZ')
    }))
}

/**
 * 将真实时刻或业务当地时间转换为毫秒精度 RFC 3339 字符串。
 *
 * @param {string|Date} value 原始时刻或业务日期时间
 * @param {Object} options 时区和重复时间的偏移选择
 * @param {string} options.timezoneName 业务 IANA 时区名称
 * @param {string} options.offset 夏令时重复时间使用的 UTC 偏移
 * @returns {string|undefined} RFC 3339 字符串，空输入返回 undefined
 * @throws {TimeInputError} 当地时间不存在或重复时间尚未选择偏移时抛出异常
 */
export function toRfc3339(value, { timezoneName = getDisplayTimezone(), offset } = {}) {
  if (value === undefined || value === null || value === '') {
    return undefined
  }

  const epoch = parseInstantMilliseconds(value)
  if (epoch !== null) {
    if (value instanceof Date) {
      return value.toISOString()
    }
    const match = value.match(RFC3339_PATTERN)
    return `${match[1]}.${(match[2]?.slice(1) || '').padEnd(3, '0').slice(0, 3)}${match[3]}`
  }

  const candidates = getWallTimeCandidates(value, timezoneName)
  if (!candidates.length) {
    throw new TimeInputError(`${value} 在 ${timezoneName} 不存在，请选择夏令时跳转后的有效时间`, 'DST_GAP')
  }
  if (candidates.length === 1) {
    return candidates[0].value
  }

  const selected = candidates.find(candidate => candidate.offset === offset)
  if (selected) {
    return selected.value
  }
  throw new TimeInputError(`${value} 在 ${timezoneName} 出现两次，请选择 UTC 偏移`, 'DST_FOLD', candidates)
}

/**
 * 将真实时刻转换为日期时间输入控件使用的业务时间。
 *
 * @param {string|Date} value 原始真实时刻
 * @param {string} timezoneName 业务 IANA 时区名称
 * @returns {string|null} 不含偏移的日期时间，非法输入返回 null
 */
export function toBusinessDateTimeInput(value, timezoneName = getDisplayTimezone()) {
  return formatBusinessTime(value, 'YYYY-MM-DD HH:mm:ss', timezoneName)
}

/**
 * 按字段语义规范化日期或精确时刻查询边界。
 *
 * @param {string|Date} value 日期或真实时刻
 * @returns {string|undefined} 纯日期或 RFC 3339 字符串，空输入返回 undefined
 */
export function normalizeRangeBoundary(value) {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  if (typeof value === 'string' && DATE_ONLY_PATTERN.test(value)) {
    if (parseWallTimeMilliseconds(value, true) === null) {
      throw new TimeInputError(`无效的日期: ${value}`, 'INVALID_DATE')
    }
    return value
  }
  return toRfc3339(value)
}

/**
 * 创建可编辑的业务时间字段，并保存原始时刻供无修改提交时使用。
 *
 * @param {Object} record API 返回的原始记录
 * @param {string[]} fields 需要转换的真实时刻字段
 * @param {string} timezoneName 业务 IANA 时区名称
 * @returns {Object} 包含业务时间和原值快照的新记录
 */
export function prepareTimeFields(record, fields, timezoneName = getDisplayTimezone()) {
  const result = { ...record }
  const originals = {}
  for (const field of fields) {
    if (!(field in record)) {
      continue
    }

    const original = record[field]
    const input = original == null || original === '' ? original : toBusinessDateTimeInput(original, timezoneName)
    if (input === null && original != null) {
      throw new TimeInputError(`字段 ${field} 包含无效的 RFC 3339 时间`, 'INVALID_TIME')
    }
    result[field] = input
    originals[field] = { original, input }
  }
  result[ORIGINAL_TIME_FIELDS] = { originals, timezoneName }
  return result
}

/**
 * 构造提交记录，保留未修改字段的原始毫秒和偏移。
 *
 * @param {Object} record 当前编辑记录
 * @param {string[]} fields 需要转换的真实时刻字段
 * @param {Object<string, string>} offsets 各重复时间字段选定的 UTC 偏移
 * @returns {Object} 可提交的新记录，不修改当前表单
 */
export function serializeTimeFields(record, fields, offsets = {}) {
  const result = { ...record }
  const state = record[ORIGINAL_TIME_FIELDS]
  delete result[ORIGINAL_TIME_FIELDS]

  for (const field of fields) {
    if (!(field in record)) {
      continue
    }

    const value = record[field]
    const original = state?.originals[field]
    if (original && value === original.input) {
      result[field] = original.original
    } else if (value == null) {
      result[field] = value
    } else if (value === '') {
      result[field] = null
    } else {
      try {
        result[field] = toRfc3339(value, {
          timezoneName: state?.timezoneName || getDisplayTimezone(),
          offset: offsets[field]
        })
      } catch (error) {
        error.field = field
        throw error
      }
    }
  }
  return result
}

/**
 * 逐项处理重复时间的偏移选择，再生成可提交记录。
 *
 * @param {Object} record 当前编辑记录
 * @param {string[]} fields 需要转换的真实时刻字段
 * @param {function(TimeInputError): Promise<string>} chooseOffset 请求用户选择偏移的回调
 * @returns {Promise<Object>} 已解决重复时间歧义的提交记录
 */
export async function resolveTimeFields(record, fields, chooseOffset) {
  const offsets = {}
  while (true) {
    try {
      return serializeTimeFields(record, fields, offsets)
    } catch (error) {
      if (error.code !== 'DST_FOLD') {
        throw error
      }
      const offset = await chooseOffset(error)
      if (!error.candidates.some(candidate => candidate.offset === offset)) {
        throw error
      }
      offsets[error.field] = offset
    }
  }
}

setBusinessTimezone(businessTimezone.value)
refreshDeviceTimezone()
