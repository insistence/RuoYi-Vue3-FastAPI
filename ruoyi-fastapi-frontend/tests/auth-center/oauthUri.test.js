import assert from 'node:assert/strict'

import {
  splitRegisteredUris,
  validateRegisteredUri,
  validateRegisteredUriList
} from '../../src/utils/oauthUri.js'

assert.deepEqual(splitRegisteredUris('https://one.example/cb,\nhttps://two.example/cb'), [
  'https://one.example/cb',
  'https://two.example/cb'
])
assert.equal(
  validateRegisteredUri('https://portal.example/callback?tenant=one', 'redirect'),
  'https://portal.example/callback?tenant=one'
)
assert.equal(validateRegisteredUri('http://localhost:8080/callback', 'redirect'), 'http://localhost:8080/callback')
assert.equal(validateRegisteredUri('https://portal.example', 'cors_origin'), 'https://portal.example')
assert.equal(validateRegisteredUri('https://portal.example:443', 'cors_origin'), 'https://portal.example:443')
assert.throws(() => validateRegisteredUri('http://portal.example/callback', 'redirect'), /本地开发/)
assert.throws(() => validateRegisteredUri('https://user@portal.example/callback', 'redirect'), /用户信息/)
assert.throws(() => validateRegisteredUri('https://portal.example/callback#fragment', 'redirect'), /Fragment/)
assert.throws(() => validateRegisteredUri('https://portal.example/logout?token=1', 'backchannel_logout'), /查询参数/)
assert.throws(() => validateRegisteredUri('https://portal.example/', 'cors_origin'), /协议、主机和端口/)
assert.throws(() => validateRegisteredUriList('', 'redirect', true), /至少填写/)
