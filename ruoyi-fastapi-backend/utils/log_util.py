"""
@modifier: left666
@modify_time: 2025/9/25  9:00
"""
import os
import sys
import time
from loguru import logger as _logger


class LoggerInitializer:

    format_str = (
        '<green>{time:YYYY-MM-DD HH:mm:ss.S}</green> | '
        '<cyan>{trace_id}</cyan> | '
        '<level>{level: <8}</level> | '
        '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
        '<level>{message}</level>'
    )  # 自定义日志格式

    def __init__(self):
        self.log_path = os.path.join(os.getcwd(), 'logs')
        self.__ensure_log_directory_exists()
        # self.log_path_error = os.path.join(self.log_path, f'{time.strftime("%Y-%m-%d")}_error.log')

    def __ensure_log_directory_exists(self):
        """
        确保日志目录存在，如果不存在则创建
        """
        if not os.path.exists(self.log_path):
            os.mkdir(self.log_path)

    @staticmethod
    def __sift_out_common(log) -> bool:
        """
        筛选出非request日志，并添加trace_id
        """
        if log["level"].name != "request":
            from middlewares.trace_middleware import TraceCtx
            log['trace_id'] = TraceCtx.get_id()
            return True
        return False

    @staticmethod
    def __status_code_color(status_code: int) -> str:
        """根据状态码返回对应的颜色标签"""
        if status_code < 200:
            return "blue"  # 1xx 信息响应
        elif 200 <= status_code < 300:
            return "green"  # 2xx 成功
        elif 300 <= status_code < 400:
            return "cyan"  # 3xx 重定向
        elif 400 <= status_code < 500:
            return "yellow"  # 4xx 客户端错误
        else:
            return "red"  # 5xx 服务器错误

    def __format_request_log(self, log) -> str:
        """请求记录格式处理器"""
        status_code = log["extra"].get("status_code", 0)
        duration = log["extra"].get("duration", 0)
        if status_code == 0:
            return self.format_str
        color = self.__status_code_color(status_code)
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.S}</green> |- "
            "<level>{message}</level>"
            f"<{color}>  {status_code}</{color}>"
            f" -| <level>{duration}ms</level>\n"
        )

    def init_log(self):
        """
        初始化日志配置
        """
        _logger.level(name="request", no=23, color="<magenta>")  # 自定义等级(介于info与success之间)
        _logger.remove()  # 移除后重新添加sys.stderr, 目的: 控制台输出与文件日志内容和结构一致

        # 添加请求记录控制台输出
        _logger.add(
            sys.stderr,
            filter=lambda log: log["level"].name == "request",
            format=self.__format_request_log,
            colorize=True,  # 终端着色
            enqueue=True  # 启用异步安全的日志记录
        )
        # 添加请求记录文件
        _logger.add(
            os.path.join(self.log_path, f'request.log'),
            rotation="50 MB",  # 文件最大50MB
            retention=1,  # 只保留一个文件
            delay=True,  # 延迟到第一条记录消息时再创建文件
            filter=lambda log: log["level"].name == "request",
            format=self.__format_request_log,
            encoding="utf-8",
            enqueue=True
        )
        # 添加普通日志控制台输出
        _logger.add(
            sys.stderr,
            filter=self.__sift_out_common,
            format=self.format_str,
            colorize=True,
            enqueue=True
        )
        # 添加普通日志文件
        _logger.add(
            os.path.join(self.log_path, f'{time.strftime("%Y-%m-%d")}_app.log'),
            rotation="00:00",  # 每天午夜创建新文件
            retention=30,  # 保留30个文件
            delay=True,
            filter=self.__sift_out_common,
            format=self.format_str,
            encoding="utf-8"
        )

        return _logger


# 初始化日志处理器
log_initializer = LoggerInitializer()
logger = log_initializer.init_log()
