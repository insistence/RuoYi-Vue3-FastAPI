import json
import mimetypes
import re
from html import escape
from pathlib import Path
from urllib.parse import quote

from starlette import status
from starlette._utils import get_route_path
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import FileResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from plugins.core.manifest.v2 import FrontendBundleManifest

_MIME_TYPES = {
    '.html': 'text/html',
    '.htm': 'text/html',
    '.js': 'text/javascript',
    '.mjs': 'text/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.map': 'application/json',
    '.svg': 'image/svg+xml',
    '.wasm': 'application/wasm',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
}
_RESERVED_FALLBACK_PATHS = frozenset({'api', 'assets', 'ws', 'docs', 'redoc'})
_HEAD_TAG = re.compile(r'<head(?:\s[^>]*)?>', re.IGNORECASE)
_HTML_TAG = re.compile(r'<html(?:\s[^>]*)?>', re.IGNORECASE)
_DOCTYPE_TAG = re.compile(r'<!doctype[^>]*>', re.IGNORECASE)
_FIRST_PRINTABLE_CHARACTER = 32


class PluginBundleASGI:
    """
    仅为 /ui 命名空间提供资源；必须包装在 PluginGatewayASGI 内。

    构建目录应在部署后保持只读。此类只负责静态交付，不签发会话、不公开资源，
    也不改变外层传输加密策略。lifespan 和非 UI 请求始终委派原始子应用。
    """

    def __init__(
        self,
        child_app: ASGIApp,
        plugin_id: str,
        plugin_root: Path,
        bundle_manifest: FrontendBundleManifest,
    ) -> None:
        """
        初始化插件前端资源交付器并校验构建目录和入口。

        :param child_app: 接收非 UI 请求的原始插件 ASGI 应用
        :param plugin_id: 插件 ID
        :param plugin_root: 插件资源根目录
        :param bundle_manifest: 插件前端构建产物声明
        :return: None
        """
        self.child_app = child_app
        self.plugin_id = plugin_id
        self.plugin_root = Path(plugin_root).resolve(strict=True)
        self.bundle_manifest = bundle_manifest
        self.bundle_root = self._resolve_declared_path(self.plugin_root, bundle_manifest.directory)
        if not self.bundle_root.is_dir():
            raise ValueError('插件 bundle 目录不存在')
        self.entry_path = self._resolve_declared_path(self.bundle_root, bundle_manifest.entry)
        if not self.entry_path.is_file():
            raise ValueError('插件 bundle 入口不存在')

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        交付 UI 静态资源，并将其他请求委派给原始子应用。

        :param scope: ASGI 请求作用域
        :param receive: ASGI 消息接收函数
        :param send: ASGI 消息发送函数
        :return: None
        """
        if scope['type'] != 'http':
            await self.child_app(scope, receive, send)
            return
        route_path = get_route_path(scope)
        if route_path != '/ui' and not route_path.startswith('/ui/'):
            await self.child_app(scope, receive, send)
            return
        if scope['method'] not in {'GET', 'HEAD'}:
            response = Response(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                headers={**self._headers('no-store'), 'Allow': 'GET, HEAD'},
            )
        elif route_path == '/ui':
            location = self._base_paths(scope)['uiBase']
            if scope.get('query_string'):
                location += '?' + scope['query_string'].decode('latin-1')
            response = RedirectResponse(location, headers=self._headers('no-store'))
        else:
            response = await run_in_threadpool(self._resource_response, scope, route_path[4:])
        await response(scope, receive, send)

    def _resource_response(self, scope: Scope, resource_path: str) -> Response:
        """
        校验资源路径并生成文件响应或允许的页面回退响应。

        :param scope: ASGI 请求作用域
        :param resource_path: 相对于 UI 命名空间的请求资源路径
        :return: 静态资源、HTML 页面或访问错误响应
        """
        accepts_html = self._accepts_html(scope)
        relative_path = resource_path.rstrip('/')
        if resource_path and not self._safe_parts(relative_path):
            return self._not_found()
        candidate = self.entry_path if not resource_path else self.bundle_root / relative_path
        try:
            candidate = candidate.resolve()
            if not candidate.is_relative_to(self.bundle_root):
                return self._not_found()
            if candidate.is_dir():
                return self._not_found()
            if not candidate.is_file():
                if not self._allows_fallback(relative_path, accepts_html):
                    return self._not_found()
                candidate = self._resolve_declared_path(self.bundle_root, self.bundle_manifest.entry)
            elif resource_path.endswith('/'):
                return self._not_found()
            if not candidate.is_file():
                return self._not_found()
            media_type = _MIME_TYPES.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0]
            if media_type == 'text/html':
                if not accepts_html:
                    return Response(status_code=status.HTTP_406_NOT_ACCEPTABLE, headers=self._headers('no-store'))
                html = candidate.read_text(encoding='utf-8')
                if candidate == self.entry_path:
                    html = self._inject_config(html, scope)
                content = html.encode('utf-8')
                return Response(
                    content=content if scope['method'] == 'GET' else b'',
                    media_type='text/html',
                    headers={**self._headers('no-store'), 'Content-Length': str(len(content))},
                )
            return FileResponse(
                candidate,
                media_type=media_type or 'application/octet-stream',
                headers=self._headers('no-cache'),
            )
        except (OSError, ValueError, RuntimeError):
            return self._not_found()

    def _allows_fallback(self, path: str, accepts_html: bool) -> bool:
        """
        判断缺失资源是否允许回退到单页应用入口。

        :param path: 相对于构建目录的请求路径
        :param accepts_html: 请求是否接受 HTML 响应
        :return: 是否允许执行页面回退
        """
        parts = path.split('/')
        return (
            self.bundle_manifest.spa_fallback
            and accepts_html
            and parts[0].lower() not in _RESERVED_FALLBACK_PATHS
            and all('.' not in part for part in parts)
        )

    def _inject_config(self, html: str, scope: Scope) -> str:
        """
        向入口页面注入资源基址和经过转义的插件配置。

        :param html: 插件入口页面的 HTML 内容
        :param scope: 包含实际挂载路径的 ASGI 请求作用域
        :return: 注入插件配置后的 HTML 内容
        """
        paths = self._base_paths(scope)
        config = json.dumps({'pluginId': self.plugin_id, **paths}, ensure_ascii=True)
        # JSON 位于 HTML raw-text 元素中，转义 < 可阻止 </script> 提前结束数据块。
        for character, escaped in (('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026')):
            config = config.replace(character, escaped)
        injected = (
            f'<base href="{escape(paths["uiBase"], quote=True)}">'
            f'<script id="ruoyi-plugin-config" type="application/json">{config}</script>'
        )
        head = _HEAD_TAG.search(html)
        if head:
            return html[: head.end()] + injected + html[head.end() :]
        # 兼容省略 head 的 HTML；保留 doctype，避免把正常页面切换到 quirks mode。
        opening = _HTML_TAG.search(html) or _DOCTYPE_TAG.search(html)
        position = opening.end() if opening else 0
        return html[:position] + f'<head>{injected}</head>' + html[position:]

    @staticmethod
    def _base_paths(scope: Scope) -> dict[str, str]:
        """
        根据实际挂载路径生成插件页面和接口基址。

        :param scope: ASGI 请求作用域
        :return: 页面和接口基址字典
        """
        mount_path = quote(scope.get('root_path', '').rstrip('/'), safe='/')
        return {'uiBase': f'{mount_path}/ui/', 'apiBase': f'{mount_path}/api/'}

    @staticmethod
    def _accepts_html(scope: Scope) -> bool:
        """
        检查 Accept 请求头是否明确接受有效权重的 HTML 类型。

        :param scope: ASGI 请求作用域
        :return: 请求是否接受 HTML 响应
        """
        for item in Headers(scope=scope).get('accept', '').split(','):
            media_type, *parameters = item.strip().lower().split(';')
            if media_type != 'text/html':
                continue
            quality = next((part.strip()[2:] for part in parameters if part.strip().startswith('q=')), '1')
            try:
                if 0 < float(quality) <= 1:
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _safe_parts(path: str) -> bool:
        """
        检查相对资源路径的各级名称是否满足安全限制。

        :param path: 待检查的相对资源路径
        :return: 路径各级名称是否安全
        """
        return bool(path) and all(
            part
            and not part.startswith('.')
            and not part.endswith(('.', ' '))
            and not any(character in '<>:"\\|?*' or ord(character) < _FIRST_PRINTABLE_CHARACTER for character in part)
            for part in path.split('/')
        )

    @classmethod
    def _resolve_declared_path(cls, root: Path, relative_path: str) -> Path:
        """
        解析清单声明的资源路径并校验真实路径边界。

        :param root: 允许访问的资源根目录
        :param relative_path: 清单声明的相对资源路径
        :return: 位于允许目录内的资源绝对路径
        """
        if not cls._safe_parts(relative_path):
            raise ValueError('插件 bundle 资源路径非法')
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError('插件 bundle 资源路径越界')
        return path

    @staticmethod
    def _headers(cache_control: str) -> dict[str, str]:
        """
        生成静态资源的缓存控制和同源安全响应头。

        :param cache_control: 当前资源的缓存控制策略
        :return: 静态资源响应头字典
        """
        return {
            'Cache-Control': cache_control,
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'Content-Security-Policy': "frame-ancestors 'self'",
            'Cross-Origin-Resource-Policy': 'same-origin',
        }

    @classmethod
    def _not_found(cls) -> Response:
        """
        生成禁止缓存的资源不存在响应。

        :return: 携带安全响应头的 HTTP 404 响应
        """
        return Response(status_code=status.HTTP_404_NOT_FOUND, headers=cls._headers('no-store'))
