from fastapi import APIRouter
from fastapi import Depends
from config.get_db import get_db
from module_admin.service.login_service import LoginService, CurrentUserModel
from module_admin.service.dict_service import *
from utils.response_util import *
from utils.log_util import *
from utils.page_util import PageResponseModel
from utils.common_util import bytes2file_response
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.annotation.log_annotation import log_decorator


dictController = APIRouter(prefix='/system/dict', dependencies=[Depends(LoginService.get_current_user)])


@dictController.get("/type/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:list'))])
async def get_system_dict_type_list(request: Request, dict_type_page_query: DictTypePageQueryModel = Depends(DictTypePageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        dict_type_page_query_result = DictTypeService.get_dict_type_list_services(query_db, dict_type_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=dict_type_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.post("/type", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:add'))])
@log_decorator(title='字典管理', business_type=1)
async def add_system_dict_type(request: Request, add_dict_type: DictTypeModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_dict_type.create_by = current_user.user.user_name
        add_dict_type.update_by = current_user.user.user_name
        add_dict_type_result = await DictTypeService.add_dict_type_services(request, query_db, add_dict_type)
        if add_dict_type_result.is_success:
            logger.info(add_dict_type_result.message)
            return ResponseUtil.success(msg=add_dict_type_result.message)
        else:
            logger.warning(add_dict_type_result.message)
            return ResponseUtil.failure(msg=add_dict_type_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.put("/type", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:edit'))])
@log_decorator(title='字典管理', business_type=2)
async def edit_system_dict_type(request: Request, edit_dict_type: DictTypeModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_dict_type.update_by = current_user.user.user_name
        edit_dict_type.update_time = datetime.now()
        edit_dict_type_result = await DictTypeService.edit_dict_type_services(request, query_db, edit_dict_type)
        if edit_dict_type_result.is_success:
            logger.info(edit_dict_type_result.message)
            return ResponseUtil.success(msg=edit_dict_type_result.message)
        else:
            logger.warning(edit_dict_type_result.message)
            return ResponseUtil.failure(msg=edit_dict_type_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.delete("/type/refreshCache", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@log_decorator(title='字典管理', business_type=2)
async def refresh_system_dict(request: Request, query_db: Session = Depends(get_db)):
    try:
        refresh_dict_result = await DictTypeService.refresh_sys_dict_services(request, query_db)
        if refresh_dict_result.is_success:
            logger.info(refresh_dict_result.message)
            return ResponseUtil.success(msg=refresh_dict_result.message)
        else:
            logger.warning(refresh_dict_result.message)
            return ResponseUtil.failure(msg=refresh_dict_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.delete("/type/{dict_ids}", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@log_decorator(title='字典管理', business_type=3)
async def delete_system_dict_type(request: Request, dict_ids: str, query_db: Session = Depends(get_db)):
    try:
        delete_dict_type = DeleteDictTypeModel(dictIds=dict_ids)
        delete_dict_type_result = await DictTypeService.delete_dict_type_services(request, query_db, delete_dict_type)
        if delete_dict_type_result.is_success:
            logger.info(delete_dict_type_result.message)
            return ResponseUtil.success(msg=delete_dict_type_result.message)
        else:
            logger.warning(delete_dict_type_result.message)
            return ResponseUtil.failure(msg=delete_dict_type_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.get("/type/optionselect", response_model=List[DictTypeModel])
async def query_system_dict_type_options(request: Request, query_db: Session = Depends(get_db)):
    try:
        dict_type_query_result = DictTypeService.get_dict_type_list_services(query_db, DictTypePageQueryModel(**dict()), is_page=False)
        logger.info(f'获取成功')
        return ResponseUtil.success(data=dict_type_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.get("/type/{dict_id}", response_model=DictTypeModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:query'))])
async def query_detail_system_dict_type(request: Request, dict_id: int, query_db: Session = Depends(get_db)):
    try:
        dict_type_detail_result = DictTypeService.dict_type_detail_services(query_db, dict_id)
        logger.info(f'获取dict_id为{dict_id}的信息成功')
        return ResponseUtil.success(data=dict_type_detail_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.post("/type/export", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:export'))])
@log_decorator(title='字典管理', business_type=5)
async def export_system_dict_type_list(request: Request, dict_type_page_query: DictTypePageQueryModel = Depends(DictTypePageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        dict_type_query_result = DictTypeService.get_dict_type_list_services(query_db, dict_type_page_query, is_page=False)
        dict_type_export_result = DictTypeService.export_dict_type_list_services(dict_type_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(dict_type_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.get("/data/type/{dict_type}")
async def query_system_dict_type_data(request: Request, dict_type: str, query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        dict_data_query_result = await DictDataService.query_dict_data_list_from_cache_services(request.app.state.redis, dict_type)
        logger.info('获取成功')
        return ResponseUtil.success(data=dict_data_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.get("/data/list", response_model=PageResponseModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:list'))])
async def get_system_dict_data_list(request: Request, dict_data_page_query: DictDataPageQueryModel = Depends(DictDataPageQueryModel.as_query), query_db: Session = Depends(get_db)):
    try:
        # 获取分页数据
        dict_data_page_query_result = DictDataService.get_dict_data_list_services(query_db, dict_data_page_query, is_page=True)
        logger.info('获取成功')
        return ResponseUtil.success(model_content=dict_data_page_query_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.post("/data", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:add'))])
@log_decorator(title='字典管理', business_type=1)
async def add_system_dict_data(request: Request, add_dict_data: DictDataModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        add_dict_data.create_by = current_user.user.user_name
        add_dict_data.update_by = current_user.user.user_name
        add_dict_data_result = await DictDataService.add_dict_data_services(request, query_db, add_dict_data)
        if add_dict_data_result.is_success:
            logger.info(add_dict_data_result.message)
            return ResponseUtil.success(msg=add_dict_data_result.message)
        else:
            logger.warning(add_dict_data_result.message)
            return ResponseUtil.failure(msg=add_dict_data_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.put("/data", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:edit'))])
@log_decorator(title='字典管理', business_type=2)
async def edit_system_dict_data(request: Request, edit_dict_data: DictDataModel, query_db: Session = Depends(get_db), current_user: CurrentUserModel = Depends(LoginService.get_current_user)):
    try:
        edit_dict_data.update_by = current_user.user.user_name
        edit_dict_data.update_time = datetime.now()
        edit_dict_data_result = await DictDataService.edit_dict_data_services(request, query_db, edit_dict_data)
        if edit_dict_data_result.is_success:
            logger.info(edit_dict_data_result.message)
            return ResponseUtil.success(msg=edit_dict_data_result.message)
        else:
            logger.warning(edit_dict_data_result.message)
            return ResponseUtil.failure(msg=edit_dict_data_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.delete("/data/{dict_codes}", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:remove'))])
@log_decorator(title='字典管理', business_type=3)
async def delete_system_dict_data(request: Request, dict_codes: str, query_db: Session = Depends(get_db)):
    try:
        delete_dict_data = DeleteDictDataModel(dictCodes=dict_codes)
        delete_dict_data_result = await DictDataService.delete_dict_data_services(request, query_db, delete_dict_data)
        if delete_dict_data_result.is_success:
            logger.info(delete_dict_data_result.message)
            return ResponseUtil.success(msg=delete_dict_data_result.message)
        else:
            logger.warning(delete_dict_data_result.message)
            return ResponseUtil.failure(msg=delete_dict_data_result.message)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.get("/data/{dict_code}", response_model=DictDataModel, dependencies=[Depends(CheckUserInterfaceAuth('system:dict:query'))])
async def query_detail_system_dict_data(request: Request, dict_code: int, query_db: Session = Depends(get_db)):
    try:
        detail_dict_data_result = DictDataService.dict_data_detail_services(query_db, dict_code)
        logger.info(f'获取dict_code为{dict_code}的信息成功')
        return ResponseUtil.success(data=detail_dict_data_result)
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))


@dictController.post("/data/export", dependencies=[Depends(CheckUserInterfaceAuth('system:dict:export'))])
@log_decorator(title='字典管理', business_type=5)
async def export_system_dict_data_list(request: Request, dict_data_page_query: DictDataPageQueryModel = Depends(DictDataPageQueryModel.as_form), query_db: Session = Depends(get_db)):
    try:
        # 获取全量数据
        dict_data_query_result = DictDataService.get_dict_data_list_services(query_db, dict_data_page_query, is_page=False)
        dict_data_export_result = DictDataService.export_dict_data_list_services(dict_data_query_result)
        logger.info('导出成功')
        return ResponseUtil.streaming(data=bytes2file_response(dict_data_export_result))
    except Exception as e:
        logger.exception(e)
        return ResponseUtil.error(msg=str(e))
