from cli.utils import SHELL_TEXT_FORMATTER


class PluginCommandPresenter:
    """
    插件命令文本渲染器。
    """

    def build_list_text(self, payload: dict[str, object]) -> str:
        """
        将插件列表负载渲染为文本。

        :param payload: 插件列表负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'count: {payload.get("count", 0)}',
        ]
        if 'databaseAvailable' in payload:
            database_available = bool(payload.get('databaseAvailable', False))
            lines.append(f'database_available: {str(database_available).lower()}')
            if not database_available:
                database_error = SHELL_TEXT_FORMATTER.truncate_text(payload.get('databaseError', '') or '', 120)
                lines.append(f'database_error: {database_error or "-"}')
        plugins = payload.get('plugins')
        if not isinstance(plugins, list) or not plugins:
            lines.append('plugins: none')
            return '\n'.join(lines)

        lines.append('plugins:')
        lines.extend(self._build_plugin_summary_line(plugin) for plugin in plugins if isinstance(plugin, dict))
        return '\n'.join(lines)

    def build_info_text(self, payload: dict[str, object]) -> str:
        """
        将插件详情负载渲染为文本。

        :param payload: 插件详情负载
        :return: 文本输出
        """
        plugin = payload.get('plugin')
        if not isinstance(plugin, dict):
            return '\n'.join(
                [
                    f'ok: {str(payload.get("ok", False)).lower()}',
                    f'message: {payload.get("message", "-")}',
                ]
            )

        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'plugin_id: {plugin.get("pluginId", "-")}',
            f'name: {plugin.get("name", "-")}',
            f'version: {plugin.get("version", "-")}',
            f'installed_version: {plugin.get("installedVersion", "-") or "-"}',
            f'runtime_enabled: {str(plugin.get("runtimeEnabled", False)).lower()}',
            f'status: {plugin.get("status", "-")}',
            f'source: {plugin.get("source", "-")}',
            f'last_error: {SHELL_TEXT_FORMATTER.truncate_text(plugin.get("lastError", "") or "", 100) or "-"}',
            f'description: {SHELL_TEXT_FORMATTER.truncate_text(plugin.get("description", ""), 100)}',
            f'backend_path: {SHELL_TEXT_FORMATTER.truncate_text(plugin.get("backendPath", ""), 120)}',
            f'frontend_path: {SHELL_TEXT_FORMATTER.truncate_text(plugin.get("frontendPath", "") or "", 120) or "-"}',
            f'menu_count: {plugin.get("menuCount", 0)}',
            f'permission_count: {plugin.get("permissionCount", 0)}',
        ]
        database = plugin.get('database')
        if isinstance(database, dict):
            lines.append(f'database_available: {str(database.get("available", False)).lower()}')
            lines.append(f'database_installed: {str(database.get("installed", False)).lower()}')
            if 'configuredEnabled' in database:
                lines.append(f'configured_enabled: {str(database.get("configuredEnabled", False)).lower()}')
        dependencies = plugin.get('dependencies')
        if isinstance(dependencies, list):
            lines.append(f'dependencies: {len(dependencies)}')
            lines.extend(self._build_dependency_lines(dependencies))

        return '\n'.join(lines)

    def build_check_text(self, payload: dict[str, object]) -> str:
        """
        将插件检查负载渲染为文本。

        :param payload: 插件检查负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'count: {payload.get("count", 0)}',
        ]
        checks = payload.get('checks')
        if not isinstance(checks, list) or not checks:
            lines.append('checks: none')
            return '\n'.join(lines)

        lines.append('checks:')
        lines.extend(self._build_check_summary_line(check) for check in checks if isinstance(check, dict))
        return '\n'.join(lines)

    def build_dependency_text(self, payload: dict[str, object]) -> str:
        """
        将插件依赖检查负载渲染为文本。

        :param payload: 插件依赖检查负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'dependency_ok: {str(payload.get("dependencyOk", False)).lower()}',
        ]
        dependencies = payload.get('dependencies')
        if isinstance(dependencies, list):
            lines.append(f'dependencies: {len(dependencies)}')
            lines.extend(self._build_dependency_lines(dependencies))
        else:
            lines.append('dependencies: none')

        return '\n'.join(lines)

    def build_precheck_text(self, payload: dict[str, object]) -> str:
        """
        将插件操作预检负载渲染为文本。

        :param payload: 插件操作预检负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'operation: {payload.get("operation", "-")}',
            f'dependency_ok: {str(payload.get("dependencyOk", False)).lower()}',
            f'plugin_dependency_ok: {str(payload.get("pluginDependencyOk", False)).lower()}',
            f'structure_ok: {str(payload.get("structureOk", False)).lower()}',
            f'menu_conflict_ok: {str(payload.get("menuConflictOk", False)).lower()}',
            f'database_available: {str(payload.get("databaseAvailable", False)).lower()}',
        ]
        actions = payload.get('actions')
        lines.append(f'actions: {len(actions) if isinstance(actions, list) else 0}')
        precheck = payload.get('precheck')
        if isinstance(precheck, dict):
            lines.append(f'dependencies: {len(precheck.get("dependencies", []))}')
            lines.append(f'structure_errors: {len(precheck.get("structureErrors", []))}')
            lines.append(f'menu_conflicts: {len(precheck.get("menuConflicts", []))}')

        return '\n'.join(lines)

    def build_health_text(self, payload: dict[str, object]) -> str:
        """
        将插件健康检查负载渲染为文本。

        :param payload: 插件健康检查负载
        :return: 文本输出
        """
        health = payload.get('health')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
        ]
        if not isinstance(health, dict):
            return '\n'.join(lines)

        lines.extend(
            [
                f'status: {health.get("status", "-")}',
                f'checker: {health.get("checker", "-") or "-"}',
                f'duration_ms: {health.get("durationMs", 0)}',
            ]
        )
        if health.get('error'):
            lines.append(f'error: {SHELL_TEXT_FORMATTER.truncate_text(health.get("error", ""), 120)}')
        details = health.get('details')
        if isinstance(details, dict):
            lines.append(f'details: {len(details)}')

        return '\n'.join(lines)

    def build_diagnose_text(self, payload: dict[str, object]) -> str:
        """
        将插件诊断包负载渲染为文本。

        :param payload: 插件诊断包负载
        :return: 文本输出
        """
        info = payload.get('info')
        check = payload.get('check')
        menu_plan = payload.get('menuPlan')
        config = payload.get('config')
        audit = payload.get('audit')
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
        ]
        if isinstance(info, dict):
            lines.append(f'status: {info.get("status", "-")}')
            lines.append(f'installed_version: {info.get("installedVersion", "-") or "-"}')
            lines.append(
                f'last_error: {SHELL_TEXT_FORMATTER.truncate_text(info.get("lastError", "") or "", 100) or "-"}'
            )
        if isinstance(check, dict):
            checks = check.get('checks')
            check_items = checks if isinstance(checks, list) else []
            first_check = check_items[0] if check_items and isinstance(check_items[0], dict) else {}
            lines.append(f'check_ok: {str(check.get("ok", False)).lower()}')
            lines.append(f'dependency_count: {len(first_check.get("dependencies", [])) if first_check else 0}')
            lines.append(f'structure_errors: {len(first_check.get("structureErrors", [])) if first_check else 0}')
            lines.append(f'menu_conflicts: {len(first_check.get("menuConflicts", [])) if first_check else 0}')
        if isinstance(menu_plan, dict):
            lines.append(
                f'menu_plan: total={menu_plan.get("total", 0)} | '
                f'permissions={menu_plan.get("permissionCount", 0)} | '
                f'enabled={menu_plan.get("enabledCount", 0)}'
            )
        if isinstance(config, dict):
            configs = config.get('configs')
            lines.append(f'configs: {len(configs) if isinstance(configs, list) else 0}')
            summary = config.get('summary')
            if isinstance(summary, dict):
                lines.append(
                    f'config_summary: total={summary.get("total", 0)} | '
                    f'secret={summary.get("secretCount", 0)} | '
                    f'missing_required={summary.get("missingRequiredCount", 0)}'
                )
        if isinstance(audit, dict):
            lines.append(f'audit_available: {str(audit.get("available", False)).lower()}')
        if payload.get('outputFile'):
            lines.append(f'output_file: {payload.get("outputFile")}')
            lines.append(f'exported: {str(payload.get("exported", False)).lower()}')

        return '\n'.join(lines)

    def build_docs_text(self, payload: dict[str, object]) -> str:
        """
        将插件文档生成负载渲染为文本。

        :param payload: 插件文档生成负载
        :return: 文本输出
        """
        if payload.get('ok') and isinstance(payload.get('markdown'), str) and not payload.get('outputFile'):
            return str(payload.get('markdown', ''))

        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'format: {payload.get("format", "-")}',
            f'length: {payload.get("length", 0)}',
        ]
        if payload.get('outputFile'):
            lines.append(f'output_file: {payload.get("outputFile")}')
            lines.append(f'exported: {str(payload.get("exported", False)).lower()}')

        return '\n'.join(lines)

    def build_test_text(self, payload: dict[str, object]) -> str:
        """
        将插件测试负载渲染为文本。

        :param payload: 插件测试负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'keyword: {payload.get("keyword", "") or "-"}',
            f'maxfail: {payload.get("maxfail", 0)}',
            f'quiet: {str(payload.get("quiet", False)).lower()}',
            f'frontend_build: {str(payload.get("frontendBuild", False)).lower()}',
        ]
        targets = payload.get('targets')
        if isinstance(targets, list):
            lines.append(f'targets: {len(targets)}')
            lines.extend(f'  - {target}' for target in targets)
        command = payload.get('command')
        if isinstance(command, list):
            lines.append(f'command: {" ".join(str(item) for item in command)}')
        results = payload.get('results')
        if isinstance(results, list):
            lines.append(f'results: {len(results)}')
            for item in results:
                if not isinstance(item, dict):
                    continue
                test_result = item.get('test') if isinstance(item.get('test'), dict) else {}
                lines.append(
                    f'  - {item.get("kind", "-")}: {item.get("target", "-")} [{test_result.get("returnCode", "-")}]'
                )
        test_payload = payload.get('test')
        if isinstance(test_payload, dict):
            lines.append(f'return_code: {test_payload.get("returnCode", "-")}')
            stdout = str(test_payload.get('stdout', '') or '').strip()
            stderr = str(test_payload.get('stderr', '') or '').strip()
            if stdout:
                lines.append(f'stdout: {SHELL_TEXT_FORMATTER.truncate_text(stdout, 300)}')
            if stderr:
                lines.append(f'stderr: {SHELL_TEXT_FORMATTER.truncate_text(stderr, 300)}')

        return '\n'.join(lines)

    def build_dependency_install_text(self, payload: dict[str, object]) -> str:
        """
        将插件依赖安装负载渲染为文本。

        :param payload: 插件依赖安装负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'plan_count: {payload.get("planCount", 0)}',
        ]
        plan = payload.get('plan')
        if isinstance(plan, list) and plan:
            lines.append('plan:')
            lines.extend(self._build_dependency_plan_line(item) for item in plan if isinstance(item, dict))
        else:
            lines.append('plan: none')

        results = payload.get('results')
        if isinstance(results, list):
            lines.append(f'results: {len(results)}')
        policy = payload.get('policy')
        if isinstance(policy, dict):
            lines.extend(
                [
                    f'policy_mode: {policy.get("mode", "-")}',
                    f'policy_allowed: {str(policy.get("allowed", False)).lower()}',
                ]
            )
            reasons = policy.get('reasons')
            if isinstance(reasons, list) and reasons:
                lines.append('policy_reasons:')
                lines.extend(f'  - {reason}' for reason in reasons)
            requirements = policy.get('requirements')
            if isinstance(requirements, list) and requirements:
                lines.append('policy_requirements:')
                lines.extend(f'  - {requirement}' for requirement in requirements)

        return '\n'.join(lines)

    def build_dependency_lock_text(self, payload: dict[str, object]) -> str:
        """
        将插件依赖锁文件模板负载渲染为文本。

        :param payload: 插件依赖锁文件模板负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'output_file: {payload.get("outputFile", "-")}',
            f'written: {str(payload.get("written", False)).lower()}',
            f'overwritten: {str(payload.get("overwritten", False)).lower()}',
            f'entry_count: {payload.get("entryCount", 0)}',
            f'artifact_count: {payload.get("artifactCount", 0)}',
        ]
        warnings = payload.get('warnings')
        if isinstance(warnings, list) and warnings:
            lines.append('warnings:')
            lines.extend(f'  - {warning}' for warning in warnings)
        return '\n'.join(lines)

    def build_dependency_allowlist_example_text(self, payload: dict[str, object]) -> str:
        """
        将插件依赖允许列表示例负载渲染为文本。

        :param payload: 插件依赖允许列表示例负载
        :return: 文本输出
        """
        if payload.get('ok') and isinstance(payload.get('allowlist'), str) and payload.get('dryRun'):
            return str(payload.get('allowlist', ''))

        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'message: {payload.get("message", "-")}',
                f'env: {payload.get("env", "-")}',
                f'dry_run: {str(payload.get("dryRun", False)).lower()}',
                f'output_file: {payload.get("outputFile", "-")}',
                f'written: {str(payload.get("written", False)).lower()}',
                f'overwritten: {str(payload.get("overwritten", False)).lower()}',
            ]
        )

    def build_plan_text(self, payload: dict[str, object]) -> str:
        """
        将插件批量操作拓扑计划负载渲染为文本。

        :param payload: 插件批量操作拓扑计划负载
        :return: 文本输出
        """
        plan = payload.get('plan')
        items = plan.get('items') if isinstance(plan, dict) else None
        blockers = plan.get('blockers') if isinstance(plan, dict) else None
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'operation: {payload.get("operation", "-")}',
            f'blocker_count: {plan.get("blockerCount", 0) if isinstance(plan, dict) else 0}',
        ]
        if isinstance(items, list) and items:
            lines.append('plan:')
            lines.extend(self._build_plugin_plan_line(item) for item in items if isinstance(item, dict))
        else:
            lines.append('plan: none')
        if isinstance(blockers, list) and blockers:
            lines.append('blockers:')
            lines.extend(self._build_plugin_plan_blocker_line(item) for item in blockers if isinstance(item, dict))
        else:
            lines.append('blockers: none')

        return '\n'.join(lines)

    def build_batch_text(self, payload: dict[str, object]) -> str:
        """
        将插件批量执行负载渲染为文本。

        :param payload: 插件批量执行负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'operation: {payload.get("operation", "-")}',
            f'env: {payload.get("env", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'continue_on_error: {str(payload.get("continueOnError", False)).lower()}',
        ]
        plan = payload.get('plan')
        if isinstance(plan, dict):
            lines.append(f'plan_items: {len(plan.get("items", []))}')
            lines.append(f'blocker_count: {plan.get("blockerCount", 0)}')
        summary = payload.get('summary')
        if isinstance(summary, dict):
            lines.append(
                f'summary: total={summary.get("total", 0)} | succeeded={summary.get("succeeded", 0)} | '
                f'failed={summary.get("failed", 0)} | skipped={summary.get("skipped", 0)}'
            )
        executed = payload.get('executed')
        if isinstance(executed, list) and executed:
            lines.append('executed:')
            lines.extend(self._build_batch_result_line(item) for item in executed if isinstance(item, dict))
        else:
            lines.append('executed: none')
        failed = payload.get('failed')
        if isinstance(failed, dict):
            lines.append(
                f'failed: {failed.get("pluginId", "-")} | '
                f'operation: {failed.get("operation", "-")} | message: {failed.get("message", "-")}'
            )
            if failed.get('suggestion'):
                lines.append(f'suggestion: {failed.get("suggestion", "-")}')
        else:
            lines.append('failed: none')

        return '\n'.join(lines)

    def build_create_text(self, payload: dict[str, object]) -> str:
        """
        将插件创建负载渲染为文本。

        :param payload: 插件创建负载
        :return: 文本输出
        """
        lines = [
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'template: {payload.get("template", "-")}',
            f'backend: {str(payload.get("backend", False)).lower()}',
            f'frontend: {str(payload.get("frontend", False)).lower()}',
            f'frontend_version: {payload.get("frontendVersion") or "-"}',
            f'migration: {str(payload.get("migration", False)).lower()}',
            f'seed: {str(payload.get("seed", False)).lower()}',
            f'job: {str(payload.get("job", False)).lower()}',
            f'config: {str(payload.get("config", False)).lower()}',
            f'test: {str(payload.get("test", False)).lower()}',
        ]
        conflicts = payload.get('conflicts')
        if isinstance(conflicts, list) and conflicts:
            lines.append('conflicts:')
            lines.extend(f'  - {conflict}' for conflict in conflicts)

        files = payload.get('files')
        if not isinstance(files, list) or not files:
            lines.append('files: none')
            return '\n'.join(lines)

        lines.append(f'files: {len(files)}')
        lines.extend(f'  - {file_payload.get("path", "-")}' for file_payload in files if isinstance(file_payload, dict))

        return '\n'.join(lines)

    def build_install_text(self, payload: dict[str, object]) -> str:
        """
        将插件安装负载渲染为文本。

        :param payload: 插件安装负载
        :return: 文本输出
        """
        lines = [
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'dependency_ok: {str(payload.get("dependencyOk", False)).lower()}',
            f'structure_ok: {str(payload.get("structureOk", True)).lower()}',
            f'menu_conflict_ok: {str(payload.get("menuConflictOk", True)).lower()}',
        ]
        actions = payload.get('actions')
        if isinstance(actions, list) and actions:
            lines.append('actions:')
            lines.extend(self._build_action_summary_line(action) for action in actions if isinstance(action, dict))
        else:
            lines.append('actions: none')

        dependencies = payload.get('dependencies')
        if isinstance(dependencies, list) and dependencies:
            lines.append(f'dependencies: {len(dependencies)}')
        else:
            lines.append('dependencies: none')

        structure_errors = payload.get('structureErrors')
        if isinstance(structure_errors, list) and structure_errors:
            lines.append(f'structure_errors: {len(structure_errors)}')
        else:
            lines.append('structure_errors: none')

        menu_conflicts = payload.get('menuConflicts')
        if isinstance(menu_conflicts, list) and menu_conflicts:
            lines.append(f'menu_conflicts: {len(menu_conflicts)}')
        else:
            lines.append('menu_conflicts: none')

        self._append_lifecycle_migration_lines(lines, payload)

        return '\n'.join(lines)

    def build_upgrade_text(self, payload: dict[str, object]) -> str:
        """
        将插件升级负载渲染为文本。

        :param payload: 插件升级负载
        :return: 文本输出
        """
        lines = [
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'installed: {str(payload.get("installed", False)).lower()}',
            f'installed_version: {payload.get("installedVersion", "-") or "-"}',
            f'current_version: {payload.get("currentVersion", "-") or "-"}',
            f'needs_upgrade: {str(payload.get("needsUpgrade", False)).lower()}',
            f'database_available: {str(payload.get("databaseAvailable", True)).lower()}',
            f'dependency_ok: {str(payload.get("dependencyOk", False)).lower()}',
            f'structure_ok: {str(payload.get("structureOk", True)).lower()}',
            f'menu_conflict_ok: {str(payload.get("menuConflictOk", True)).lower()}',
        ]
        actions = payload.get('actions')
        if isinstance(actions, list) and actions:
            lines.append('actions:')
            lines.extend(self._build_action_summary_line(action) for action in actions if isinstance(action, dict))
        else:
            lines.append('actions: none')

        structure_errors = payload.get('structureErrors')
        if isinstance(structure_errors, list) and structure_errors:
            lines.append(f'structure_errors: {len(structure_errors)}')
        else:
            lines.append('structure_errors: none')

        menu_conflicts = payload.get('menuConflicts')
        if isinstance(menu_conflicts, list) and menu_conflicts:
            lines.append(f'menu_conflicts: {len(menu_conflicts)}')
        else:
            lines.append('menu_conflicts: none')

        self._append_lifecycle_migration_lines(lines, payload)

        return '\n'.join(lines)

    def build_enabled_text(self, payload: dict[str, object]) -> str:
        """
        将插件启停负载渲染为文本。

        :param payload: 插件启停负载
        :return: 文本输出
        """
        lines = [
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'operation: {payload.get("operation", "-")}',
            f'target_enabled: {str(payload.get("targetEnabled", False)).lower()}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
        ]
        actions = payload.get('actions')
        if isinstance(actions, list) and actions:
            lines.append('actions:')
            lines.extend(self._build_action_summary_line(action) for action in actions if isinstance(action, dict))
        else:
            lines.append('actions: none')

        return '\n'.join(lines)

    def build_purge_text(self, payload: dict[str, object]) -> str:
        """
        将插件物理清理负载渲染为文本。

        :param payload: 插件物理清理负载
        :return: 文本输出
        """
        plan = payload.get('plan')
        plan_items = plan.get('items') if isinstance(plan, dict) else None
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'env: {payload.get("env", "-")}',
            f'operation: {payload.get("operation", "-")}',
            f'dry_run: {str(payload.get("dryRun", False)).lower()}',
            f'safe_mode: {str(payload.get("safeMode", False)).lower()}',
            f'removes_source: {str(payload.get("removesSource", False)).lower()}',
            f'destructive_count: {plan.get("destructiveCount", 0) if isinstance(plan, dict) else 0}',
        ]
        if isinstance(plan_items, list) and plan_items:
            lines.append('plan:')
            lines.extend(self._build_purge_plan_line(item) for item in plan_items if isinstance(item, dict))
        else:
            lines.append('plan: none')

        hooks = payload.get('hooks')
        if isinstance(hooks, list) and hooks:
            lines.append(f'hooks: {len(hooks)}')
        else:
            lines.append('hooks: none')

        return '\n'.join(lines)

    def build_migration_list_text(self, payload: dict[str, object]) -> str:
        """
        将插件 migration 历史负载渲染为文本。

        :param payload: 插件 migration 历史负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
            f'status: {payload.get("status", "-") or "-"}',
            f'count: {payload.get("count", 0)}',
        ]
        migrations = payload.get('migrations')
        if not isinstance(migrations, list) or not migrations:
            lines.append('migrations: none')
            return '\n'.join(lines)

        lines.append('migrations:')
        lines.extend(
            self._build_migration_summary_line(migration) for migration in migrations if isinstance(migration, dict)
        )
        return '\n'.join(lines)

    def build_migration_mark_text(self, payload: dict[str, object]) -> str:
        """
        将插件 migration 人工标记负载渲染为文本。

        :param payload: 插件 migration 人工标记负载
        :return: 文本输出
        """
        return '\n'.join(
            [
                f'ok: {str(payload.get("ok", False)).lower()}',
                f'message: {payload.get("message", "-")}',
                f'plugin_id: {payload.get("pluginId", "-")}',
                f'env: {payload.get("env", "-")}',
                f'operation: {payload.get("operation", "-")}',
                f'migration_path: {payload.get("migrationPath", "-")}',
                f'status: {payload.get("status", "-")}',
            ]
        )

    def build_config_text(self, payload: dict[str, object]) -> str:
        """
        将插件配置负载渲染为文本。

        :param payload: 插件配置负载
        :return: 文本输出
        """
        lines = [
            f'ok: {str(payload.get("ok", False)).lower()}',
            f'message: {payload.get("message", "-")}',
            f'plugin_id: {payload.get("pluginId", "-")}',
        ]
        configs = payload.get('configs')
        if not isinstance(configs, list) or not configs:
            lines.append('configs: none')
            return '\n'.join(lines)

        lines.append(f'configs: {len(configs)}')
        lines.extend(self._build_config_summary_line(config) for config in configs if isinstance(config, dict))

        return '\n'.join(lines)

    @staticmethod
    def _build_dependency_lines(dependencies: list[object]) -> list[str]:
        """
        构建依赖检查文本行。

        :param dependencies: 依赖检查负载列表
        :return: 文本行列表
        """
        if not dependencies:
            return ['dependencies_detail: none']
        lines = ['dependencies_detail:']
        lines.extend(
            PluginCommandPresenter._build_dependency_summary_line(dependency)
            for dependency in dependencies
            if isinstance(dependency, dict)
        )
        return lines

    @staticmethod
    def _build_plugin_summary_line(plugin: dict[str, object]) -> str:
        """
        构建插件摘要文本行。

        :param plugin: 插件摘要负载
        :return: 文本行
        """
        return (
            f'  - {plugin.get("pluginId", "-")} | {plugin.get("name", "-")} | '
            f'version: {plugin.get("version", "-")} | '
            f'runtime_enabled: {str(plugin.get("runtimeEnabled", False)).lower()} | '
            f'status: {plugin.get("status", "-")}'
        )

    @staticmethod
    def _build_config_summary_line(config: dict[str, object]) -> str:
        """
        构建插件配置摘要文本行。

        :param config: 插件配置负载
        :return: 文本行
        """
        return (
            f'  - {config.get("key", "-")} | {config.get("label", "-") or "-"} | '
            f'type: {config.get("type", "-")} | value: {config.get("value", "-")}'
        )

    @staticmethod
    def _build_migration_summary_line(migration: dict[str, object]) -> str:
        """
        构建插件 migration 历史摘要文本行。

        :param migration: migration 历史负载
        :return: 文本行
        """
        checksum = str(migration.get('migrationChecksum') or migration.get('checksum') or '')
        migration_path = migration.get('migrationPath') or migration.get('migration_path') or '-'
        status = migration.get('status', '-')
        attempts = migration.get('attemptCount', migration.get('attempt_count', 0))
        version = migration.get('version', '-') or '-'
        duration_ms = migration.get('durationMs', migration.get('duration_ms'))
        duration_text = f' | duration_ms: {duration_ms}' if duration_ms is not None else ''
        return (
            f'  - {migration_path} | status: {status} | attempts: {attempts} | version: {version} | '
            f'checksum: {checksum[:12] or "-"}{duration_text}'
        )

    def _append_lifecycle_migration_lines(self, lines: list[str], payload: dict[str, object]) -> None:
        """
        追加生命周期 migration 结果和恢复建议文本。

        :param lines: 文本行列表
        :param payload: 生命周期负载
        :return: None
        """
        migration_recovery = payload.get('migrationRecovery')
        if isinstance(migration_recovery, dict):
            lines.append(
                'migration_recovery: '
                f'{migration_recovery.get("migrationPath", "-")} | '
                f'status: {migration_recovery.get("status", "-")} | '
                f'suggestion: {migration_recovery.get("suggestion", "-")}'
            )

        migrations = payload.get('migrations')
        if not isinstance(migrations, list) or not migrations:
            lines.append('migrations: none')
            return

        lines.append('migrations:')
        lines.extend(
            self._build_migration_summary_line(migration) for migration in migrations if isinstance(migration, dict)
        )

    @staticmethod
    def _build_dependency_plan_line(item: dict[str, object]) -> str:
        """
        构建依赖安装计划文本行。

        :param item: 依赖安装计划项
        :return: 文本行
        """
        return (
            f'  - {item.get("kind", "-")} | {item.get("requirement", "-")} | '
            f'workdir: {item.get("workdir", "-")} | command: {item.get("commandText", "-")}'
        )

    @staticmethod
    def _build_purge_plan_line(item: dict[str, object]) -> str:
        """
        构建插件物理清理计划文本行。

        :param item: 插件物理清理计划项
        :return: 文本行
        """
        will_run = item.get('willRun', item.get('enabled', False))
        return (
            f'  - {item.get("name", "-")} | will_run: {str(will_run).lower()} | '
            f'destructive: {str(item.get("destructive", False)).lower()} | '
            f'count: {item.get("count", "-") if item.get("count") is not None else "-"} | '
            f'label: {item.get("label", "-")}'
        )

    @staticmethod
    def _build_plugin_plan_line(item: dict[str, object]) -> str:
        """
        构建插件批量操作计划文本行。

        :param item: 插件批量操作计划项
        :return: 文本行
        """
        return (
            f'  - #{item.get("order", "-")} {item.get("pluginId", "-")} | '
            f'ready: {str(item.get("ready", False)).lower()} | '
            f'requested: {str(item.get("requested", False)).lower()} | '
            f'deps: {len(item.get("dependencies", []))}'
        )

    @staticmethod
    def _build_plugin_plan_blocker_line(item: dict[str, object]) -> str:
        """
        构建插件批量操作计划阻塞项文本行。

        :param item: 插件批量操作计划阻塞项
        :return: 文本行
        """
        return (
            f'  - {item.get("pluginId", "-")} -> {item.get("dependencyId", "-")} | '
            f'status: {item.get("status", "-")} | message: {item.get("message", "-")}'
        )

    @staticmethod
    def _build_batch_result_line(item: dict[str, object]) -> str:
        """
        构建插件批量执行结果文本行。

        :param item: 插件批量执行结果项
        :return: 文本行
        """
        return (
            f'  - {item.get("pluginId", "-")} | operation: {item.get("operation", "-")} | '
            f'ok: {str(item.get("ok", False)).lower()} | status: {item.get("status", "-")} | '
            f'duration_ms: {item.get("durationMs", 0)} | message: {item.get("message", "-")}'
        )

    @staticmethod
    def _build_check_summary_line(check: dict[str, object]) -> str:
        """
        构建插件检查摘要文本行。

        :param check: 插件检查负载
        :return: 文本行
        """
        missing_dependencies = check.get('missingDependencies', [])
        unsatisfied_dependencies = check.get('unsatisfiedDependencies', [])
        structure_errors = check.get('structureErrors', [])
        menu_conflicts = check.get('menuConflicts', [])
        return (
            f'  - {check.get("pluginId", "-")} | ok: {str(check.get("ok", False)).lower()} | '
            f'missing: {len(missing_dependencies)} | unsatisfied: {len(unsatisfied_dependencies)} | '
            f'structure_errors: {len(structure_errors)} | menu_conflicts: {len(menu_conflicts)}'
        )

    @staticmethod
    def _build_dependency_summary_line(dependency: dict[str, object]) -> str:
        """
        构建依赖检查摘要文本行。

        :param dependency: 依赖检查负载
        :return: 文本行
        """
        return (
            f'  - {dependency.get("kind", "-")}:{dependency.get("name", "-")} | '
            f'ok: {str(dependency.get("ok", False)).lower()} | '
            f'required: {dependency.get("requiredVersion", "-") or "-"} | '
            f'installed: {dependency.get("installedVersion", "-") or "-"}'
        )

    @staticmethod
    def _build_action_summary_line(action: dict[str, object]) -> str:
        """
        构建安装动作摘要文本行。

        :param action: 安装动作负载
        :return: 文本行
        """
        will_run = action.get('willRun', action.get('enabled', False))
        return f'  - {action.get("name", "-")} | will_run: {str(will_run).lower()} | label: {action.get("label", "-")}'
