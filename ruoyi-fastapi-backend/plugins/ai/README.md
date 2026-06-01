# AI backend plugin

AI backend plugin for model management and chat.

It keeps the original API prefixes, menu permissions, and provider dictionary behavior:

- `/ai/model`
- `/ai/chat`
- `ai:model:*`
- `ai:chat:list`
- `ai_provider_type`

The plugin is disabled by default in `plugin.yaml`.
Install or check plugin dependencies before enabling it in a fresh environment.

## Files

- `plugin.yaml`: backend manifest, dependency declaration, menu declaration, migration declaration, and seed declaration.
- `controller/`: FastAPI controllers auto-scanned when the plugin is enabled.
- `service/`, `dao/`, `entity/`: AI business code migrated from the old module.
- `migrations/mysql/001_init.sql`, `migrations/postgresql/001_init.sql`: AI plugin table schema.
- `seeds/mysql/ai_provider_type.sql`, `seeds/postgresql/ai_provider_type.sql`: idempotent provider dictionary seeds executed by `ruoyi plugin install ai`.

## Commands

```bash
ruoyi plugin check ai --env=dev
ruoyi plugin install ai --env=dev --yes
ruoyi plugin disable ai --env=dev --yes
ruoyi plugin enable ai --env=dev --yes
```

`plugin check` verifies dependency declarations, plugin structure, frontend views, and menu conflicts.
Python and npm dependencies are declared by `plugin.yaml` and installed through the plugin dependency workflow.
