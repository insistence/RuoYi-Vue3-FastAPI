let loading

/** 按需加载站点自带的 Monaco 编辑器与 JSON 语言服务。 */
export function loadMonaco() {
  if (loading) return loading
  loading = new Promise((resolve, reject) => {
    const base = `${process.env.BASE_URL}monaco-json/vs`
    const start = () => {
      window.require.config({ paths: { vs: base } })
      window.require(['vs/editor/editor.main'], () => resolve(window.monaco), reject)
    }
    if (window.require && window.require.config) {
      start()
      return
    }
    const script = document.createElement('script')
    script.src = `${base}/loader.js`
    script.onload = start
    script.onerror = () => {
      script.remove()
      reject(new Error('编辑器资源加载失败'))
    }
    document.head.appendChild(script)
  }).catch((error) => {
    loading = null
    throw error
  })
  return loading
}
