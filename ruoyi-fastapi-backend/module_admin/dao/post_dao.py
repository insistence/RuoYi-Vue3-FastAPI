from sqlalchemy.orm import Session
from module_admin.entity.do.post_do import SysPost
from module_admin.entity.vo.post_vo import *
from utils.page_util import PageUtil


class PostDao:
    """
    岗位管理模块数据库操作层
    """

    @classmethod
    def get_post_by_id(cls, db: Session, post_id: int):
        """
        根据岗位id获取在用岗位详细信息
        :param db: orm对象
        :param post_id: 岗位id
        :return: 在用岗位信息对象
        """
        post_info = db.query(SysPost) \
            .filter(SysPost.post_id == post_id,
                    SysPost.status == 0) \
            .first()

        return post_info

    @classmethod
    def get_post_detail_by_id(cls, db: Session, post_id: int):
        """
        根据岗位id获取岗位详细信息
        :param db: orm对象
        :param post_id: 岗位id
        :return: 岗位信息对象
        """
        post_info = db.query(SysPost) \
            .filter(SysPost.post_id == post_id) \
            .first()

        return post_info

    @classmethod
    def get_post_detail_by_info(cls, db: Session, post: PostModel):
        """
        根据岗位参数获取岗位信息
        :param db: orm对象
        :param post: 岗位参数对象
        :return: 岗位信息对象
        """
        post_info = db.query(SysPost) \
            .filter(SysPost.post_name == post.post_name if post.post_name else True,
                    SysPost.post_code == post.post_code if post.post_code else True,
                    SysPost.post_sort == post.post_sort if post.post_sort else True) \
            .first()

        return post_info

    @classmethod
    def get_post_list(cls, db: Session, query_object: PostPageQueryModel, is_page: bool = False):
        """
        根据查询参数获取岗位列表信息
        :param db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 岗位列表信息对象
        """
        query = db.query(SysPost) \
            .filter(SysPost.post_code.like(f'%{query_object.post_code}%') if query_object.post_code else True,
                    SysPost.post_name.like(f'%{query_object.post_name}%') if query_object.post_name else True,
                    SysPost.status == query_object.status if query_object.status else True
                    ) \
            .order_by(SysPost.post_sort) \
            .distinct()
        post_list = PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        return post_list

    @classmethod
    def add_post_dao(cls, db: Session, post: PostModel):
        """
        新增岗位数据库操作
        :param db: orm对象
        :param post: 岗位对象
        :return:
        """
        db_post = SysPost(**post.model_dump())
        db.add(db_post)
        db.flush()

        return db_post

    @classmethod
    def edit_post_dao(cls, db: Session, post: dict):
        """
        编辑岗位数据库操作
        :param db: orm对象
        :param post: 需要更新的岗位字典
        :return:
        """
        db.query(SysPost) \
            .filter(SysPost.post_id == post.get('post_id')) \
            .update(post)

    @classmethod
    def delete_post_dao(cls, db: Session, post: PostModel):
        """
        删除岗位数据库操作
        :param db: orm对象
        :param post: 岗位对象
        :return:
        """
        db.query(SysPost) \
            .filter(SysPost.post_id == post.post_id) \
            .delete()
