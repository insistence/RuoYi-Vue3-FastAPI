from module_admin.dao.job_log_dao import *
from module_admin.dao.dict_dao import DictDataDao
from module_admin.entity.vo.common_vo import CrudResponseModel
from utils.common_util import export_list2excel, CamelCaseUtil


class JobLogService:
    """
    定时任务日志管理模块服务层
    """

    @classmethod
    def get_job_log_list_services(cls, query_db: Session, query_object: JobLogQueryModel):
        """
        获取定时任务日志列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :return: 定时任务日志列表信息对象
        """
        job_log_list_result = JobLogDao.get_job_log_list(query_db, query_object)

        return CamelCaseUtil.transform_result(job_log_list_result)

    @classmethod
    def add_job_log_services(cls, query_db: Session, page_object: JobLogModel):
        """
        新增定时任务日志信息service
        :param query_db: orm对象
        :param page_object: 新增定时任务日志对象
        :return: 新增定时任务日志校验结果
        """
        try:
            JobLogDao.add_job_log_dao(query_db, page_object)
            query_db.commit()
            result = dict(is_success=True, message='新增成功')
        except Exception as e:
            query_db.rollback()
            result = dict(is_success=False, message=str(e))

        return CrudResponseModel(**result)

    @classmethod
    def delete_job_log_services(cls, query_db: Session, page_object: DeleteJobLogModel):
        """
        删除定时任务日志信息service
        :param query_db: orm对象
        :param page_object: 删除定时任务日志对象
        :return: 删除定时任务日志校验结果
        """
        if page_object.job_log_ids.split(','):
            job_log_id_list = page_object.job_log_ids.split(',')
            try:
                for job_log_id in job_log_id_list:
                    JobLogDao.delete_job_log_dao(query_db, JobLogModel(jobLogId=job_log_id))
                query_db.commit()
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入定时任务日志id为空')
        return CrudResponseModel(**result)

    @classmethod
    def clear_job_log_services(cls, query_db: Session):
        """
        清除定时任务日志信息service
        :param query_db: orm对象
        :return: 清除定时任务日志校验结果
        """
        try:
            JobLogDao.clear_job_log_dao(query_db)
            query_db.commit()
            result = dict(is_success=True, message='清除成功')
        except Exception as e:
            query_db.rollback()
            raise e

        return CrudResponseModel(**result)

    @staticmethod
    def export_job_log_list_services(query_db, job_log_list: List):
        """
        导出定时任务日志信息service
        :param query_db: orm对象
        :param job_log_list: 定时任务日志信息列表
        :return: 定时任务日志信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "jobLogId": "任务日志编码",
            "jobName": "任务名称",
            "jobGroup": "任务组名",
            "jobExecutor": "任务执行器",
            "invokeTarget": "调用目标字符串",
            "jobArgs": "位置参数",
            "jobKwargs": "关键字参数",
            "jobTrigger": "任务触发器",
            "jobMessage": "日志信息",
            "status": "执行状态",
            "exceptionInfo": "异常信息",
            "createTime": "创建时间",
        }

        data = job_log_list
        job_group_list = DictDataDao.query_dict_data_list(query_db, dict_type='sys_job_group')
        job_group_option = [dict(label=item.dict_label, value=item.dict_value) for item in job_group_list]
        job_group_option_dict = {item.get('value'): item for item in job_group_option}

        for item in data:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '暂停'
            if str(item.get('job_group')) in job_group_option_dict.keys():
                item['job_group'] = job_group_option_dict.get(str(item.get('job_group'))).get('label')
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in
                    data]
        binary_data = export_list2excel(new_data)

        return binary_data
