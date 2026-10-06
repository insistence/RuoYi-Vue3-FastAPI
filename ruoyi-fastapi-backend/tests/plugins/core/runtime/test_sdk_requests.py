import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from starlette import status

from middlewares.trace_middleware.ctx import CTX_REQUEST_ID
from plugins.core.sdk import PluginHostContext, PluginRequestContext, plugin_endpoint


class ReportBody(BaseModel):
    """验证原生和 Python 回调共享的业务输入数据。"""

    name: str = Field(min_length=2)
    count: int = Field(ge=1)


def endpoint_app(tmp_path: Path, callback: Any, **options: Any) -> FastAPI:
    """创建只使用宿主签发身份的 SDK 接口测试应用。"""
    app = FastAPI()
    context = PluginRequestContext(PluginHostContext('sdk_demo', tmp_path), object(), frozenset({'sdk_demo:view'}))

    @app.middleware('http')
    async def inject(request: Request, call_next: Any) -> Any:
        request.state.plugin_context = context
        return await call_next(request)

    app.add_api_route(
        '/reports/{report_id}',
        plugin_endpoint(callback, permission='sdk_demo:view', **options),
        methods=['GET', 'POST'],
    )
    return app


@pytest.mark.asyncio
async def test_endpoint_exposes_typed_body_multi_value_query_and_host_trace(tmp_path: Path) -> None:
    """请求数据保留重复参数，模型输出转换为可供原生代码消费的 JSON。"""
    callback = AsyncMock(side_effect=lambda context: context.request.to_payload())
    app = endpoint_app(tmp_path, callback, body_model=ReportBody)
    token = CTX_REQUEST_ID.set('host-request-123')
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post(
                '/reports/7?tag=alpha&tag=beta&empty=',
                json={'name': 'report', 'count': '3'},
                headers={'authorization': 'Bearer secret-token', 'cookie': 'private-cookie'},
            )
    finally:
        CTX_REQUEST_ID.reset(token)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        'method': 'POST',
        'path': '/reports/7',
        'pathParams': {'report_id': '7'},
        'query': {'tag': ['alpha', 'beta'], 'empty': ['']},
        'body': {'name': 'report', 'count': 3},
    }
    assert callback.await_args.args[0].request_id == 'host-request-123'
    assert 'secret-token' not in response.text
    assert 'private-cookie' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('content', 'content_type', 'expected'),
    [
        (b'{broken', 'application/json', status.HTTP_400_BAD_REQUEST),
        (b'{"value": NaN}', 'application/json', status.HTTP_400_BAD_REQUEST),
        (b'{"value": Infinity}', 'application/json', status.HTTP_400_BAD_REQUEST),
        (b'{}', 'text/plain', status.HTTP_415_UNSUPPORTED_MEDIA_TYPE),
    ],
)
async def test_endpoint_rejects_invalid_json_before_callback(
    tmp_path: Path, content: bytes, content_type: str, expected: int
) -> None:
    """非法 JSON 或错误媒体类型不会进入业务回调。"""
    callback = AsyncMock()
    app = endpoint_app(tmp_path, callback, json_body=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/reports/7', content=content, headers={'content-type': content_type})
    assert response.status_code == expected
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_endpoint_limits_streamed_body_without_trusting_content_length(tmp_path: Path) -> None:
    """分块请求同样按接收字节数受限，不依赖 Content-Length。"""
    callback = AsyncMock()
    app = endpoint_app(tmp_path, callback, json_body=True, max_body_bytes=8)

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"a":'
        yield b'"too large"}'

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/reports/7', content=chunks(), headers={'content-type': 'application/json'})
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_model_validation_does_not_echo_sensitive_input(tmp_path: Path) -> None:
    """模型错误只返回字段位置和规则，不反射请求值。"""
    callback = AsyncMock()
    app = endpoint_app(tmp_path, callback, body_model=ReportBody)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/reports/7', json={'name': 'x', 'count': 'never-echo-this'})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert 'never-echo-this' not in response.text
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_permission_check_precedes_reading_body_and_legacy_adapter_leaves_body_unread(tmp_path: Path) -> None:
    """未授权请求不读取请求体；默认适配器保持原有不读取请求体的行为。"""
    receive = AsyncMock(side_effect=AssertionError('body must not be read'))
    context = PluginRequestContext(PluginHostContext('sdk_demo', tmp_path), object())
    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/reports/7',
        'query_string': b'',
        'headers': [],
        'state': {'plugin_context': context},
    }
    callback = AsyncMock(return_value={})
    from fastapi import HTTPException  # noqa: PLC0415

    with pytest.raises(HTTPException) as denied:
        await plugin_endpoint(callback, permission='sdk_demo:view', json_body=True)(Request(scope, receive))
    assert denied.value.status_code == status.HTTP_403_FORBIDDEN
    await plugin_endpoint(callback, permission='sdk_demo:view')(
        Request(
            {
                **scope,
                'state': {'plugin_context': PluginRequestContext(context.host, object(), frozenset({'sdk_demo:view'}))},
            },
            receive,
        )
    )
    assert callback.await_args.args[0].request.body is None
    receive.assert_not_called()


@pytest.mark.asyncio
async def test_payload_copy_does_not_mutate_callback_request(tmp_path: Path) -> None:
    """原生调用方修改导出的 JSON 副本不会修改上下文内的原始请求数据。"""
    callback = AsyncMock(return_value={})
    app = endpoint_app(tmp_path, callback, json_body=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        await client.post('/reports/7', json={'nested': [1, 2]})
    context = callback.await_args.args[0]
    payload = context.request.to_payload()
    payload['body']['nested'].append(3)
    assert context.request.body == {'nested': [1, 2]}
    with pytest.raises(TypeError):
        context.request.path_params['report_id'] = '8'


@pytest.mark.parametrize('limit', [0, -1, True, 1.5])
def test_invalid_body_limits_fail_at_registration(limit: Any) -> None:
    """不合法限制必须在注册阶段失败。"""
    with pytest.raises(ValueError, match='正整数'):
        plugin_endpoint(AsyncMock(), permission='sdk_demo:view', max_body_bytes=limit)


@pytest.mark.asyncio
async def test_request_cancellation_reaches_callback(tmp_path: Path) -> None:
    """适配器继续传播 asyncio 取消，允许业务释放资源。"""
    entered = asyncio.Event()
    stopped = asyncio.Event()

    async def callback(context: PluginRequestContext) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    app = endpoint_app(tmp_path, callback)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        task = asyncio.create_task(client.get('/reports/7'))
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stopped.is_set()
