import ast
import json
import logging
import os
import re
import sys
import traceback
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger as _logger
from loguru._logger import Logger

from config.env import AppConfig, LogConfig
from middlewares.trace_middleware import TraceCtx
from utils.server_util import WorkerIdUtil


def _split_field_tokens(field_name: str) -> tuple[str, ...]:
    """
    拆分字段名为文本匹配用的 token

    :param field_name: 原始字段名
    :return: token 元组
    """
    separated_name = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', field_name)
    normalized_name = re.sub(r'[^A-Za-z0-9]+', ' ', separated_name)
    return tuple(token.lower() for token in normalized_name.split() if token)


def _build_text_key_pattern(field_name: str) -> str:
    """
    构建文本日志中的字段名匹配正则，自动兼容 snake_case / camelCase / kebab-case / dot.case

    :param field_name: 原始字段名
    :return: 正则片段
    """
    tokens = _split_field_tokens(field_name)
    if not tokens:
        return re.escape(field_name)
    return r'[\s._-]*'.join(re.escape(token) for token in tokens)


def _build_text_assignment_patterns(key_pattern: str) -> list[re.Pattern[str]]:
    """
    构建文本日志中的键值对匹配正则

    :param key_pattern: 字段名正则片段
    :return: 正则列表
    """
    if not key_pattern:
        return []
    return [
        re.compile(
            rf'(?P<prefix>(?P<key_quote>[\'"]?)(?P<key>(?:{key_pattern}))(?P=key_quote)\s*[:=]\s*)'
            r'(?P<quote>[\'"])(?P<value>.*?)(?P=quote)',
            re.IGNORECASE,
        ),
        re.compile(
            rf'(?P<prefix>(?P<key_quote>[\'"]?)(?P<key>(?:{key_pattern}))(?P=key_quote)\s*[:=]\s*)'
            r'(?P<quote>[\'"]?)(?P<value>[^\'"\s,;]+)(?P=quote)',
            re.IGNORECASE,
        ),
    ]


