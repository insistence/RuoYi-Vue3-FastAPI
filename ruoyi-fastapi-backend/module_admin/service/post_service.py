from module_admin.dao.post_dao import *
from module_admin.entity.vo.common_vo import CrudResponseModel
from utils.common_util import export_list2excel, CamelCaseUtil


class PostService:
    """
    岗位管理模块服务层
    """
    @classmethod
    def get_post_list_services(cls, query_db: Session, query_object: PostPageQueryModel, is_page: bool = False):
        """
        获取岗位列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 岗位列表信息对象
        """
        post_list_result = PostDao.get_post_list(query_db, query_object, is_page)

        return post_list_result

    @classmethod
    def add_post_services(cls, query_db: Session, page_object: PostModel):
        """
        新增岗位信息service
        :param query_db: orm对象
        :param page_object: 新增岗位对象
        :return: 新增岗位校验结果
        """
        post = PostDao.get_post_detail_by_info(query_db, PostModel(postName=page_object.post_name))
        if post:
            result = dict(is_success=False, message='岗位名称已存在')
        else:
            try:
                PostDao.add_post_dao(query_db, page_object)
                query_db.commit()
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    def edit_post_services(cls, query_db: Session, page_object: PostModel):
        """
        编辑岗位信息service
        :param query_db: orm对象
        :param page_object: 编辑岗位对象
        :return: 编辑岗位校验结果
        """
        edit_post = page_object.model_dump(exclude_unset=True)
        post_info = cls.post_detail_services(query_db, edit_post.get('post_id'))
        if post_info:
            if post_info.post_name != page_object.post_name:
                post = PostDao.get_post_detail_by_info(query_db, PostModel(postName=page_object.post_name))
                if post:
                    result = dict(is_success=False, message='岗位名称已存在')
                    return CrudResponseModel(**result)
            try:
                PostDao.edit_post_dao(query_db, edit_post)
                query_db.commit()
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='岗位不存在')

        return CrudResponseModel(**result)

    @classmethod
    def delete_post_services(cls, query_db: Session, page_object: DeletePostModel):
        """
        删除岗位信息service
        :param query_db: orm对象
        :param page_object: 删除岗位对象
        :return: 删除岗位校验结果
        """
        if page_object.post_ids.split(','):
            post_id_list = page_object.post_ids.split(',')
            try:
                for post_id in post_id_list:
                    PostDao.delete_post_dao(query_db, PostModel(postId=post_id))
                query_db.commit()
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入岗位id为空')
        return CrudResponseModel(**result)

    @classmethod
    def post_detail_services(cls, query_db: Session, post_id: int):
        """
        获取岗位详细信息service
        :param query_db: orm对象
        :param post_id: 岗位id
        :return: 岗位id对应的信息
        """
        post = PostDao.get_post_detail_by_id(query_db, post_id=post_id)
        result = PostModel(**CamelCaseUtil.transform_result(post))

        return result

    @staticmethod
    def export_post_list_services(post_list: List):
        """
        导出岗位信息service
        :param post_list: 岗位信息列表
        :return: 岗位信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "postId": "岗位编号",
            "postCode": "岗位编码",
            "postName": "岗位名称",
            "postSort": "显示顺序",
            "status": "状态",
            "createBy": "创建者",
            "createTime": "创建时间",
            "updateBy": "更新者",
            "updateTime": "更新时间",
            "remark": "备注",
        }

        data = post_list

        for item in data:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in data]
        binary_data = export_list2excel(new_data)

        return binary_data
