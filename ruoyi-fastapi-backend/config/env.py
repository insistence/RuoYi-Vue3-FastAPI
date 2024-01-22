import os


class JwtConfig:
    """
    Jwt配置
    """
    SECRET_KEY = "b01c66dc2c58dc6a0aabfe2144256be36226de378bf87f72c0c795dda67f4d55"
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 1440
    REDIS_TOKEN_EXPIRE_MINUTES = 30


class DataBaseConfig:
    """
    数据库配置
    """
    HOST = "127.0.0.1"
    PORT = 3306
    USERNAME = 'root'
    PASSWORD = 'mysqlroot'
    DB = 'ruoyi-fastapi'


class RedisConfig:
    """
    Redis配置
    """
    HOST = "127.0.0.1"
    PORT = 6379
    USERNAME = ''
    PASSWORD = ''
    DB = 2


class CachePathConfig:
    """
    缓存目录配置
    """
    PATH = os.path.join(os.path.abspath(os.getcwd()), 'caches')
    PATHSTR = 'caches'


class RedisInitKeyConfig:
    """
    系统内置Redis键名
    """
    ACCESS_TOKEN = {'key': 'access_token', 'remark': '登录令牌信息'}
    SYS_DICT = {'key': 'sys_dict', 'remark': '数据字典'}
    SYS_CONFIG = {'key': 'sys_config', 'remark': '配置信息'}
    CAPTCHA_CODES = {'key': 'captcha_codes', 'remark': '图片验证码'}
    ACCOUNT_LOCK = {'key': 'account_lock', 'remark': '用户锁定'}
    PASSWORD_ERROR_COUNT = {'key': 'password_error_count', 'remark': '密码错误次数'}
    SMS_CODE = {'key': 'sms_code', 'remark': '短信验证码'}
