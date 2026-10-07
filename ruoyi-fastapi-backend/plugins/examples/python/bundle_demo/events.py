import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, status
from starlette.responses import StreamingResponse

from utils.time_util import TimezoneUtil

MAX_CURSOR_LENGTH = 2


def register_event_routes(app: FastAPI, *, permission: str = 'bundle_demo:view', interval: float = 0.5) -> None:
    """
    注册有限时长的事件流示例，通过数字游标演示显式恢复接收。

    :param app: 当前插件的 ASGI 子应用
    :param permission: 访问事件流所需的接口权限
    :param interval: 示例事件发送间隔，单位为秒
    :return: None
    """

    @app.get(
        '/api/events',
        summary='接收插件示例实时事件接口',
        description='返回最多 20 条编号事件；Last-Event-ID 指定最后收到的编号，重连仅补发后续编号',
        response_class=StreamingResponse,
    )
    async def events(request: Request, count: Annotated[int, Query(ge=1, le=20)] = 10) -> StreamingResponse:
        request.state.plugin_context.require_permission(permission)
        cursor = request.headers.get('last-event-id', '0')
        if not cursor.isascii() or not cursor.isdigit() or len(cursor) > MAX_CURSOR_LENGTH or int(cursor) > count:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail='事件游标无效')

        async def generate() -> AsyncIterator[str]:
            """
            逐条生成有界示例事件，由 ASGI 响应负责取消断开的请求。

            :return: 已编码的 SSE 事件片段
            """
            for index in range(int(cursor) + 1, count + 1):
                await asyncio.sleep(interval)
                data = json.dumps(
                    {'index': index, 'total': count, 'serverTime': TimezoneUtil.utc_now().isoformat()},
                    ensure_ascii=False,
                )
                yield f'id: {index}\nevent: tick\ndata: {data}\n\n'

        return StreamingResponse(
            generate(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'},
        )