class LogSanitizer:
    """
    日志脱敏工具
    """

    _MASK = LogConfig.log_mask_placeholder
    _PHONE_MIN_LENGTH = 7
    _PHONE_PREFIX_LENGTH = 3
    _PHONE_SUFFIX_LENGTH = 4
    _EMAIL_SHORT_LOCAL_LENGTH = 2
    _IPV4_PARTS = 4
    _IPV4_VISIBLE_PARTS = 3
    _IPV6_MASK_THRESHOLD = 2
    _IPV6_VISIBLE_PARTS = 2
    _SENSITIVE_FIELDS = {
        re.sub(r'[^a-z0-9]', '', item.lower())
        for item in (field.strip() for field in LogConfig.log_mask_fields.split(','))
        if item
    }
    _TEXT_SENSITIVE_FIELDS = tuple(field.strip() for field in LogConfig.log_mask_fields.split(',') if field.strip())
    _TEXT_SENSITIVE_KEY_PATTERN = '|'.join(
        sorted({_build_text_key_pattern(field_name) for field_name in _TEXT_SENSITIVE_FIELDS}, key=len, reverse=True)
    )
    _PARTIAL_MASK_FIELDS = {
        re.sub(r'[^a-z0-9]', '', item.lower())
        for item in (field.strip() for field in LogConfig.log_partial_mask_fields.split(','))
        if item
    }
    _TEXT_PARTIAL_FIELDS = tuple(
        field.strip() for field in LogConfig.log_partial_mask_fields.split(',') if field.strip()
    )
    _TEXT_PARTIAL_KEY_PATTERN = '|'.join(
        sorted({_build_text_key_pattern(field_name) for field_name in _TEXT_PARTIAL_FIELDS}, key=len, reverse=True)
    )
    _CONFIG_SECRET_PATTERNS = [
        re.compile(pattern.strip(), re.IGNORECASE)
        for pattern in LogConfig.log_config_secret_patterns.split(',')
        if pattern.strip()
    ]
    _KV_PATTERNS = [
        re.compile(
            r'(?P<prefix>authorization\s*[:=]\s*)(?P<quote>[\'"]?)(?P<value>bearer\s+[^\s\'",;]+|[^\s\'",;]+)(?P=quote)',
            re.IGNORECASE,
        ),
        *_build_text_assignment_patterns(_TEXT_SENSITIVE_KEY_PATTERN),
        re.compile(r'(?P<prefix>Bearer\s+)(?P<value>[A-Za-z0-9\-._~+/]+=*)', re.IGNORECASE),
    ]
    _PARTIAL_KV_PATTERNS = _build_text_assignment_patterns(_TEXT_PARTIAL_KEY_PATTERN)
    _LOGIN_CODE_PATTERN = re.compile(r'^[A-Za-z0-9]{4,8}$')

    @classmethod
    def sanitize_data(cls, data: Any, field_name: str | None = None) -> Any:
        """
        对日志数据进行脱敏

        :param data: 原始日志数据
        :param field_name: 当前字段名
        :return: 脱敏后的数据
        """
        if not LogConfig.log_mask_enabled:
            return data
        if data is None:
            return None
        if hasattr(data, 'model_dump'):
            return cls.sanitize_data(data.model_dump(by_alias=True, exclude_none=True), field_name)
        if isinstance(data, Mapping):
            return cls._sanitize_mapping(data)
        if isinstance(data, str):
            return cls._sanitize_string(data, field_name)
        if isinstance(data, bytes):
            return f'<bytes:{len(data)}>'
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return [cls.sanitize_data(item, field_name) for item in data]
        return data

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """
        对普通文本日志进行脱敏

        :param text: 原始文本
        :return: 脱敏后的文本
        """
        if not LogConfig.log_mask_enabled:
            return text
        if not isinstance(text, str):
            return text
        sanitized_text = cls._sanitize_string(text)
        return sanitized_text if isinstance(sanitized_text, str) else json.dumps(sanitized_text, ensure_ascii=False)

    @classmethod
    def _sanitize_mapping(cls, data: Mapping[Any, Any]) -> dict[Any, Any]:
        """
        对字典类型数据进行脱敏

        :param data: 字典数据
        :return: 脱敏后的字典
        """
        sanitized: dict[Any, Any] = {}
        normalized_map = {cls._normalize_key(str(key)): value for key, value in data.items()}

        for key, value in data.items():
            key_str = str(key)
            normalized_key = cls._normalize_key(key_str)
            if cls._should_fully_mask_field(normalized_key, value, normalized_map):
                sanitized[key] = cls._MASK
            elif normalized_key in cls._PARTIAL_MASK_FIELDS and isinstance(value, str):
                sanitized[key] = cls._mask_partial_value(value, normalized_key)
            else:
                sanitized[key] = cls.sanitize_data(value, key_str)

        config_key = normalized_map.get('configkey')
        if isinstance(config_key, str) and cls._is_secret_config_key(config_key):
            for key in data:
                if cls._normalize_key(str(key)) == 'configvalue':
                    sanitized[key] = cls._MASK

        return sanitized

    @classmethod
    def _sanitize_string(cls, value: str, field_name: str | None = None) -> Any:
        """
        对字符串数据进行脱敏

        :param value: 字符串值
        :param field_name: 当前字段名
        :return: 脱敏后的字符串或结构化数据
        """
        normalized_field = cls._normalize_key(field_name or '')
        if normalized_field in cls._SENSITIVE_FIELDS:
            return cls._MASK
        if normalized_field in cls._PARTIAL_MASK_FIELDS:
            return cls._mask_partial_value(value, normalized_field)

        stripped_value = value.strip()
        if stripped_value and stripped_value[0] in '{[':
            try:
                parsed_value = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                try:
                    parsed_value = ast.literal_eval(value)
                except (SyntaxError, ValueError):
                    pass
                else:
                    return cls._dump_sanitized_structured_text(
                        cls.sanitize_data(parsed_value, field_name),
                        original_text=value,
                    )
            else:
                return cls._dump_sanitized_structured_text(
                    cls.sanitize_data(parsed_value, field_name),
                    original_text=value,
                )

        sanitized_text = value
        for pattern in cls._KV_PATTERNS:
            sanitized_text = pattern.sub(cls._replace_text_secret, sanitized_text)
        for pattern in cls._PARTIAL_KV_PATTERNS:
            sanitized_text = pattern.sub(cls._replace_text_partial_secret, sanitized_text)

        if '验证码' in sanitized_text:
            sanitized_text = re.sub(r'(验证码(?:为|是)?\s*)([A-Za-z0-9]{4,8})', rf'\1{cls._MASK}', sanitized_text)

        return sanitized_text

    @classmethod
    def _replace_text_secret(cls, match: re.Match[str]) -> str:
        """
        替换文本中的敏感值

        :param match: 正则匹配对象
        :return: 脱敏后的文本
        """
        prefix = match.group('prefix')
        quote = match.groupdict().get('quote', '')
        if quote is None:
            quote = ''
        return f'{prefix}{quote}{cls._MASK}{quote}'

    @classmethod
    def _replace_text_partial_secret(cls, match: re.Match[str]) -> str:
        """
        替换文本中的部分脱敏字段值

        :param match: 正则匹配对象
        :return: 脱敏后的文本
        """
        prefix = match.group('prefix')
        quote = match.groupdict().get('quote', '')
        if quote is None:
            quote = ''
        normalized_key = cls._normalize_key(match.groupdict().get('key', ''))
        masked_value = cls._mask_partial_value(match.group('value'), normalized_key)
        return f'{prefix}{quote}{masked_value}{quote}'

    @staticmethod
    def _dump_sanitized_structured_text(sanitized_value: Any, original_text: str) -> Any:
        """
        将脱敏后的结构化数据恢复为文本，并尽量保持原始换行风格

        :param sanitized_value: 脱敏后的结构化数据
        :param original_text: 原始文本
        :return: 文本或原始值
        """
        if isinstance(sanitized_value, (dict, list)):
            indent = 2 if '\n' in original_text or '\r' in original_text else None
            return json.dumps(sanitized_value, ensure_ascii=False, indent=indent)
        return sanitized_value

    @classmethod
    def _should_fully_mask_field(
        cls, normalized_key: str, value: Any, full_mapping: Mapping[str, Any] | None = None
    ) -> bool:
        """
        判断字段是否需要全量脱敏

        :param normalized_key: 标准化后的字段名
        :param value: 字段值
        :param full_mapping: 当前层级的完整字段映射
        :return: 是否需要全量脱敏
        """
        if normalized_key in cls._SENSITIVE_FIELDS:
            return True
        if normalized_key in {'captchacode', 'smscode'}:
            return True
        if normalized_key == 'code' and isinstance(value, str):
            sibling_keys = set((full_mapping or {}).keys())
            if 'uuid' in sibling_keys and cls._LOGIN_CODE_PATTERN.fullmatch(value):
                return True
        return False

    @classmethod
    def _is_secret_config_key(cls, config_key: str) -> bool:
        """
        判断参数键是否属于敏感配置

        :param config_key: 参数键
        :return: 是否敏感
        """
        return any(pattern.search(config_key) for pattern in cls._CONFIG_SECRET_PATTERNS)

    @classmethod
    def _mask_partial_value(cls, value: str, normalized_field: str) -> str:
        """
        对部分字段进行部分脱敏

        :param value: 原始值
        :param normalized_field: 标准化后的字段名
        :return: 脱敏后的值
        """
        if normalized_field in {'phonenumber', 'phone', 'mobile'}:
            return cls._mask_phone(value)
        if normalized_field == 'email':
            return cls._mask_email(value)
        if normalized_field in {'ip', 'ipaddr', 'operip', 'loginip'}:
            return cls._mask_ip(value)
        return cls._MASK

    @staticmethod
    def _normalize_key(field_name: str) -> str:
        """
        标准化字段名

        :param field_name: 原始字段名
        :return: 标准化字段名
        """
        return re.sub(r'[^a-z0-9]', '', field_name.lower())

    @classmethod
    def _mask_phone(cls, value: str) -> str:
        """
        手机号脱敏

        :param value: 原始手机号
        :return: 脱敏后的手机号
        """
        digits = re.sub(r'\D', '', value)
        if len(digits) < cls._PHONE_MIN_LENGTH:
            return cls._MASK
        return f'{digits[: cls._PHONE_PREFIX_LENGTH]}****{digits[-cls._PHONE_SUFFIX_LENGTH :]}'

    @classmethod
    def _mask_email(cls, value: str) -> str:
        """
        邮箱脱敏

        :param value: 原始邮箱
        :return: 脱敏后的邮箱
        """
        if '@' not in value:
            return cls._MASK
        local_part, domain = value.split('@', 1)
        masked_local = (
            f'{local_part[:1]}***'
            if len(local_part) <= cls._EMAIL_SHORT_LOCAL_LENGTH
            else f'{local_part[:1]}***{local_part[-1:]}'
        )
        return f'{masked_local}@{domain}'

    @classmethod
    def _mask_ip(cls, value: str) -> str:
        """
        IP地址脱敏

        :param value: 原始IP
        :return: 脱敏后的IP
        """
        if '.' in value:
            parts = value.split('.')
            if len(parts) == cls._IPV4_PARTS:
                return '.'.join([*parts[: cls._IPV4_VISIBLE_PARTS], '*'])
        if ':' in value:
            parts = value.split(':')
            if len(parts) > cls._IPV6_MASK_THRESHOLD:
                return ':'.join([*parts[: cls._IPV6_VISIBLE_PARTS], '*', '*'])
        return cls._MASK


