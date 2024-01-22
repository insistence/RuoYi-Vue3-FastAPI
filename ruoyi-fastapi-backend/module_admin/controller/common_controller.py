from fastapi import APIRouter, Request
from fastapi import Depends, File, Form, Query
from sqlalchemy.orm import Session
from config.env import CachePathConfig
from config.get_db import get_db
from module_admin.service.login_service import LoginService
from module_admin.service.common_service import *
from module_admin.service.config_service import ConfigService
from utils.response_util import *
from utils.log_util import *
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from typing import Optional


commonController = APIRouter(prefix='/common')


@commonController.post("/upload", dependencies=[Depends(LoginService.get_current_user), Depends(CheckUserInterfaceAuth('common'))])
async def common_upload(request: Request, taskPath: str = Form(), uploadId: str = Form(), file: UploadFile = File(...)):
    try:
        try:
            os.makedirs(os.path.join(CachePathConfig.PATH, taskPath, uploadId))
        except FileExistsError:
            pass
        CommonService.upload_service(CachePathConfig.PATH, taskPath, uploadId, file)
        logger.info('上传成功')
        return response_200(data={'filename': file.filename, 'path': f'/common/{CachePathConfig.PATHSTR}?taskPath={taskPath}&taskId={uploadId}&filename={file.filename}'}, message="上传成功")
    except Exception as e:
        logger.exception(e)
        return response_500(data="", message=str(e))


@commonController.post("/uploadForEditor", dependencies=[Depends(LoginService.get_current_user), Depends(CheckUserInterfaceAuth('common'))])
async def editor_upload(request: Request, baseUrl: str = Form(), uploadId: str = Form(), taskPath: str = Form(), file: UploadFile = File(...)):
    try:
        try:
            os.makedirs(os.path.join(CachePathConfig.PATH, taskPath, uploadId))
        except FileExistsError:
            pass
        CommonService.upload_service(CachePathConfig.PATH, taskPath, uploadId, file)
        logger.info('上传成功')
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                {
                    'errno': 0,
                    'data': {
                        'url': f'{baseUrl}/common/{CachePathConfig.PATHSTR}?taskPath={taskPath}&taskId={uploadId}&filename={file.filename}'
                    },
                }
            )
        )
    except Exception as e:
        logger.exception(e)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=jsonable_encoder(
                {
                    'errno': 1,
                    'message': str(e),
                }
            )
        )


@commonController.get(f"/{CachePathConfig.PATHSTR}")
async def common_download(request: Request, task_path: str = Query(alias='taskPath'), task_id: str = Query(alias='taskId'), filename: str = Query()):
    try:
        def generate_file():
            with open(os.path.join(CachePathConfig.PATH, task_path, task_id, filename), 'rb') as response_file:
                yield from response_file
        return streaming_response_200(data=generate_file())
    except Exception as e:
        logger.exception(e)
        return response_500(data="", message=str(e))


@commonController.get("/config/query/{config_key}")
async def query_system_config(request: Request, config_key: str):
    try:
        # 获取全量数据
        config_query_result = await ConfigService.query_config_list_from_cache_services(request.app.state.redis, config_key)
        logger.info('获取成功')
        return response_200(data=config_query_result, message="获取成功")
    except Exception as e:
        logger.exception(e)
        return response_500(data="", message=str(e))
