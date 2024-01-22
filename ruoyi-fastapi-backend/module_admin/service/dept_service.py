from module_admin.dao.dept_dao import *
from module_admin.entity.vo.common_vo import CrudResponseModel
from utils.common_util import CamelCaseUtil


class DeptService:
    """
    部门管理模块服务层
    """

    @classmethod
    def get_dept_tree_services(cls, query_db: Session, page_object: DeptModel, data_scope_sql: str):
        """
        获取部门树信息service
        :param query_db: orm对象
        :param page_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门树信息对象
        """
        dept_list_result = DeptDao.get_dept_list_for_tree(query_db, page_object, data_scope_sql)
        dept_tree_result = cls.list_to_tree(dept_list_result)

        return dept_tree_result

    @classmethod
    def get_dept_for_edit_option_services(cls, query_db: Session, page_object: DeptModel, data_scope_sql: str):
        """
        获取部门编辑部门树信息service
        :param query_db: orm对象
        :param page_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门树信息对象
        """
        dept_list_result = DeptDao.get_dept_info_for_edit_option(query_db, page_object, data_scope_sql)

        return CamelCaseUtil.transform_result(dept_list_result)

    @classmethod
    def get_dept_list_services(cls, query_db: Session, page_object: DeptModel, data_scope_sql: str):
        """
        获取部门列表信息service
        :param query_db: orm对象
        :param page_object: 分页查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 部门列表信息对象
        """
        dept_list_result = DeptDao.get_dept_list(query_db, page_object, data_scope_sql)

        return CamelCaseUtil.transform_result(dept_list_result)

    @classmethod
    def add_dept_services(cls, query_db: Session, page_object: DeptModel):
        """
        新增部门信息service
        :param query_db: orm对象
        :param page_object: 新增部门对象
        :return: 新增部门校验结果
        """
        parent_info = DeptDao.get_dept_by_id(query_db, page_object.parent_id)
        if parent_info:
            page_object.ancestors = f'{parent_info.ancestors},{page_object.parent_id}'
        else:
            page_object.ancestors = '0'
        dept = DeptDao.get_dept_detail_by_info(query_db, DeptModel(parentId=page_object.parent_id,
                                                                   deptName=page_object.dept_name))
        if dept:
            result = dict(is_success=False, message='同一部门下不允许存在同名的部门')
        else:
            try:
                DeptDao.add_dept_dao(query_db, page_object)
                query_db.commit()
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    def edit_dept_services(cls, query_db: Session, page_object: DeptModel):
        """
        编辑部门信息service
        :param query_db: orm对象
        :param page_object: 编辑部门对象
        :return: 编辑部门校验结果
        """
        parent_info = DeptDao.get_dept_by_id(query_db, page_object.parent_id)
        if parent_info:
            page_object.ancestors = f'{parent_info.ancestors},{page_object.parent_id}'
        else:
            page_object.ancestors = '0'
        edit_dept = page_object.model_dump(exclude_unset=True)
        dept_info = cls.dept_detail_services(query_db, edit_dept.get('dept_id'))
        if dept_info:
            if dept_info.parent_id != page_object.parent_id or dept_info.dept_name != page_object.dept_name:
                dept = DeptDao.get_dept_detail_by_info(query_db, DeptModel(parentId=page_object.parent_id,
                                                                           deptName=page_object.dept_name))
                if dept:
                    result = dict(is_success=False, message='同一部门下不允许存在同名的部门')
                    return CrudResponseModel(**result)
            try:
                DeptDao.edit_dept_dao(query_db, edit_dept)
                cls.update_children_info(query_db, DeptModel(deptId=page_object.dept_id,
                                                             ancestors=page_object.ancestors,
                                                             updateBy=page_object.update_by,
                                                             updateTime=page_object.update_time
                                                             )
                                         )
                query_db.commit()
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='部门不存在')

        return CrudResponseModel(**result)

    @classmethod
    def delete_dept_services(cls, query_db: Session, page_object: DeleteDeptModel):
        """
        删除部门信息service
        :param query_db: orm对象
        :param page_object: 删除部门对象
        :return: 删除部门校验结果
        """
        if page_object.dept_ids.split(','):
            dept_id_list = page_object.dept_ids.split(',')
            ancestors = DeptDao.get_dept_all_ancestors(query_db)
            try:
                for dept_id in dept_id_list:
                    for ancestor in ancestors:
                        if dept_id in ancestor[0]:
                            result = dict(is_success=False, message='该部门下有子部门，不允许删除')

                            return CrudResponseModel(**result)

                    DeptDao.delete_dept_dao(query_db, DeptModel(deptId=dept_id))
                query_db.commit()
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入部门id为空')
        return CrudResponseModel(**result)

    @classmethod
    def dept_detail_services(cls, query_db: Session, dept_id: int):
        """
        获取部门详细信息service
        :param query_db: orm对象
        :param dept_id: 部门id
        :return: 部门id对应的信息
        """
        dept = DeptDao.get_dept_detail_by_id(query_db, dept_id=dept_id)
        result = DeptModel(**CamelCaseUtil.transform_result(dept))

        return result

    @classmethod
    def list_to_tree(cls, permission_list: list) -> list:
        """
        工具方法：根据部门列表信息生成树形嵌套数据
        :param permission_list: 部门列表信息
        :return: 部门树形嵌套数据
        """
        permission_list = [dict(id=item.dept_id, label=item.dept_name, parentId=item.parent_id) for item in
                           permission_list]
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
    def update_children_info(cls, query_db, page_object):
        """
        工具方法：递归更新子部门信息
        :param query_db: orm对象
        :param page_object: 编辑部门对象
        :return:
        """
        children_info = DeptDao.get_children_dept(query_db, page_object.dept_id)
        if children_info:
            for child in children_info:
                child.ancestors = f'{page_object.ancestors},{page_object.dept_id}'
                DeptDao.edit_dept_dao(query_db,
                                      dict(dept_id=child.dept_id,
                                           ancestors=child.ancestors,
                                           update_by=page_object.update_by,
                                           update_time=page_object.update_time
                                           )
                                      )
                cls.update_children_info(query_db, DeptModel(dept_id=child.dept_id,
                                                             ancestors=child.ancestors,
                                                             update_by=page_object.update_by,
                                                             update_time=page_object.update_time
                                                             ))
