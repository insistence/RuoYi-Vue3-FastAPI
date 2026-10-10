from dataclasses import dataclass


@dataclass(frozen=True)
class PageCase:
    """两套 Web 工程共有的内置菜单、实际页面内容与首屏业务请求。"""

    path: str
    title: str
    content: str
    api: str | None = None
    selector: str = '.el-table'


MENU_PAGES = (
    PageCase('/system/user', '用户管理', '用户名称', '/system/user/list'),
    PageCase('/system/role', '角色管理', '权限字符', '/system/role/list'),
    PageCase('/system/menu', '菜单管理', '菜单名称', '/system/menu/list'),
    PageCase('/system/dept', '部门管理', '部门名称', '/system/dept/list'),
    PageCase('/system/post', '岗位管理', '岗位编码', '/system/post/list'),
    PageCase('/system/dict', '字典管理', '字典类型', '/system/dict/type/list'),
    PageCase('/system/config', '参数设置', '参数键名', '/system/config/list'),
    PageCase('/system/notice', '通知公告', '公告标题', '/system/notice/list'),
    PageCase('/system/log/operlog', '操作日志', '系统模块', '/monitor/operlog/list'),
    PageCase('/system/log/logininfor', '登录日志', '用户名称', '/monitor/logininfor/list'),
    PageCase('/system/file', '文件管理', '文件名称', '/system/file/list'),
    PageCase('/system/plugin', '插件管理', '插件ID', '/system/plugin/list'),
    PageCase('/system/oauth/client', '客户端管理', '应用', '/system/oauth/client/list'),
    PageCase('/system/oauth/resource', '资源管理', '服务', '/system/oauth/resource/list'),
    PageCase('/system/oauth/scope', '范围管理', '权限', '/system/oauth/scope/list'),
    PageCase('/system/oauth/session', '外部会话', '会话', '/system/oauth/session/list'),
    PageCase('/system/oauth/grant', '外部授权', '授权', '/system/oauth/grant/list'),
    PageCase('/system/oauth/key', '签名密钥', '当前签名密钥', '/system/oauth/key/list'),
    PageCase('/monitor/online', '在线用户', '登录名称', '/monitor/online/list'),
    PageCase('/monitor/job', '定时任务', '任务名称', '/monitor/job/list'),
    PageCase('/monitor/druid', '数据监控', '我是数据监控', selector=':scope > div'),
    PageCase('/monitor/server', '服务监控', 'CPU', '/monitor/server', '.el-card'),
    PageCase('/monitor/cache', '缓存监控', 'Redis版本', '/monitor/cache'),
    PageCase('/monitor/cacheList', '缓存列表', '缓存名称', '/monitor/cache/getNames'),
    PageCase('/monitor/transportCrypto', '传输加密', '传输加密状态', '/transport/crypto/monitor', '.summary-card'),
    PageCase('/monitor/oauthAudit', 'OAuth审计', '安全日志', '/monitor/oauth/audit/list'),
    PageCase('/tool/build', '表单构建', '输入型组件', selector='.components-list'),
    PageCase('/tool/gen', '代码生成', '表名称', '/tool/gen/list'),
    PageCase('/tool/swagger', '系统接口', '', selector='iframe'),
)
