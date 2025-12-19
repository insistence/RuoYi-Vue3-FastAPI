import contextvars
from uuid import uuid4

CTX_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar('request-id', default='')


class TraceCtx:
    @staticmethod
    def set_id() -> str:
        _id = uuid4().hex
        CTX_REQUEST_ID.set(_id)
        return _id

    @staticmethod
    def get_id() -> str:
        return CTX_REQUEST_ID.get()
