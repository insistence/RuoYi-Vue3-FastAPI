from module_admin.entity.vo.user_vo import UserInfoModel, UserRolePageQueryModel
from module_admin.entity.vo.common_vo import CrudResponseModel
from module_admin.dao.user_dao import UserDao
from module_admin.dao.role_dao import *
from utils.page_util import PageResponseModel
from utils.common_util import export_list2excel, CamelCaseUtil


class RoleService:
    """
    角色管理模块服务层
    """

    @classmethod
    def get_role_select_option_services(cls, query_db: Session):
        """
        获取角色列表不分页信息service
        :param query_db: orm对象
        :return: 角色列表不分页信息对象
        """
        role_list_result = RoleDao.get_role_select_option_dao(query_db)

        return CamelCaseUtil.transform_result(role_list_result)

    @classmethod
    def get_role_dept_tree_services(cls, query_db: Session, role_id: int):
        """
        根据角色id获取部门树信息service
        :param query_db: orm对象
        :param role_id: 角色id
        :return: 当前角色id的部门树信息对象
        """
        role_dept_list = RoleDao.get_role_dept_dao(query_db, role_id)
        checked_keys = [row.dept_id for row in role_dept_list]
        result = RoleDeptQueryModel(
            checkedKeys=checked_keys
        )

        return result

    @classmethod
    def get_role_list_services(cls, query_db: Session, query_object: RolePageQueryModel, is_page: bool = False):
        """
        获取角色列表信息service
        :param query_db: orm对象
        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 角色列表信息对象
        """
        role_list_result = RoleDao.get_role_list(query_db, query_object, is_page)

        return role_list_result

    @classmethod
    def add_role_services(cls, query_db: Session, page_object: AddRoleModel):
        """
        新增角色信息service
        :param query_db: orm对象
        :param page_object: 新增角色对象
        :return: 新增角色校验结果
        """
        add_role = RoleModel(**page_object.model_dump(by_alias=True))
        role_name = RoleDao.get_role_by_info(query_db, RoleModel(roleName=page_object.role_name))
        role_key = RoleDao.get_role_by_info(query_db, RoleModel(roleKey=page_object.role_key))
        if role_name:
            result = dict(is_success=False, message='角色名称已存在')
        elif role_key:
            result = dict(is_success=False, message='权限字符已存在')
        else:
            try:
                add_result = RoleDao.add_role_dao(query_db, add_role)
                role_id = add_result.role_id
                if page_object.menu_ids:
                    for menu in page_object.menu_ids:
                        RoleDao.add_role_menu_dao(query_db, RoleMenuModel(roleId=role_id, menuId=menu))
                query_db.commit()
                result = dict(is_success=True, message='新增成功')
            except Exception as e:
                query_db.rollback()
                raise e

        return CrudResponseModel(**result)

    @classmethod
    def edit_role_services(cls, query_db: Session, page_object: AddRoleModel):
        """
        编辑角色信息service
        :param query_db: orm对象
        :param page_object: 编辑角色对象
        :return: 编辑角色校验结果
        """
        edit_role = page_object.model_dump(exclude_unset=True, exclude={'admin'})
        if page_object.type != 'status':
            del edit_role['menu_ids']
        if page_object.type == 'status':
            del edit_role['type']
        role_info = cls.role_detail_services(query_db, edit_role.get('role_id'))
        if role_info:
            if page_object.type != 'status' and role_info.role_name != page_object.role_name:
                role_name = RoleDao.get_role_by_info(query_db, RoleModel(roleName=page_object.role_name))
                if role_name:
                    result = dict(is_success=False, message='角色名称已存在')
                    return CrudResponseModel(**result)
            elif page_object.type != 'status' and role_info.role_key != page_object.role_key:
                role_key = RoleDao.get_role_by_info(query_db, RoleModel(roleKey=page_object.role_key))
                if role_key:
                    result = dict(is_success=False, message='权限字符已存在')
                    return CrudResponseModel(**result)
            try:
                RoleDao.edit_role_dao(query_db, edit_role)
                if page_object.type != 'status':
                    RoleDao.delete_role_menu_dao(query_db, RoleMenuModel(roleId=page_object.role_id))
                    if page_object.menu_ids:
                        for menu in page_object.menu_ids:
                            RoleDao.add_role_menu_dao(query_db, RoleMenuModel(roleId=page_object.role_id, menuId=menu))
                query_db.commit()
                result = dict(is_success=True, message='更新成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='角色不存在')

        return CrudResponseModel(**result)

    @classmethod
    def role_datascope_services(cls, query_db: Session, page_object: AddRoleModel):
        """
        分配角色数据权限service
        :param query_db: orm对象
        :param page_object: 角色数据权限对象
        :return: 分配角色数据权限结果
        """
        edit_role = page_object.model_dump(exclude_unset=True, exclude={'admin'})
        del edit_role['dept_ids']
        role_info = cls.role_detail_services(query_db, edit_role.get('role_id'))
        if role_info:
            if role_info.role_name != page_object.role_name:
                role_name = RoleDao.get_role_by_info(query_db, RoleModel(roleName=page_object.role_name))
                if role_name:
                    result = dict(is_success=False, message='角色名称已存在')
                    return CrudResponseModel(**result)
            elif role_info.role_key != page_object.role_key:
                role_key = RoleDao.get_role_by_info(query_db, RoleModel(roleKey=page_object.role_key))
                if role_key:
                    result = dict(is_success=False, message='权限字符已存在')
                    return CrudResponseModel(**result)
            try:
                RoleDao.edit_role_dao(query_db, edit_role)
                RoleDao.delete_role_dept_dao(query_db, RoleDeptModel(roleId=page_object.role_id))
                if page_object.dept_ids and page_object.data_scope == '2':
                    for dept in page_object.dept_ids:
                        RoleDao.add_role_dept_dao(query_db, RoleDeptModel(roleId=page_object.role_id, deptId=dept))
                query_db.commit()
                result = dict(is_success=True, message='分配成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='角色不存在')

        return CrudResponseModel(**result)

    @classmethod
    def delete_role_services(cls, query_db: Session, page_object: DeleteRoleModel):
        """
        删除角色信息service
        :param query_db: orm对象
        :param page_object: 删除角色对象
        :return: 删除角色校验结果
        """
        if page_object.role_ids.split(','):
            role_id_list = page_object.role_ids.split(',')
            try:
                for role_id in role_id_list:
                    role_id_dict = dict(roleId=role_id, updateBy=page_object.update_by, updateTime=page_object.update_time)
                    RoleDao.delete_role_menu_dao(query_db, RoleMenuModel(**role_id_dict))
                    RoleDao.delete_role_dao(query_db, RoleModel(**role_id_dict))
                query_db.commit()
                result = dict(is_success=True, message='删除成功')
            except Exception as e:
                query_db.rollback()
                raise e
        else:
            result = dict(is_success=False, message='传入角色id为空')
        return CrudResponseModel(**result)

    @classmethod
    def role_detail_services(cls, query_db: Session, role_id: int):
        """
        获取角色详细信息service
        :param query_db: orm对象
        :param role_id: 角色id
        :return: 角色id对应的信息
        """
        role = RoleDao.get_role_detail_by_id(query_db, role_id=role_id)
        result = RoleModel(**CamelCaseUtil.transform_result(role))

        return result

    @staticmethod
    def export_role_list_services(role_list: List):
        """
        导出角色列表信息service
        :param role_list: 角色信息列表
        :return: 角色列表信息对象
        """
        # 创建一个映射字典，将英文键映射到中文键
        mapping_dict = {
            "roleId": "角色编号",
            "roleName": "角色名称",
            "roleKey": "权限字符",
            "roleSort": "显示顺序",
            "status": "状态",
            "createBy": "创建者",
            "createTime": "创建时间",
            "updateBy": "更新者",
            "updateTime": "更新时间",
            "remark": "备注",
        }

        data = role_list

        for item in data:
            if item.get('status') == '0':
                item['status'] = '正常'
            else:
                item['status'] = '停用'
        new_data = [{mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in data]
        binary_data = export_list2excel(new_data)

        return binary_data

    @classmethod
    def get_role_user_allocated_list_services(cls, query_db: Session, page_object: UserRolePageQueryModel, is_page: bool = False):
        """
        根据角色id获取已分配用户列表
        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :param is_page: 是否开启分页
        :return: 已分配用户列表
        """
        query_user_list = UserDao.get_user_role_allocated_list_by_role_id(query_db, page_object, is_page)
        allocated_list = PageResponseModel(
            **{
                **query_user_list.model_dump(by_alias=True),
                'rows': [UserInfoModel(**row) for row in query_user_list.rows]
            }
        )

        return allocated_list

    @classmethod
    def get_role_user_unallocated_list_services(cls, query_db: Session, page_object: UserRolePageQueryModel, is_page: bool = False):
        """
        根据角色id获取未分配用户列表
        :param query_db: orm对象
        :param page_object: 用户关联角色对象
        :param is_page: 是否开启分页
        :return: 未分配用户列表
        """
        query_user_list = UserDao.get_user_role_unallocated_list_by_role_id(query_db, page_object, is_page)
        unallocated_list = PageResponseModel(
            **{
                **query_user_list.model_dump(by_alias=True),
                'rows': [UserInfoModel(**row) for row in query_user_list.rows]
            }
        )

        return unallocated_list
