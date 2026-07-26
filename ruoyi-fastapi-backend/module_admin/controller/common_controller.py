from typing import Annotated
from uuid import UUID

from fastapi import BackgroundTasks, File, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.constant import ApiNamespace
from common.router import APIRouterPro
from common.vo import DynamicResponseModel
from module_admin.entity.vo.common_vo import UploadResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from utils.log_util import logger
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

common_controller = APIRouterPro(prefix='/common', order_num=16, tags=['通用模块'], dependencies=[PreAuthDependency()])


@common_controller.post(
    '/upload',
    summary='通用文件上传接口',
    description='用于上传文件',
    response_model=DynamicResponseModel[UploadResponseModel],
)
@ApiRateLimit(namespace=ApiNamespace.COMMON_UPLOAD, preset=ApiRateLimitPreset.COMMON_UPLOAD)
async def common_upload(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    upload_result = await CommonService.upload_service(request, query_db, current_user, file, access_type='public')
    logger.info('上传成功')

    return ResponseUtil.success(model_content=upload_result.result)


@common_controller.post(
    '/files/upload',
    summary='受保护文件上传接口',
    description='用于上传仅授权用户可以访问的受保护文件',
    response_model=DynamicResponseModel[UploadResponseModel],
)
@ApiRateLimit(namespace=ApiNamespace.COMMON_PRIVATE_UPLOAD, preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def common_private_upload(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    upload_result = await CommonService.upload_service(request, query_db, current_user, file, access_type='private')
    logger.info('受保护文件上传成功')

    return ResponseUtil.success(model_content=upload_result.result)


@common_controller.get(
    '/files/{file_id}/download/{display_name}',
    summary='已登记文件下载接口',
    description='用于根据文件ID下载已登记的公开或受保护文件',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回文件',
            'content': {
                'application/octet-stream': {},
            },
        },
        206: {'description': '分段返回文件'},
        416: {'description': '请求的字节范围不可满足'},
    },
)
@ApiRateLimit(namespace=ApiNamespace.COMMON_FILE_DOWNLOAD, preset=ApiRateLimitPreset.USER_RESOURCE_DOWNLOAD)
async def common_managed_file_download(
    request: Request,
    file_id: UUID,
    display_name: str,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    download_result = await CommonService.download_managed_file_services(
        request,
        query_db,
        current_user,
        str(file_id),
        range_header=request.headers.get('Range'),
    )
    logger.info(f'文件{file_id}下载成功')

    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type='application/octet-stream',
        status_code=206 if download_result.byte_range.is_partial else 200,
    )


@common_controller.get(
    '/download',
    summary='通用文件下载接口',
    description='用于下载下载目录中的文件',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回文件',
            'content': {
                'application/octet-stream': {},
            },
        },
        206: {'description': '分段返回文件'},
        416: {'description': '请求的字节范围不可满足'},
    },
)
async def common_download(
    request: Request,
    background_tasks: BackgroundTasks,
    file_name: Annotated[str, Query(alias='fileName')],
    delete: Annotated[bool, Query()],
) -> Response:
    download_result = await CommonService.download_services(
        background_tasks,
        file_name,
        delete,
        range_header=request.headers.get('Range'),
    )
    logger.info('下载成功')

    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type='application/octet-stream',
        status_code=206 if download_result.byte_range.is_partial else 200,
    )


@common_controller.get(
    '/download/resource',
    summary='通用资源文件下载接口',
    description='用于下载上传目录中的资源文件',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回文件',
            'content': {
                'application/octet-stream': {},
            },
        },
        206: {'description': '分段返回文件'},
        416: {'description': '请求的字节范围不可满足'},
    },
)
async def common_download_resource(request: Request, resource: Annotated[str, Query()]) -> Response:
    download_result = await CommonService.download_resource_services(
        resource,
        range_header=request.headers.get('Range'),
    )
    logger.info('下载成功')

    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type='application/octet-stream',
        status_code=206 if download_result.byte_range.is_partial else 200,
    )
