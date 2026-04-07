from config.env import DataBaseConfig


class CommonConstant:
    """
    常用常量

    PASSWORD_ERROR_COUNT: 密码错误次数
    WWW: www主域
    HTTP: http请求
    HTTPS: https请求
    LOOKUP_RMI: RMI远程方法调用
    LOOKUP_LDAP: LDAP远程方法调用
    LOOKUP_LDAPS: LDAPS远程方法调用
    YES: 是否为系统默认（是）
    NO: 是否为系统默认（否）
    DEPT_NORMAL: 部门正常状态
    DEPT_DISABLE: 部门停用状态
    UNIQUE: 校验是否唯一的返回标识（是）
    NOT_UNIQUE: 校验是否唯一的返回标识（否）
    """

    PASSWORD_ERROR_COUNT = 5
    WWW = 'www.'
    HTTP = 'http://'
    HTTPS = 'https://'
    LOOKUP_RMI = 'rmi:'
    LOOKUP_LDAP = 'ldap:'
    LOOKUP_LDAPS = 'ldaps:'
    YES = 'Y'
    NO = 'N'
    DEPT_NORMAL = '0'
    DEPT_DISABLE = '1'
    UNIQUE = True
    NOT_UNIQUE = False


class HttpStatusConstant:
    """
    返回状态码

    SUCCESS: 操作成功
    CREATED: 对象创建成功
    ACCEPTED: 请求已经被接受
    NO_CONTENT: 操作已经执行成功，但是没有返回数据
    MOVED_PERM: 资源已被移除
    SEE_OTHER: 重定向
    NOT_MODIFIED: 资源没有被修改
    BAD_REQUEST: 参数列表错误（缺少，格式不匹配）
    UNAUTHORIZED: 未授权
    FORBIDDEN: 访问受限，授权过期
    NOT_FOUND: 资源，服务未找到
    BAD_METHOD: 不允许的http方法
    CONFLICT: 资源冲突，或者资源被锁
    UNSUPPORTED_TYPE: 不支持的数据，媒体类型
    ERROR: 系统内部错误
    NOT_IMPLEMENTED: 接口未实现
    WARN: 系统警告消息
    """

    SUCCESS = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    MOVED_PERM = 301
    SEE_OTHER = 303
    NOT_MODIFIED = 304
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    BAD_METHOD = 405
    CONFLICT = 409
    UNSUPPORTED_TYPE = 415
    ERROR = 500
    NOT_IMPLEMENTED = 501
    WARN = 601


class JobConstant:
    """
    定时任务常量

    JOB_ERROR_LIST: 定时任务禁止调用模块及违规字符串列表
    JOB_WHITE_LIST: 定时任务允许调用模块列表
    """

    JOB_ERROR_LIST = [
        'app',
        'config',
        'exceptions',
        'import ',
        'middlewares',
        'module_admin',
        'open(',
        'os.',
        'server',
        'sub_applications',
        'subprocess.',
        'sys.',
        'utils',
        'while ',
        '__import__',
        '"',
        "'",
        ',',
        '?',
        ':',
        ';',
        '/',
        '|',
        '+',
        '-',
        '=',
        '~',
        '!',
        '#',
        '$',
        '%',
        '^',
        '&',
        '*',
        '<',
        '>',
        '(',
        ')',
        '[',
        ']',
        '{',
        '}',
        ' ',
    ]
    JOB_WHITE_LIST = ['module_task']


class LockConstant:
    """
    分布式锁常量
    """

    APP_STARTUP_LOCK_KEY = 'app:startup:lock'
    LOCK_EXPIRE_SECONDS = 60
    LOCK_RENEWAL_INTERVAL = 20


