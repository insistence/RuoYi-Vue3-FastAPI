VIEW_LABELS = {
    'dashboard': '总览',
    'app': '应用',
    'ops': '运维',
    'database': '数据库',
    'cache': '缓存',
    'jobs': '任务',
    'gen': '代码生成',
    'configs': '参数配置',
    'crypto': '加密',
}

STATUS_LABELS = {
    'ok': '正常',
    'success': '正常',
    'healthy': '正常',
    'fail': '失败',
    'error': '失败',
    'down': '失败',
    'warn': '警告',
    'warning': '警告',
    'degraded': '警告',
    'info': '信息',
}

GENERAL_COPY = {
    'action_confirm_cancel_label': '取消',
    'action_confirm_hint': '按键提示 · [Enter] 确认执行  [Esc] 取消返回',
    'more_detail_hint': '> 进入对应页面查看更多',
    'tui_command_help': '进入只读巡检工作台',
    'tui_missing_dependency_hint': '请重新执行 `pip install -r requirements.txt` 或 `pip install -r requirements-pg.txt`',
    'tui_missing_dependency_message': '当前环境未安装 TUI 可选依赖，无法启动 `ruoyi tui`',
}

STATE_SUGGESTIONS = {
    'dashboard_empty': '按 [R] 刷新，或进入对应页面查看更多上下文',
    'dashboard_failure': '按 [R] 刷新，或进入对应页面查看完整诊断信息',
    'empty': '可按 [R] 刷新，或切换到其他页面继续查看',
    'failure': '可按 [R] 刷新，或切换页面后重新进入',
    'loading': '可继续切换其他区域，当前内容加载完成后会自动刷新',
}

PAGE_SUBTITLES = {
    'crypto': '查看运行校验、公钥身份和兼容版本信息',
    'ops': '查看基础连通性、依赖版本与服务器资源',
}

NAVIGATION_DESCRIPTIONS = {
    'dashboard': '全链路态势与关键健康信号',
    'app': '环境解析、配置快照、补全诊断与路由摘要',
    'ops': '健康检查、依赖版本与服务器资源',
    'database': '连接、迁移版本与存储状态',
    'cache': 'Redis 容量、热点与命中信号',
    'jobs': '定时任务、执行轨迹与失败样本',
    'gen': '业务表、字段与生成配置',
    'configs': '配置巡检、漂移与异常值',
    'crypto': '传输加密校验、公钥身份与兼容版本',
}

DASHBOARD_HERO_COPY = {
    'subtitle': '先看整体风险和巡检结论，再进入数据库、缓存、任务等分区继续定位',
    'title': '运行驾驶舱',
}

STATUS_PANEL_COPY = {
    'empty': '暂无数据',
}

ACTION_LABELS = {
    'app_run': '直接启动应用',
    'app_run_wizard': '打开启动向导',
    'cache_clear_wizard': '打开缓存清理向导',
    'cache_warmup': '执行缓存预热',
    'completion_install': '安装当前 Shell 补全',
    'config_sync': '刷新参数缓存',
    'crypto_keygen': '打开密钥生成入口',
    'crypto_rotate_dry_run': '执行轮换预演',
    'db_init_dry_run': '执行初始化预演',
    'db_upgrade_wizard': '打开升级向导',
    'gen_export_dry_run': '执行导出预演',
    'gen_export_wizard': '打开导出向导',
    'gen_import_wizard': '打开导入向导',
    'gen_sync_db': '同步数据库表结构',
    'job_pause': '暂停任务',
    'job_resume': '恢复任务',
    'job_run_once': '执行一次任务',
    'job_sync': '同步调度配置',
    'ops_ping_db': '执行数据库探活',
    'ops_ping_redis': '执行 Redis 探活',
    'prod_check_wizard': '打开生产巡检向导',
}

ACTION_SCOPE_LABELS = {
    'cache_warmup': '系统字典与系统参数基础缓存',
    'completion_install': '当前终端活动 Shell 的补全安装流程',
    'config_sync': '当前环境全部系统参数',
    'db_init_dry_run': '当前环境数据库初始化流程',
    'gen_export_dry_run': '当前业务表的代码导出结果预演',
    'gen_sync_db': '当前业务表对应的生成配置和物理表结构',
    'job_sync': '当前环境调度器配置',
    'ops_ping_db': '当前环境数据库连接与基础读写探活',
    'ops_ping_redis': '当前环境 Redis 连接与基础命令探活',
}

