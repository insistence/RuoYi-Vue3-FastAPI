from sqlalchemy import asc, desc
from sqlalchemy.orm import Session
from module_admin.entity.do.log_do import SysOperLog, SysLogininfor
from module_admin.entity.vo.log_vo import *
from utils.page_util import PageUtil
from utils.common_util import CamelCaseUtil
from datetime import datetime, time


class OperationLogDao:
    """
    操作日志管理模块数据库操作层
    """
    @classmethod
    def get_operation_log_list(cls, db: Session, query_object: OperLogPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取操作日志列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 操作日志列表信息对象
        """
        if query_object.is_asc == 'ascending':
            order_by_column = asc(getattr(SysOperLog, CamelCaseUtil.camel_to_snake(query_object.order_by_column), None))
        elif query_object.is_asc == 'descending':
            order_by_column = desc(getattr(SysOperLog, CamelCaseUtil.camel_to_snake(query_object.order_by_column), None))
        else:
            order_by_column = desc(SysOperLog.oper_time)
        query = db.query(SysOperLog) \
            .filter(SysOperLog.title.like(f'%{query_object.title}%') if query_object.title else True,
                    SysOperLog.oper_name.like(f'%{query_object.oper_name}%') if query_object.oper_name else True,
                    SysOperLog.business_type == query_object.business_type if query_object.business_type else True,
                    SysOperLog.status == query_object.status if query_object.status else True,
                    SysOperLog.oper_time.between(
                        datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                        datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)))
                                if query_object.begin_time and query_object.end_time else True
                    )\
            .distinct().order_by(order_by_column)
        operation_log_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return operation_log_list

    @classmethod
    def add_operation_log_dao(cls, db: Session, operation_log: OperLogModel):
        """
        新增操作日志数据库操作
        :param db: orm对象
        :param operation_log: 操作日志对象
        :return: 新增校验结果
        """
        db_operation_log = SysOperLog(**operation_log.model_dump())
        db.add(db_operation_log)
        db.flush()

        return db_operation_log

    @classmethod
    def delete_operation_log_dao(cls, db: Session, operation_log: OperLogModel):
        """
        删除操作日志数据库操作
        :param db: orm对象
        :param operation_log: 操作日志对象
        :return:
        """
        db.query(SysOperLog) \
            .filter(SysOperLog.oper_id == operation_log.oper_id) \
            .delete()

    @classmethod
    def clear_operation_log_dao(cls, db: Session):
        """
        清除操作日志数据库操作
        :param db: orm对象
        :return:
        """
        db.query(SysOperLog) \
            .delete()


class LoginLogDao:
    """
    登录日志管理模块数据库操作层
    """

    @classmethod
    def get_login_log_list(cls, db: Session, query_object: LoginLogPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取登录日志列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 登录日志列表信息对象
        """
        if query_object.is_asc == 'ascending':
            order_by_column = asc(getattr(SysLogininfor, CamelCaseUtil.camel_to_snake(query_object.order_by_column), None))
        elif query_object.is_asc == 'descending':
            order_by_column = desc(getattr(SysLogininfor, CamelCaseUtil.camel_to_snake(query_object.order_by_column), None))
        else:
            order_by_column = desc(SysLogininfor.login_time)
        query = db.query(SysLogininfor) \
            .filter(SysLogininfor.ipaddr.like(f'%{query_object.ipaddr}%') if query_object.ipaddr else True,
                    SysLogininfor.user_name.like(f'%{query_object.user_name}%') if query_object.user_name else True,
                    SysLogininfor.status == query_object.status if query_object.status else True,
                    SysLogininfor.login_time.between(
                        datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                        datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)))
                                if query_object.begin_time and query_object.end_time else True
                    )\
            .distinct().order_by(order_by_column)
        login_log_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return login_log_list

    @classmethod
    def add_login_log_dao(cls, db: Session, login_log: LogininforModel):
        """
        新增登录日志数据库操作
        :param db: orm对象
        :param login_log: 登录日志对象
        :return: 新增校验结果
        """
        db_login_log = SysLogininfor(**login_log.model_dump())
        db.add(db_login_log)
        db.flush()

        return db_login_log

    @classmethod
    def delete_login_log_dao(cls, db: Session, login_log: LogininforModel):
        """
        删除登录日志数据库操作
        :param db: orm对象
        :param login_log: 登录日志对象
        :return:
        """
        db.query(SysLogininfor) \
            .filter(SysLogininfor.info_id == login_log.info_id) \
            .delete()

    @classmethod
    def clear_login_log_dao(cls, db: Session):
        """
        清除登录日志数据库操作
        :param db: orm对象
        :return:
        """
        db.query(SysLogininfor) \
            .delete()
