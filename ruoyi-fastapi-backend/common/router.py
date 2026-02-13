import glob
import importlib
import os
import sys
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Annotated, Any, Literal

from annotated_doc import Doc
from fastapi import FastAPI, params
from fastapi.datastructures import Default
from fastapi.routing import APIRoute, APIRouter
from fastapi.utils import generate_unique_id
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Lifespan
from typing_extensions import deprecated

from config.env import AppConfig


class APIRouterPro(APIRouter):
    """
    `APIRouterPro` class, inherited from the `APIRouter` class, it has all the functions of `APIRouter` and provides some additional parameter settings.
    `APIRouter` class, used to group *path operations*, for example to structure
    an app in multiple files. It would then be included in the `FastAPI` app, or
    in another `APIRouter` (ultimately included in the app).

    Read more about it in the
    [FastAPI docs for Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

    ## Example

    ```python
    from common.router import APIRouterPro, FastAPI

    app = FastAPI()
    router = APIRouterPro()


    @router.get('/users/', tags=['users'])
    async def read_users():
        return [{'username': 'Rick'}, {'username': 'Morty'}]


    app.include_router(router)
    ```
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        prefix: Annotated[str, Doc('An optional path prefix for the router.')] = '',
        order_num: Annotated[int, Doc('An optional order number for the router.')] = 100,
        auto_register: Annotated[bool, Doc('An optional auto register flag for the router.')] = True,
        tags: Annotated[
            list[str | Enum] | None,
            Doc(
                """
                A list of tags to be applied to all the *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
            ),
        ] = None,
        dependencies: Annotated[
            Sequence[params.Depends] | None,
            Doc(
                """
                A list of dependencies (using `Depends()`) to be applied to all the
                *path operations* in this router.

                Read more about it in the
                [FastAPI docs for Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).
                """
            ),
        ] = None,
        default_response_class: Annotated[
            type[Response],
            Doc(
                """
                The default response class to be used.

                Read more in the
                [FastAPI docs for Custom Response - HTML, Stream, File, others](https://fastapi.tiangolo.com/advanced/custom-response/#default-response-class).
                """
            ),
        ] = Default(JSONResponse),
        responses: Annotated[
            dict[int | str, dict[str, Any]] | None,
            Doc(
                """
                Additional responses to be shown in OpenAPI.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Additional Responses in OpenAPI](https://fastapi.tiangolo.com/advanced/additional-responses/).

                And in the
                [FastAPI docs for Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).
                """
            ),
        ] = None,
        callbacks: Annotated[
            list[BaseRoute] | None,
            Doc(
                """
                OpenAPI callbacks that should apply to all *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for OpenAPI Callbacks](https://fastapi.tiangolo.com/advanced/openapi-callbacks/).
                """
            ),
        ] = None,
        routes: Annotated[
            list[BaseRoute] | None,
            Doc(
                """
                **Note**: you probably shouldn't use this parameter, it is inherited
                from Starlette and supported for compatibility.

                ---

                A list of routes to serve incoming HTTP and WebSocket requests.
                """
            ),
            deprecated(
                """
                You normally wouldn't use this parameter with FastAPI, it is inherited
                from Starlette and supported for compatibility.

                In FastAPI, you normally would use the *path operation methods*,
                like `router.get()`, `router.post()`, etc.
                """
            ),
        ] = None,
        redirect_slashes: Annotated[
            bool,
            Doc(
                """
                Whether to detect and redirect slashes in URLs when the client doesn't
                use the same format.
                """
            ),
        ] = True,
        default: Annotated[
            ASGIApp | None,
            Doc(
                """
                Default function handler for this router. Used to handle
                404 Not Found errors.
                """
            ),
        ] = None,
        dependency_overrides_provider: Annotated[
            Any | None,
            Doc(
                """
                Only used internally by FastAPI to handle dependency overrides.

                You shouldn't need to use it. It normally points to the `FastAPI` app
                object.
                """
            ),
        ] = None,
        route_class: Annotated[
            type[APIRoute],
            Doc(
                """
                Custom route (*path operation*) class to be used by this router.

                Read more about it in the
                [FastAPI docs for Custom Request and APIRoute class](https://fastapi.tiangolo.com/how-to/custom-request-and-route/#custom-apiroute-class-in-a-router).
                """
            ),
        ] = APIRoute,
        on_startup: Annotated[
            Sequence[Callable[[], Any]] | None,
            Doc(
                """
                A list of startup event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        on_shutdown: Annotated[
            Sequence[Callable[[], Any]] | None,
            Doc(
                """
                A list of shutdown event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        # the generic to Lifespan[AppType] is the type of the top level application
        # which the router cannot know statically, so we use typing.Any
        lifespan: Annotated[
            Lifespan[Any] | None,
            Doc(
                """
                A `Lifespan` context manager handler. This replaces `startup` and
                `shutdown` functions with a single context manager.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        deprecated: Annotated[
            bool | None,
            Doc(
                """
                Mark all *path operations* in this router as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
            ),
        ] = None,
        include_in_schema: Annotated[
            bool,
            Doc(
                """
                To include (or not) all the *path operations* in this router in the
                generated OpenAPI.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-parameters-from-openapi).
                """
            ),
        ] = True,
        generate_unique_id_function: Annotated[
            Callable[[APIRoute], str],
            Doc(
                """
                Customize the function used to generate unique IDs for the *path
                operations* shown in the generated OpenAPI.

                This is particularly useful when automatically generating clients or
                SDKs for your API.

                Read more about it in the
                [FastAPI docs about how to Generate Clients](https://fastapi.tiangolo.com/advanced/generate-clients/#custom-generate-unique-id-function).
                """
            ),
        ] = Default(generate_unique_id),
    ) -> None:
        self.order_num = order_num
        self.auto_register = auto_register
        super().__init__(
            prefix=prefix,
            tags=tags,
            dependencies=dependencies,
            default_response_class=default_response_class,
            responses=responses,
            callbacks=callbacks,
            routes=routes,
            redirect_slashes=redirect_slashes,
            default=default,
            dependency_overrides_provider=dependency_overrides_provider,
            route_class=route_class,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
            generate_unique_id_function=generate_unique_id_function,
        )


class RouterRegister:
    """
    路由注册器，用于自动注册所有controller目录下的路由
    """

    def __init__(self, app: FastAPI) -> None:
        """
        初始化路由注册器

        :param app: FastAPI对象
        """
        self.app = app
        # 获取项目根目录
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        sys.path.insert(0, self.project_root)

    def _find_controller_files(self) -> list[str]:
        """
        查找所有controller目录下的py文件

        :return: py文件路径列表
        """
        pattern = os.path.join(self.project_root, '*', 'controller', '[!_]*.py')
        files = glob.glob(pattern)
        # 去重并保持顺序 VSCode 调试模式 + Uvicorn 热重载 环境下，可能返回重复的文件路径。 ：os.path.join(self.project_root, '*', 'controller', '[!_]*.py') 中的 * 可能匹配到符号链接指向的同一物理目录，导致同一个文件通过不同路径（真实路径 vs 链接路径）被重复匹配。
        return sorted(dict.fromkeys(files))

    def _exclude_controller_file_and_manual_import_routers(
        self, all_file_names: list[str]
    ) -> tuple[list[str], list[tuple[str, APIRouter]]]:
        """
        排除指定的controller文件，并手动导入路由实例（性能比较烂的朋友在debug+reload的时候可以快一点）

        :param file_name: 要排除的controller文件名
        :return: 路由实例列表
        """
        exclude_file_names = [
            'ai_chat_controller.py',
            'ai_model_controller.py',
        ]

        if not exclude_file_names:
            return all_file_names, []

        all_file_names_exclude = []  # 过滤后的文件名列表
        all_file_names_exclude = [
            fname for fname in all_file_names if not any(exclude in fname for exclude in exclude_file_names)
        ]

        routers = []
        # 手动导入路由实例
        from module_ai.controller import ai_chat_controller, ai_model_controller  # noqa: PLC0415

        # 这个文件太大了，电脑性能很差的用户动态导入会很久5s+
        routers.append(('module_ai.controller.ai_chat_controller', ai_chat_controller.ai_chat_controller))
        routers.append(('module_ai.controller.ai_model_controller', ai_model_controller.ai_model_controller))

        return all_file_names_exclude, routers

    def _import_module_and_get_routers(self, controller_files: list[str]) -> list[tuple[str, APIRouter]]:
        """
        导入模块并获取路由实例

        :param controller_files: controller目录下的py文件路径列表
        :return: 路由实例列表
        """
        routers = []

        if AppConfig.app_manual_import_routers:
            controller_files, manual_routers = self._exclude_controller_file_and_manual_import_routers(controller_files)
            routers.extend(manual_routers)

        for file_path in controller_files:
            # 计算模块路径
            relative_path = os.path.relpath(file_path, self.project_root)
            module_name = relative_path.replace(os.sep, '.')[:-3]

            # 动态导入模块
            module = importlib.import_module(module_name)
            # 直接遍历模块__dict__，只检查模块自身定义的属性
            for attr_name, attr in module.__dict__.items():
                # 对于APIRouterPro实例，只有当auto_register=True时才添加
                if isinstance(attr, APIRouterPro):
                    if attr.auto_register:
                        routers.append((attr_name, attr))
                # 对于APIRouter实例，直接添加
                elif isinstance(attr, APIRouter):
                    routers.append((attr_name, attr))
        return routers

    def _sort_routers(self, routers: list[tuple[str, APIRouter]]) -> list[tuple[str, APIRouter]]:
        """
        按规则排序路由

        :param routers: 路由实例列表
        :return: 排序后的路由实例列表
        """

        # 按规则排序路由
        def sort_key(item: tuple[str, APIRouter]) -> tuple[Literal[0], int, str] | tuple[Literal[1], str]:
            attr_name, router = item
            # APIRouterPro实例按order_num排序，序号越小越靠前
            if isinstance(router, APIRouterPro):
                return (0, router.order_num, attr_name)
            # APIRouter实例按变量名首字母排序
            return (1, attr_name)

        return sorted(routers, key=sort_key)

    def _register_routers_to_app(self, routers: list[tuple[str, APIRouter]]) -> None:
        """
        将路由注册到FastAPI应用

        :param routers: 排序后的路由实例列表
        :return: None
        """
        for _attr_name, router in routers:
            self.app.include_router(router=router)

    def register_routers(self) -> None:
        """
        自动注册所有controller目录下的路由

        :return: None
        """
        # 查找所有controller目录下的py文件
        controller_files = self._find_controller_files()
        # 导入模块并获取路由实例
        routers = self._import_module_and_get_routers(controller_files)
        # 按规则排序路由
        sorted_routers = self._sort_routers(routers)
        # 注册路由到FastAPI应用
        self._register_routers_to_app(sorted_routers)


def auto_register_routers(app: FastAPI) -> None:
    """
    自动注册所有controller目录下的路由

    :param app: FastAPI对象
    :return: None
    """
    # 使用路由注册器进行注册
    router_register = RouterRegister(app)
    router_register.register_routers()