ACTION_PURPOSE_LABELS = {
    'cache_warmup': '重建运行所需的基础缓存内容',
    'completion_install': '自动识别当前 Shell，写入补全脚本并按需更新 rc 文件激活命令',
    'config_sync': '将数据库中的参数值重新写入 Redis 缓存',
    'db_init_dry_run': '仅预演初始化到最新迁移版本，不直接执行真实升级',
    'gen_export_dry_run': '先演练导出流程并确认输出模式、模板数量和结果摘要',
    'gen_sync_db': '将数据库中的最新字段结构同步回当前业务表配置',
    'job_sync': '将最新任务配置同步到调度执行器',
    'ops_ping_db': '快速确认当前环境数据库是否可连接并返回基础探活结果',
    'ops_ping_redis': '快速确认当前环境 Redis 是否可连接并返回基础命令探活结果',
}

ACTION_PREVIEW_TITLES = {
    'command': '## 执行命令',
    'consequence': '## 确认后果',
    'env': '## 执行环境',
    'summary': '## 动作信息',
}

ACTION_PREVIEW_FIELD_LABELS = {
    'current_status': '当前状态',
    'job': '任务',
    'job_id': '任务 ID',
    'purpose': '用途',
    'scope': '作用范围',
    'target_action': '目标动作',
    'target_env': '目标环境',
}

ACTION_RESULT_FIELD_LABELS = {
    'count': '影响数量',
    'exit_code': '退出码',
    'fail': '失败',
    'hint': '建议',
    'job_id': '任务 ID',
    'name': '动作名称',
    'operation': '操作标签',
    'outcome': '结果',
    'service': '服务反馈',
    'success': '成功',
    'summary': '摘要',
}

ACTION_CONSEQUENCE_TEXTS = {
    'external': '确认后会暂时挂起 TUI，并在当前终端中执行对应命令；命令结束后自动返回工作台。',
    'preview': '确认后会立即执行对应 CLI 低风险命令，并按结果刷新当前页面。',
    'wizard': '确认后会暂时挂起 TUI，并在当前终端中打开对应向导；向导结束后自动返回工作台。',
}

APP_BINDING_LABELS = {
    'next': '下一页',
    'previous': '上一页',
    'quit': '退出',
    'refresh': '刷新',
    'sidebar': '侧边栏',
}

INTERNAL_BINDING_LABELS = {
    'action_global': '同步动作',
    'action_primary': '执行动作',
    'action_secondary': '切换状态',
    'action_utility': '工具动作',
    'clear_search': '清空搜索',
    'confirm_cancel': '取消',
    'confirm_submit': '确认',
    'end': '跳到末尾',
    'filter_1': '筛选项 1',
    'filter_2': '筛选项 2',
    'filter_3': '筛选项 3',
    'filter_4': '筛选项 4',
    'focus_left': '向左聚焦',
    'focus_right': '向右聚焦',
    'home': '回到顶部',
    'page_down': '下翻页',
    'page_up': '上翻页',
    'scroll_down': '向下滚动',
    'scroll_up': '向上滚动',
    'search': '页内搜索',
}

BROWSER_EMPTY_RECORD_COPY = {
    'detail': '当前页面没有可浏览记录',
    'label': '记录列表',
    'summary': '当前页面没有可浏览记录',
    'title': '暂无记录数据',
    'value': '暂无数据',
}

BROWSER_LOADING_COPY = {
    'detail': '正在后台加载当前记录详情，请稍候',
    'label': '详情状态',
    'title': '详情加载中',
    'value': '加载中',
}

DETAIL_EMPTY_SECTION_COPY = {
    'detail_page': '当前页面没有可展示的分区详情',
    'detail_record': '当前记录没有可展示的分区详情',
    'label': '分区详情',
    'title': '暂无分区数据',
    'value': '暂无内容',
}

CAPABILITY_LABELS = {
    'app_run': ACTION_LABELS['app_run'],
    'app_run_wizard': ACTION_LABELS['app_run_wizard'],
    'cache_clear_wizard': ACTION_LABELS['cache_clear_wizard'],
    'cache_warmup': ACTION_LABELS['cache_warmup'],
    'completion_install': ACTION_LABELS['completion_install'],
    'config_sync': ACTION_LABELS['config_sync'],
    'crypto_keygen': ACTION_LABELS['crypto_keygen'],
    'crypto_rotate_dry_run': ACTION_LABELS['crypto_rotate_dry_run'],
    'db_init_dry_run': ACTION_LABELS['db_init_dry_run'],
    'db_upgrade_wizard': ACTION_LABELS['db_upgrade_wizard'],
    'gen_export_dry_run': ACTION_LABELS['gen_export_dry_run'],
    'gen_export_wizard': ACTION_LABELS['gen_export_wizard'],
    'gen_import_wizard': ACTION_LABELS['gen_import_wizard'],
    'gen_sync_db': ACTION_LABELS['gen_sync_db'],
    'job_run_once': ACTION_LABELS['job_run_once'],
    'job_toggle': '暂停/恢复任务',
    'job_sync': ACTION_LABELS['job_sync'],
    'ops_ping_db': ACTION_LABELS['ops_ping_db'],
    'ops_ping_redis': ACTION_LABELS['ops_ping_redis'],
    'prod_check_wizard': ACTION_LABELS['prod_check_wizard'],
}

