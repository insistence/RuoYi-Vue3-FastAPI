import json
import logging
import os
import sys
from typing import Any

from loguru import logger as _logger
from loguru._logger import Logger

from config.env import AppConfig, LogConfig
from middlewares.trace_middleware import TraceCtx
from utils.server_util import WorkerIdUtil


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        """
        拦截标准 logging 记录并转发到 Loguru

        :param record: 原生 logging 日志记录
        :return: None
        """
        try:
            level = _logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        _logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


class LoggerInitializer:
    def __init__(self) -> None:
        """
        初始化日志基础配置与运行时标识

        :return: None
        """
        self.worker_id = WorkerIdUtil.get_worker_id(LogConfig.log_worker_id)
        self.instance_id = LogConfig.log_instance_id
        self.service_name = LogConfig.log_service_name or AppConfig.app_name
        self._log_file_enabled = LogConfig.log_file_enabled
        self._log_base_dir = LogConfig.log_file_base_dir
        self._ensure_log_directory_exists()

    def _ensure_log_directory_exists(self) -> None:
        """
        确保日志目录存在

        :return: None
        """
        if not self._log_file_enabled:
            return
        if self._log_base_dir and not os.path.exists(self._log_base_dir):
            os.makedirs(self._log_base_dir, exist_ok=True)

    def _filter(self, record: dict) -> bool:
        """
        注入 Trace 上下文并控制启动阶段日志输出

        :param record: Loguru 日志记录字典
        :return: 是否允许输出日志
        """
        record['extra']['trace_id'] = TraceCtx.get_trace_id()
        record['extra']['request_id'] = TraceCtx.get_request_id()
        record['extra']['span_id'] = TraceCtx.get_span_id()
        record['extra']['path'] = TraceCtx.get_request_path()
        record['extra']['method'] = TraceCtx.get_request_method()
        record['extra']['worker_id'] = self.worker_id
        record['extra']['instance_id'] = self.instance_id
        record['extra']['service'] = self.service_name
        if record['extra'].get('startup_phase'):
            return bool(record['extra'].get('startup_log_enabled'))
        return True

    def _stdout_sink(self, message: Any) -> None:
        """
        将 Loguru 日志记录序列化为 JSON 并输出到 stdout

        :param message: Loguru 消息对象
        :return: None
        """
        record = message.record
        exception = None
        if record['exception']:
            exception = {
                'type': record['exception'].type.__name__ if record['exception'].type else None,
                'value': str(record['exception'].value) if record['exception'].value else None,
                'traceback': str(record['exception'].traceback) if record['exception'].traceback else None,
            }
        payload = {
            'timestamp': record['time'].isoformat(),
            'level': record['level'].name,
            'message': record['message'],
            'logger': record['name'],
            'trace_id': record['extra'].get('trace_id'),
            'request_id': record['extra'].get('request_id'),
            'span_id': record['extra'].get('span_id'),
            'worker_id': record['extra'].get('worker_id'),
            'instance_id': record['extra'].get('instance_id'),
            'service': record['extra'].get('service'),
            'method': record['extra'].get('method'),
            'path': record['extra'].get('path'),
            'module': record['module'],
            'function': record['function'],
            'line': record['line'],
            'exception': exception,
            'extra': record['extra'],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=str) + '\n')

    def _info_file_filter(self, record: dict) -> bool:
        """
        仅输出 INFO 级别日志到 info 文件

        :param record: Loguru 日志记录字典
        :return: 是否允许输出日志
        """
        return self._filter(record) and record['level'].name == 'INFO'

    def _error_file_filter(self, record: dict) -> bool:
        """
        输出 WARNING 及以上日志到 error 文件

        :param record: Loguru 日志记录字典
        :return: 是否允许输出日志
        """
        return self._filter(record) and record['level'].no >= logging.WARNING

    def _configure_logging(self) -> None:
        """
        统一接管标准 logging 与第三方日志输出

        :return: None
        """
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
        for logger_name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'fastapi'):
            logging.getLogger(logger_name).handlers = [InterceptHandler()]
            logging.getLogger(logger_name).propagate = False
        for logger_name in ('LiteLLM', 'litellm'):
            logging.getLogger(logger_name).setLevel(logging.WARNING)

    def init_log(self) -> Logger:
        """
        初始化 Loguru 输出与标准 logging 配置

        :return: 已配置的 Loguru Logger 实例
        """
        _logger.remove()
        info_log_path = os.path.join(self._log_base_dir, '{time:YYYY}', '{time:MM}', '{time:DD}', 'info.log')
        error_log_path = os.path.join(self._log_base_dir, '{time:YYYY}', '{time:MM}', '{time:DD}', 'error.log')
        if LogConfig.loguru_stdout:
            if LogConfig.loguru_json:
                _logger.add(
                    self._stdout_sink,
                    level=LogConfig.loguru_level,
                    enqueue=True,
                    filter=self._filter,
                )
            else:
                format_str = (
                    '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
                    '<cyan>{extra[trace_id]}</cyan> | '
                    '<magenta>{extra[span_id]}</magenta> | '
                    '<yellow>{extra[request_id]}</yellow> | '
                    '<blue>{extra[worker_id]}</blue> | '
                    '<level>{level: <8}</level> | '
                    '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
                    '<level>{message}</level>'
                )
                _logger.add(
                    sys.stdout,
                    level=LogConfig.loguru_level,
                    enqueue=True,
                    filter=self._filter,
                    format=format_str,
                )
        if self._log_file_enabled:
            _logger.add(
                info_log_path,
                level='INFO',
                rotation=LogConfig.loguru_rotation,
                retention=LogConfig.loguru_retention,
                compression=LogConfig.loguru_compression,
                enqueue=True,
                filter=self._info_file_filter,
                serialize=LogConfig.loguru_json,
            )
            _logger.add(
                error_log_path,
                level='WARNING',
                rotation=LogConfig.loguru_rotation,
                retention=LogConfig.loguru_retention,
                compression=LogConfig.loguru_compression,
                enqueue=True,
                filter=self._error_file_filter,
                serialize=LogConfig.loguru_json,
            )
        self._configure_logging()
        return _logger


# 初始化日志处理器
log_initializer = LoggerInitializer()
logger = log_initializer.init_log()