class InterceptHandler(logging.Handler):
    target_logger = _logger

    def emit(self, record: logging.LogRecord) -> None:
        """
        拦截标准 logging 记录并转发到 Loguru

        :param record: 原生 logging 日志记录
        :return: None
        """
        try:
            level = self.target_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        self.target_logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


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
        startup_phase = record['extra'].get('startup_phase')
        startup_log_enabled = record['extra'].get('startup_log_enabled')
        record['extra'] = LogSanitizer.sanitize_data(record['extra'])
        if startup_phase:
            return bool(startup_log_enabled)
        return True

    @staticmethod
    def _get_exception_value_text(exception: Any) -> str | None:
        """
        获取脱敏后的异常值文本

        :param exception: Loguru 异常对象
        :return: 脱敏后的异常值文本
        """
        if not exception or not exception.value:
            return None
        return LogSanitizer.sanitize_text(str(exception.value))

    def _get_exception_traceback_text(self, exception: Any) -> str | None:
        """
        获取脱敏后的异常堆栈文本

        :param exception: Loguru 异常对象
        :return: 脱敏后的异常堆栈文本
        """
        if not exception or not exception.traceback:
            return None
        if isinstance(exception.traceback, str):
            traceback_text = exception.traceback
        elif exception.type and exception.value:
            traceback_text = ''.join(traceback.format_exception(exception.type, exception.value, exception.traceback))
        else:
            traceback_text = str(exception.traceback)
        return LogSanitizer.sanitize_text(traceback_text.rstrip())

    def _build_plain_exception_suffix(self, record: dict) -> str:
        """
        构建普通文本日志使用的异常后缀

        :param record: Loguru 日志记录字典
        :return: 异常后缀文本
        """
        exception_text = self._get_exception_traceback_text(record.get('exception'))
        return f'\n{exception_text}' if exception_text else ''

    def _build_json_payload(self, record: dict) -> dict:
        """
        构建统一的 JSON 日志结构

        :param record: Loguru 日志记录字典
        :return: JSON 日志结构
        """
        exception = None
        if record['exception']:
            exception = {
                'type': record['exception'].type.__name__ if record['exception'].type else None,
                'value': self._get_exception_value_text(record['exception']),
                'traceback': self._get_exception_traceback_text(record['exception']),
            }
        return {
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

    def _json_log_formatter(self, record: dict) -> str:
        """
        将 Loguru 日志记录格式化为 JSON 文本

        :param record: Loguru 日志记录字典
        :return: JSON 格式文本
        """
        return json.dumps(self._build_json_payload(record), ensure_ascii=False, default=str) + '\n'

    def _plain_log_formatter(self, record: dict) -> str:
        """
        将 Loguru 日志记录格式化为普通文本，并追加脱敏后的异常堆栈

        :param record: Loguru 日志记录字典
        :return: 普通文本格式模板
        """
        record['extra']['sanitized_exception'] = self._build_plain_exception_suffix(record)
        return (
            '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
            '<cyan>{extra[trace_id]}</cyan> | '
            '<magenta>{extra[span_id]}</magenta> | '
            '<yellow>{extra[request_id]}</yellow> | '
            '<blue>{extra[worker_id]}</blue> | '
            '<level>{level: <8}</level> | '
            '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
            '<level>{message}</level>{extra[sanitized_exception]}'
        )

    def _patch_record(self, record: dict) -> dict:
        """
        在日志落地前统一脱敏

        :param record: Loguru 日志记录字典
        :return: 脱敏后的日志记录字典
        """
        record['message'] = LogSanitizer.sanitize_text(record['message'])
        return record

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
        configured_logger = _logger.patch(self._patch_record)
        InterceptHandler.target_logger = configured_logger
        configured_logger.remove()
        info_log_path = os.path.join(self._log_base_dir, '{time:YYYY}', '{time:MM}', '{time:DD}', 'info.log')
        error_log_path = os.path.join(self._log_base_dir, '{time:YYYY}', '{time:MM}', '{time:DD}', 'error.log')
        if LogConfig.loguru_stdout:
            if LogConfig.loguru_json:
                configured_logger.add(
                    sys.stdout,
                    level=LogConfig.loguru_level,
                    enqueue=True,
                    filter=self._filter,
                    format=self._json_log_formatter,
                )
            else:
                configured_logger.add(
                    sys.stdout,
                    level=LogConfig.loguru_level,
                    enqueue=True,
                    filter=self._filter,
                    format=self._plain_log_formatter,
                )
        if self._log_file_enabled:
            if LogConfig.loguru_json:
                configured_logger.add(
                    info_log_path,
                    level='INFO',
                    rotation=LogConfig.loguru_rotation,
                    retention=LogConfig.loguru_retention,
                    compression=LogConfig.loguru_compression,
                    enqueue=True,
                    filter=self._info_file_filter,
                    serialize=False,
                    format=self._json_log_formatter,
                )
                configured_logger.add(
                    error_log_path,
                    level='WARNING',
                    rotation=LogConfig.loguru_rotation,
                    retention=LogConfig.loguru_retention,
                    compression=LogConfig.loguru_compression,
                    enqueue=True,
                    filter=self._error_file_filter,
                    serialize=False,
                    format=self._json_log_formatter,
                )
            else:
                configured_logger.add(
                    info_log_path,
                    level='INFO',
                    rotation=LogConfig.loguru_rotation,
                    retention=LogConfig.loguru_retention,
                    compression=LogConfig.loguru_compression,
                    enqueue=True,
                    filter=self._info_file_filter,
                    format=self._plain_log_formatter,
                )
                configured_logger.add(
                    error_log_path,
                    level='WARNING',
                    rotation=LogConfig.loguru_rotation,
                    retention=LogConfig.loguru_retention,
                    compression=LogConfig.loguru_compression,
                    enqueue=True,
                    filter=self._error_file_filter,
                    format=self._plain_log_formatter,
                )
        self._configure_logging()
        return configured_logger


# 初始化日志处理器
log_initializer = LoggerInitializer()
logger = log_initializer.init_log()
