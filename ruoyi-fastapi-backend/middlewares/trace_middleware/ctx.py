import contextvars
from uuid import uuid4

CTX_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar('trace-id', default='')
CTX_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar('request-id', default='')
CTX_SPAN_ID: contextvars.ContextVar[str] = contextvars.ContextVar('span-id', default='')
CTX_REQUEST_PATH: contextvars.ContextVar[str] = contextvars.ContextVar('request-path', default='')
CTX_REQUEST_METHOD: contextvars.ContextVar[str] = contextvars.ContextVar('request-method', default='')


class TraceCtx:
    @staticmethod
    def set_trace_id() -> str:
        _id = uuid4().hex
        CTX_TRACE_ID.set(_id)
        return _id

    @staticmethod
    def get_trace_id() -> str:
        return CTX_TRACE_ID.get()

    @staticmethod
    def set_request_id() -> str:
        _id = uuid4().hex
        CTX_REQUEST_ID.set(_id)
        return _id

    @staticmethod
    def get_request_id() -> str:
        return CTX_REQUEST_ID.get()

    @staticmethod
    def set_span_id() -> str:
        _id = uuid4().hex
        CTX_SPAN_ID.set(_id)
        return _id

    @staticmethod
    def get_span_id() -> str:
        return CTX_SPAN_ID.get()

    @staticmethod
    def set_request_path(path: str) -> None:
        CTX_REQUEST_PATH.set(path)

    @staticmethod
    def get_request_path() -> str:
        return CTX_REQUEST_PATH.get()

    @staticmethod
    def set_request_method(method: str) -> None:
        CTX_REQUEST_METHOD.set(method)

    @staticmethod
    def get_request_method() -> str:
        return CTX_REQUEST_METHOD.get()

    @staticmethod
    def clear() -> None:
        CTX_TRACE_ID.set('')
        CTX_REQUEST_ID.set('')
        CTX_SPAN_ID.set('')
        CTX_REQUEST_PATH.set('')
        CTX_REQUEST_METHOD.set('')
