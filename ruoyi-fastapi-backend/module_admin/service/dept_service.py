from sqlalchemy.ext.asyncio import AsyncSession
from config.constant import CommonConstant
from exceptions.exception import ServiceException, ServiceWarning
from module_admin.dao.dept_dao import DeptDao
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.entity.vo.dept_vo import DeleteDeptModel, DeptModel
from utils.common_util import CamelCaseUtil


class DeptService:
    """
    部门管理模块服务层
    """

    @classmethod
    async def get_dept_tree_services(cls, query_db: AsyncSession, page_object: DeptModel, data_scope_sql: str):
        """
        获取部门树信息service

        :param query_db: orm对象
        :param page_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门树信息对象
        """
        dept_list_result = await DeptDao.get_dept_list_for_tree(query_db, page_object, data_scope_sql)
        dept_tree_result = cls.list_to_tree(dept_list_result)

        return dept_tree_result

    @classmethod
    async def get_dept_for_edit_option_services(
        cls, query_db: AsyncSession, page_object: DeptModel, data_scope_sql: str
    ):
        """
        获取部门编辑部门树信息service

        :param query_db: orm对象
        :param page_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门树信息对象
        """
        dept_list_result = await DeptDao.get_dept_info_for_edit_option(query_db, page_object, data_scope_sql)

        return CamelCaseUtil.transform_result(dept_list_result)

    @classmethod
    async def get_dept_list_services(cls, query_db: AsyncSession, page_object: DeptModel, data_scope_sql: str):
        """
        获取部门列表信息service

        :param query_db: orm对象
        :param page_object: 分页查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息对象
        """
        dept_list_result = await DeptDao.get_dept_list(query_db, page_object, data_scope_sql)

        return CamelCaseUtil.transform_result(dept_list_result)

    @classmethod
    async def check_dept_data_scope_services(cls, query_db: AsyncSession, dept_id: int, data_scope_sql: str):
        """
        校验部门是否有数据权限service

        :param query_db: orm对象
        :param dept_id: 部门id
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 校验结果
        """
        depts = await DeptDao.get_dept_list(query_db, DeptModel(deptId=dept_id), data_scope_sql)
        if depts:
            return CrudResponseModel(is_success=True, message='校验通过')
        else:
            raise ServiceException(message='没有权限访问部门数据')

    @classmethod
    async def check_dept_name_unique_services(cls, query_db: AsyncSession, page_object: DeptModel):
        """
        校验部门名称是否唯一service

        :param query_db: orm对象
        :param page_object: 部门对象
        :return: 校验结果
        """
        dept_id = -1 if page_object.dept_id is None else page_object.dept_id
        dept = await DeptDao.get_dept_detail_by_info(
            query_db, DeptModel(deptName=page_object.dept_name, parentId=page_object.parent_id)
        )
        if dept and dept.dept_id != dept_id:
            return CommonConstant.NOT_UNIQUE
        return CommonConstant.UNIQUE

    @classmethod
    async def add_dept_services(cls, query_db: AsyncSession, page_object: DeptModel):
        """
        新增部门信息service

        :param query_db: orm对象
        :param page_object: 新增部门对象
        :return: 新增部门校验结果
        """
        if not await cls.check_dept_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'新增部门{page_object.dept_name}失败，部门名称已存在')
        parent_info = await DeptDao.get_dept_by_id(query_db, page_object.parent_id)
        if parent_info.status != CommonConstant.DEPT_NORMAL:
            raise ServiceException(message=f'部门{parent_info.dept_name}停用，不允许新增')
        page_object.ancestors = f'{parent_info.ancestors},{page_object.parent_id}'
        try:
            await DeptDao.add_dept_dao(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='新增成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def edit_dept_services(cls, query_db: AsyncSession, page_object: DeptModel):
        """
        编辑部门信息service

        :param query_db: orm对象
        :param page_object: 编辑部门对象
        :return: 编辑部门校验结果
        """
        if not await cls.check_dept_name_unique_services(query_db, page_object):
            raise ServiceException(message=f'修改部门{page_object.dept_name}失败，部门名称已存在')
        elif page_object.dept_id == page_object.parent_id:
            raise ServiceException(message=f'修改部门{page_object.dept_name}失败，上级部门不能是自己')
        elif (
            page_object.status == CommonConstant.DEPT_DISABLE
            and (await DeptDao.count_normal_children_dept_dao(query_db, page_object.dept_id)) > 0
        ):
            raise ServiceException(message=f'修改部门{page_object.dept_name}失败，该部门包含未停用的子部门')
        new_parent_dept = await DeptDao.get_dept_by_id(query_db, page_object.parent_id)
        old_dept = await DeptDao.get_dept_by_id(query_db, page_object.dept_id)
        try:
            if new_parent_dept and old_dept:
                new_ancestors = f'{new_parent_dept.ancestors},{new_parent_dept.dept_id}'
                old_ancestors = old_dept.ancestors
                page_object.ancestors = new_ancestors
                await cls.update_dept_children(query_db, page_object.dept_id, new_ancestors, old_ancestors)
            edit_dept = page_object.model_dump(exclude_unset=True)
            await DeptDao.edit_dept_dao(query_db, edit_dept)
            if (
                page_object.status == CommonConstant.DEPT_NORMAL
                and page_object.ancestors
                and page_object.ancestors != 0
            ):
                await cls.update_parent_dept_status_normal(query_db, page_object)
            await query_db.commit()
            return CrudResponseModel(is_success=True, message='更新成功')
        except Exception as e:
            await query_db.rollback()
            raise e

    @classmethod
    async def delete_dept_services(cls, query_db: AsyncSession, page_object: DeleteDeptModel):
        """
        删除部门信息service

        :param query_db: orm对象
        :param page_object: 删除部门对象
        :return: 删除部门校验结果
        """
        if page_object.dept_ids:
            dept_id_list = page_object.dept_ids.split(',')
            try:
                for dept_id in dept_id_list:
                    if (await DeptDao.count_children_dept_dao(query_db, int(dept_id))) > 0:
                        raise ServiceWarning(message='存在下级部门,不允许删除')
                    elif (await DeptDao.count_dept_user_dao(query_db, int(dept_id))) > 0:
                        raise ServiceWarning(message='部门存在用户,不允许删除')

                    await DeptDao.delete_dept_dao(query_db, DeptModel(deptId=dept_id))
                await query_db.commit()
                return CrudResponseModel(is_success=True, message='删除成功')
            except Exception as e:
                await query_db.rollback()
                raise e
        else:
            raise ServiceException(message='传入部门id为空')

    @classmethod
    async def dept_detail_services(cls, query_db: AsyncSession, dept_id: int):
        """
        获取部门详细信息service

        :param query_db: orm对象
        :param dept_id: 部门id
        :return: 部门id对应的信息
        """
        dept = await DeptDao.get_dept_detail_by_id(query_db, dept_id=dept_id)
        if dept:
            result = DeptModel(**CamelCaseUtil.transform_result(dept))
        else:
            result = DeptModel(**dict())

        return result

    @classmethod
    def list_to_tree(cls, permission_list: list) -> list:
        """
        工具方法：根据部门列表信息生成树形嵌套数据

        :param permission_list: 部门列表信息
        :return: 部门树形嵌套数据
        """
        permission_list = [
            dict(id=item.dept_id, label=item.dept_name, parentId=item.parent_id) for item in permission_list
        ]
        # 转成id为key的字典
        mapping: dict = dict(zip([i['id'] for i in permission_list], permission_list))

        # 树容器
        container: list = []

        for d in permission_list:
            # 如果找不到父级项，则是根节点
            parent: dict = mapping.get(d['parentId'])
            if parent is None:
                container.append(d)
            else:
                children: list = parent.get('children')
                if not children:
                    children = []
                children.append(d)
                parent.update({'children': children})

        return container

    @classmethod
    async def replace_first(cls, original_str: str, old_str: str, new_str: str):
        """
        工具方法：替换字符串

        :param original_str: 需要替换的原始字符串
        :param old_str: 用于匹配的字符串
        :param new_str: 替换的字符串
        :return: 替换后的字符串
        """
        if original_str.startswith(old_str):
            return original_str.replace(old_str, new_str, 1)
        else:
            return original_str

    @classmethod
    async def update_parent_dept_status_normal(cls, query_db: AsyncSession, dept: DeptModel):
        """
        更新父部门状态为正常

        :param query_db: orm对象
        :param dept: 部门对象
        :return:
        """
        dept_id_list = dept.ancestors.split(',')
        await DeptDao.update_dept_status_normal_dao(query_db, list(map(int, dept_id_list)))

    @classmethod
    async def update_dept_children(cls, query_db: AsyncSession, dept_id: int, new_ancestors: str, old_ancestors: str):
        """
        更新子部门信息

        :param query_db: orm对象
        :param dept_id: 部门id
        :param new_ancestors: 新的祖先
        :param old_ancestors: 旧的祖先
        :return:
        """
        children = await DeptDao.get_children_dept_dao(query_db, dept_id)
        update_children = []
        for child in children:
            child_ancestors = await cls.replace_first(child.ancestors, old_ancestors, new_ancestors)
            update_children.append({'dept_id': child.dept_id, 'ancestors': child_ancestors})
        if children:
            await DeptDao.update_dept_children_dao(query_db, update_children)
