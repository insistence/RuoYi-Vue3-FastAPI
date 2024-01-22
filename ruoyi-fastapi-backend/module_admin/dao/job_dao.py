from sqlalchemy.orm import Session
from module_admin.entity.do.job_do import SysJob
from module_admin.entity.vo.job_vo import *


class JobDao:
    """
    定时任务管理模块数据库操作层
    """

    @classmethod
    def get_job_detail_by_id(cls, db: Session, job_id: int):
        """
        根据定时任务id获取定时任务详细信息
        :param db: orm对象
        :param job_id: 定时任务id
        :return: 定时任务信息对象
        """
        job_info = db.query(SysJob) \
            .filter(SysJob.job_id == job_id) \
            .first()

        return job_info

    @classmethod
    def get_job_detail_by_info(cls, db: Session, job: JobModel):
        """
        根据定时任务参数获取定时任务信息
        :param db: orm对象
        :param job: 定时任务参数对象
        :return: 定时任务信息对象
        """
        job_info = db.query(SysJob) \
            .filter(SysJob.job_name == job.job_name if job.job_name else True,
                    SysJob.job_group == job.job_group if job.job_group else True,
                    SysJob.invoke_target == job.invoke_target if job.invoke_target else True,
                    SysJob.cron_expression == job.cron_expression if job.cron_expression else True) \
            .first()

        return job_info

    @classmethod
    def get_job_list(cls, db: Session, query_object: JobModel):
        """
        根据查询参数获取定时任务列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :return: 定时任务列表信息对象
        """
        job_list = db.query(SysJob) \
            .filter(SysJob.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                    SysJob.job_group == query_object.job_group if query_object.job_group else True,
                    SysJob.status == query_object.status if query_object.status else True
                    ) \
            .distinct().all()

        return job_list

    @classmethod
    def get_job_list_for_scheduler(cls, db: Session):
        """
        获取定时任务列表信息
        :param db: orm对象
        :return: 定时任务列表信息对象
        """
        job_list = db.query(SysJob) \
            .filter(SysJob.status == 0) \
            .distinct().all()

        return job_list

    @classmethod
    def add_job_dao(cls, db: Session, job: JobModel):
        """
        新增定时任务数据库操作
        :param db: orm对象
        :param job: 定时任务对象
        :return:
        """
        db_job = SysJob(**job.model_dump())
        db.add(db_job)
        db.flush()

        return db_job

    @classmethod
    def edit_job_dao(cls, db: Session, job: dict):
        """
        编辑定时任务数据库操作
        :param db: orm对象
        :param job: 需要更新的定时任务字典
        :return:
        """
        db.query(SysJob) \
            .filter(SysJob.job_id == job.get('job_id')) \
            .update(job)

    @classmethod
    def delete_job_dao(cls, db: Session, job: JobModel):
        """
        删除定时任务数据库操作
        :param db: orm对象
        :param job: 定时任务对象
        :return:
        """
        db.query(SysJob) \
            .filter(SysJob.job_id == job.job_id) \
            .delete()