class CacheNamespace:
    """
    接口缓存命名空间常量

    MONITOR_SERVER_INFO: 服务监控信息缓存
    MONITOR_JOB_LIST: 定时任务分页列表缓存
    MONITOR_JOB_DETAIL: 定时任务详情缓存
    LOGIN_USER_INFO: 登录用户信息缓存
    LOGIN_USER_ROUTERS: 登录用户路由缓存
    SYSTEM_MENU_TREE: 菜单树缓存
    SYSTEM_MENU_ROLE_TREE: 角色菜单树缓存
    SYSTEM_MENU_LIST: 菜单分页列表缓存
    SYSTEM_MENU_DETAIL: 菜单详情缓存
    SYSTEM_DEPT_EDIT_TREE: 部门编辑树缓存
    SYSTEM_DEPT_LIST: 部门列表缓存
    SYSTEM_DEPT_DETAIL: 部门详情缓存
    SYSTEM_POST_LIST: 岗位列表缓存
    SYSTEM_POST_DETAIL: 岗位详情缓存
    SYSTEM_NOTICE_LIST: 通知公告列表缓存
    SYSTEM_NOTICE_DETAIL: 通知公告详情缓存
    SYSTEM_ROLE_DEPT_TREE: 角色部门树缓存
    SYSTEM_ROLE_LIST: 角色列表缓存
    SYSTEM_ROLE_DETAIL: 角色详情缓存
    SYSTEM_ROLE_ALLOCATED_USER_LIST: 已分配用户角色列表缓存
    SYSTEM_ROLE_UNALLOCATED_USER_LIST: 未分配用户角色列表缓存
    SYSTEM_USER_DEPT_TREE: 用户部门树缓存
    SYSTEM_USER_LIST: 用户列表缓存
    SYSTEM_USER_PROFILE: 用户个人信息缓存
    SYSTEM_USER_DETAIL: 用户详情缓存
    SYSTEM_CONFIG_LIST: 参数配置列表缓存
    SYSTEM_CONFIG_DETAIL: 参数配置详情缓存
    SYSTEM_DICT_TYPE_LIST: 字典类型列表缓存
    SYSTEM_DICT_TYPE_OPTIONS: 字典类型选项缓存
    SYSTEM_DICT_TYPE_DETAIL: 字典类型详情缓存
    SYSTEM_DICT_DATA_LIST: 字典数据列表缓存
    SYSTEM_DICT_DATA_DETAIL: 字典数据详情缓存
    AI_MODEL_LIST: AI模型列表缓存
    AI_MODEL_ALL: AI模型全量列表缓存
    AI_MODEL_DETAIL: AI模型详情缓存
    AI_CHAT_CONFIG: AI对话配置缓存
    TOOL_GEN_LIST: 代码生成列表缓存
    TOOL_GEN_DB_LIST: 代码生成数据源列表缓存
    TOOL_GEN_DETAIL: 代码生成详情缓存
    TOOL_GEN_PREVIEW: 代码生成预览缓存
    """

    MONITOR_SERVER_INFO = 'monitor:server:info'
    MONITOR_JOB_LIST = 'monitor:job:list'
    MONITOR_JOB_DETAIL = 'monitor:job:detail'

    LOGIN_USER_INFO = 'login:user:info'
    LOGIN_USER_ROUTERS = 'login:user:routers'

    SYSTEM_MENU_TREE = 'system:menu:tree'
    SYSTEM_MENU_ROLE_TREE = 'system:menu:role-tree'
    SYSTEM_MENU_LIST = 'system:menu:list'
    SYSTEM_MENU_DETAIL = 'system:menu:detail'

    SYSTEM_DEPT_EDIT_TREE = 'system:dept:edit-tree'
    SYSTEM_DEPT_LIST = 'system:dept:list'
    SYSTEM_DEPT_DETAIL = 'system:dept:detail'

    SYSTEM_POST_LIST = 'system:post:list'
    SYSTEM_POST_DETAIL = 'system:post:detail'

    SYSTEM_NOTICE_LIST = 'system:notice:list'
    SYSTEM_NOTICE_DETAIL = 'system:notice:detail'

    SYSTEM_ROLE_DEPT_TREE = 'system:role:dept-tree'
    SYSTEM_ROLE_LIST = 'system:role:list'
    SYSTEM_ROLE_DETAIL = 'system:role:detail'
    SYSTEM_ROLE_ALLOCATED_USER_LIST = 'system:role:allocated-user-list'
    SYSTEM_ROLE_UNALLOCATED_USER_LIST = 'system:role:unallocated-user-list'

    SYSTEM_USER_DEPT_TREE = 'system:user:dept-tree'
    SYSTEM_USER_LIST = 'system:user:list'
    SYSTEM_USER_PROFILE = 'system:user:profile'
    SYSTEM_USER_DETAIL = 'system:user:detail'

    SYSTEM_CONFIG_LIST = 'system:config:list'
    SYSTEM_CONFIG_DETAIL = 'system:config:detail'

    SYSTEM_DICT_TYPE_LIST = 'system:dict:type-list'
    SYSTEM_DICT_TYPE_OPTIONS = 'system:dict:type-options'
    SYSTEM_DICT_TYPE_DETAIL = 'system:dict:type-detail'
    SYSTEM_DICT_DATA_LIST = 'system:dict:data-list'
    SYSTEM_DICT_DATA_DETAIL = 'system:dict:data-detail'

    AI_MODEL_LIST = 'ai:model:list'
    AI_MODEL_ALL = 'ai:model:all'
    AI_MODEL_DETAIL = 'ai:model:detail'
    AI_CHAT_CONFIG = 'ai:chat:config'

    TOOL_GEN_LIST = 'tool:gen:list'
    TOOL_GEN_DB_LIST = 'tool:gen:db-list'
    TOOL_GEN_DETAIL = 'tool:gen:detail'
    TOOL_GEN_PREVIEW = 'tool:gen:preview'


