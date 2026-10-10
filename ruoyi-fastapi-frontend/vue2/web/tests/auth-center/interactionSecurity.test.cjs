const assert = require('node:assert/strict')
const { loadModule } = require('../support/load-module.cjs')

const { interactionRouteLocation, readInteractionCsrf, trustedCompletionUrl } = loadModule(
  require('node:path').resolve(__dirname, '../../src/views/auth-center/interactionSecurity.js')
)

assert.equal(readInteractionCsrf('#csrf=token%2Bvalue&ignored=1'), 'token+value')
assert.equal(readInteractionCsrf('#ignored=1'), '')
assert.equal(readInteractionCsrf(null), '')
assert.equal(
  interactionRouteLocation('/auth-center/login', 'id/with space'),
  '/auth-center/login?interaction=id%2Fwith%20space'
)

const origin = 'https://auth.example.com'
const interactionId = 'interaction-1'
assert.equal(
  trustedCompletionUrl('/auth/interaction/interaction-1/complete', origin, interactionId)?.origin,
  origin
)
assert.equal(trustedCompletionUrl('https://evil.example/complete', origin, interactionId), null)
assert.equal(trustedCompletionUrl('/auth/interaction/other/complete', origin, interactionId), null)
assert.equal(
  trustedCompletionUrl('/auth/interaction/interaction-1/complete.evil', origin, interactionId),
  null
)
