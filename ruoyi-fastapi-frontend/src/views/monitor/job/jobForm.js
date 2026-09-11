/** 校验并解析任务参数，保留JSON值类型 */
export function parseJobParameter(value, field) {
  const isArgs = field === 'jobArgs'
  const message = isArgs ? '位置参数必须是JSON数组，例如 ["test", 1]' : '关键字参数必须是JSON对象，例如 {"enabled": true}'
  let result
  try {
    result = JSON.parse(value)
  } catch {
    throw new Error(message)
  }
  if (isArgs ? !Array.isArray(result) : result === null || Array.isArray(result) || typeof result !== 'object') {
    throw new Error(message)
  }
  JSON.stringify(result, (_key, item) => {
    if (typeof item === 'number' && !Number.isFinite(item)) {
      throw new Error('参数中的数字超出可表示范围')
    }
    return item
  })
  return result
}

/** 将表单中的JSON文本转为接口数组和对象 */
export function buildJobPayload(form) {
  return {
    ...form,
    jobArgs: parseJobParameter(form.jobArgs, 'jobArgs'),
    jobKwargs: parseJobParameter(form.jobKwargs, 'jobKwargs')
  }
}
