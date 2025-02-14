class CommonConstant:
    """
    常用常量

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
    """

    """单表（增删改查）"""
    TPL_CRUD = 'crud'

    """树表（增删改查）"""
    TPL_TREE = 'tree'

    """主子表（增删改查）"""
    TPL_SUB = 'sub'

    """树编码字段"""
    TREE_CODE = 'treeCode'

    """树父编码字段"""
    TREE_PARENT_CODE = 'treeParentCode'

    """树名称字段"""
    TREE_NAME = 'treeName'

    """上级菜单ID字段"""
    PARENT_MENU_ID = 'parentMenuId'

    """上级菜单名称字段"""
    PARENT_MENU_NAME = 'parentMenuName'

    """数据库字符串类型"""
    COLUMNTYPE_STR = ['char', 'varchar', 'nvarchar', 'varchar2']

    """数据库文本类型"""
    COLUMNTYPE_TEXT = ['tinytext', 'text', 'mediumtext', 'longtext']

    """数据库时间类型"""
    COLUMNTYPE_TIME = ['datetime', 'time', 'date', 'timestamp']

    """数据库数字类型"""
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

    """页面不需要编辑字段"""
    COLUMNNAME_NOT_EDIT = ['id', 'create_by', 'create_time', 'del_flag']

    """页面不需要显示的列表字段"""
    COLUMNNAME_NOT_LIST = ['id', 'create_by', 'create_time', 'del_flag', 'update_by', 'update_time']

    """页面不需要查询字段"""
    COLUMNNAME_NOT_QUERY = ['id', 'create_by', 'create_time', 'del_flag', 'update_by', 'update_time', 'remark']

    """Entity基类字段"""
    BASE_ENTITY = ['createBy', 'createTime', 'updateBy', 'updateTime', 'remark']

    """Tree基类字段"""
    TREE_ENTITY = ['parentName', 'parentId', 'orderNum', 'ancestors', 'children']

    """文本框"""
    HTML_INPUT = 'input'

    """文本域"""
    HTML_TEXTAREA = 'textarea'

    """下拉框"""
    HTML_SELECT = 'select'

    """单选框"""
    HTML_RADIO = 'radio'

    """复选框"""
    HTML_CHECKBOX = 'checkbox'

    """日期控件"""
    HTML_DATETIME = 'datetime'

    """图片上传控件"""
    HTML_IMAGE_UPLOAD = 'imageUpload'

    """文件上传控件"""
    HTML_FILE_UPLOAD = 'fileUpload'

    """富文本控件"""
    HTML_EDITOR = 'editor'

    """高精度计算类型"""
    TYPE_DECIMAL = 'Decimal'

    """时间类型"""
    TYPE_DATE = ['date', 'time', 'datetime']

    """模糊查询"""
    QUERY_LIKE = 'LIKE'

    """相等查询"""
    QUERY_EQ = 'EQ'

    """需要"""
    REQUIRE = '1'

    MYSQL_TO_SQLALCHEMY_TYPE_MAPPING = {
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
        'GEOMETRY': 'geoalchemy2.Geometry',  # 需要安装 geoalchemy2
        'POINT': 'geoalchemy2.Geometry',
        'LINESTRING': 'geoalchemy2.Geometry',
        'POLYGON': 'geoalchemy2.Geometry',
        'MULTIPOINT': 'geoalchemy2.Geometry',
        'MULTILINESTRING': 'geoalchemy2.Geometry',
        'MULTIPOLYGON': 'geoalchemy2.Geometry',
        'GEOMETRYCOLLECTION': 'geoalchemy2.Geometry',
    }

    MYSQL_TO_PYTHON_TYPE_MAPPING = {
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