class CacheGroup:
    """
    接口缓存失效分组常量

    PERMISSION_MUTATION: 权限及菜单视图关联缓存失效基础分组
    DATA_SCOPE_MUTATION: 数据范围相关视图关联缓存失效基础分组
    MENU_MUTATION: 菜单写操作关联缓存失效分组
    JOB_MUTATION: 定时任务写操作关联缓存失效分组
    POST_MUTATION: 岗位写操作关联缓存失效分组
    NOTICE_MUTATION: 通知公告写操作关联缓存失效分组
    ROLE_ENTITY_MUTATION: 角色实体信息变更关联缓存失效分组
    ROLE_PERMISSION_MUTATION: 角色权限变更关联缓存失效分组
    ROLE_MUTATION: 角色通用写操作关联缓存失效组合分组
    USER_ENTITY_MUTATION: 用户实体信息变更关联缓存失效分组
    USER_PERMISSION_MUTATION: 用户权限变更关联缓存失效分组
    USER_INFO_MUTATION: 用户资料与安全相关写操作关联缓存失效分组
    LOGIN_SUCCESS_MUTATION: 登录成功后关联缓存失效分组
    LOGOUT_MUTATION: 登出后关联缓存失效分组
    CONFIG_MUTATION: 参数配置写操作关联缓存失效分组
    DICT_TYPE_MUTATION: 字典类型写操作关联缓存失效分组
    DICT_DATA_MUTATION: 字典数据写操作关联缓存失效分组
    AI_MODEL_MUTATION: AI模型写操作关联缓存失效分组
    AI_CHAT_CONFIG_MUTATION: AI对话配置写操作关联缓存失效分组
    GEN_MUTATION: 代码生成写操作关联缓存失效分组
    """

    PERMISSION_MUTATION = (
        CacheNamespace.LOGIN_USER_INFO,
        CacheNamespace.LOGIN_USER_ROUTERS,
        CacheNamespace.SYSTEM_MENU_TREE,
        CacheNamespace.SYSTEM_MENU_ROLE_TREE,
        CacheNamespace.SYSTEM_MENU_LIST,
    )

    DATA_SCOPE_MUTATION = (
        CacheNamespace.LOGIN_USER_INFO,
        CacheNamespace.SYSTEM_DEPT_EDIT_TREE,
        CacheNamespace.SYSTEM_DEPT_LIST,
        CacheNamespace.SYSTEM_DEPT_DETAIL,
        CacheNamespace.SYSTEM_ROLE_DEPT_TREE,
        CacheNamespace.SYSTEM_ROLE_LIST,
        CacheNamespace.SYSTEM_ROLE_DETAIL,
        CacheNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        CacheNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
        CacheNamespace.SYSTEM_USER_DEPT_TREE,
        CacheNamespace.SYSTEM_USER_LIST,
        CacheNamespace.SYSTEM_USER_DETAIL,
        CacheNamespace.SYSTEM_USER_PROFILE,
        CacheNamespace.AI_MODEL_LIST,
        CacheNamespace.AI_MODEL_ALL,
        CacheNamespace.AI_MODEL_DETAIL,
    )

    MENU_MUTATION = (
        *PERMISSION_MUTATION,
        CacheNamespace.SYSTEM_MENU_DETAIL,
    )

    JOB_MUTATION = (
        CacheNamespace.MONITOR_JOB_LIST,
        CacheNamespace.MONITOR_JOB_DETAIL,
    )

    POST_MUTATION = (
        CacheNamespace.SYSTEM_POST_LIST,
        CacheNamespace.SYSTEM_POST_DETAIL,
        CacheNamespace.SYSTEM_USER_DETAIL,
        CacheNamespace.SYSTEM_USER_PROFILE,
    )

    NOTICE_MUTATION = (
        CacheNamespace.SYSTEM_NOTICE_LIST,
        CacheNamespace.SYSTEM_NOTICE_DETAIL,
    )

    ROLE_ENTITY_MUTATION = (
        CacheNamespace.SYSTEM_ROLE_DEPT_TREE,
        CacheNamespace.SYSTEM_ROLE_LIST,
        CacheNamespace.SYSTEM_ROLE_DETAIL,
        CacheNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        CacheNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
        CacheNamespace.SYSTEM_MENU_ROLE_TREE,
        CacheNamespace.SYSTEM_USER_DETAIL,
    )

    ROLE_PERMISSION_MUTATION = (
        *ROLE_ENTITY_MUTATION,
        CacheNamespace.SYSTEM_USER_PROFILE,
        CacheNamespace.LOGIN_USER_INFO,
        *PERMISSION_MUTATION,
    )

    ROLE_MUTATION = (
        *ROLE_PERMISSION_MUTATION,
        *DATA_SCOPE_MUTATION,
    )

    USER_ENTITY_MUTATION = (
        CacheNamespace.SYSTEM_USER_LIST,
        CacheNamespace.SYSTEM_USER_DETAIL,
        CacheNamespace.SYSTEM_ROLE_ALLOCATED_USER_LIST,
        CacheNamespace.SYSTEM_ROLE_UNALLOCATED_USER_LIST,
    )

    USER_PERMISSION_MUTATION = (
        *DATA_SCOPE_MUTATION,
        *PERMISSION_MUTATION,
    )

    USER_INFO_MUTATION = (
        CacheNamespace.SYSTEM_USER_LIST,
        CacheNamespace.SYSTEM_USER_DETAIL,
        CacheNamespace.SYSTEM_USER_PROFILE,
        CacheNamespace.LOGIN_USER_INFO,
    )

    LOGIN_SUCCESS_MUTATION = (
        CacheNamespace.SYSTEM_USER_LIST,
        CacheNamespace.LOGIN_USER_INFO,
        CacheNamespace.LOGIN_USER_ROUTERS,
        CacheNamespace.SYSTEM_USER_PROFILE,
        CacheNamespace.SYSTEM_USER_DETAIL,
    )

    LOGOUT_MUTATION = (
        CacheNamespace.LOGIN_USER_INFO,
        CacheNamespace.LOGIN_USER_ROUTERS,
    )

    CONFIG_MUTATION = (
        CacheNamespace.SYSTEM_CONFIG_LIST,
        CacheNamespace.SYSTEM_CONFIG_DETAIL,
    )

    DICT_TYPE_MUTATION = (
        CacheNamespace.SYSTEM_DICT_TYPE_LIST,
        CacheNamespace.SYSTEM_DICT_TYPE_OPTIONS,
        CacheNamespace.SYSTEM_DICT_TYPE_DETAIL,
        CacheNamespace.SYSTEM_DICT_DATA_LIST,
        CacheNamespace.SYSTEM_DICT_DATA_DETAIL,
    )

    DICT_DATA_MUTATION = (
        CacheNamespace.SYSTEM_DICT_DATA_LIST,
        CacheNamespace.SYSTEM_DICT_DATA_DETAIL,
    )

    AI_MODEL_MUTATION = (
        CacheNamespace.AI_MODEL_LIST,
        CacheNamespace.AI_MODEL_ALL,
        CacheNamespace.AI_MODEL_DETAIL,
    )

    AI_CHAT_CONFIG_MUTATION = (CacheNamespace.AI_CHAT_CONFIG,)

    GEN_MUTATION = (
        CacheNamespace.TOOL_GEN_LIST,
        CacheNamespace.TOOL_GEN_DB_LIST,
        CacheNamespace.TOOL_GEN_DETAIL,
        CacheNamespace.TOOL_GEN_PREVIEW,
    )


