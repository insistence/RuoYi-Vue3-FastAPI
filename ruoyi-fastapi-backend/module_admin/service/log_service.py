from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from exceptions.exception import ServiceException
from module_admin.dao.log_dao import LoginLogDao, OperationLogDao
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.log_vo import (
    DeleteLoginLogModel,
    DeleteOperLogModel,
    LogininforModel,
    LoginLogPageQueryModel,
    OperLogModel,
    OperLogPageQueryModel,
    UnlockUser,
)
from module_admin.service.dict_service import DictDataService
from utils.excel_util import ExcelUtil


class OperationLogService:
    """
    操作日志管理模块服务层
    """

    @classmethod
    async def get_operation_log_list_services(
        cls, query_db: AsyncSession, query_object: OperLogPageQueryModel, is_page: bool = False
    ):
        """
        获取操作日志列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 操作日志列表信息对象
        """
        operation_log_list_result = await OperationLogDao.get_operation_log_list(query_db, query_object, is_page)

        return operation_log_list_result

    @classmethod
    async def add_operation_log_services(cls, query_db: AsyncSession, page_object: OperLogModel):
        """
        新增操作日志service

        :param query_db: orm对象
        :param page_object: 新增操作日志对象
        :return: 新增操作日志校验结果
        """
        try:
            await OperationLogDao.add_operation_log_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def delete_operation_log_services(cls, query_db: AsyncSession, page_object: DeleteOperLogModel):
        """
        删除操作日志信息service

        :param query_db: orm对象
        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.oper_ids:
            oper_id_list = page_object.oper_ids.split(',')
            try:
                for oper_id in oper_id_list:
                    await OperationLogDao.delete_operation_log_dao(query_db, OperLogModel(operId=oper_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入操作日志id为空')

    @classmethod
    async def clear_operation_log_services(cls, query_db: AsyncSession):
        """
        清除操作日志信息service

        :param query_db: orm对象
        :return: 清除操作日志校验结果
        """
        try:
            await OperationLogDao.clear_operation_log_dao(query_db)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='清除成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def export_operation_log_list_services(cls, request: Request, operation_log_list: List):
        """
        导出操作日志信息service

        :param request: Request对象
        :param operation_log_list: 操作日志信息列表
        :return: 操作日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'operId': '日志编号',
            'title': '系统模块',
            'businessType': '操作类型',
            'method': '方法名称',
            'requestMethod': '请求方式',
            'operName': '操作人员',
            'deptName': '部门名称',
            'operUrl': '请求URL',
            'operIp': '操作地址',
            'operLocation': '操作地点',
            'operParam': '请求参数',
            'jsonResult': '返回参数',
            'status': '操作状态',
            'error_msg': '错误消息',
            'operTime': '操作日期',
            'costTime': '消耗时间（毫秒）',
        }

        operation_type_list = await DictDataService.query_dict_data_list_from_cache_services(
            request.app.state.redis, dict_type='sys_oper_type'
        )
        operation_type_option = [
            dict(label=item.get('dictLabel'), value=item.get('dictValue')) for item in operation_type_list
        ]
        operation_type_option_dict = {item.get('value'): item for item in operation_type_option}

        for item in operation_log_list:
            if item.get('status') == 0:
                item['status'] = '成功'
            else:
                item['status'] = '失败'
            if str(item.get('businessType')) in operation_type_option_dict.keys():
                item['businessType'] = operation_type_option_dict.get(str(item.get('businessType'))).get('label')
        binary_data = ExcelUtil.export_list2excel(operation_log_list, mapping_dict)

        return binary_data


class LoginLogService:
    """
    登录日志管理模块服务层
    """

    @classmethod
    async def get_login_log_list_services(
        cls, query_db: AsyncSession, query_object: LoginLogPageQueryModel, is_page: bool = False
    ):
        """
        获取登录日志列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 登录日志列表信息对象
        """
        operation_log_list_result = await LoginLogDao.get_login_log_list(query_db, query_object, is_page)

        return operation_log_list_result

    @classmethod
    async def add_login_log_services(cls, query_db: AsyncSession, page_object: LogininforModel):
        """
        新增登录日志service

        :param query_db: orm对象
        :param page_object: 新增登录日志对象
        :return: 新增登录日志校验结果
        """
        try:
            await LoginLogDao.add_login_log_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def delete_login_log_services(cls, query_db: AsyncSession, page_object: DeleteLoginLogModel):
        """
        删除操作日志信息service

        :param query_db: orm对象
        :param page_object: 删除操作日志对象
        :return: 删除操作日志校验结果
        """
        if page_object.info_ids:
            info_id_list = page_object.info_ids.split(',')
            try:
                for info_id in info_id_list:
                    await LoginLogDao.delete_login_log_dao(query_db, LogininforModel(infoId=info_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入登录日志id为空')

    @classmethod
    async def clear_login_log_services(cls, query_db: AsyncSession):
        """
        清除操作日志信息service

        :param query_db: orm对象
        :return: 清除操作日志校验结果
        """
        try:
            await LoginLogDao.clear_login_log_dao(query_db)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='清除成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def unlock_user_services(cls, request: Request, unlock_user: UnlockUser):
        locked_user = await request.app.state.redis.get(f'account_lock:{unlock_user.user_name}')
        if locked_user:
            await request.app.state.redis.delete(f'account_lock:{unlock_user.user_name}')
            return CrudResponseModel(is_success=True, message='解锁成功')
        else:
            raise ServiceException(message='该用户未锁定')

    @staticmethod
    async def export_login_log_list_services(login_log_list: List):
        """
        导出登录日志信息service

        :param login_log_list: 登录日志信息列表
        :return: 登录日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'infoId': '访问编号',
            'userName': '用户名称',
            'ipaddr': '登录地址',
            'loginLocation': '登录地点',
            'browser': '浏览器',
            'os': '操作系统',
            'status': '登录状态',
            'msg': '操作信息',
            'loginTime': '登录日期',
        }

        for item in login_log_list:
            if item.get('status') == '0':
                item['status'] = '成功'
            else:
                item['status'] = '失败'
        binary_data = ExcelUtil.export_list2excel(login_log_list, mapping_dict)

        return binary_data
