import assert from 'node:assert/strict'

// 最小 bridge v1 JSON 宿主协议夹具，不是历史宿主实现的源码快照。
// 固定旧消息形状；可传入未知能力版本，验证新客户端不会据此发起未协商请求。
export function createJsonOnlyHost({ hostWindow, childWindow, origin, capabilities }) {
  const instance = 'json-host-protocol-v1'
  const calls = []
  const send = (type, payload, id) => {
    childWindow.postMessage(
      {
        namespace: 'ruoyi.plugin',
        version: 1,
        pluginId: 'demo',
        type,
        instance,
        payload,
        ...(id === undefined ? {} : { id }),
      },
      origin
    )
  }
  const listener = (event) => {
    assert.equal(event.origin, origin)
    assert.equal(event.source, childWindow)
    const message = event.data
    assert.equal(message.namespace, 'ruoyi.plugin')
    assert.equal(message.version, 1)
    assert.equal(message.pluginId, 'demo')
    assert.ok(
      Object.keys(message).every((key) =>
        ['namespace', 'version', 'pluginId', 'type', 'instance', 'payload', 'id'].includes(key)
      )
    )
    if (message.type === 'ready') {
      assert.equal(message.instance, '')
      assert.deepEqual(Object.keys(message.payload), ['clientId'])
      send('initialize', {
        clientId: message.payload.clientId,
        uiBase: '/apps/demo/ui/',
        apiBase: '/apps/demo/api/',
        ...(capabilities === undefined ? {} : { capabilities }),
      })
      return
    }
    assert.equal(message.instance, instance)
    if (message.type === 'cancel') return
    calls.push(message)
    send(
      'result',
      message.type === 'request'
        ? { ok: true, data: { accepted: message.payload } }
        : { ok: false, message: 'JSON 协议夹具不支持该请求' },
      message.id
    )
  }
  hostWindow.addEventListener('message', listener)
  return {
    calls,
    destroy: () => hostWindow.removeEventListener('message', listener),
  }
}
