import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compileFunction } from 'node:vm'
import { compileScript, parse } from 'vue/compiler-sfc'
import { splitRegisteredUris } from '../../src/utils/oauthUri.js'

// 执行真实组件的表单转换，覆盖从后台详情重新打开后切换授权方式的场景。
const source = readFileSync(
  new URL('../../src/views/system/oauth/client/index.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const { scriptSetupAst } = compileScript(descriptor, { id: 'client-form-regression' })
const functions = scriptSetupAst
  .filter(
    (node) =>
      node.type === 'FunctionDeclaration' &&
      ['emptyForm', 'toEditor', 'payload'].includes(node.id.name)
  )
  .map((node) => descriptor.scriptSetup.content.slice(node.start, node.end))
  .join('\n')
const { form, toEditor, payload } = compileFunction(
  `${functions}\nconst form = emptyForm(); return { form, toEditor, payload };`,
  ['splitRegisteredUris']
)(splitRegisteredUris)

Object.assign(
  form,
  toEditor({
    clientId: 'machine-client',
    clientName: '服务应用',
    clientType: 'confidential',
    tokenEndpointAuthMethod: 'client_secret_basic',
    grantTypes: ['client_credentials'],
    responseTypes: [],
    scopeCodes: ['openid'],
  })
)
form.grantTypes.push('authorization_code')
form.redirectUris = ['https://app.example/callback']
const withLogin = payload()
assert.deepEqual(withLogin.responseTypes, ['code'])
assert.deepEqual(withLogin.grantTypes, ['client_credentials', 'authorization_code'])
assert.deepEqual(withLogin.redirectUris, ['https://app.example/callback'])

Object.assign(form, toEditor(withLogin))
form.grantTypes = ['client_credentials']
assert.deepEqual(payload().responseTypes, [])
form.grantTypes = ['authorization_code', 'refresh_token']
assert.deepEqual(payload().responseTypes, ['code'])
