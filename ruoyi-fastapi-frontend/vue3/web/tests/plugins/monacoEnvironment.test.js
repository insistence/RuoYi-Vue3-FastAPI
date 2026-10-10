import assert from 'node:assert/strict'

import createMonacoEnvironment from '../../vite/plugins/monaco-environment.js'

const plugin = createMonacoEnvironment()
const transform = plugin.transformIndexHtml.handler

const monacoHtml = `<!DOCTYPE html>
<html>
<head>
  <script>self["MonacoEnvironment"] = (function (paths) {
    return {
      globalAPI: false,
      getWorkerUrl: function (moduleId, label) {
        return paths[label]
      }
    }
  })({
    "editorWorkerService": "/monacoeditorwork/editor.worker..bundle.js"
  });</script>
  <meta charset="utf-8">
</head>
</html>`

const transformedHtml = transform(monacoHtml)

assert.match(transformedHtml, /<script type="module" src="\/monaco-environment\.js"><\/script>/)
assert.doesNotMatch(transformedHtml, /self\["MonacoEnvironment"\]/)
assert.match(transformedHtml, /<meta charset="utf-8">/)

const unchangedHtml = '<!DOCTYPE html><html><head><meta charset="utf-8"></head></html>'
assert.equal(transform(unchangedHtml), unchangedHtml)
