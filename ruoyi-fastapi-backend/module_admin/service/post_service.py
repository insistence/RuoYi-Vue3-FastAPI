from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from config.constant import CommonConstant
from exceptions.exception import ServiceException
from module_admin.dao.post_dao import PostDao
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.post_vo import DeletePostModel, PostModel, PostPageQueryModel
from utils.common_util import CamelCaseUtil
from utils.excel_util import ExcelUtil


class PostService:
    """
    岗位管理模块服务层
    """

    @classmethod
    async def get_post_list_services(
        cls, query_db: AsyncSession, query_object: PostPageQueryModel, is_page: bool = False
    ):
        """
        获取岗位列表信息service

        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 岗位列表信息对象
        """
        post_list_result = await PostDao.get_post_list(query_db, query_object, is_page)

        return post_list_result

    @classmethod
    async def check_post_name_unique_services(cls, query_db: AsyncSession, page_object: PostModel):
        """
        检查岗位名称是否唯一service

        :param query_db: orm对象
        :param page_object: 岗位对象
        :return: 校验结果
        """
        post_id = -1 if page_object.post_id is None else page_object.post_id
        post = await PostDao.get_post_detail_by_info(query_db, PostModel(postName=page_object.post_name))
        if post and post.post_id != post_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def check_post_code_unique_services(cls, query_db: AsyncSession, page_object: PostModel):
        """
        检查岗位编码是否唯一service

        :param query_db: orm对象
        :param page_object: 岗位对象
        :return: 校验结果
        """
        post_id = -1 if page_object.post_id is None else page_object.post_id
        post = await PostDao.get_post_detail_by_info(query_db, PostModel(postCode=page_object.post_code))
        if post and post.post_id != post_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_post_services(cls, query_db: AsyncSession, page_object: PostModel):
        """
        新增岗位信息service

        :param query_db: orm对象
        :param page_object: 新增岗位对象
        :return: 新增岗位校验结果
        """
        if not await cls.check_post_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增岗位{page_object.post_name}失败，岗位名称已存在')
        elif not await cls.check_post_code_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增岗位{page_object.post_name}失败，岗位编码已存在')
        else:
            try:
                await PostDao.add_post_dao(query_db, page_object)
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='新增成功')
            except Exception as e:
                await query_db.rollback()
                raise e

    @classmethod
    async def edit_post_services(cls, query_db: AsyncSession, page_object: PostModel):
        """
        编辑岗位信息service

        :param query_db: orm对象
        :param page_object: 编辑岗位对象
        :return: 编辑岗位校验结果
        """
        edit_post = page_object.model_dump(exclude_unset=True)
        post_info = await cls.post_detail_services(query_db, page_object.post_id)
        if post_info.post_id:
            if not await cls.check_post_name_unique_services(query_db, page_object):
                raise ServiceException(message=f'修改岗位{page_object.post_name}失败，岗位名称已存在')
            elif not await cls.check_post_code_unique_services(query_db, page_object):
                raise ServiceException(message=f'修改岗位{page_object.post_name}失败，岗位编码已存在')
            else:
                try:
                    await PostDao.edit_post_dao(query_db, edit_post)
                    await query_db.commit()
                    return CrudResponseModel(is_success=True, message='更新成功')
                except Exception as e:
                    await query_db.rollback()
                    raise e
        else:
            raise ServiceException(message='岗位不存在')

    @classmethod
    async def delete_post_services(cls, query_db: AsyncSession, page_object: DeletePostModel):
        """
        删除岗位信息service

        :param query_db: orm对象
        :param page_object: 删除岗位对象
        :return: 删除岗位校验结果
        """
        if page_object.post_ids:
            post_id_list = page_object.post_ids.split(',')
            try:
                for post_id in post_id_list:
                    post = await cls.post_detail_services(query_db, int(post_id))
                    if (await PostDao.count_user_post_dao(query_db, int(post_id))) > 0:
                        raise ServiceException(message=f'{post.post_name}已分配，不能删除')
                    await PostDao.delete_post_dao(query_db, PostModel(postId=post_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入岗位id为空')

    @classmethod
    async def post_detail_services(cls, query_db: AsyncSession, post_id: int):
        """
        获取岗位详细信息service

        :param query_db: orm对象
        :param post_id: 岗位id
        :return: 岗位id对应的信息
        """
        post = await PostDao.get_post_detail_by_id(query_db, post_id=post_id)
        if post:
            result = PostModel(**CamelCaseUtil.transform_result(post))
        else:
            result = PostModel(**dict())

        return result

    @staticmethod
    async def export_post_list_services(post_list: List):
        """
        导出岗位信息service

        :param post_list: 岗位信息列表
        :return: 岗位信息对应excel的二进制数据
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            'postId': '岗位编号',
            'postCode': '岗位编码',
            'postName': '岗位名称',
            'postSort': '显示顺序',
            'status': '状态',
            'createBy': '创建者',
            'createTime': '创建时间',
            'updateBy': '更新者',
            'updateTime': '更新时间',
            'remark': '备注',
        }

        for item in post_list:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
        binary_data = ExcelUtil.export_list2excel(post_list, mapping_dict)

        return binary_data
