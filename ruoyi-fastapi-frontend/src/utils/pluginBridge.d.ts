export const PLUGIN_BRIDGE_NAMESPACE: 'ruoyi.plugin'
export const PLUGIN_BRIDGE_VERSION: 1
export const PLUGIN_BRIDGE_MAX_BYTES: number
export const PLUGIN_BRIDGE_MAX_PENDING: number
export const PLUGIN_BRIDGE_MAX_FILE_BYTES: number
export const PLUGIN_BRIDGE_MAX_STREAMS: number
export const PLUGIN_BRIDGE_MAX_STREAM_BYTES: number
export const PLUGIN_BRIDGE_STREAM_TIMEOUT: number

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue }
export type PluginMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS'
export interface PluginRequest {
  method: PluginMethod
  path: string
  params?: Record<string, JsonValue>
  data?: JsonValue
}
export interface PluginProgress {
  phase: 'upload' | 'download'
  loaded: number
  /** 未提供响应长度时为 null，不应显示虚假的百分比。 */
  total: number | null
}
export interface PluginRequestOptions {
  signal?: AbortSignal
  onProgress?: (event: PluginProgress) => void
}
export interface PluginStreamRequest {
  path: string
  params?: Record<string, JsonValue>
  lastEventId?: string
}
export interface PluginStreamEvent {
  event: string
  data: string
  id: string
}
export interface PluginStreamOptions {
  signal?: AbortSignal
  /** 返回的 Promise 完成后才接收下一条事件；拒绝时关闭连接。 */
  onEvent(event: PluginStreamEvent): void | Promise<void>
}
export interface PluginUpload {
  path: string
  file: Blob
  method?: 'POST' | 'PUT' | 'PATCH'
  filename?: string
  fieldName?: string
  fields?: Record<string, string>
  params?: Record<string, JsonValue>
}
export interface PluginContext {
  clientId: string
  uiBase: string
  apiBase: string
  theme?: { mode?: string; [key: string]: JsonValue | undefined }
  language?: string
  timeZone?: string
  route?: string
  capabilities?: {
    files?: { version: 1; maxBytes: number }
    streams?: {
      version: 1
      maxConcurrent: number
      maxEventBytes: number
      maxBytes: number
      maxDurationMs: number
    }
  }
}
export interface PluginClientOptions {
  pluginId: string
  eventTarget?: Window
  parentWindow?: Window
  origin?: string
  timeoutMs?: number
  transferTimeoutMs?: number
  streamTimeoutMs?: number
}
export interface PluginClient {
  ready: Promise<PluginContext>
  readonly context: PluginContext | null
  request<T = JsonValue>(payload: PluginRequest, options?: PluginRequestOptions): Promise<T>
  upload<T = JsonValue>(payload: PluginUpload, options?: PluginRequestOptions): Promise<T>
  download(
    payload: Omit<PluginRequest, 'method'> & { method?: PluginMethod },
    options?: PluginRequestOptions
  ): Promise<Blob>
  /** 正常 EOF 完成；取消、超时、回调失败和传输失败均拒绝。不会自动重连。 */
  stream(payload: PluginStreamRequest, options: PluginStreamOptions): Promise<void>
  navigate(route: string): void
  subscribe(
    handler: (event: {
      type: 'initialize' | 'preferences' | 'route' | 'refresh' | 'logout'
      payload: Partial<PluginContext>
    }) => void
  ): () => void
  destroy(message?: string): void
}
export interface PluginSession {
  pluginId: string
  bridgeVersion: 1
  uiBase: string
  apiBase: string
  csrfToken: string
  expiresIn: number
  expiresAt: number
}
export function createPluginClient(options: PluginClientOptions): PluginClient
export function validatePluginId(pluginId: string): string
export function normalizePluginBase(base?: string): string
export function validatePluginApiPath(path: string): string
export function validatePluginRoute(route: string): string
export function validatePluginSession(
  value: unknown,
  pluginId: string,
  base?: string,
  now?: number
): PluginSession
export function createPluginHostBridge(options: {
  pluginId: string
  session: PluginSession
  getTarget(): Window | null
  request(config: Record<string, unknown>): Promise<unknown>
  stream?(config: {
    url: string
    params?: Record<string, JsonValue>
    lastEventId?: string
    csrfToken: string
    signal: AbortSignal
  }): AsyncIterable<PluginStreamEvent>
  getContext?(): Partial<PluginContext>
  onReady?(): void
  onRoute?(route: string): void
  onDisconnect?(message: string): void
  eventTarget?: Window
  origin?: string
  now?(): number
  timeoutMs?: number
  transferTimeoutMs?: number
  streamTimeoutMs?: number
}): {
  setSession(session: PluginSession): void
  updatePreferences(): void
  updateRoute(route: string): void
  refresh(): void
  destroy(options?: { logout?: boolean }): void
}
