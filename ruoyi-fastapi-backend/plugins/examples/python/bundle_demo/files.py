import hashlib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette import status
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException
from starlette.types import Message

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FORM_BYTES = 64 * 1024


class FileInspection(BaseModel):
    """
    返回文件元数据与摘要，不保存上传内容。
    """

    filename: str = Field(description='客户端提交的文件名，仅作展示')
    size: int = Field(description='文件实际字节数')
    sha256: str = Field(description='文件内容的 SHA-256 摘要')


def register_file_routes(app: FastAPI, *, permission: str = 'bundle_demo:view') -> None:
    """
    注册有界上传检查和固定报表下载接口，便于验证文件桥的真实 HTTP 链路。

    :param app: 插件所属的子应用
    :param permission: 两个文件接口要求的插件权限
    :return: None
    """

    @app.post(
        '/api/files/inspect',
        summary='检查插件上传文件接口',
        description='校验权限后接收最多 10 MiB 的单文件，返回摘要且不持久化内容',
    )
    async def inspect_file(request: Request) -> FileInspection:
        request.state.plugin_context.require_permission(permission)
        received = 0

        async def limited_receive() -> Message:
            """
            累计实际请求体大小，在解析 multipart 之前执行硬上限检查。

            :return: 当前 ASGI 消息
            """
            nonlocal received
            message = await request.receive()
            received += len(message.get('body', b''))
            if received > MAX_FILE_BYTES + MAX_FORM_BYTES:
                # 使用解析器异常以关闭已创建的临时文件，再在外层转换为 413。
                raise MultiPartException('上传请求超过大小限制')
            return message

        bounded_request = Request(request.scope, limited_receive)
        try:
            async with bounded_request.form(max_files=1, max_fields=16, max_part_size=MAX_FORM_BYTES) as form:
                file = form.get('file')
                if not isinstance(file, UploadFile):
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, '缺少 file 文件字段')
                if file.size is None or file.size > MAX_FILE_BYTES:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, '文件不能超过 10 MiB')
                digest = hashlib.sha256()
                while content := await file.read(MAX_FORM_BYTES):
                    digest.update(content)
                return FileInspection(filename=file.filename or 'upload.bin', size=file.size, sha256=digest.hexdigest())
        except StarletteHTTPException as exc:
            if received > MAX_FILE_BYTES + MAX_FORM_BYTES:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, '上传请求超过大小限制') from exc
            raise

    @app.get(
        '/api/files/report',
        summary='下载插件示例报表接口',
        description='校验插件权限后下载固定 CSV 示例，响应不包含用户或配置数据',
        response_class=Response,
    )
    async def download_report(request: Request) -> Response:
        request.state.plugin_context.require_permission(permission)
        return Response(
            '\ufeffname,value\nmode,authenticated-plugin\n',
            media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename="plugin-report.csv"', 'Cache-Control': 'no-store'},
        )