class MenuConstant:
    """
    菜单常量

    TYPE_DIR: 菜单类型（目录）
    TYPE_MENU: 菜单类型（菜单）
    TYPE_BUTTON: 菜单类型（按钮）
    YES_FRAME: 是否菜单外链（是）
    NO_FRAME: 是否菜单外链（否）
    LAYOUT: Layout组件标识
    PARENT_VIEW: ParentView组件标识
    INNER_LINK: InnerLink组件标识
    """

    TYPE_DIR = 'M'
    TYPE_MENU = 'C'
    TYPE_BUTTON = 'F'
    YES_FRAME = 0
    NO_FRAME = 1
    LAYOUT = 'Layout'
    PARENT_VIEW = 'ParentView'
    INNER_LINK = 'InnerLink'


class GenConstant:
    """
    代码生成常量

    TPL_CRUD: 单表（增删改查
    TPL_TREE: 树表（增删改查）
    TPL_SUB: 主子表（增删改查）
    TREE_CODE: 树编码字段
    TREE_PARENT_CODE: 树父编码字段
    TREE_NAME: 树名称字段
    PARENT_MENU_ID: 上级菜单ID字段
    PARENT_MENU_NAME: 上级菜单名称字段
    COLUMNTYPE_STR: 数据库字符串类型
    COLUMNTYPE_TEXT: 数据库文本类型
    COLUMNTYPE_TIME: 数据库时间类型
    COLUMNTYPE_GEOMETRY: 数据库字空间类型
    COLUMNTYPE_NUMBER: 数据库数字类型
    COLUMNNAME_NOT_EDIT: 页面不需要编辑字段
    COLUMNNAME_NOT_LIST: 页面不需要显示的列表字段
    COLUMNNAME_NOT_QUERY: 页面不需要查询字段
    BASE_ENTITY: Entity基类字段
    TREE_ENTITY: Tree基类字段
    HTML_INPUT: 文本框
    HTML_TEXTAREA: 文本域
    HTML_SELECT: 下拉框
    HTML_RADIO: 单选框
    HTML_CHECKBOX: 复选框
    HTML_DATETIME: 日期控件
    HTML_IMAGE_UPLOAD: 图片上传控件
    HTML_FILE_UPLOAD: 文件上传控件
    HTML_EDITOR: 富文本控件
    TYPE_DECIMAL: 高精度计算类型
    TYPE_DATE: 时间类型
    QUERY_LIKE: 模糊查询
    QUERY_EQ: 相等查询
    REQUIRE: 需要
    DB_TO_SQLALCHEMY_TYPE_MAPPING: 数据库类型与sqlalchemy类型映射
    DB_TO_PYTHON_TYPE_MAPPING: 数据库类型与python类型映射
    """

    TPL_CRUD = 'crud'
    TPL_TREE = 'tree'
    TPL_SUB = 'sub'
    TREE_CODE = 'treeCode'
    TREE_PARENT_CODE = 'treeParentCode'
    TREE_NAME = 'treeName'
    PARENT_MENU_ID = 'parentMenuId'
    PARENT_MENU_NAME = 'parentMenuName'
    COLUMNTYPE_STR = (
        ['character varying', 'varchar', 'character', 'char']
        if DataBaseConfig.db_type == 'postgresql'
        else ['char', 'varchar', 'nvarchar', 'varchar2']
    )
    COLUMNTYPE_TEXT = (
        ['text', 'citext'] if DataBaseConfig.db_type == 'postgresql' else ['tinytext', 'text', 'mediumtext', 'longtext']
    )
    COLUMNTYPE_TIME = (
        [
            'date',
            'time',
            'time with time zone',
            'time without time zone',
            'timestamp',
            'timestamp with time zone',
            'timestamp without time zone',
            'interval',
        ]
        if DataBaseConfig.db_type == 'postgresql'
        else ['datetime', 'time', 'date', 'timestamp']
    )
    COLUMNTYPE_GEOMETRY = (
        ['point', 'line', 'lseg', 'box', 'path', 'polygon', 'circle']
        if DataBaseConfig.db_type == 'postgresql'
        else [
            'geometry',
            'point',
            'linestring',
            'polygon',
            'multipoint',
            'multilinestring',
            'multipolygon',
            'geometrycollection',
        ]
    )
    COLUMNTYPE_NUMBER = [
        'tinyint',
        'smallint',
        'mediumint',
        'int',
        'number',
        'integer',
        'bit',
        'bigint',
        'float',
        'double',
        'decimal',
    ]
    COLUMNNAME_NOT_ADD_SHOW = ['create_by', 'create_time']
    COLUMNNAME_NOT_EDIT_SHOW = ['update_by', 'update_time']
    COLUMNNAME_NOT_EDIT = ['id', 'create_by', 'create_time', 'del_flag']
    COLUMNNAME_NOT_LIST = ['id', 'create_by', 'create_time', 'del_flag', 'update_by', 'update_time']
    COLUMNNAME_NOT_QUERY = ['id', 'create_by', 'create_time', 'del_flag', 'update_by', 'update_time', 'remark']
    BASE_ENTITY = ['createBy', 'createTime', 'updateBy', 'updateTime', 'remark']
    TREE_ENTITY = ['parentName', 'parentId', 'orderNum', 'ancestors', 'children']
    HTML_INPUT = 'input'
    HTML_TEXTAREA = 'textarea'
    HTML_SELECT = 'select'
    HTML_RADIO = 'radio'
    HTML_CHECKBOX = 'checkbox'
    HTML_DATETIME = 'datetime'
    HTML_IMAGE_UPLOAD = 'imageUpload'
    HTML_FILE_UPLOAD = 'fileUpload'
    HTML_EDITOR = 'editor'
    TYPE_DECIMAL = 'Decimal'
    TYPE_DATE = ['date', 'time', 'datetime']
    QUERY_LIKE = 'LIKE'
    QUERY_EQ = 'EQ'
    REQUIRE = '1'
    DB_TO_SQLALCHEMY_TYPE_MAPPING = (
        {
            'boolean': 'Boolean',
            'smallint': 'SmallInteger',
            'integer': 'Integer',
            'bigint': 'BigInteger',
            'real': 'Float',
            'double precision': 'Float',
            'numeric': 'Numeric',
            'character varying': 'String',
            'character': 'String',
            'text': 'Text',
            'bytea': 'LargeBinary',
            'date': 'Date',
            'time': 'Time',
            'time with time zone': 'Time',
            'time without time zone': 'Time',
            'timestamp': 'DateTime',
            'timestamp with time zone': 'DateTime',
            'timestamp without time zone': 'DateTime',
            'interval': 'Interval',
            'json': 'JSON',
            'jsonb': 'JSONB',
            'uuid': 'Uuid',
            'inet': 'INET',
            'cidr': 'CIDR',
            'macaddr': 'MACADDR',
            'point': 'Geometry',
            'line': 'Geometry',
            'lseg': 'Geometry',
            'box': 'Geometry',
            'path': 'Geometry',
            'polygon': 'Geometry',
            'circle': 'Geometry',
            'bit': 'Bit',
            'bit varying': 'Bit',
            'tsvector': 'TSVECTOR',
            'tsquery': 'TSQUERY',
            'xml': 'String',
            'array': 'ARRAY',
            'composite': 'JSON',
            'enum': 'Enum',
            'range': 'Range',
            'money': 'Numeric',
            'pg_lsn': 'BigInteger',
            'txid_snapshot': 'String',
            'oid': 'BigInteger',
            'regproc': 'String',
            'regclass': 'String',
            'regtype': 'String',
            'regrole': 'String',
            'regnamespace': 'String',
            'int2vector': 'ARRAY',
            'oidvector': 'ARRAY',
            'pg_node_tree': 'Text',
        }
        if DataBaseConfig.db_type == 'postgresql'
        else {
            # 数值类型
            'TINYINT': 'SmallInteger',
            'SMALLINT': 'SmallInteger',
            'MEDIUMINT': 'Integer',
            'INT': 'Integer',
            'INTEGER': 'Integer',
            'BIGINT': 'BigInteger',
            'FLOAT': 'Float',
            'DOUBLE': 'Float',
            'DECIMAL': 'DECIMAL',
            'BIT': 'Integer',
            # 日期和时间类型
            'DATE': 'Date',
            'TIME': 'Time',
            'DATETIME': 'DateTime',
            'TIMESTAMP': 'TIMESTAMP',
            'YEAR': 'Integer',
            # 字符串类型
            'CHAR': 'CHAR',
            'VARCHAR': 'String',
            'TINYTEXT': 'Text',
            'TEXT': 'Text',
            'MEDIUMTEXT': 'Text',
            'LONGTEXT': 'Text',
            'BINARY': 'BINARY',
            'VARBINARY': 'VARBINARY',
            'TINYBLOB': 'LargeBinary',
            'BLOB': 'LargeBinary',
            'MEDIUMBLOB': 'LargeBinary',
            'LONGBLOB': 'LargeBinary',
            # 枚举和集合类型
            'ENUM': 'Enum',
            'SET': 'String',
            # JSON 类型
            'JSON': 'JSON',
            # 空间数据类型（需要扩展支持，如 GeoAlchemy2）
            'GEOMETRY': 'Geometry',  # 需要安装 geoalchemy2
            'POINT': 'Geometry',
            'LINESTRING': 'Geometry',
            'POLYGON': 'Geometry',
            'MULTIPOINT': 'Geometry',
            'MULTILINESTRING': 'Geometry',
            'MULTIPOLYGON': 'Geometry',
            'GEOMETRYCOLLECTION': 'Geometry',
        }
    )
    DB_TO_PYTHON_TYPE_MAPPING = (
        {
            'boolean': 'bool',
            'smallint': 'int',
            'integer': 'int',
            'bigint': 'int',
            'real': 'float',
            'double precision': 'float',
            'numeric': 'Decimal',
            'character varying': 'str',
            'character': 'str',
            'text': 'str',
            'bytea': 'bytes',
            'date': 'date',
            'time': 'time',
            'time with time zone': 'time',
            'time without time zone': 'time',
            'timestamp': 'datetime',
            'timestamp with time zone': 'datetime',
            'timestamp without time zone': 'datetime',
            'interval': 'timedelta',
            'json': 'dict',
            'jsonb': 'dict',
            'uuid': 'str',
            'inet': 'str',
            'cidr': 'str',
            'macaddr': 'str',
            'point': 'list',
            'line': 'list',
            'lseg': 'list',
            'box': 'list',
            'path': 'list',
            'polygon': 'list',
            'circle': 'list',
            'bit': 'int',
            'bit varying': 'int',
            'tsvector': 'str',
            'tsquery': 'str',
            'xml': 'str',
            'array': 'list',
            'composite': 'dict',
            'enum': 'str',
            'range': 'list',
            'money': 'Decimal',
            'pg_lsn': 'int',
            'txid_snapshot': 'str',
            'oid': 'int',
            'regproc': 'str',
            'regclass': 'str',
            'regtype': 'str',
            'regrole': 'str',
            'regnamespace': 'str',
            'int2vector': 'list',
            'oidvector': 'list',
            'pg_node_tree': 'str',
        }
        if DataBaseConfig.db_type == 'postgresql'
        else {
            # 数值类型
            'TINYINT': 'int',
            'SMALLINT': 'int',
            'MEDIUMINT': 'int',
            'INT': 'int',
            'INTEGER': 'int',
            'BIGINT': 'int',
            'FLOAT': 'float',
            'DOUBLE': 'float',
            'DECIMAL': 'Decimal',
            'BIT': 'int',
            # 日期和时间类型
            'DATE': 'date',
            'TIME': 'time',
            'DATETIME': 'datetime',
            'TIMESTAMP': 'datetime',
            'YEAR': 'int',
            # 字符串类型
            'CHAR': 'str',
            'VARCHAR': 'str',
            'TINYTEXT': 'str',
            'TEXT': 'str',
            'MEDIUMTEXT': 'str',
            'LONGTEXT': 'str',
            'BINARY': 'bytes',
            'VARBINARY': 'bytes',
            'TINYBLOB': 'bytes',
            'BLOB': 'bytes',
            'MEDIUMBLOB': 'bytes',
            'LONGBLOB': 'bytes',
            # 枚举和集合类型
            'ENUM': 'str',
            'SET': 'str',
            # JSON 类型
            'JSON': 'dict',
            # 空间数据类型（通常需要特殊处理）
            'GEOMETRY': 'bytes',
            'POINT': 'bytes',
            'LINESTRING': 'bytes',
            'POLYGON': 'bytes',
            'MULTIPOINT': 'bytes',
            'MULTILINESTRING': 'bytes',
            'MULTIPOLYGON': 'bytes',
            'GEOMETRYCOLLECTION': 'bytes',
        }
    )
