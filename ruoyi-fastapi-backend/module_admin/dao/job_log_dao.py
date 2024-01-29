from sqlalchemy.orm import Session
from module_admin.entity.do.job_do import SysJobLog
from module_admin.entity.vo.job_vo import *
from utils.page_util import PageUtil
from datetime import datetime, time


class JobLogDao:
    """
    定时任务日志管理模块数据库操作层
    """

    @classmethod
    def get_job_log_list(cls, db: Session, query_object: JobLogPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取定时任务日志列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务日志列表信息对象
        """
        query = db.query(SysJobLog) \
            .filter(SysJobLog.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                    SysJobLog.job_group == query_object.job_group if query_object.job_group else True,
                    SysJobLog.status == query_object.status if query_object.status else True,
                    SysJobLog.create_time.between(
                        datetime.combine(datetime.strptime(query_object.begin_time, '%Y-%m-%d'), time(00, 00, 00)),
                        datetime.combine(datetime.strptime(query_object.end_time, '%Y-%m-%d'), time(23, 59, 59)))
                    if query_object.begin_time and query_object.end_time else True
                    ) \
            .distinct()
        job_log_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return job_log_list

    @classmethod
    def add_job_log_dao(cls, db: Session, job_log: JobLogModel):
        """
        新增定时任务日志数据库操作
        :param db: orm对象
        :param job_log: 定时任务日志对象
        :return:
        """
        db_job_log = SysJobLog(**job_log.model_dump())
        db.add(db_job_log)
        db.flush()

        return db_job_log

    @classmethod
    def delete_job_log_dao(cls, db: Session, job_log: JobLogModel):
        """
        删除定时任务日志数据库操作
        :param db: orm对象
        :param job_log: 定时任务日志对象
        :return:
        """
        db.query(SysJobLog) \
            .filter(SysJobLog.job_log_id == job_log.job_log_id) \
            .delete()

    @classmethod
    def clear_job_log_dao(cls, db: Session):
        """
        清除定时任务日志数据库操作
        :param db: orm对象
        :return:
        """
        db.query(SysJobLog) \
            .delete()
