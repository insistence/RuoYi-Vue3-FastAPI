# AI frontend plugin

AI frontend plugin migrated from `src/api/ai` and `src/views/ai`.

Backend menu component paths map to these pages:

```text
plugin/ai/model/index -> plugins/ai/views/model/index.vue
plugin/ai/chat/index -> plugins/ai/views/chat/index.vue
```

## Files

- `api/model.js`: AI model API client.
- `api/chat.js`: AI chat API client.
- `views/model/index.vue`: model management page.
- `views/chat/index.vue`: AI chat page.
- `views/chat/components/AiMessage.vue`: chat message component.

Frontend paths, menu components, and npm dependencies are declared by the backend `plugins/ai/plugin.yaml`.

## Verification

```bash
npm run test:plugin
npm run build:prod
```
