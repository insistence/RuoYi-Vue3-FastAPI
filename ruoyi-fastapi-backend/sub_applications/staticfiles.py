from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from config.env import UploadConfig


class SecureStaticFiles(StaticFiles):
    """
    安全静态文件服务类
    """

    DOWNLOAD_ONLY_EXTENSIONS = {'.html', '.htm'}

    async def get_response(self, path: str, scope: Scope) -> Response:
        """
        获取带有安全响应头的静态文件响应

        :param path: 静态文件路径
        :param scope: ASGI连接作用域
        :return: 静态文件响应
        """
        response = await super().get_response(path, scope)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if Path(path).suffix.lower() in self.DOWNLOAD_ONLY_EXTENSIONS:
            encoded_name = quote(Path(path).name)
            response.headers['Content-Type'] = 'application/octet-stream'
            response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoded_name}"
            response.headers['Content-Security-Policy'] = (
                "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            )
            response.headers['X-Frame-Options'] = 'DENY'
        return response


def mount_staticfiles(app: FastAPI) -> None:
    """
    挂载静态文件
    """
    app.mount(
        f'{UploadConfig.UPLOAD_PREFIX}',
        SecureStaticFiles(directory=f'{UploadConfig.UPLOAD_PATH}'),
        name='profile',
    )
