# 插件 Migration 故障处理手册

## 适用场景

本手册用于处理插件安装、升级过程中 `migration` 执行失败或中断的问题。

插件 migration 采用显式状态记录，不承诺自动回滚 MySQL DDL。平台会保留执行历史，并通过状态阻断不安全的自动重跑。

## 状态说明

| 状态 | 含义 | 处理方式 |
| --- | --- | --- |
| `success` | migration 已成功执行 | checksum 一致时自动跳过；checksum 变化时必须新增 migration 文件 |
| `failed` | migration 执行失败并记录错误 | 修复脚本幂等性或数据库结构后可重试 |
| `running` | 已开始执行但未记录成功或失败 | 人工确认数据库结构后标记 success 或 failed |
| `unknown` | 平台无法判断状态 | 人工核查后标记为明确状态 |

## 常见处理流程

### running 状态

1. 查看 migration 历史。
   - CLI: `ruoyi plugin migration-list <plugin_id> --status running`
   - Web: 插件管理页打开插件详情，在“依赖 / 执行历史”中查看。
2. 检查数据库结构是否已经按 migration 完成。
3. 如果已完成，标记成功。
   - CLI: `ruoyi plugin mark-success <plugin_id> <migration_path> --note "已人工确认结构完成"`
   - Web: 点击执行历史中的“标记成功”。
4. 如果未完成，标记失败。
   - CLI: `ruoyi plugin mark-failed <plugin_id> <migration_path> --note "未完成，允许修复后重试"`
   - Web: 点击执行历史中的“标记失败”。
5. 修复 migration 幂等性或数据库结构后重新执行安装/升级。

### failed 状态

1. 查看错误信息和 `attempt_count`。
2. 修复 migration 脚本，保证重复执行安全。
3. 重新执行安装或升级。
4. 如果已通过人工方式完成结构变更，可标记成功。

### checksum 变化

已成功执行的 migration 文件不能修改。

处理方式:

- 恢复原 migration 文件内容；或
- 新增一个后续 migration 文件承载变更。

## 插件作者约束

- SQL migration 应尽量拆小，避免单个文件包含大量不可回滚 DDL。
- migration 必须可幂等重试，尤其是 `ALTER TABLE`、索引、初始化数据。
- seed 和 hook 也应可重复执行，不依赖外层事务自动撤销副作用。
- 不要通过修改已发布 migration 文件修正历史变更。

## 观测字段

`sys_plugin_migration` 会记录:

- `status`: 当前执行状态。
- `attempt_count`: 尝试次数。
- `started_time`: 最近开始时间。
- `finished_time`: 最近结束时间。
- `update_time`: 最近状态更新时间。
- `error_message`: 最近失败错误。

生命周期返回 payload 中的 `migrations` 会包含 `status` 和 `duration_ms`。当 migration 失败或中断需要人工处理时，payload 会包含 `migrationRecovery`，用于展示 migration 路径、状态和恢复建议。