CAPABILITY_HINT_LABELS = {
    'app_run': '直接启动',
    'app_run_wizard': '打开启动向导',
    'cache_clear_wizard': '清理向导',
    'cache_warmup': '执行缓存预热',
    'completion_install': '安装补全',
    'config_sync': '刷新参数缓存',
    'crypto_keygen': '密钥生成',
    'crypto_rotate_dry_run': '执行轮换预演',
    'db_init_dry_run': '初始化预演',
    'db_upgrade_wizard': '打开升级向导',
    'gen_export_dry_run': '导出预演',
    'gen_export_wizard': '导出向导',
    'gen_import_wizard': '导入向导',
    'gen_sync_db': '同步表结构',
    'job_run_once': '执行一次',
    'job_toggle': '暂停/恢复',
    'job_sync': '同步调度',
    'ops_ping_db': '数据库探活',
    'ops_ping_redis': 'Redis 探活',
    'prod_check_wizard': '打开生产巡检向导',
}

WORKSPACE_LABELS = {
    'current_section': '当前分区',
    'menu': '菜单',
    'overview': '概览',
    'record': '记录',
    'section': '分区',
    'shortcut': '快捷键',
    'status': '状态',
}

WORKSPACE_TITLES = {
    'action_feedback': '【执行反馈】',
    'detail_content': '详情内容',
    'key_fields': '【关键字段】',
    'key_info': '【关键信息】',
}

WORKSPACE_EMPTY_TEXTS = {
    'actions': '暂无可执行动作',
    'detail': '暂无详情',
    'key_info': '暂无关键信息',
}

STATE_SECTION_TITLES = {
    'detail': '## 补充说明',
    'diagnostic': '## 诊断线索',
    'error': '## 错误摘要',
    'status': '## 当前状态',
    'suggestion': '## 下一步',
}

ACTION_NOTIFICATION_COPY = {
    'empty_line': '当前记录没有可执行的低风险动作',
    'title': 'TUI 动作',
    'unavailable_message': '当前页面没有可执行的对应快捷动作',
}

BROWSER_ACTION_PANEL_COPY = {
    'action_section_title': '## 可执行动作',
    'operation_section_title': '## 浏览操作',
    'recent_action_section_title': '## 最近动作反馈',
}

COMMAND_HINT_TITLES = {
    'command': '## 推荐命令',
    'guide': '## 使用说明',
    'scenario': '## 适用场景',
}

SIGNAL_RAIL_COPY = {
    'empty': '暂无实时信号',
    'title': '系统信号带',
}

METRIC_COPY = {
    'hint_label': '说明',
    'label': '指标',
    'value_label': '数值',
}

ACTION_HINT_COPY = {
    'browser_default': '当前页面以浏览为主。{interaction_hint}',
    'browser_templates': {
        'cache': '建议先核对 Redis 概览与键值样本，再决定预热或进入清理向导。{interaction_hint}',
        'configs': '建议先看高风险配置，再决定是否刷新参数缓存。{interaction_hint}',
        'gen': '建议先看生成前校验、同步预检查与代码预览，再决定是否进入导入向导、同步表结构或进入导出向导。{interaction_hint}',
        'jobs': '建议先看失败聚合，再决定执行一次、暂停恢复或同步调度。{interaction_hint}',
    },
    'detail_default': '当前页面以查看分区为主。{interaction_hint}',
    'detail_templates': {
        'app': '建议先确认环境映射、应用配置、启动前检查、补全诊断和路由状态，再决定是安装补全、直接启动应用还是进入启动向导。{interaction_hint}',
        'crypto': '建议先确认运行校验、公钥身份和兼容版本，再决定是否生成新密钥或执行轮换预演。{interaction_hint}',
        'database': '建议先确认 revision、Heads 和历史链路，再决定是否执行初始化预演或进入升级向导。{interaction_hint}',
        'ops': '建议先确认数据库探活、Redis 探活、依赖版本和服务器资源，再决定是否进入生产巡检。{interaction_hint}',
    },
    'operation_hint_lines': [
        '> [←/→] 切换焦点',
        '> [J/K] 向上/向下滚动',
        '> [PgUp/PgDn] 整页滚动',
        '> [Home/End] 跳到首尾',
    ],
}

ACTION_FEEDBACK_COPY = {
    'toast_prefix': '动作结果',
}
