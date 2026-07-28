import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import Text

from config.env import LogConfig
from module_admin.dao.file_access_dao import FileAccessLogDao
from module_admin.entity.do.file_do import SysFileAccessLog
from module_admin.entity.vo.file_vo import FileAccessLogModel
from module_admin.service.file_access_service import FileAuditService
from module_admin.service.log_service import LogAggregatorService, LogQueueService

FILE_SIZE = 12
BATCH_FILE_COUNT = 2
LONG_OPERATION_DETAIL_LENGTH = 3000


class AsyncSessionContext:
    """测试用异步数据库会话上下文。"""

    def __init__(self, session: SimpleNamespace) -> None:
        self.session = session

    async def __aenter__(self) -> SimpleNamespace:
        return self.session

    async def __aexit__(self, exc_type: type | None, exc_value: BaseException | None, traceback: object) -> None:
        return None


def make_file_access_log() -> FileAccessLogModel:
    return FileAccessLogModel(
        fileId='file-id',
        action='download',
        actorUserId=10,
        actorName='user10',
        result='completed',
        requestId='request-id',
        traceId='trace-id',
        ipAddress='127.0.0.1',
        userAgent='pytest',
        bytesSent=FILE_SIZE,
        operationDetail='{"newStatus":"active"}',
        accessTime=datetime(2026, 7, 19, 12, 0, 0),
    )


def test_file_access_log_operation_detail_uses_unbounded_text_type() -> None:
    operation_detail_column = SysFileAccessLog.__table__.c.operation_detail

    assert isinstance(operation_detail_column.type, Text)
    assert operation_detail_column.type.length is None


def test_file_access_log_is_enqueued_to_redis_stream() -> None:
    redis = SimpleNamespace(xadd=AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))

    with (
        patch('module_admin.service.log_service.TraceCtx.get_request_id', return_value='request-id'),
        patch('module_admin.service.log_service.TraceCtx.get_trace_id', return_value='trace-id'),
        patch('module_admin.service.log_service.TraceCtx.get_span_id', return_value='span-id'),
    ):
        asyncio.run(LogQueueService.enqueue_file_access_log(request, make_file_access_log(), 'file:download:completed'))

    redis.xadd.assert_awaited_once()
    stream_name, event = redis.xadd.await_args.args
    assert stream_name == LogConfig.log_stream_key
    assert event['event_type'] == 'file_access'
    payload = json.loads(event['payload'])
    assert payload['fileId'] == 'file-id'
    assert payload['result'] == 'completed'
    assert payload['bytesSent'] == FILE_SIZE
    assert payload['operationDetail'] == '{"newStatus":"active"}'


def test_file_access_log_event_is_persisted_and_acknowledged() -> None:
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    redis = SimpleNamespace(set=AsyncMock(return_value=True), xack=AsyncMock(), delete=AsyncMock())
    file_access_log = make_file_access_log()
    messages = [
        (
            '1-0',
            {
                'event_type': 'file_access',
                'event_id': 'event-id',
                'payload': json.dumps(file_access_log.model_dump(by_alias=True, exclude_none=True), default=str),
            },
        )
    ]

    with (
        patch(
            'module_admin.service.log_service.AsyncSessionLocal',
            return_value=AsyncSessionContext(session),
        ),
        patch.object(FileAccessLogDao, 'add_file_access_log_dao', new_callable=AsyncMock) as add_file_access_log,
    ):
        asyncio.run(LogAggregatorService._process_messages(redis, LogConfig.log_stream_key, messages))

    add_file_access_log.assert_awaited_once()
    saved_log = add_file_access_log.await_args.args[1]
    assert saved_log.file_id == 'file-id'
    assert saved_log.result == 'completed'
    assert saved_log.operation_detail == '{"newStatus":"active"}'
    session.commit.assert_awaited_once()
    redis.xack.assert_awaited_once_with(LogConfig.log_stream_key, LogConfig.log_stream_group, '1-0')


def test_file_audit_batch_events_use_independent_deduplication_keys() -> None:
    redis = SimpleNamespace(xadd=AsyncMock())
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis)),
        headers={'User-Agent': 'pytest'},
        client=SimpleNamespace(host='127.0.0.1'),
    )
    current_user = SimpleNamespace(user=SimpleNamespace(user_id=10, user_name='user10'))

    async def enqueue_batch() -> None:
        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            'file-id-1',
            'transfer',
            'completed',
            operation_detail={'previousOwnerUserId': 10, 'newOwnerUserId': 20},
        )
        await FileAuditService.enqueue_file_audit(
            request,
            current_user,
            'file-id-2',
            'transfer',
            'completed',
            operation_detail={'previousOwnerUserId': 10, 'newOwnerUserId': 20},
        )

    with (
        patch('module_admin.service.file_access_service.TraceCtx.get_request_id', return_value='request-id'),
        patch('module_admin.service.file_access_service.TraceCtx.get_trace_id', return_value='trace-id'),
        patch('module_admin.service.log_service.TraceCtx.get_request_id', return_value='request-id'),
        patch('module_admin.service.log_service.TraceCtx.get_trace_id', return_value='trace-id'),
        patch('module_admin.service.log_service.TraceCtx.get_span_id', return_value='span-id'),
    ):
        asyncio.run(enqueue_batch())

    assert redis.xadd.await_count == BATCH_FILE_COUNT
    first_event = redis.xadd.await_args_list[0].args[1]
    second_event = redis.xadd.await_args_list[1].args[1]
    assert first_event['event_id'] != second_event['event_id']
    assert json.loads(first_event['payload'])['operationDetail'] == ('{"previousOwnerUserId":10,"newOwnerUserId":20}')


def test_file_audit_operation_detail_is_not_truncated() -> None:
    reason = 'a' * LONG_OPERATION_DETAIL_LENGTH
    serialized_detail = FileAuditService._serialize_operation_detail({'reason': reason})

    parsed_detail = json.loads(serialized_detail)
    assert parsed_detail['reason'] == reason
