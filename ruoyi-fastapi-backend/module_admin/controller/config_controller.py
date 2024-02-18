from fastapi import APIRouter
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.config_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import *
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


configController = APIRouter(prefix='/system/config', dependencies=[Depends(LoginService.get_current_user)])


@configController.get("/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:config:list'))])
async def get_system_config_list(request: Request, config_page_query: ConfigPageQueryModel = Depends(ConfigPageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        config_page_query_result = ConfigService.get_config_list_services(query_db, config_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=config_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.post("", dependencies=[Depends(CheckUserInterfaceAuth('system:config:add'))])
@log_decorator(title='参数管理', business_type=1)
async def add_system_config(request: Request, add_config: ConfigModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_config.create_by = current_user.user.user_name
        add_config.update_by = current_user.user.user_name
        add_config_result = await ConfigService.add_config_services(request, query_db, add_config)
        if add_config_result.is_success:
            logger.info(add_config_result.message)
            return ResponseUtil.success(msg=add_config_result.message)
        else:
            logger.warning(add_config_result.message)
            return ResponseUtil.failure(msg=add_config_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.put("", dependencies=[Depends(CheckUserInterfaceAuth('system:config:edit'))])
@log_decorator(title='参数管理', business_type=2)
async def edit_system_config(request: Request, edit_config: ConfigModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_config.update_by = current_user.user.user_name
        edit_config.update_time = datetime.now()
        edit_config_result = await ConfigService.edit_config_services(request, query_db, edit_config)
        if edit_config_result.is_success:
            logger.info(edit_config_result.message)
            return ResponseUtil.success(msg=edit_config_result.message)
        else:
            logger.warning(edit_config_result.message)
            return ResponseUtil.failure(msg=edit_config_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.delete("/refreshCache", dependencies=[Depends(CheckUserInterfaceAuth('system:config:remove'))])
@log_decorator(title='参数管理', business_type=2)
async def refresh_system_config(request: Request, query_db: Session = Depends(get_db)):
    try:
        refresh_config_result = await ConfigService.refresh_sys_config_services(request, query_db)
        if refresh_config_result.is_success:
            logger.info(refresh_config_result.message)
            return ResponseUtil.success(msg=refresh_config_result.message)
        else:
            logger.warning(refresh_config_result.message)
            return ResponseUtil.failure(msg=refresh_config_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.delete("/{config_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:config:remove'))])
@log_decorator(title='参数管理', business_type=3)
async def delete_system_config(request: Request, config_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_config = DeleteConfigModel(configIds=config_ids)
        delete_config_result = await ConfigService.delete_config_services(request, query_db, delete_config)
        if delete_config_result.is_success:
            logger.info(delete_config_result.message)
            return ResponseUtil.success(msg=delete_config_result.message)
        else:
            logger.warning(delete_config_result.message)
            return ResponseUtil.failure(msg=delete_config_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.get("/{config_id}", response_model=ConfigModel, dependencies=[Depends(CheckUserInterfaceAuth('system:config:query'))])
async def query_detail_system_config(request: Request, config_id: int, query_db: Session = Depends(get_db)):
    try:
        config_detail_result = ConfigService.config_detail_services(query_db, config_id)
        logger.info(f'获取config_id为{config_id}的信息成功')
        return ResponseUtil.success(data=config_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.get("/configKey/{config_key}")
async def query_system_config(request: Request, config_key: str):
    try:
        # 获取全量数据
        config_query_result = await ConfigService.query_config_list_from_cache_services(request.app.state.redis, config_key)
        logger.info('获取成功')
        return ResponseUtil.success(msg=config_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@configController.post("/export", dependencies=[Depends(CheckUserInterfaceAuth('system:config:export'))])
@log_decorator(title='参数管理', business_type=5)
async def export_system_config_list(request: Request, config_page_query: ConfigPageQueryModel = Depends(ConfigPageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        config_query_result = ConfigService.get_config_list_services(query_db, config_page_query, is_page=False)
        config_export_result = ConfigService.export_config_list_services(config_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(config_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
