import axios from 'axios'
import { ElLoading, ElMessage } from 'element-plus'
import { saveAs } from 'file-saver'
import { getToken } from '@/utils/auth'
import errorCode from '@/utils/errorCode'
import { blobValidate } from '@/utils/ruoyi'

const baseURL = import.meta.env.VITE_APP_BASE_API
const DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024
const DOWNLOAD_CHUNK_RETRY_COUNT = 2
let downloadLoadingInstance;

function parseContentRange(contentRange) {
  const rangeMatch = /^bytes (\d+)-(\d+)\/(\d+)$/i.exec(contentRange || '')
  if (!rangeMatch) {
    throw new Error('分段下载响应缺少有效的Content-Range')
  }
  return {
    start: Number(rangeMatch[1]),
    end: Number(rangeMatch[2]),
    total: Number(rangeMatch[3])
  }
}

function isRetryableDownloadError(error) {
  return !error.response || error.response.status >= 500
}

async function requestDownloadChunk(url, start) {
  let lastError
  for (let retryCount = 0; retryCount <= DOWNLOAD_CHUNK_RETRY_COUNT; retryCount++) {
    try {
      return await axios({
        method: 'get',
        url,
        responseType: 'blob',
        headers: {
          'Authorization': 'Bearer ' + getToken(),
          'Range': `bytes=${start}-${start + DOWNLOAD_CHUNK_SIZE - 1}`
        }
      })
    } catch (error) {
      lastError = error
      if (!isRetryableDownloadError(error) || retryCount === DOWNLOAD_CHUNK_RETRY_COUNT) {
        throw error
      }
    }
  }
  throw lastError
}

function requestFullDownload(url) {
  return axios({
    method: 'get',
    url,
    responseType: 'blob',
    headers: { 'Authorization': 'Bearer ' + getToken() }
  })
}

async function downloadByRange(url) {
  const chunks = []
  let filename
  let contentType
  let nextStart = 0

  while (true) {
    let response
    try {
      response = await requestDownloadChunk(url, nextStart)
    } catch (error) {
      if (nextStart !== 0 || error.response?.status !== 416) {
        throw error
      }
      response = await requestFullDownload(url)
    }
    if (!blobValidate(response.data)) {
      return { errorData: response.data }
    }

    filename = filename || response.headers['download-filename']
    contentType = contentType || response.data.type
    if (response.status !== 206) {
      return {
        blob: new Blob([response.data], { type: contentType }),
        filename
      }
    }

    const contentRange = parseContentRange(response.headers['content-range'])
    if (
      contentRange.start !== nextStart ||
      contentRange.end < contentRange.start ||
      contentRange.total <= contentRange.end ||
      response.data.size !== contentRange.end - contentRange.start + 1
    ) {
      throw new Error('分段下载响应范围不一致')
    }
    chunks.push(response.data)
    if (contentRange.end + 1 === contentRange.total) {
      return {
        blob: new Blob(chunks, { type: contentType }),
        filename
      }
    }
    nextStart = contentRange.end + 1
  }
}

export default {
  name(name, isDelete = true) {
    var url = baseURL + "/common/download?fileName=" + encodeURIComponent(name) + "&delete=" + isDelete
    axios({
      method: 'get',
      url: url,
      responseType: 'blob',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    }).then((res) => {
      const isBlob = blobValidate(res.data);
      if (isBlob) {
        const blob = new Blob([res.data])
        this.saveAs(blob, decodeURIComponent(res.headers['download-filename']))
      } else {
        this.printErrMsg(res.data);
      }
    })
  },
  async resource(resource) {
    var url = baseURL + "/common/download/resource?resource=" + encodeURIComponent(resource);
    try {
      const result = await downloadByRange(url)
      if (result.errorData) {
        await this.printErrMsg(result.errorData)
        return
      }
      this.saveAs(result.blob, decodeURIComponent(result.filename))
    } catch (error) {
      console.error(error)
      ElMessage.error('下载文件出现错误，请联系管理员！')
    }
  },
  async file(resource) {
    var url = baseURL + resource;
    try {
      const result = await downloadByRange(url)
      if (result.errorData) {
        await this.printErrMsg(result.errorData)
        return
      }
      const fallbackFileName = resource.split('/').pop();
      this.saveAs(result.blob, result.filename ? decodeURIComponent(result.filename) : fallbackFileName)
    } catch (error) {
      console.error(error)
      ElMessage.error('下载文件出现错误，请联系管理员！')
    }
  },
  zip(url, name) {
    var url = baseURL + url
    downloadLoadingInstance = ElLoading.service({ text: "正在下载数据，请稍候", background: "rgba(0, 0, 0, 0.7)", })
    axios({
      method: 'get',
      url: url,
      responseType: 'blob',
      headers: { 'Authorization': 'Bearer ' + getToken() }
    }).then((res) => {
      const isBlob = blobValidate(res.data);
      if (isBlob) {
        const blob = new Blob([res.data], { type: 'application/zip' })
        this.saveAs(blob, name)
      } else {
        this.printErrMsg(res.data);
      }
      downloadLoadingInstance.close();
    }).catch((r) => {
      console.error(r)
      ElMessage.error('下载文件出现错误，请联系管理员！')
      downloadLoadingInstance.close();
    })
  },
  saveAs(text, name, opts) {
    saveAs(text, name, opts);
  },
  async printErrMsg(data) {
    const resText = await data.text();
    const rspObj = JSON.parse(resText);
    const errMsg = errorCode[rspObj.code] || rspObj.msg || errorCode['default']
    ElMessage.error(errMsg);
  }
}

